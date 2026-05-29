"""Evaluation and benchmarking for trained proof search models."""

from __future__ import annotations

from bimodal_harness.evaluation.baseline import (
    BaselineRunner,
    MockBaseline,
    NaiveBFSBaseline,
    SuccessPatternsBaseline,
)
from bimodal_harness.evaluation.benchmark import (
    BenchmarkReport,
    BenchmarkSuite,
)
from bimodal_harness.evaluation.generator import (
    BenchmarkGenerator,
    compute_checksum,
    compute_stats,
    load_jsonl,
    save_jsonl,
    write_checksums,
)
from bimodal_harness.evaluation.metrics import (
    BenchmarkMetrics,
    DescriptiveStats,
    SearchResult,
    compute_metrics,
    format_results_table,
    metrics_to_dict,
)
from bimodal_harness.evaluation.models import (
    BenchmarkConfig,
    BenchmarkProblem,
)

__all__ = [
    # Baseline runners
    "BaselineRunner",
    "MockBaseline",
    "NaiveBFSBaseline",
    "SuccessPatternsBaseline",
    # Benchmark suite
    "BenchmarkReport",
    "BenchmarkSuite",
    # Generator
    "BenchmarkGenerator",
    "compute_checksum",
    "compute_stats",
    "load_jsonl",
    "save_jsonl",
    "write_checksums",
    # Metrics
    "BenchmarkMetrics",
    "DescriptiveStats",
    "SearchResult",
    "compute_metrics",
    "format_results_table",
    "metrics_to_dict",
    # Models
    "BenchmarkConfig",
    "BenchmarkProblem",
]
