"""Benchmark evaluation suite for bimodal logic proof search."""

from __future__ import annotations

import json
import platform
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bimodal_harness.evaluation.baseline import BaselineRunner, MockBaseline
from bimodal_harness.evaluation.generator import (
    BenchmarkGenerator,
    compute_stats,
    load_jsonl,
    save_jsonl,
    write_checksums,
)
from bimodal_harness.evaluation.metrics import (
    BenchmarkMetrics,
    compute_metrics,
    format_results_table,
    metrics_to_dict,
)
from bimodal_harness.evaluation.models import BenchmarkConfig, BenchmarkProblem


@dataclass
class BenchmarkReport:
    """Report from running a benchmark evaluation.

    Holds per-system metrics, benchmark statistics, and run metadata.
    """

    per_system_metrics: dict[str, BenchmarkMetrics]
    """Metrics keyed by system name (e.g. 'mock', 'success_patterns')."""

    benchmark_stats: dict[str, Any]
    """Aggregate statistics about the benchmark problems (from compute_stats)."""

    run_metadata: dict[str, Any]
    """Metadata about the evaluation run (timestamp, machine, budgets)."""

    budget_ks: list[int]
    """Node budgets used for SR@K computation."""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        return {
            "per_system_metrics": {
                name: metrics_to_dict(m) for name, m in self.per_system_metrics.items()
            },
            "benchmark_stats": self.benchmark_stats,
            "run_metadata": self.run_metadata,
            "budget_ks": self.budget_ks,
        }

    def format_comparison_table(self) -> str:
        """Format all systems into a combined comparison table."""
        sections: list[str] = []
        for system_name, metrics in self.per_system_metrics.items():
            table = format_results_table(metrics, system_name)
            sections.append(table)
        return "\n\n".join(sections)


class BenchmarkSuite:
    """End-to-end benchmark evaluation orchestrator.

    Ties together benchmark loading/generation, baseline evaluation,
    metrics computation, and report generation.

    Usage
    -----
    Quick evaluation with an existing benchmark::

        suite = BenchmarkSuite(benchmark_path="benchmark.jsonl", systems=[MockBaseline()])
        report = suite.run()
        suite.save_report(report, output_dir=Path("results/"))

    Generate-and-evaluate in one shot::

        BenchmarkSuite.generate_and_save(config=BenchmarkConfig(), output_dir=Path("artifacts/"))
    """

    def __init__(
        self,
        benchmark_path: str | Path,
        systems: list[BaselineRunner],
        budget_ks: list[int] | None = None,
    ) -> None:
        """Initialize the BenchmarkSuite.

        Parameters
        ----------
        benchmark_path:
            Path to the benchmark JSONL file to evaluate on.
        systems:
            List of BaselineRunner instances to evaluate.
        budget_ks:
            Node budgets for SR@K computation.
            Defaults to [1000, 5000, 10000].
        """
        self._benchmark_path = Path(benchmark_path)
        self._systems = systems
        self._budget_ks = budget_ks if budget_ks is not None else [1000, 5000, 10000]
        self._problems: list[BenchmarkProblem] | None = None

    @property
    def problems(self) -> list[BenchmarkProblem]:
        """Load and cache the benchmark problems."""
        if self._problems is None:
            self._problems = load_jsonl(self._benchmark_path)
        return self._problems

    def run(self) -> BenchmarkReport:
        """Run all evaluation systems on all benchmark problems.

        Returns
        -------
        BenchmarkReport
            Report with per-system metrics and benchmark statistics.
        """
        problems = self.problems
        per_system_metrics: dict[str, BenchmarkMetrics] = {}

        for system in self._systems:
            print(f"Running {system.name} on {len(problems)} problems...")
            results = system.solve_batch(problems)
            metrics = compute_metrics(results, budget_ks=self._budget_ks)
            per_system_metrics[system.name] = metrics

        benchmark_stats = compute_stats(problems)
        run_metadata = _build_run_metadata(
            benchmark_path=str(self._benchmark_path),
            system_names=[s.name for s in self._systems],
            budget_ks=self._budget_ks,
        )

        return BenchmarkReport(
            per_system_metrics=per_system_metrics,
            benchmark_stats=benchmark_stats,
            run_metadata=run_metadata,
            budget_ks=self._budget_ks,
        )

    def save_report(self, report: BenchmarkReport, output_dir: str | Path) -> Path:
        """Save a BenchmarkReport to disk.

        Creates the output directory if it doesn't exist. Writes:
        - ``report.json``: Full report in JSON format
        - ``comparison_table.txt``: Human-readable comparison table

        Parameters
        ----------
        report:
            The BenchmarkReport to save.
        output_dir:
            Directory where report files will be written.

        Returns
        -------
        Path
            Path to the written report.json file.
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Write JSON report
        report_path = output_dir / "report.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)

        # Write comparison table
        table_path = output_dir / "comparison_table.txt"
        table_path.write_text(report.format_comparison_table(), encoding="utf-8")

        return report_path

    @classmethod
    def generate_and_save(
        cls,
        output_dir: str | Path,
        config: BenchmarkConfig | None = None,
        systems: list[BaselineRunner] | None = None,
        budget_ks: list[int] | None = None,
    ) -> BenchmarkReport:
        """Generate a benchmark and evaluate it in one shot.

        Creates the full publication artifact directory:
        - ``benchmark.jsonl``: Generated benchmark problems
        - ``benchmark_stats.json``: Aggregate statistics
        - ``checksums.sha256``: SHA-256 checksums
        - ``report.json``: Evaluation report (if systems provided)
        - ``comparison_table.txt``: Human-readable table (if systems provided)

        Parameters
        ----------
        output_dir:
            Directory where the benchmark artifact will be written.
        config:
            BenchmarkConfig for generation. Defaults to BenchmarkConfig().
        systems:
            List of BaselineRunner instances to evaluate.
            Defaults to [MockBaseline()].
        budget_ks:
            Node budgets for SR@K computation.
            Defaults to [1000, 5000, 10000].

        Returns
        -------
        BenchmarkReport
            Evaluation report from running all systems.
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        if config is None:
            config = BenchmarkConfig()
        if systems is None:
            systems = [MockBaseline()]
        if budget_ks is None:
            budget_ks = [1000, 5000, 10000]

        # Generate benchmark
        print(f"Generating benchmark ({config.target_size} problems)...")
        gen = BenchmarkGenerator()
        problems = gen.generate(config)

        # Save JSONL
        benchmark_path = output_dir / "benchmark.jsonl"
        save_jsonl(problems, benchmark_path)
        print(f"Saved {len(problems)} problems to {benchmark_path}")

        # Save stats
        stats = compute_stats(problems)
        stats_path = output_dir / "benchmark_stats.json"
        with open(stats_path, "w", encoding="utf-8") as f:
            json.dump(stats, f, indent=2, ensure_ascii=False)

        # Write checksums
        checksums_path = output_dir / "checksums.sha256"
        write_checksums([benchmark_path, stats_path], checksums_path)

        # Run evaluation
        suite = cls(benchmark_path=benchmark_path, systems=systems, budget_ks=budget_ks)
        report = suite.run()
        suite.save_report(report, output_dir)

        return report


def _build_run_metadata(
    benchmark_path: str,
    system_names: list[str],
    budget_ks: list[int],
) -> dict[str, Any]:
    """Build run metadata for a BenchmarkReport.

    Parameters
    ----------
    benchmark_path:
        Path to the benchmark JSONL file.
    system_names:
        Names of the systems evaluated.
    budget_ks:
        Node budgets used for SR@K computation.

    Returns
    -------
    dict[str, Any]
        Metadata dict with timestamp, machine info, and evaluation config.
    """
    return {
        "timestamp": datetime.now(tz=UTC).isoformat(),
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "machine": platform.machine(),
        "benchmark_path": benchmark_path,
        "systems_evaluated": system_names,
        "budget_ks": budget_ks,
    }
