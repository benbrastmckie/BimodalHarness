"""Metrics computation engine for bimodal logic benchmark evaluation.

Computes SR@K (Success Rate at K nodes), nodes-visited statistics,
time-to-proof statistics, and proof length statistics, with per-tier
and per-frame-class breakdowns.

Primary metric: SR@K at K=1000, 5000, 10000 nodes (matching miniF2F/LeanDojo conventions).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class SearchResult:
    """Result from running a proof search on a single benchmark problem.

    Represents the outcome of running one search system on one formula.
    """

    problem_id: str
    """Benchmark ID of the problem (matches BenchmarkProblem.benchmark_id)."""

    success: bool
    """True if the proof was found within the node budget."""

    nodes_visited: int
    """Number of search nodes expanded during the search attempt.

    For failed searches, this equals the node budget (capped).
    For successful searches, this is the actual count at termination.
    """

    time_seconds: float
    """Wall-clock time in seconds for the search attempt."""

    proof_height: int | None
    """Derivation tree height for successful proofs; None for failures."""

    node_budget: int
    """Node budget used for this search."""

    difficulty_tier: str
    """Difficulty tier of the problem (for breakdown computation)."""

    frame_class: str
    """Frame class of the problem (for breakdown computation)."""


@dataclass(slots=True)
class DescriptiveStats:
    """Descriptive statistics for a list of numeric values.

    Handles edge cases: empty lists return all zeros, single element
    returns that value for all stats.
    """

    mean: float
    """Arithmetic mean of the values."""

    median: float
    """Median (50th percentile) of the values."""

    p90: float
    """90th percentile of the values."""

    min: float
    """Minimum value."""

    max: float
    """Maximum value."""

    count: int
    """Number of values used to compute the statistics."""

    @classmethod
    def from_values(cls, values: list[float | int]) -> DescriptiveStats:
        """Compute DescriptiveStats from a list of numeric values.

        Parameters
        ----------
        values:
            List of numeric values. May be empty.

        Returns
        -------
        DescriptiveStats
            Statistics computed from the values. Returns all-zero stats
            for empty input.
        """
        if not values:
            return cls(mean=0.0, median=0.0, p90=0.0, min=0.0, max=0.0, count=0)

        sorted_vals = sorted(float(v) for v in values)
        n = len(sorted_vals)

        mean = sum(sorted_vals) / n
        min_val = sorted_vals[0]
        max_val = sorted_vals[-1]

        # Median: average of two middle values for even n
        if n == 1:
            median = sorted_vals[0]
        elif n % 2 == 0:
            median = (sorted_vals[n // 2 - 1] + sorted_vals[n // 2]) / 2.0
        else:
            median = sorted_vals[n // 2]

        # P90: linear interpolation
        p90 = _percentile(sorted_vals, 90.0)

        return cls(
            mean=mean,
            median=median,
            p90=p90,
            min=min_val,
            max=max_val,
            count=n,
        )

    def to_dict(self) -> dict[str, float | int]:
        """Serialize to a JSON-compatible dict."""
        return {
            "mean": self.mean,
            "median": self.median,
            "p90": self.p90,
            "min": self.min,
            "max": self.max,
            "count": self.count,
        }


def _percentile(sorted_vals: list[float], p: float) -> float:
    """Compute the p-th percentile of a sorted list using linear interpolation.

    Parameters
    ----------
    sorted_vals:
        Pre-sorted list of values (ascending).
    p:
        Percentile to compute (0 to 100).

    Returns
    -------
    float
        Interpolated percentile value.
    """
    n = len(sorted_vals)
    if n == 0:
        return 0.0
    if n == 1:
        return sorted_vals[0]

    # Compute fractional index
    index = (p / 100.0) * (n - 1)
    lower = int(math.floor(index))
    upper = int(math.ceil(index))
    fraction = index - lower

    if lower == upper:
        return sorted_vals[lower]
    return sorted_vals[lower] * (1.0 - fraction) + sorted_vals[upper] * fraction


@dataclass
class BenchmarkMetrics:
    """Aggregated metrics for a benchmark evaluation run.

    Top-level metrics aggregate over all results. The per_tier and
    per_frame_class fields provide breakdowns by stratum.
    """

    success_rate_at_k: dict[int, float]
    """SR@K: fraction of problems with nodes_visited <= K and success=True.

    Keys are node budgets (e.g. 1000, 5000, 10000).
    Values are fractions in [0.0, 1.0].
    """

    nodes_visited_stats: DescriptiveStats
    """Descriptive statistics over nodes_visited for all results.

    Failed searches are capped at the node budget.
    """

    time_to_proof_stats: DescriptiveStats
    """Descriptive statistics over time_seconds for successful searches only."""

    proof_height_stats: DescriptiveStats
    """Descriptive statistics over proof_height for successful searches only."""

    per_tier: dict[str, BenchmarkMetrics] = field(default_factory=dict)
    """Per-difficulty-tier breakdowns (nested BenchmarkMetrics without per_tier/per_frame_class)."""

    per_frame_class: dict[str, BenchmarkMetrics] = field(default_factory=dict)
    """Per-frame-class breakdowns (nested BenchmarkMetrics without per_tier/per_frame_class)."""

    total_problems: int = 0
    """Total number of problems in this result set."""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        return metrics_to_dict(self)


def compute_metrics(
    results: list[SearchResult],
    budget_ks: list[int] | None = None,
) -> BenchmarkMetrics:
    """Compute benchmark metrics from a list of search results.

    Parameters
    ----------
    results:
        List of SearchResult objects from running a search system.
    budget_ks:
        Node budgets at which to compute SR@K.
        Defaults to [1000, 5000, 10000].

    Returns
    -------
    BenchmarkMetrics
        Computed metrics with per-tier and per-frame-class breakdowns.
    """
    if budget_ks is None:
        budget_ks = [1000, 5000, 10000]

    return _compute_metrics_for_results(results, budget_ks, include_breakdowns=True)


def _compute_metrics_for_results(
    results: list[SearchResult],
    budget_ks: list[int],
    include_breakdowns: bool = False,
) -> BenchmarkMetrics:
    """Internal helper to compute metrics from a result set.

    Parameters
    ----------
    results:
        List of SearchResult objects.
    budget_ks:
        Node budget values for SR@K computation.
    include_breakdowns:
        If True, compute per_tier and per_frame_class breakdowns recursively.

    Returns
    -------
    BenchmarkMetrics
        Metrics computed from the results.
    """
    n = len(results)

    # SR@K computation
    success_rate_at_k: dict[int, float] = {}
    for k in budget_ks:
        if n == 0:
            success_rate_at_k[k] = 0.0
        else:
            successes_at_k = sum(
                1 for r in results if r.success and r.nodes_visited <= k
            )
            success_rate_at_k[k] = successes_at_k / n

    # Nodes visited: all results (failed = capped at budget)
    nodes_visited_values: list[float] = [float(r.nodes_visited) for r in results]

    # Time to proof: successful searches only
    ttp_values: list[float] = [r.time_seconds for r in results if r.success]

    # Proof height: successful searches with known height
    ph_values: list[float] = [
        float(r.proof_height) for r in results if r.success and r.proof_height is not None
    ]

    nodes_visited_stats = DescriptiveStats.from_values(nodes_visited_values)
    time_to_proof_stats = DescriptiveStats.from_values(ttp_values)
    proof_height_stats = DescriptiveStats.from_values(ph_values)

    # Compute per-tier and per-frame-class breakdowns
    per_tier: dict[str, BenchmarkMetrics] = {}
    per_frame_class: dict[str, BenchmarkMetrics] = {}

    if include_breakdowns and results:
        # Group by tier
        tier_groups: dict[str, list[SearchResult]] = {}
        for r in results:
            tier_groups.setdefault(r.difficulty_tier, []).append(r)
        for tier, tier_results in tier_groups.items():
            per_tier[tier] = _compute_metrics_for_results(
                tier_results, budget_ks, include_breakdowns=False
            )

        # Group by frame class
        fc_groups: dict[str, list[SearchResult]] = {}
        for r in results:
            fc_groups.setdefault(r.frame_class, []).append(r)
        for fc, fc_results in fc_groups.items():
            per_frame_class[fc] = _compute_metrics_for_results(
                fc_results, budget_ks, include_breakdowns=False
            )

    return BenchmarkMetrics(
        success_rate_at_k=success_rate_at_k,
        nodes_visited_stats=nodes_visited_stats,
        time_to_proof_stats=time_to_proof_stats,
        proof_height_stats=proof_height_stats,
        per_tier=per_tier,
        per_frame_class=per_frame_class,
        total_problems=n,
    )


def format_results_table(metrics: BenchmarkMetrics, system_name: str) -> str:
    """Format metrics as a TABLEAUX/CADE-style comparison table.

    Produces a plain-text table with SR@K columns at each node budget,
    plus average nodes visited for failed searches.

    Parameters
    ----------
    metrics:
        Computed BenchmarkMetrics instance.
    system_name:
        Name of the system being evaluated (e.g. "SuccessPatterns").

    Returns
    -------
    str
        Formatted table string.
    """
    budgets = sorted(metrics.success_rate_at_k.keys())

    # Build header
    header_cols = [f"{'System':<24}"] + [f"SR@{k:<8}" for k in budgets] + [f"{'NV_mean':<12}", f"{'TTP_mean':<12}"]
    header = " | ".join(header_cols)
    separator = "-" * len(header)

    # Build overall row
    sr_cols = [f"{metrics.success_rate_at_k[k]:<8.3f}" for k in budgets]
    nv_mean = f"{metrics.nodes_visited_stats.mean:<12.1f}"
    ttp_mean = f"{metrics.time_to_proof_stats.mean:<12.3f}"
    row = " | ".join(
        [f"{system_name:<24}"] + sr_cols + [nv_mean, ttp_mean]
    )

    lines = [header, separator, row]

    # Per-tier breakdown
    if metrics.per_tier:
        lines.append("")
        lines.append("Per-Tier Breakdown:")
        tier_header = " | ".join(
            [f"{'Tier':<24}"] + [f"SR@{k:<8}" for k in budgets] + [f"{'Count':<12}"]
        )
        lines.append(tier_header)
        lines.append("-" * len(tier_header))
        for tier in sorted(metrics.per_tier.keys()):
            tier_metrics = metrics.per_tier[tier]
            tier_sr = [f"{tier_metrics.success_rate_at_k[k]:<8.3f}" for k in budgets]
            tier_row = " | ".join(
                [f"{tier:<24}"] + tier_sr + [f"{tier_metrics.total_problems:<12}"]
            )
            lines.append(tier_row)

    # Per-frame-class breakdown
    if metrics.per_frame_class:
        lines.append("")
        lines.append("Per-Frame-Class Breakdown:")
        fc_header = " | ".join(
            [f"{'Frame Class':<24}"] + [f"SR@{k:<8}" for k in budgets] + [f"{'Count':<12}"]
        )
        lines.append(fc_header)
        lines.append("-" * len(fc_header))
        for fc in sorted(metrics.per_frame_class.keys()):
            fc_metrics = metrics.per_frame_class[fc]
            fc_sr = [f"{fc_metrics.success_rate_at_k[k]:<8.3f}" for k in budgets]
            fc_row = " | ".join(
                [f"{fc:<24}"] + fc_sr + [f"{fc_metrics.total_problems:<12}"]
            )
            lines.append(fc_row)

    return "\n".join(lines)


def metrics_to_dict(metrics: BenchmarkMetrics) -> dict[str, Any]:
    """Serialize BenchmarkMetrics to a JSON-compatible dict.

    Parameters
    ----------
    metrics:
        BenchmarkMetrics instance to serialize.

    Returns
    -------
    dict[str, Any]
        Serialized metrics dict.
    """
    result: dict[str, Any] = {
        "success_rate_at_k": {str(k): v for k, v in metrics.success_rate_at_k.items()},
        "nodes_visited_stats": metrics.nodes_visited_stats.to_dict(),
        "time_to_proof_stats": metrics.time_to_proof_stats.to_dict(),
        "proof_height_stats": metrics.proof_height_stats.to_dict(),
        "total_problems": metrics.total_problems,
    }

    if metrics.per_tier:
        result["per_tier"] = {
            tier: metrics_to_dict(tier_metrics)
            for tier, tier_metrics in metrics.per_tier.items()
        }

    if metrics.per_frame_class:
        result["per_frame_class"] = {
            fc: metrics_to_dict(fc_metrics)
            for fc, fc_metrics in metrics.per_frame_class.items()
        }

    return result
