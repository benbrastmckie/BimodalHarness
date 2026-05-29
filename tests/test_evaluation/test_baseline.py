"""Tests for baseline runners: MockBaseline, SuccessPatternsBaseline, NaiveBFSBaseline."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from bimodal_harness.evaluation.baseline import (
    MockBaseline,
    NaiveBFSBaseline,
    SuccessPatternsBaseline,
)
from bimodal_harness.evaluation.metrics import SearchResult
from bimodal_harness.evaluation.models import BenchmarkProblem
from bimodal_harness.schema.records import PatternKey


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_problem(
    benchmark_id: str = "bench_0001",
    difficulty_tier: str = "easy",
    frame_class: str = "Base",
) -> BenchmarkProblem:
    """Create a minimal BenchmarkProblem for testing."""
    formula_json = {"tag": "imp", "left": {"tag": "atom", "name": "p"}, "right": {"tag": "atom", "name": "q"}}
    pattern_key = PatternKey(
        modal_depth=0,
        temporal_depth=0,
        imp_count=1,
        complexity=3,
        top_operator="Implication",
    )
    return BenchmarkProblem(
        benchmark_id=benchmark_id,
        formula_json=formula_json,
        formula_pretty="(p → q)",
        ground_truth_label=None,
        ground_truth_proof_height=None,
        ground_truth_countermodel=None,
        difficulty_tier=difficulty_tier,
        frame_class=frame_class,
        pattern_key=pattern_key,
    )


# ---------------------------------------------------------------------------
# MockBaseline tests
# ---------------------------------------------------------------------------


def test_mock_baseline_name() -> None:
    """Test that MockBaseline has the expected name."""
    baseline = MockBaseline()
    assert baseline.name == "mock"


def test_mock_baseline_returns_search_result() -> None:
    """Test that MockBaseline.solve returns a SearchResult."""
    baseline = MockBaseline(budget=1000, seed=42)
    problem = _make_problem()
    result = baseline.solve(problem)
    assert isinstance(result, SearchResult)
    assert result.problem_id == "bench_0001"
    assert result.node_budget == 1000
    assert result.difficulty_tier == "easy"
    assert result.frame_class == "Base"


def test_mock_baseline_deterministic() -> None:
    """Test that MockBaseline produces identical results with same seed."""
    baseline1 = MockBaseline(budget=1000, seed=42)
    baseline2 = MockBaseline(budget=1000, seed=42)
    problem = _make_problem("bench_0001")
    result1 = baseline1.solve(problem)
    result2 = baseline2.solve(problem)
    assert result1.success == result2.success
    assert result1.nodes_visited == result2.nodes_visited
    assert result1.proof_height == result2.proof_height


def test_mock_baseline_different_seeds_may_differ() -> None:
    """Test that different seeds can produce different results."""
    # With enough problems, different seeds should produce at least one difference
    problems = [_make_problem(f"bench_{i:04d}") for i in range(20)]
    baseline_a = MockBaseline(budget=1000, seed=1)
    baseline_b = MockBaseline(budget=1000, seed=999)
    results_a = baseline_a.solve_batch(problems)
    results_b = baseline_b.solve_batch(problems)
    # At least one result should differ (with very high probability for 20 problems)
    any_diff = any(
        ra.success != rb.success or ra.nodes_visited != rb.nodes_visited
        for ra, rb in zip(results_a, results_b)
    )
    assert any_diff, "Expected different seeds to produce at least one different result"


def test_mock_baseline_success_within_budget() -> None:
    """Test that successful results have nodes_visited < budget."""
    baseline = MockBaseline(budget=5000, seed=42)
    problems = [_make_problem(f"bench_{i:04d}", difficulty_tier="easy") for i in range(50)]
    results = baseline.solve_batch(problems)
    for r in results:
        if r.success:
            assert r.nodes_visited < r.node_budget, (
                f"Successful result should have nodes_visited < budget, "
                f"got {r.nodes_visited} >= {r.node_budget}"
            )


def test_mock_baseline_failure_equals_budget() -> None:
    """Test that failed results have nodes_visited = budget (capped)."""
    baseline = MockBaseline(budget=1000, seed=42)
    problems = [_make_problem(f"bench_{i:04d}", difficulty_tier="very_hard") for i in range(30)]
    results = baseline.solve_batch(problems)
    for r in results:
        if not r.success:
            assert r.nodes_visited == r.node_budget, (
                f"Failed result should have nodes_visited == budget, "
                f"got {r.nodes_visited} != {r.node_budget}"
            )


def test_mock_baseline_proof_height_on_success() -> None:
    """Test that successful results have a positive proof height."""
    baseline = MockBaseline(budget=1000, seed=42)
    problems = [_make_problem(f"bench_{i:04d}", difficulty_tier="easy") for i in range(50)]
    results = baseline.solve_batch(problems)
    for r in results:
        if r.success:
            assert r.proof_height is not None
            assert r.proof_height > 0


def test_mock_baseline_proof_height_none_on_failure() -> None:
    """Test that failed results have proof_height=None."""
    baseline = MockBaseline(budget=1000, seed=42)
    problems = [_make_problem(f"bench_{i:04d}", difficulty_tier="very_hard") for i in range(30)]
    results = baseline.solve_batch(problems)
    for r in results:
        if not r.success:
            assert r.proof_height is None


def test_mock_baseline_tier_affects_success_rate() -> None:
    """Test that harder tiers produce lower success rates."""
    n = 100
    easy_problems = [_make_problem(f"easy_{i:04d}", difficulty_tier="easy") for i in range(n)]
    hard_problems = [_make_problem(f"hard_{i:04d}", difficulty_tier="very_hard") for i in range(n)]

    baseline = MockBaseline(budget=10000, seed=42)
    easy_results = baseline.solve_batch(easy_problems)
    hard_results = baseline.solve_batch(hard_problems)

    easy_sr = sum(1 for r in easy_results if r.success) / n
    hard_sr = sum(1 for r in hard_results if r.success) / n
    assert easy_sr > hard_sr, f"Expected easy SR ({easy_sr}) > hard SR ({hard_sr})"


def test_mock_baseline_progress_callback() -> None:
    """Test that solve_batch invokes the progress callback."""
    baseline = MockBaseline(budget=1000, seed=42)
    problems = [_make_problem(f"bench_{i:04d}") for i in range(5)]
    callback_calls: list[tuple[int, int]] = []

    def callback(current: int, total: int, result: SearchResult) -> None:
        callback_calls.append((current, total))

    baseline.solve_batch(problems, progress_callback=callback)
    assert len(callback_calls) == 5
    assert callback_calls[0] == (1, 5)
    assert callback_calls[-1] == (5, 5)


# ---------------------------------------------------------------------------
# SuccessPatternsBaseline tests with mocked LeanBridge
# ---------------------------------------------------------------------------


def _make_mock_lean_bridge(success: bool = True, nodes: int = 300, height: int = 3) -> MagicMock:
    """Create a mocked LeanBridge that returns a fixed response."""
    import json

    bridge = MagicMock()
    if success:
        response_data = {"success": True, "nodesVisited": nodes, "proofHeight": height}
    else:
        response_data = {"success": False, "nodesVisited": nodes}

    mock_response = MagicMock()
    mock_response.ok = True
    mock_response.output = json.dumps(response_data)
    bridge.send_command.return_value = mock_response
    return bridge


def _make_mock_lean_bridge_error() -> MagicMock:
    """Create a mocked LeanBridge that returns an error response."""
    bridge = MagicMock()
    mock_response = MagicMock()
    mock_response.ok = False
    mock_response.output = ""
    bridge.send_command.return_value = mock_response
    return bridge


def test_success_patterns_baseline_name() -> None:
    """Test that SuccessPatternsBaseline has the expected name."""
    bridge = _make_mock_lean_bridge()
    baseline = SuccessPatternsBaseline(bridge, budget=5000)
    assert baseline.name == "success_patterns"


def test_success_patterns_baseline_success() -> None:
    """Test SuccessPatternsBaseline parses a successful mocked response."""
    bridge = _make_mock_lean_bridge(success=True, nodes=300, height=3)
    baseline = SuccessPatternsBaseline(bridge, budget=5000)
    problem = _make_problem()
    result = baseline.solve(problem)
    assert result.success is True
    assert result.nodes_visited == 300
    assert result.proof_height == 3
    assert result.problem_id == "bench_0001"


def test_success_patterns_baseline_failure() -> None:
    """Test SuccessPatternsBaseline parses a failed mocked response."""
    bridge = _make_mock_lean_bridge(success=False, nodes=5000)
    baseline = SuccessPatternsBaseline(bridge, budget=5000)
    problem = _make_problem()
    result = baseline.solve(problem)
    assert result.success is False
    assert result.proof_height is None


def test_success_patterns_baseline_repl_error() -> None:
    """Test SuccessPatternsBaseline handles REPL errors gracefully."""
    bridge = _make_mock_lean_bridge_error()
    baseline = SuccessPatternsBaseline(bridge, budget=1000)
    problem = _make_problem()
    result = baseline.solve(problem)
    assert result.success is False
    assert result.nodes_visited == 1000
    assert result.proof_height is None


def test_success_patterns_baseline_exception_handling() -> None:
    """Test SuccessPatternsBaseline handles exceptions without crashing."""
    bridge = MagicMock()
    bridge.send_command.side_effect = RuntimeError("REPL crashed")
    baseline = SuccessPatternsBaseline(bridge, budget=2000)
    problem = _make_problem()
    result = baseline.solve(problem)
    assert result.success is False
    assert result.nodes_visited == 2000


def test_success_patterns_baseline_batch() -> None:
    """Test SuccessPatternsBaseline.solve_batch aggregates results."""
    bridge = _make_mock_lean_bridge(success=True, nodes=200)
    baseline = SuccessPatternsBaseline(bridge, budget=5000)
    problems = [_make_problem(f"bench_{i:04d}") for i in range(3)]
    results = baseline.solve_batch(problems)
    assert len(results) == 3
    for r in results:
        assert r.success is True


# ---------------------------------------------------------------------------
# NaiveBFSBaseline tests with mocked LeanBridge
# ---------------------------------------------------------------------------


def test_naive_bfs_baseline_name() -> None:
    """Test that NaiveBFSBaseline has the expected name."""
    bridge = _make_mock_lean_bridge()
    baseline = NaiveBFSBaseline(bridge, budget=5000)
    assert baseline.name == "naive_bfs"


def test_naive_bfs_baseline_success() -> None:
    """Test NaiveBFSBaseline parses a successful mocked response."""
    bridge = _make_mock_lean_bridge(success=True, nodes=400, height=5)
    baseline = NaiveBFSBaseline(bridge, budget=5000)
    problem = _make_problem()
    result = baseline.solve(problem)
    assert result.success is True
    assert result.nodes_visited == 400
    assert result.proof_height == 5


def test_naive_bfs_baseline_failure() -> None:
    """Test NaiveBFSBaseline parses a failed mocked response."""
    bridge = _make_mock_lean_bridge(success=False, nodes=5000)
    baseline = NaiveBFSBaseline(bridge, budget=5000)
    problem = _make_problem()
    result = baseline.solve(problem)
    assert result.success is False
    assert result.proof_height is None


def test_naive_bfs_baseline_exception_handling() -> None:
    """Test NaiveBFSBaseline handles exceptions without crashing."""
    bridge = MagicMock()
    bridge.send_command.side_effect = ValueError("Unexpected error")
    baseline = NaiveBFSBaseline(bridge, budget=3000)
    problem = _make_problem()
    result = baseline.solve(problem)
    assert result.success is False
    assert result.nodes_visited == 3000
