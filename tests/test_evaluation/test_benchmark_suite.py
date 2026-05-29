"""Tests for BenchmarkSuite, BenchmarkReport, and the evaluate CLI."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from bimodal_harness.evaluation.baseline import MockBaseline
from bimodal_harness.evaluation.benchmark import BenchmarkReport, BenchmarkSuite
from bimodal_harness.evaluation.generator import load_jsonl, save_jsonl
from bimodal_harness.evaluation.models import BenchmarkConfig, BenchmarkProblem
from bimodal_harness.schema.records import PatternKey


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_small_benchmark(n: int = 10) -> list[BenchmarkProblem]:
    """Create a small benchmark for testing."""
    config = BenchmarkConfig(
        target_size=n,
        seed=42,
        tier_distribution={"easy": 0.5, "medium": 0.5, "hard": 0.0, "very_hard": 0.0},
        frame_class_distribution={"Base": 0.5, "Dense": 0.25, "Discrete": 0.25},
    )
    from bimodal_harness.evaluation.generator import BenchmarkGenerator
    gen = BenchmarkGenerator()
    return gen.generate(config)


def _write_benchmark(tmpdir: Path, problems: list[BenchmarkProblem]) -> Path:
    """Write problems to JSONL and return the path."""
    path = tmpdir / "benchmark.jsonl"
    save_jsonl(problems, path)
    return path


# ---------------------------------------------------------------------------
# BenchmarkReport tests
# ---------------------------------------------------------------------------


def test_benchmark_report_to_dict_keys() -> None:
    """Test that BenchmarkReport.to_dict has expected top-level keys."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        problems = _make_small_benchmark(5)
        bench_path = _write_benchmark(tmpdir, problems)

        suite = BenchmarkSuite(
            benchmark_path=bench_path,
            systems=[MockBaseline(budget=1000, seed=42)],
            budget_ks=[1000],
        )
        report = suite.run()
        d = report.to_dict()

    assert "per_system_metrics" in d
    assert "benchmark_stats" in d
    assert "run_metadata" in d
    assert "budget_ks" in d
    assert "mock" in d["per_system_metrics"]


def test_benchmark_report_to_dict_is_json_serializable() -> None:
    """Test that BenchmarkReport.to_dict produces JSON-serializable output."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        problems = _make_small_benchmark(5)
        bench_path = _write_benchmark(tmpdir, problems)

        suite = BenchmarkSuite(
            benchmark_path=bench_path,
            systems=[MockBaseline(budget=1000, seed=42)],
            budget_ks=[1000],
        )
        report = suite.run()
        # Should not raise
        serialized = json.dumps(report.to_dict())
        # Should deserialize back
        d = json.loads(serialized)
        assert d["budget_ks"] == [1000]


def test_benchmark_report_format_comparison_table() -> None:
    """Test that BenchmarkReport.format_comparison_table returns a non-empty string."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        problems = _make_small_benchmark(5)
        bench_path = _write_benchmark(tmpdir, problems)

        suite = BenchmarkSuite(
            benchmark_path=bench_path,
            systems=[MockBaseline(budget=1000, seed=42)],
            budget_ks=[1000],
        )
        report = suite.run()
        table = report.format_comparison_table()

    assert isinstance(table, str)
    assert len(table) > 0
    assert "mock" in table


# ---------------------------------------------------------------------------
# BenchmarkSuite.run() tests
# ---------------------------------------------------------------------------


def test_benchmark_suite_run_with_mock() -> None:
    """Test BenchmarkSuite.run() with MockBaseline produces valid report."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        problems = _make_small_benchmark(10)
        bench_path = _write_benchmark(tmpdir, problems)

        suite = BenchmarkSuite(
            benchmark_path=bench_path,
            systems=[MockBaseline(budget=1000, seed=42)],
            budget_ks=[1000, 5000],
        )
        report = suite.run()

    assert "mock" in report.per_system_metrics
    metrics = report.per_system_metrics["mock"]
    assert 1000 in metrics.success_rate_at_k
    assert 5000 in metrics.success_rate_at_k
    assert 0.0 <= metrics.success_rate_at_k[1000] <= 1.0
    assert metrics.total_problems == 10


def test_benchmark_suite_run_multiple_systems() -> None:
    """Test BenchmarkSuite.run() with multiple systems having distinct names."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        problems = _make_small_benchmark(8)
        bench_path = _write_benchmark(tmpdir, problems)

        # Create two systems with different names by subclassing
        class MockBaselineA(MockBaseline):
            @property
            def name(self) -> str:
                return "mock_a"

        class MockBaselineB(MockBaseline):
            @property
            def name(self) -> str:
                return "mock_b"

        systems = [
            MockBaselineA(budget=1000, seed=42),
            MockBaselineB(budget=2000, seed=99),
        ]

        suite = BenchmarkSuite(
            benchmark_path=bench_path,
            systems=systems,
            budget_ks=[1000],
        )
        report = suite.run()

    # Both systems produce results
    assert len(report.per_system_metrics) == 2
    for metrics in report.per_system_metrics.values():
        assert metrics.total_problems == 8


def test_benchmark_suite_loads_problems_lazily() -> None:
    """Test that BenchmarkSuite loads problems on first access."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        problems = _make_small_benchmark(5)
        bench_path = _write_benchmark(tmpdir, problems)

        suite = BenchmarkSuite(
            benchmark_path=bench_path,
            systems=[MockBaseline()],
        )
        # Problems not loaded yet
        assert suite._problems is None
        # Access triggers load
        loaded = suite.problems
        assert suite._problems is not None
        assert len(loaded) == len(problems)


def test_benchmark_suite_save_report() -> None:
    """Test that BenchmarkSuite.save_report creates expected files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        problems = _make_small_benchmark(5)
        bench_path = _write_benchmark(tmpdir, problems)

        suite = BenchmarkSuite(
            benchmark_path=bench_path,
            systems=[MockBaseline(budget=1000, seed=42)],
            budget_ks=[1000],
        )
        report = suite.run()
        output_dir = tmpdir / "results"
        suite.save_report(report, output_dir)

        assert (output_dir / "report.json").exists()
        assert (output_dir / "comparison_table.txt").exists()
        # Verify report.json is valid JSON
        with open(output_dir / "report.json", encoding="utf-8") as f:
            data = json.load(f)
        assert "per_system_metrics" in data


def test_benchmark_suite_save_report_creates_dir() -> None:
    """Test that save_report creates the output directory if it doesn't exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        problems = _make_small_benchmark(3)
        bench_path = _write_benchmark(tmpdir, problems)

        suite = BenchmarkSuite(
            benchmark_path=bench_path,
            systems=[MockBaseline()],
        )
        report = suite.run()
        output_dir = tmpdir / "deep" / "nested" / "output"
        suite.save_report(report, output_dir)

        assert output_dir.exists()
        assert (output_dir / "report.json").exists()


# ---------------------------------------------------------------------------
# BenchmarkSuite.generate_and_save() tests
# ---------------------------------------------------------------------------


def test_generate_and_save_creates_artifact_directory() -> None:
    """Test that generate_and_save creates the benchmark artifact directory structure."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir) / "artifacts"
        config = BenchmarkConfig(
            target_size=20,
            seed=42,
            tier_distribution={"easy": 0.5, "medium": 0.5, "hard": 0.0, "very_hard": 0.0},
            frame_class_distribution={"Base": 1.0, "Dense": 0.0, "Discrete": 0.0},
        )
        report = BenchmarkSuite.generate_and_save(
            output_dir=output_dir,
            config=config,
            systems=[MockBaseline(budget=500, seed=42)],
            budget_ks=[500],
        )

        assert output_dir.exists()
        assert (output_dir / "benchmark.jsonl").exists()
        assert (output_dir / "benchmark_stats.json").exists()
        assert (output_dir / "checksums.sha256").exists()
        assert (output_dir / "report.json").exists()


def test_generate_and_save_benchmark_stats_valid() -> None:
    """Test that benchmark_stats.json is valid JSON with expected structure."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir) / "artifacts"
        config = BenchmarkConfig(
            target_size=15,
            seed=42,
            tier_distribution={"easy": 0.5, "medium": 0.5, "hard": 0.0, "very_hard": 0.0},
            frame_class_distribution={"Base": 1.0, "Dense": 0.0, "Discrete": 0.0},
        )
        BenchmarkSuite.generate_and_save(
            output_dir=output_dir,
            config=config,
            systems=[MockBaseline(budget=500, seed=42)],
            budget_ks=[500],
        )
        with open(output_dir / "benchmark_stats.json", encoding="utf-8") as f:
            stats = json.load(f)

        assert "total" in stats
        assert "by_tier" in stats
        assert "by_frame_class" in stats
        assert stats["total"] > 0


def test_generate_and_save_checksums_format() -> None:
    """Test that checksums.sha256 has correct format."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir) / "artifacts"
        config = BenchmarkConfig(
            target_size=5,
            seed=42,
            tier_distribution={"easy": 1.0, "medium": 0.0, "hard": 0.0, "very_hard": 0.0},
            frame_class_distribution={"Base": 1.0, "Dense": 0.0, "Discrete": 0.0},
        )
        BenchmarkSuite.generate_and_save(
            output_dir=output_dir,
            config=config,
            systems=[MockBaseline(budget=500, seed=42)],
            budget_ks=[500],
        )
        checksums_content = (output_dir / "checksums.sha256").read_text(encoding="utf-8")

        lines = [line for line in checksums_content.strip().split("\n") if line]
        assert len(lines) >= 2  # At least benchmark.jsonl and benchmark_stats.json
        for line in lines:
            parts = line.split("  ")
            assert len(parts) == 2
            assert len(parts[0]) == 64  # SHA-256 hex length


def test_generate_and_save_jsonl_roundtrip() -> None:
    """Test that generated benchmark JSONL round-trips correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir) / "artifacts"
        config = BenchmarkConfig(
            target_size=10,
            seed=42,
            tier_distribution={"easy": 0.5, "medium": 0.5, "hard": 0.0, "very_hard": 0.0},
            frame_class_distribution={"Base": 1.0, "Dense": 0.0, "Discrete": 0.0},
        )
        BenchmarkSuite.generate_and_save(
            output_dir=output_dir,
            config=config,
            systems=[MockBaseline(budget=500, seed=42)],
            budget_ks=[500],
        )
        loaded = load_jsonl(output_dir / "benchmark.jsonl")

        assert len(loaded) > 0
        for p in loaded:
            assert p.benchmark_id.startswith("bench_")
            assert p.difficulty_tier in ("easy", "medium", "hard", "very_hard")
            assert p.frame_class in ("Base", "Dense", "Discrete")
            assert p.pattern_key is not None


# ---------------------------------------------------------------------------
# CLI argument parsing tests
# ---------------------------------------------------------------------------


def test_cli_parser_generate_flag() -> None:
    """Test that the CLI parser accepts --generate flag."""
    from scripts.evaluate import build_parser

    parser = build_parser()
    args = parser.parse_args(["--generate", "--output-dir", "/tmp/test"])
    assert args.generate is True
    assert args.output_dir == Path("/tmp/test")


def test_cli_parser_benchmark_path() -> None:
    """Test that the CLI parser accepts --benchmark-path."""
    from scripts.evaluate import build_parser

    parser = build_parser()
    args = parser.parse_args(["--benchmark-path", "/tmp/benchmark.jsonl"])
    assert args.benchmark_path == Path("/tmp/benchmark.jsonl")


def test_cli_parser_systems_default() -> None:
    """Test that the CLI parser defaults --systems to 'mock'."""
    from scripts.evaluate import build_parser

    parser = build_parser()
    args = parser.parse_args(["--generate"])
    assert args.systems == "mock"


def test_cli_parser_budgets_default() -> None:
    """Test that the CLI parser defaults --budgets to '1000,5000,10000'."""
    from scripts.evaluate import build_parser

    parser = build_parser()
    args = parser.parse_args(["--generate"])
    assert args.budgets == "1000,5000,10000"


def test_cli_parse_budgets() -> None:
    """Test parse_budgets function with valid input."""
    from scripts.evaluate import parse_budgets

    budgets = parse_budgets("500,2000,10000")
    assert budgets == [500, 2000, 10000]


def test_cli_parse_budgets_single() -> None:
    """Test parse_budgets function with a single budget."""
    from scripts.evaluate import parse_budgets

    budgets = parse_budgets("5000")
    assert budgets == [5000]


def test_cli_parse_systems_mock() -> None:
    """Test parse_systems returns MockBaseline for 'mock'."""
    from scripts.evaluate import parse_systems

    runners = parse_systems("mock", budget=1000)
    assert len(runners) == 1
    assert runners[0].name == "mock"


def test_cli_parse_systems_multiple() -> None:
    """Test parse_systems handles multiple comma-separated systems."""
    from scripts.evaluate import parse_systems

    runners = parse_systems("mock,mock", budget=1000)
    # Two mocks
    assert len(runners) == 2


# ---------------------------------------------------------------------------
# Integration test: full pipeline
# ---------------------------------------------------------------------------


def test_integration_full_pipeline() -> None:
    """Integration test: generate, evaluate, and save report end-to-end."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        config = BenchmarkConfig(
            target_size=50,
            seed=42,
            tier_distribution={"easy": 0.5, "medium": 0.5, "hard": 0.0, "very_hard": 0.0},
            frame_class_distribution={"Base": 0.5, "Dense": 0.25, "Discrete": 0.25},
        )
        report = BenchmarkSuite.generate_and_save(
            output_dir=tmpdir / "artifacts",
            config=config,
            systems=[MockBaseline(budget=1000, seed=42)],
            budget_ks=[1000, 5000],
        )

    # Verify report structure
    assert "mock" in report.per_system_metrics
    metrics = report.per_system_metrics["mock"]
    assert 1000 in metrics.success_rate_at_k
    assert 5000 in metrics.success_rate_at_k

    # Verify per-tier breakdown exists
    assert len(metrics.per_tier) > 0

    # Verify all tier counts match total
    tier_total = sum(m.total_problems for m in metrics.per_tier.values())
    assert tier_total == metrics.total_problems

    # Verify metrics are valid fractions
    for k, sr in metrics.success_rate_at_k.items():
        assert 0.0 <= sr <= 1.0, f"SR@{k} = {sr} is not in [0, 1]"
