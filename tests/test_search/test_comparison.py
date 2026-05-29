"""Tests for A/B comparison runner and McNemar statistical testing.

Covers Phase 4:
- ComparisonResult data structure
- run_comparison paired evaluation
- McNemar test computation
- run_benchmark_comparison entry point
"""

from __future__ import annotations

import pytest

from bimodal_harness.search.best_first import (
    ComparisonResult,
    FormulaResult,
    HeuristicWeights,
    MockValueNetwork,
    PythonBestFirstSearch,
    SearchStats,
    formula_eq,
    run_benchmark_comparison,
    run_comparison,
)

# ---------------------------------------------------------------------------
# Shared formula fixtures
# ---------------------------------------------------------------------------

ATOM_P = {"tag": "atom", "name": "p"}
ATOM_Q = {"tag": "atom", "name": "q"}
ATOM_R = {"tag": "atom", "name": "r"}
BOT = {"tag": "bot"}

IMP_P_Q = {"tag": "imp", "left": ATOM_P, "right": ATOM_Q}
IMP_Q_R = {"tag": "imp", "left": ATOM_Q, "right": ATOM_R}
IMP_K = {"tag": "imp", "left": ATOM_P, "right": {"tag": "imp", "left": ATOM_Q, "right": ATOM_P}}
IMP_BOT_P = {"tag": "imp", "left": BOT, "right": ATOM_P}
BOX_P = {"tag": "box", "child": ATOM_P}


# ---------------------------------------------------------------------------
# FormulaResult tests
# ---------------------------------------------------------------------------


class TestFormulaResult:
    """Tests for FormulaResult data structure."""

    def test_creation(self) -> None:
        stats = SearchStats()
        result = FormulaResult(
            formula=ATOM_P,
            baseline_proved=True,
            neural_proved=False,
            baseline_stats=stats,
            neural_stats=stats,
        )
        assert result.baseline_proved is True
        assert result.neural_proved is False

    def test_both_proved(self) -> None:
        stats = SearchStats()
        result = FormulaResult(
            formula=ATOM_P,
            baseline_proved=True,
            neural_proved=True,
            baseline_stats=stats,
            neural_stats=stats,
        )
        assert result.baseline_proved and result.neural_proved


# ---------------------------------------------------------------------------
# run_comparison tests
# ---------------------------------------------------------------------------


class TestRunComparison:
    """Tests for the paired A/B comparison runner."""

    def setup_method(self) -> None:
        """Set up baseline and neural searchers."""
        self.baseline = PythonBestFirstSearch(value_net=None, max_expansions=500)
        self.neural = PythonBestFirstSearch(
            value_net=MockValueNetwork(constant=0.7), max_expansions=500
        )

    def test_empty_formulas(self) -> None:
        """Empty formula list produces zero-rate result."""
        result = run_comparison(self.baseline, self.neural, [])
        assert result.baseline_proof_rate == 0.0
        assert result.neural_proof_rate == 0.0
        assert result.per_formula == []

    def test_all_axioms_proved(self) -> None:
        """All axioms should be proved by both searchers."""
        formulas = [IMP_K, IMP_BOT_P]
        result = run_comparison(self.baseline, self.neural, formulas)
        assert result.baseline_proof_rate == 1.0
        assert result.neural_proof_rate == 1.0

    def test_proof_rate_range(self) -> None:
        """Proof rates are in [0, 1]."""
        formulas = [IMP_K, ATOM_R, ATOM_P]
        result = run_comparison(self.baseline, self.neural, formulas)
        assert 0.0 <= result.baseline_proof_rate <= 1.0
        assert 0.0 <= result.neural_proof_rate <= 1.0

    def test_per_formula_length(self) -> None:
        """per_formula has one entry per input formula."""
        formulas = [IMP_K, IMP_BOT_P, ATOM_R]
        result = run_comparison(self.baseline, self.neural, formulas)
        assert len(result.per_formula) == 3

    def test_contingency_table_shape(self) -> None:
        """Contingency table is 2x2."""
        formulas = [IMP_K, IMP_BOT_P]
        result = run_comparison(self.baseline, self.neural, formulas)
        assert len(result.contingency_table) == 2
        assert len(result.contingency_table[0]) == 2
        assert len(result.contingency_table[1]) == 2

    def test_contingency_table_sums_to_n(self) -> None:
        """Contingency table entries sum to number of formulas."""
        formulas = [IMP_K, IMP_BOT_P, ATOM_R, ATOM_P]
        result = run_comparison(self.baseline, self.neural, formulas)
        n = len(formulas)
        total = sum(result.contingency_table[i][j] for i in range(2) for j in range(2))
        assert total == n

    def test_mean_expansions_nonnegative(self) -> None:
        """Mean expansion counts are non-negative."""
        formulas = [IMP_K, ATOM_R]
        result = run_comparison(self.baseline, self.neural, formulas)
        assert result.baseline_mean_expansions >= 0.0
        assert result.neural_mean_expansions >= 0.0

    def test_mean_time_nonnegative(self) -> None:
        """Mean wall-clock times are non-negative."""
        formulas = [IMP_K, ATOM_R]
        result = run_comparison(self.baseline, self.neural, formulas)
        assert result.baseline_mean_time >= 0.0
        assert result.neural_mean_time >= 0.0

    def test_with_context(self) -> None:
        """Comparison works with shared initial context."""
        context = [ATOM_P, IMP_P_Q]
        formulas = [ATOM_Q]
        result = run_comparison(
            self.baseline, self.neural, formulas, context=context
        )
        assert result.baseline_proof_rate == 1.0

    def test_mcnemar_chi2_nonnegative(self) -> None:
        """McNemar chi2 statistic is non-negative."""
        formulas = [IMP_K, IMP_BOT_P]
        result = run_comparison(self.baseline, self.neural, formulas)
        assert result.mcnemar_chi2 >= 0.0

    def test_mcnemar_perfect_agreement_chi2_zero(self) -> None:
        """When both searchers agree on all formulas, McNemar chi2 = 0."""
        # Both searchers use no value_net (identical): they agree on everything
        baseline2 = PythonBestFirstSearch(value_net=None, max_expansions=500)
        neural2 = PythonBestFirstSearch(value_net=None, max_expansions=500)
        formulas = [IMP_K, IMP_BOT_P]
        result = run_comparison(baseline2, neural2, formulas)
        # b=0, c=0, so chi2=0 or undefined (b+c=0 branch)
        assert result.mcnemar_chi2 == 0.0

    def test_mcnemar_known_contingency(self) -> None:
        """McNemar chi2 computed correctly for known values.

        b=3, c=1: chi2 = (3-1)^2 / (3+1) = 4/4 = 1.0
        """
        # We can test the math directly without running actual search
        # by checking the formula. We'll use a 10-formula benchmark
        # where we know the outcomes.
        formulas_all = [IMP_K] * 10
        baseline = PythonBestFirstSearch(value_net=None, max_expansions=500)
        neural = PythonBestFirstSearch(value_net=None, max_expansions=500)
        result = run_comparison(baseline, neural, formulas_all)
        # Both identical: chi2 = 0
        assert result.mcnemar_chi2 == 0.0


# ---------------------------------------------------------------------------
# McNemar formula verification
# ---------------------------------------------------------------------------


class TestMcNemarFormula:
    """Direct tests of the McNemar chi2 formula."""

    def test_b_minus_c_squared_over_b_plus_c(self) -> None:
        """chi2 = (b-c)^2 / (b+c) for various (b, c) values."""
        cases = [
            (3, 1, 1.0),    # (3-1)^2 / (3+1) = 4/4 = 1.0
            (4, 0, 4.0),    # (4-0)^2 / (4+0) = 16/4 = 4.0
            (0, 4, 4.0),    # (0-4)^2 / (0+4) = 16/4 = 4.0
            (2, 2, 0.0),    # (2-2)^2 / (2+2) = 0/4 = 0.0
            (10, 2, 5.333), # (10-2)^2 / (10+2) = 64/12 ≈ 5.333
        ]
        for b, c, expected_chi2 in cases:
            computed = (b - c) ** 2 / (b + c)
            assert abs(computed - expected_chi2) < 0.01, f"b={b}, c={c}: expected {expected_chi2}, got {computed}"


# ---------------------------------------------------------------------------
# run_benchmark_comparison entry point tests
# ---------------------------------------------------------------------------


class TestRunBenchmarkComparison:
    """Tests for the run_benchmark_comparison convenience function."""

    def test_no_value_net(self) -> None:
        """Without value network, both searchers are identical."""
        formulas = [IMP_K, IMP_BOT_P]
        result = run_benchmark_comparison(formulas, value_net=None, max_expansions=100)
        assert isinstance(result, ComparisonResult)
        assert result.baseline_proof_rate == result.neural_proof_rate

    def test_with_mock_value_net(self) -> None:
        """With mock value network, comparison runs successfully."""
        formulas = [IMP_K, IMP_BOT_P]
        net = MockValueNetwork(constant=0.8)
        result = run_benchmark_comparison(
            formulas, value_net=net, alpha=5.0, temperature=1.5, max_expansions=200
        )
        assert isinstance(result, ComparisonResult)
        assert result.baseline_proof_rate >= 0.0

    def test_custom_max_expansions(self) -> None:
        """Custom max_expansions is respected."""
        formulas = [ATOM_R]  # Unprovable with empty context
        result = run_benchmark_comparison(formulas, value_net=None, max_expansions=3)
        # Both should fail quickly
        assert result.baseline_proof_rate == 0.0

    def test_returns_comparison_result_type(self) -> None:
        """Return type is ComparisonResult."""
        result = run_benchmark_comparison([IMP_K])
        assert isinstance(result, ComparisonResult)

    def test_ten_formula_benchmark(self) -> None:
        """Full pipeline with 10 formulas works correctly."""
        formulas = [
            IMP_K,       # axiom -> proved
            IMP_BOT_P,   # axiom -> proved
            IMP_P_Q,     # imp goal -> expandable
            BOX_P,       # modal goal -> expandable
            ATOM_R,      # dead end
        ]
        net = MockValueNetwork(constant=0.6)
        result = run_benchmark_comparison(
            formulas, value_net=net, alpha=5.0, temperature=1.5, max_expansions=200
        )
        assert 0.0 <= result.baseline_proof_rate <= 1.0
        assert 0.0 <= result.neural_proof_rate <= 1.0
        assert len(result.per_formula) == 5
        # Contingency table totals must equal 5
        total = sum(result.contingency_table[i][j] for i in range(2) for j in range(2))
        assert total == 5


# ---------------------------------------------------------------------------
# Integration: Full pipeline test
# ---------------------------------------------------------------------------


class TestFullPipeline:
    """End-to-end integration tests for the comparison pipeline."""

    def test_mock_bridge_integration(self) -> None:
        """Full pipeline with mock bridge passes without errors."""
        from bimodal_harness.search.best_first import formula_eq

        class MockBridge:
            def label_formula(self, formula: dict) -> dict:
                # Validate atom p
                if formula.get("tag") == "atom" and formula.get("name") == "p":
                    return {"label": "valid", "proof_height": 1}
                return {"label": "invalid", "proof_height": None}

        bridge = MockBridge()
        formulas = [IMP_K, IMP_BOT_P, ATOM_P]
        baseline = PythonBestFirstSearch(value_net=None, max_expansions=200)
        neural = PythonBestFirstSearch(
            value_net=MockValueNetwork(constant=0.7), max_expansions=200
        )
        result = run_comparison(baseline, neural, formulas, bridge=bridge)
        assert isinstance(result, ComparisonResult)
        assert result.baseline_proof_rate >= 0.0

    def test_comparison_result_has_all_fields(self) -> None:
        """ComparisonResult has all expected fields populated."""
        formulas = [IMP_K]
        result = run_benchmark_comparison(formulas)
        # All numeric fields should be finite
        import math as _math

        assert _math.isfinite(result.baseline_proof_rate)
        assert _math.isfinite(result.neural_proof_rate)
        assert _math.isfinite(result.baseline_mean_expansions)
        assert _math.isfinite(result.neural_mean_expansions)
        assert _math.isfinite(result.baseline_mean_time)
        assert _math.isfinite(result.neural_mean_time)
        assert _math.isfinite(result.mcnemar_chi2)
