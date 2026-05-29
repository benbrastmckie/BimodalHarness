"""Tests for the metrics computation engine."""

from __future__ import annotations

import pytest

from bimodal_harness.evaluation.metrics import (
    BenchmarkMetrics,
    DescriptiveStats,
    SearchResult,
    compute_metrics,
    format_results_table,
    metrics_to_dict,
)


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def _make_result(
    problem_id: str = "bench_0001",
    success: bool = True,
    nodes_visited: int = 500,
    time_seconds: float = 0.1,
    proof_height: int | None = 3,
    node_budget: int = 1000,
    difficulty_tier: str = "easy",
    frame_class: str = "Base",
) -> SearchResult:
    """Create a SearchResult with default values."""
    return SearchResult(
        problem_id=problem_id,
        success=success,
        nodes_visited=nodes_visited,
        time_seconds=time_seconds,
        proof_height=proof_height,
        node_budget=node_budget,
        difficulty_tier=difficulty_tier,
        frame_class=frame_class,
    )


def _make_failed_result(
    problem_id: str = "bench_fail",
    node_budget: int = 1000,
    difficulty_tier: str = "hard",
    frame_class: str = "Dense",
) -> SearchResult:
    """Create a failed SearchResult (nodes_visited = node_budget)."""
    return SearchResult(
        problem_id=problem_id,
        success=False,
        nodes_visited=node_budget,
        time_seconds=1.5,
        proof_height=None,
        node_budget=node_budget,
        difficulty_tier=difficulty_tier,
        frame_class=frame_class,
    )


# ---------------------------------------------------------------------------
# DescriptiveStats tests
# ---------------------------------------------------------------------------


def test_descriptive_stats_empty() -> None:
    """Test DescriptiveStats with empty input returns all zeros."""
    stats = DescriptiveStats.from_values([])
    assert stats.mean == 0.0
    assert stats.median == 0.0
    assert stats.p90 == 0.0
    assert stats.min == 0.0
    assert stats.max == 0.0
    assert stats.count == 0


def test_descriptive_stats_single_element() -> None:
    """Test DescriptiveStats with a single element."""
    stats = DescriptiveStats.from_values([42.0])
    assert stats.mean == 42.0
    assert stats.median == 42.0
    assert stats.p90 == 42.0
    assert stats.min == 42.0
    assert stats.max == 42.0
    assert stats.count == 1


def test_descriptive_stats_two_elements() -> None:
    """Test DescriptiveStats with two elements."""
    stats = DescriptiveStats.from_values([10.0, 20.0])
    assert stats.mean == 15.0
    assert stats.median == 15.0
    assert stats.min == 10.0
    assert stats.max == 20.0
    assert stats.count == 2


def test_descriptive_stats_known_values() -> None:
    """Test DescriptiveStats with a known dataset."""
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    stats = DescriptiveStats.from_values(values)
    assert stats.mean == 3.0
    assert stats.median == 3.0
    assert stats.min == 1.0
    assert stats.max == 5.0
    assert stats.count == 5


def test_descriptive_stats_all_same() -> None:
    """Test DescriptiveStats when all values are the same."""
    stats = DescriptiveStats.from_values([7.0, 7.0, 7.0])
    assert stats.mean == 7.0
    assert stats.median == 7.0
    assert stats.p90 == 7.0
    assert stats.min == 7.0
    assert stats.max == 7.0


def test_descriptive_stats_p90() -> None:
    """Test P90 computation with 10 elements."""
    values = [float(i) for i in range(1, 11)]  # 1..10
    stats = DescriptiveStats.from_values(values)
    # P90 of [1,2,...,10]: fractional index = 0.9 * (10-1) = 8.1
    # Linear interpolation between sorted_vals[8]=9.0 and sorted_vals[9]=10.0:
    # 9.0 * (1 - 0.1) + 10.0 * 0.1 = 8.1 + 1.0 = 9.1
    assert stats.p90 == pytest.approx(9.1, rel=1e-3)


def test_descriptive_stats_serialization() -> None:
    """Test DescriptiveStats.to_dict() output."""
    stats = DescriptiveStats.from_values([1.0, 2.0, 3.0])
    d = stats.to_dict()
    assert "mean" in d
    assert "median" in d
    assert "p90" in d
    assert "min" in d
    assert "max" in d
    assert "count" in d
    assert d["count"] == 3


# ---------------------------------------------------------------------------
# SR@K computation tests
# ---------------------------------------------------------------------------


def test_sr_at_k_all_succeed() -> None:
    """SR@K = 1.0 when all results succeed within budget."""
    results = [
        _make_result(f"bench_{i:04d}", success=True, nodes_visited=100)
        for i in range(10)
    ]
    metrics = compute_metrics(results, budget_ks=[1000])
    assert metrics.success_rate_at_k[1000] == pytest.approx(1.0)


def test_sr_at_k_none_succeed() -> None:
    """SR@K = 0.0 when no results succeed."""
    results = [
        _make_failed_result(f"bench_{i:04d}")
        for i in range(10)
    ]
    metrics = compute_metrics(results, budget_ks=[1000])
    assert metrics.success_rate_at_k[1000] == pytest.approx(0.0)


def test_sr_at_k_partial_success() -> None:
    """SR@K correctly counts partial success."""
    # 3 succeed within 500 nodes, 2 fail
    results = [
        _make_result("bench_0001", success=True, nodes_visited=200),
        _make_result("bench_0002", success=True, nodes_visited=400),
        _make_result("bench_0003", success=True, nodes_visited=500),
        _make_failed_result("bench_0004"),
        _make_failed_result("bench_0005"),
    ]
    metrics = compute_metrics(results, budget_ks=[500, 1000])
    assert metrics.success_rate_at_k[500] == pytest.approx(3 / 5)
    assert metrics.success_rate_at_k[1000] == pytest.approx(3 / 5)


def test_sr_at_k_success_exceeds_budget() -> None:
    """SR@K = 0.0 for a budget tighter than nodes_visited even on success."""
    # Success with 2000 nodes visited but we query SR@1000
    results = [
        _make_result("bench_0001", success=True, nodes_visited=2000),
    ]
    metrics = compute_metrics(results, budget_ks=[1000, 5000])
    assert metrics.success_rate_at_k[1000] == pytest.approx(0.0)
    assert metrics.success_rate_at_k[5000] == pytest.approx(1.0)


def test_sr_at_k_empty_results() -> None:
    """SR@K = 0.0 for empty results."""
    metrics = compute_metrics([], budget_ks=[1000])
    assert metrics.success_rate_at_k[1000] == pytest.approx(0.0)
    assert metrics.total_problems == 0


def test_sr_at_k_multiple_budgets() -> None:
    """SR@K computed correctly for multiple budget values."""
    results = [
        _make_result("bench_0001", success=True, nodes_visited=800),
        _make_result("bench_0002", success=True, nodes_visited=3000),
        _make_failed_result("bench_0003", node_budget=10000),
    ]
    metrics = compute_metrics(results, budget_ks=[1000, 5000, 10000])
    assert metrics.success_rate_at_k[1000] == pytest.approx(1 / 3)
    assert metrics.success_rate_at_k[5000] == pytest.approx(2 / 3)
    assert metrics.success_rate_at_k[10000] == pytest.approx(2 / 3)


# ---------------------------------------------------------------------------
# Per-tier and per-frame-class breakdown tests
# ---------------------------------------------------------------------------


def test_per_tier_breakdown() -> None:
    """Test that per_tier breakdown correctly partitions results."""
    results = [
        _make_result("bench_0001", success=True, difficulty_tier="easy"),
        _make_result("bench_0002", success=True, difficulty_tier="easy"),
        _make_result("bench_0003", success=False, difficulty_tier="hard", nodes_visited=1000),
        _make_result("bench_0004", success=True, difficulty_tier="hard"),
    ]
    metrics = compute_metrics(results, budget_ks=[1000])
    assert "easy" in metrics.per_tier
    assert "hard" in metrics.per_tier
    assert metrics.per_tier["easy"].total_problems == 2
    assert metrics.per_tier["hard"].total_problems == 2
    # SR@1000 for easy: 2/2 = 1.0
    assert metrics.per_tier["easy"].success_rate_at_k[1000] == pytest.approx(1.0)
    # SR@1000 for hard: 1/2 = 0.5
    assert metrics.per_tier["hard"].success_rate_at_k[1000] == pytest.approx(0.5)


def test_per_tier_total_matches_overall() -> None:
    """Test that per_tier total_problems sums to overall total_problems."""
    results = [
        _make_result(f"bench_{i:04d}", difficulty_tier="easy" if i < 5 else "hard")
        for i in range(10)
    ]
    metrics = compute_metrics(results, budget_ks=[1000])
    tier_total = sum(m.total_problems for m in metrics.per_tier.values())
    assert tier_total == metrics.total_problems


def test_per_frame_class_breakdown() -> None:
    """Test that per_frame_class breakdown correctly partitions results."""
    results = [
        _make_result("bench_0001", frame_class="Base"),
        _make_result("bench_0002", frame_class="Base"),
        _make_result("bench_0003", frame_class="Dense"),
    ]
    metrics = compute_metrics(results, budget_ks=[1000])
    assert "Base" in metrics.per_frame_class
    assert "Dense" in metrics.per_frame_class
    assert metrics.per_frame_class["Base"].total_problems == 2
    assert metrics.per_frame_class["Dense"].total_problems == 1


# ---------------------------------------------------------------------------
# Table formatting tests
# ---------------------------------------------------------------------------


def test_format_results_table_columns() -> None:
    """Test that format_results_table produces expected column headers."""
    results = [_make_result()]
    metrics = compute_metrics(results, budget_ks=[1000, 5000])
    table = format_results_table(metrics, "TestSystem")
    assert "TestSystem" in table
    assert "SR@1000" in table
    assert "SR@5000" in table
    assert "NV_mean" in table
    assert "TTP_mean" in table


def test_format_results_table_tier_section() -> None:
    """Test that table includes per-tier breakdown section."""
    results = [
        _make_result("bench_0001", difficulty_tier="easy"),
        _make_result("bench_0002", difficulty_tier="hard"),
    ]
    metrics = compute_metrics(results, budget_ks=[1000])
    table = format_results_table(metrics, "MySystem")
    assert "Per-Tier Breakdown" in table
    assert "easy" in table
    assert "hard" in table


def test_format_results_table_frame_class_section() -> None:
    """Test that table includes per-frame-class breakdown section."""
    results = [
        _make_result("bench_0001", frame_class="Base"),
        _make_result("bench_0002", frame_class="Discrete"),
    ]
    metrics = compute_metrics(results, budget_ks=[1000])
    table = format_results_table(metrics, "TestSystem")
    assert "Per-Frame-Class Breakdown" in table
    assert "Base" in table
    assert "Discrete" in table


# ---------------------------------------------------------------------------
# metrics_to_dict serialization tests
# ---------------------------------------------------------------------------


def test_metrics_to_dict_keys() -> None:
    """Test that metrics_to_dict produces expected top-level keys."""
    results = [_make_result()]
    metrics = compute_metrics(results, budget_ks=[1000])
    d = metrics_to_dict(metrics)
    assert "success_rate_at_k" in d
    assert "nodes_visited_stats" in d
    assert "time_to_proof_stats" in d
    assert "proof_height_stats" in d
    assert "total_problems" in d


def test_metrics_to_dict_sr_keys_are_strings() -> None:
    """Test that SR@K dict keys are strings (for JSON compatibility)."""
    results = [_make_result()]
    metrics = compute_metrics(results, budget_ks=[1000, 5000])
    d = metrics_to_dict(metrics)
    # JSON keys are always strings
    assert "1000" in d["success_rate_at_k"]
    assert "5000" in d["success_rate_at_k"]


def test_metrics_to_dict_nested() -> None:
    """Test that per_tier and per_frame_class are nested in the dict."""
    results = [
        _make_result("bench_0001", difficulty_tier="easy", frame_class="Base"),
        _make_result("bench_0002", difficulty_tier="hard", frame_class="Dense"),
    ]
    metrics = compute_metrics(results, budget_ks=[1000])
    d = metrics_to_dict(metrics)
    assert "per_tier" in d
    assert "per_frame_class" in d
    assert "easy" in d["per_tier"]
    assert "hard" in d["per_tier"]
    assert "Base" in d["per_frame_class"]
    assert "Dense" in d["per_frame_class"]
