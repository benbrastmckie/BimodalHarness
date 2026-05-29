"""Baseline runners for bimodal logic benchmark evaluation.

Provides three baseline implementations:
- SuccessPatternsBaseline: Uses LeanBridge to run pattern-guided proof search
- NaiveBFSBaseline: Uses LeanBridge to run breadth-first proof search (no heuristic)
- MockBaseline: Generates deterministic synthetic results for testing (no Lean required)

All baselines implement the same interface: solve(problem) -> SearchResult and
solve_batch(problems) -> list[SearchResult].
"""

from __future__ import annotations

import random
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from bimodal_harness.evaluation.metrics import SearchResult
from bimodal_harness.evaluation.models import BenchmarkProblem


class BaselineRunner(ABC):
    """Abstract base class for all baseline proof search runners.

    Subclasses must implement the ``solve`` method.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name for this baseline system."""

    @abstractmethod
    def solve(self, problem: BenchmarkProblem) -> SearchResult:
        """Run proof search on a single benchmark problem.

        Parameters
        ----------
        problem:
            The benchmark problem to solve.

        Returns
        -------
        SearchResult
            The result of the search attempt.
        """

    def solve_batch(
        self,
        problems: list[BenchmarkProblem],
        progress_callback: Callable[[int, int, SearchResult], None] | None = None,
    ) -> list[SearchResult]:
        """Run proof search on a batch of benchmark problems.

        Parameters
        ----------
        problems:
            List of BenchmarkProblems to evaluate.
        progress_callback:
            Optional callback called after each problem is solved.
            Receives (current_index, total_count, result) arguments.

        Returns
        -------
        list[SearchResult]
            Results for all problems, in the same order as input.
        """
        results: list[SearchResult] = []
        n = len(problems)
        for i, problem in enumerate(problems):
            result = self.solve(problem)
            results.append(result)
            if progress_callback is not None:
                progress_callback(i + 1, n, result)
        return results


class MockBaseline(BaselineRunner):
    """Mock baseline that generates deterministic synthetic search results.

    Does not require Lean to be installed. Used for testing and CI/CD.

    The mock uses tier-based success probabilities and node counts to
    produce realistic-looking (but synthetic) search results:
    - easy: 90% success rate, ~100 nodes
    - medium: 70% success rate, ~500 nodes
    - hard: 40% success rate, ~2000 nodes
    - very_hard: 15% success rate, ~8000 nodes
    """

    _TIER_PARAMS: dict[str, dict[str, Any]] = {
        "easy": {"success_prob": 0.90, "nodes_mean": 100, "nodes_std": 30, "proof_height_mean": 2},
        "medium": {"success_prob": 0.70, "nodes_mean": 500, "nodes_std": 100, "proof_height_mean": 4},
        "hard": {"success_prob": 0.40, "nodes_mean": 2000, "nodes_std": 500, "proof_height_mean": 7},
        "very_hard": {"success_prob": 0.15, "nodes_mean": 8000, "nodes_std": 1500, "proof_height_mean": 12},
    }

    def __init__(self, budget: int = 5000, seed: int = 42) -> None:
        """Initialize the MockBaseline.

        Parameters
        ----------
        budget:
            Node budget per search attempt.
        seed:
            Random seed for deterministic result generation.
        """
        self.budget = budget
        self._seed = seed
        self._rng = random.Random(seed)

    @property
    def name(self) -> str:
        """Return the name of this baseline."""
        return "mock"

    def solve(self, problem: BenchmarkProblem) -> SearchResult:
        """Generate a synthetic search result based on the problem's difficulty tier.

        Results are deterministic: the same problem always produces the same
        result when using the same seed (via benchmark_id-based seeding).
        """
        # Use a per-problem seed based on the problem ID for reproducibility
        problem_rng = random.Random(hash(problem.benchmark_id) ^ self._seed)

        tier = problem.difficulty_tier
        params = self._TIER_PARAMS.get(tier, self._TIER_PARAMS["medium"])

        success = problem_rng.random() < params["success_prob"]

        if success:
            # Successful search: nodes visited < budget
            nodes_raw = max(1, int(problem_rng.gauss(params["nodes_mean"], params["nodes_std"])))
            nodes_visited = min(nodes_raw, self.budget - 1)
            time_seconds = nodes_visited * 0.0001  # ~0.1ms per node
            proof_height = max(1, int(problem_rng.gauss(params["proof_height_mean"], 1.5)))
        else:
            # Failed search: nodes visited = budget (capped)
            nodes_visited = self.budget
            time_seconds = self.budget * 0.0001
            proof_height = None

        return SearchResult(
            problem_id=problem.benchmark_id,
            success=success,
            nodes_visited=nodes_visited,
            time_seconds=time_seconds,
            proof_height=proof_height,
            node_budget=self.budget,
            difficulty_tier=problem.difficulty_tier,
            frame_class=problem.frame_class,
        )


class SuccessPatternsBaseline(BaselineRunner):
    """Baseline using SuccessPatterns heuristic proof search via LeanBridge.

    Requires lean-interact to be installed and a Lean REPL to be running.
    Uses the PatternDatabase + heuristicBonus scoring to guide proof search.

    This is the primary non-neural comparison baseline.
    """

    def __init__(self, lean_bridge: Any, budget: int = 5000) -> None:
        """Initialize the SuccessPatterns baseline.

        Parameters
        ----------
        lean_bridge:
            An initialized LeanBridge instance. Must have a working Lean REPL.
        budget:
            Node budget per search attempt.
        """
        self._lean_bridge = lean_bridge
        self.budget = budget

    @property
    def name(self) -> str:
        """Return the name of this baseline."""
        return "success_patterns"

    def solve(self, problem: BenchmarkProblem) -> SearchResult:
        """Run SuccessPatterns proof search on a single problem via LeanBridge.

        Sends a Lean command invoking the pattern-guided proof search and
        parses the response for success, nodes visited, and proof height.

        Parameters
        ----------
        problem:
            The benchmark problem to solve.

        Returns
        -------
        SearchResult
            The result of the search attempt.
        """
        import json as _json

        formula_json_str = _json.dumps(problem.formula_json)
        # Build Lean command to invoke SuccessPatterns search
        # The command calls the batch search with learning and captures stats
        lean_cmd = (
            f'#eval do\n'
            f'  let formulaJson := {formula_json_str!r}\n'
            f'  let budget := {self.budget}\n'
            f'  let result ← BimodalHarness.batchSearchWithSuccessPatterns formulaJson budget\n'
            f'  IO.println (Lean.toJson result).compress'
        )

        start_time = time.monotonic()
        try:
            response = self._lean_bridge.send_command(lean_cmd)
            elapsed = time.monotonic() - start_time

            if response.ok:
                result_data = _json.loads(response.output.strip())
                success = bool(result_data.get("success", False))
                nodes_visited = int(result_data.get("nodesVisited", self.budget))
                proof_height = (
                    int(result_data["proofHeight"])
                    if success and "proofHeight" in result_data
                    else None
                )
            else:
                # REPL error: treat as failure
                success = False
                nodes_visited = self.budget
                proof_height = None
        except Exception:
            elapsed = time.monotonic() - start_time
            success = False
            nodes_visited = self.budget
            proof_height = None

        return SearchResult(
            problem_id=problem.benchmark_id,
            success=success,
            nodes_visited=min(nodes_visited, self.budget),
            time_seconds=elapsed,
            proof_height=proof_height,
            node_budget=self.budget,
            difficulty_tier=problem.difficulty_tier,
            frame_class=problem.frame_class,
        )


class NaiveBFSBaseline(BaselineRunner):
    """Baseline using naive breadth-first proof search via LeanBridge.

    Uses BFS without any SuccessPatterns heuristic for comparison.
    Provides a lower-bound reference point for the SuccessPatterns baseline.

    Requires lean-interact to be installed.
    """

    def __init__(self, lean_bridge: Any, budget: int = 5000) -> None:
        """Initialize the NaiveBFS baseline.

        Parameters
        ----------
        lean_bridge:
            An initialized LeanBridge instance.
        budget:
            Node budget per search attempt.
        """
        self._lean_bridge = lean_bridge
        self.budget = budget

    @property
    def name(self) -> str:
        """Return the name of this baseline."""
        return "naive_bfs"

    def solve(self, problem: BenchmarkProblem) -> SearchResult:
        """Run naive BFS proof search on a single problem via LeanBridge.

        Parameters
        ----------
        problem:
            The benchmark problem to solve.

        Returns
        -------
        SearchResult
            The result of the search attempt.
        """
        import json as _json

        formula_json_str = _json.dumps(problem.formula_json)
        # Build Lean command to invoke naive BFS (no heuristic)
        lean_cmd = (
            f'#eval do\n'
            f'  let formulaJson := {formula_json_str!r}\n'
            f'  let budget := {self.budget}\n'
            f'  let result ← BimodalHarness.naiveBFS formulaJson budget\n'
            f'  IO.println (Lean.toJson result).compress'
        )

        start_time = time.monotonic()
        try:
            response = self._lean_bridge.send_command(lean_cmd)
            elapsed = time.monotonic() - start_time

            if response.ok:
                result_data = _json.loads(response.output.strip())
                success = bool(result_data.get("success", False))
                nodes_visited = int(result_data.get("nodesVisited", self.budget))
                proof_height = (
                    int(result_data["proofHeight"])
                    if success and "proofHeight" in result_data
                    else None
                )
            else:
                success = False
                nodes_visited = self.budget
                proof_height = None
        except Exception:
            elapsed = time.monotonic() - start_time
            success = False
            nodes_visited = self.budget
            proof_height = None

        return SearchResult(
            problem_id=problem.benchmark_id,
            success=success,
            nodes_visited=min(nodes_visited, self.budget),
            time_seconds=elapsed,
            proof_height=proof_height,
            node_budget=self.budget,
            difficulty_tier=problem.difficulty_tier,
            frame_class=problem.frame_class,
        )
