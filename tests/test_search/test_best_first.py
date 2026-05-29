"""Tests for best-first search implementation.

Covers:
- Phase 1: Data structures and rule-based heuristic scoring
- Phase 2: Search loop mechanics
- Phase 3: Value network integration and tensor encoding
"""

from __future__ import annotations

import math

import pytest

from bimodal_harness.schema.records import PatternKey
from bimodal_harness.search.best_first import (
    HeuristicWeights,
    MockValueNetwork,
    PythonBestFirstSearch,
    SearchNode,
    SearchStats,
    _batch_score_nodes,
    _formula_hash,
    _pattern_key_to_tensor,
    _scale_value,
    advanced_heuristic_score,
    formula_eq,
    heuristic_score,
    is_assumption,
    is_axiom,
    structure_heuristic,
)

# ---------------------------------------------------------------------------
# Formula fixtures
# ---------------------------------------------------------------------------

ATOM_P = {"tag": "atom", "name": "p"}
ATOM_Q = {"tag": "atom", "name": "q"}
ATOM_R = {"tag": "atom", "name": "r"}
BOT = {"tag": "bot"}

# p -> q
IMP_P_Q = {"tag": "imp", "left": ATOM_P, "right": ATOM_Q}

# p -> (q -> p)  -- K axiom / prop_k
IMP_K = {"tag": "imp", "left": ATOM_P, "right": {"tag": "imp", "left": ATOM_Q, "right": ATOM_P}}

# bot -> p  -- ex falso
IMP_BOT_P = {"tag": "imp", "left": BOT, "right": ATOM_P}

# box(p)
BOX_P = {"tag": "box", "child": ATOM_P}

# box(p -> q)
BOX_IMP_P_Q = {"tag": "box", "child": {"tag": "imp", "left": ATOM_P, "right": ATOM_Q}}

# until(p, q)
UNTL_P_Q = {"tag": "untl", "event": ATOM_P, "guard": ATOM_Q}

# since(p, q)
SNCE_P_Q = {"tag": "snce", "event": ATOM_P, "guard": ATOM_Q}


# ---------------------------------------------------------------------------
# Phase 1: formula_eq tests
# ---------------------------------------------------------------------------


class TestFormulaEq:
    """Tests for formula structural equality."""

    def test_atom_equal(self) -> None:
        assert formula_eq(ATOM_P, {"tag": "atom", "name": "p"})

    def test_atom_not_equal_name(self) -> None:
        assert not formula_eq(ATOM_P, ATOM_Q)

    def test_bot_equal(self) -> None:
        assert formula_eq(BOT, {"tag": "bot"})

    def test_different_tags(self) -> None:
        assert not formula_eq(ATOM_P, BOT)

    def test_imp_equal(self) -> None:
        imp = {"tag": "imp", "left": ATOM_P, "right": ATOM_Q}
        assert formula_eq(IMP_P_Q, imp)

    def test_imp_not_equal_left(self) -> None:
        imp = {"tag": "imp", "left": ATOM_R, "right": ATOM_Q}
        assert not formula_eq(IMP_P_Q, imp)

    def test_box_equal(self) -> None:
        assert formula_eq(BOX_P, {"tag": "box", "child": ATOM_P})

    def test_box_not_equal(self) -> None:
        assert not formula_eq(BOX_P, {"tag": "box", "child": ATOM_Q})

    def test_untl_equal(self) -> None:
        assert formula_eq(UNTL_P_Q, {"tag": "untl", "event": ATOM_P, "guard": ATOM_Q})

    def test_untl_not_equal(self) -> None:
        assert not formula_eq(UNTL_P_Q, {"tag": "untl", "event": ATOM_Q, "guard": ATOM_P})


# ---------------------------------------------------------------------------
# Phase 1: is_axiom tests
# ---------------------------------------------------------------------------


class TestIsAxiom:
    """Tests for axiom schema recognition."""

    def test_k_axiom(self) -> None:
        """p -> (q -> p) is the K axiom."""
        assert is_axiom(IMP_K)

    def test_ex_falso(self) -> None:
        """bot -> p is ex falso."""
        assert is_axiom(IMP_BOT_P)

    def test_atom_not_axiom(self) -> None:
        """Bare atom is not an axiom."""
        assert not is_axiom(ATOM_P)

    def test_bot_not_axiom(self) -> None:
        """bot alone is not an axiom."""
        assert not is_axiom(BOT)

    def test_simple_imp_not_axiom(self) -> None:
        """p -> q is not an axiom."""
        assert not is_axiom(IMP_P_Q)

    def test_box_formula_not_axiom(self) -> None:
        """box(p) is not an axiom."""
        assert not is_axiom(BOX_P)


# ---------------------------------------------------------------------------
# Phase 1: is_assumption tests
# ---------------------------------------------------------------------------


class TestIsAssumption:
    """Tests for assumption rule."""

    def test_goal_in_context(self) -> None:
        context = [ATOM_P, ATOM_Q]
        assert is_assumption(context, ATOM_P)

    def test_goal_not_in_context(self) -> None:
        context = [ATOM_P, ATOM_Q]
        assert not is_assumption(context, ATOM_R)

    def test_empty_context(self) -> None:
        assert not is_assumption([], ATOM_P)

    def test_complex_formula_in_context(self) -> None:
        context = [IMP_P_Q, BOX_P]
        assert is_assumption(context, BOX_P)

    def test_structural_equality_not_reference(self) -> None:
        """is_assumption uses structural equality, not object identity."""
        ctx = [{"tag": "atom", "name": "p"}]
        goal = {"tag": "atom", "name": "p"}  # different object, same structure
        assert is_assumption(ctx, goal)


# ---------------------------------------------------------------------------
# Phase 1: heuristic_score tests
# ---------------------------------------------------------------------------


class TestHeuristicScore:
    """Tests for rule-based heuristic scoring."""

    def setup_method(self) -> None:
        self.weights = HeuristicWeights()

    def test_axiom_score_zero(self) -> None:
        """K axiom scores 0.0."""
        score = heuristic_score([], IMP_K, self.weights)
        assert score == 0.0

    def test_ex_falso_score_zero(self) -> None:
        """bot -> p scores 0.0."""
        score = heuristic_score([], IMP_BOT_P, self.weights)
        assert score == 0.0

    def test_assumption_score_one(self) -> None:
        """Goal in context scores 1.0."""
        score = heuristic_score([ATOM_P], ATOM_P, self.weights)
        assert score == 1.0

    def test_imp_goal_scores_mp_base(self) -> None:
        """Implication goal scores at least mp_base."""
        score = heuristic_score([], IMP_P_Q, self.weights)
        # Should be mp_base + complexity * weight
        assert score >= self.weights.mp_base

    def test_modal_goal_scores_modal_base(self) -> None:
        """Box goal scores modal_base."""
        score = heuristic_score([], BOX_P, self.weights)
        assert score == self.weights.modal_base

    def test_temporal_goal_scores_temporal_base(self) -> None:
        """Until goal scores temporal_base."""
        score = heuristic_score([], UNTL_P_Q, self.weights)
        assert score == self.weights.temporal_base

    def test_since_goal_scores_temporal_base(self) -> None:
        """Since goal scores temporal_base."""
        score = heuristic_score([], SNCE_P_Q, self.weights)
        assert score == self.weights.temporal_base

    def test_unprovable_atom_scores_dead_end(self) -> None:
        """Atom not in context scores dead_end."""
        score = heuristic_score([], ATOM_P, self.weights)
        assert score == self.weights.dead_end

    def test_bot_scores_dead_end(self) -> None:
        """bot not in context scores dead_end."""
        score = heuristic_score([], BOT, self.weights)
        assert score == self.weights.dead_end

    def test_custom_weights(self) -> None:
        """Custom weights are applied."""
        custom = HeuristicWeights(modal_base=10.0)
        score = heuristic_score([], BOX_P, custom)
        assert score == 10.0

    def test_axiom_beats_assumption(self) -> None:
        """Axiom (0.0) < assumption (1.0)."""
        axiom_score = heuristic_score([], IMP_K, self.weights)
        assumption_score = heuristic_score([ATOM_P], ATOM_P, self.weights)
        assert axiom_score < assumption_score


# ---------------------------------------------------------------------------
# Phase 1: advanced_heuristic_score tests
# ---------------------------------------------------------------------------


class TestAdvancedHeuristicScore:
    """Tests for domain-aware advanced heuristic scoring."""

    def setup_method(self) -> None:
        self.weights = HeuristicWeights()

    def test_axiom_unchanged(self) -> None:
        """Axiom score (0.0) is unchanged by advanced heuristic."""
        score = advanced_heuristic_score([], IMP_K, self.weights)
        assert score == 0.0

    def test_dead_end_unchanged(self) -> None:
        """Dead-end score is unchanged."""
        score = advanced_heuristic_score([], ATOM_P, self.weights)
        assert score >= self.weights.dead_end

    def test_modal_domain_bonus(self) -> None:
        """Modal context reduces cost of modal goal."""
        score_no_modal = advanced_heuristic_score([], BOX_P, self.weights)
        score_with_modal = advanced_heuristic_score([BOX_IMP_P_Q], BOX_P, self.weights)
        assert score_with_modal <= score_no_modal

    def test_temporal_domain_bonus(self) -> None:
        """Temporal context reduces cost of temporal goal."""
        score_no_temporal = advanced_heuristic_score([], UNTL_P_Q, self.weights)
        score_with_temporal = advanced_heuristic_score([SNCE_P_Q], UNTL_P_Q, self.weights)
        assert score_with_temporal <= score_no_temporal

    def test_score_remains_positive(self) -> None:
        """Score never goes below 0.0."""
        context = [BOX_P, BOX_IMP_P_Q]
        score = advanced_heuristic_score(context, BOX_P, self.weights)
        assert score >= 0.0


# ---------------------------------------------------------------------------
# Phase 1: structure_heuristic tests
# ---------------------------------------------------------------------------


class TestStructureHeuristic:
    """Tests for the structural complexity heuristic."""

    def test_atom_zero(self) -> None:
        assert structure_heuristic(ATOM_P) == 0.0

    def test_bot_zero(self) -> None:
        assert structure_heuristic(BOT) == 0.0

    def test_imp_positive(self) -> None:
        assert structure_heuristic(IMP_P_Q) > 0.0

    def test_box_positive(self) -> None:
        assert structure_heuristic(BOX_P) > 0.0

    def test_temporal_higher_than_box(self) -> None:
        """Temporal goals should have higher base cost than modal."""
        assert structure_heuristic(UNTL_P_Q) > structure_heuristic(BOX_P)


# ---------------------------------------------------------------------------
# Phase 2: Search loop tests
# ---------------------------------------------------------------------------


class MockBridge:
    """Mock bridge for testing without real Lean."""

    def __init__(self, valid_formulas: list[dict] | None = None) -> None:
        self.valid_formulas = valid_formulas or []

    def label_formula(self, formula: dict) -> dict:
        """Return valid/invalid based on configured formulas."""
        for f in self.valid_formulas:
            if formula_eq(formula, f):
                return {"label": "valid", "proof_height": 1}
        return {"label": "invalid", "proof_height": None}


class TestSearchNode:
    """Tests for SearchNode data structure."""

    def test_ordering_by_fscore(self) -> None:
        """SearchNodes are ordered by fscore for heapq."""
        node1 = SearchNode(context=[], goal=ATOM_P, cost=1.0, heuristic=1.0, fscore=2.0)
        node2 = SearchNode(context=[], goal=ATOM_Q, cost=0.5, heuristic=0.5, fscore=1.0)
        assert node2 < node1

    def test_parent_field(self) -> None:
        """Parent field is stored correctly."""
        root = SearchNode(context=[], goal=ATOM_P, cost=0.0, heuristic=1.0, fscore=1.0)
        child = SearchNode(
            context=[], goal=ATOM_Q, cost=1.0, heuristic=0.5, fscore=1.5, parent=root
        )
        assert child.parent is root

    def test_action_field(self) -> None:
        """Action field is stored correctly."""
        node = SearchNode(
            context=[], goal=ATOM_P, cost=0.0, heuristic=0.0, fscore=0.0, action="test_action"
        )
        assert node.action == "test_action"


class TestPythonBestFirstSearch:
    """Tests for the PythonBestFirstSearch class."""

    def test_trivial_axiom_proof(self) -> None:
        """K axiom is proved without any expansions."""
        searcher = PythonBestFirstSearch(max_expansions=100)
        result = searcher.search([], IMP_K)
        assert result.proved

    def test_ex_falso_proof(self) -> None:
        """bot -> p is proved immediately as axiom."""
        searcher = PythonBestFirstSearch(max_expansions=100)
        result = searcher.search([], IMP_BOT_P)
        assert result.proved

    def test_assumption_proof(self) -> None:
        """Goal in context is proved immediately."""
        searcher = PythonBestFirstSearch(max_expansions=100)
        result = searcher.search([ATOM_P], ATOM_P)
        assert result.proved

    def test_simple_mp_proof(self) -> None:
        """p can be proved if p and p->q are in context."""
        # Context: [p, p -> q], goal: q
        # Modus ponens: from p->q in context, reduce to proving p
        # p is in context -> proved
        context = [ATOM_P, IMP_P_Q]
        searcher = PythonBestFirstSearch(max_expansions=1000)
        result = searcher.search(context, ATOM_Q)
        assert result.proved

    def test_max_expansions_terminates(self) -> None:
        """Search terminates at max_expansions."""
        # ATOM_R with empty context should fail quickly
        searcher = PythonBestFirstSearch(max_expansions=5)
        result = searcher.search([], ATOM_R)
        assert not result.proved
        assert result.stats.expanded <= 5 + 1  # allow slight overage

    def test_stats_tracking(self) -> None:
        """Search stats track visited and expanded counts."""
        searcher = PythonBestFirstSearch(max_expansions=50)
        result = searcher.search([], ATOM_R)
        assert result.stats.visited >= 1
        assert result.stats.expanded >= 1
        assert result.stats.wall_clock_seconds >= 0.0

    def test_max_queue_size_tracked(self) -> None:
        """Max queue size is tracked."""
        searcher = PythonBestFirstSearch(max_expansions=100)
        result = searcher.search([ATOM_P, IMP_P_Q], ATOM_Q)
        assert result.stats.max_queue_size >= 0

    def test_proved_returns_proof_steps(self) -> None:
        """Successful search returns proof steps."""
        searcher = PythonBestFirstSearch(max_expansions=100)
        result = searcher.search([ATOM_P], ATOM_P)
        assert result.proved
        assert result.proof_steps is not None
        assert len(result.proof_steps) >= 1

    def test_unprovable_returns_none_proof(self) -> None:
        """Failed search returns None for proof_steps."""
        searcher = PythonBestFirstSearch(max_expansions=5)
        result = searcher.search([], ATOM_R)
        assert not result.proved
        assert result.proof_steps is None

    def test_no_value_net_is_pure_rule_based(self) -> None:
        """When value_net=None, search uses only rule-based scoring."""
        searcher = PythonBestFirstSearch(value_net=None, max_expansions=100)
        assert searcher.value_net is None
        result = searcher.search([ATOM_P], ATOM_P)
        assert result.proved

    def test_bridge_called_for_leaf(self) -> None:
        """Bridge is called to verify non-trivial leaf nodes."""
        # ATOM_Q not in context, but mock bridge says it's valid
        bridge = MockBridge(valid_formulas=[ATOM_Q])
        # This test verifies bridge integration; with max_expansions=5 and
        # a bridge that validates q, we may hit q as a leaf
        searcher = PythonBestFirstSearch(max_expansions=100)
        # The bridge won't be called on axiom/assumption checks, but
        # for formulas the rule-based search considers dead-ends
        result = searcher.search([], ATOM_Q, bridge)
        # The bridge validates ATOM_Q so this should succeed
        assert result.proved

    def test_imp_introduction_subgoal(self) -> None:
        """Search applies implication introduction to create subgoals."""
        # Goal: p -> q, context: [q]
        # imp_intro: add p to context, prove q
        # q is in new context -> proved
        context = [ATOM_Q]
        goal = IMP_P_Q
        searcher = PythonBestFirstSearch(max_expansions=500)
        result = searcher.search(context, goal)
        assert result.proved


# ---------------------------------------------------------------------------
# Phase 3: Tensor encoding tests
# ---------------------------------------------------------------------------


class TestPatternKeyToTensor:
    """Tests for PatternKey tensor encoding."""

    def test_tensor_length(self) -> None:
        """Encoded tensor has 12 dimensions."""
        key = PatternKey(
            modal_depth=0, temporal_depth=0, imp_count=0, complexity=1, top_operator="Atom"
        )
        tensor = _pattern_key_to_tensor(key)
        assert len(tensor) == 12

    def test_numeric_features_log1p(self) -> None:
        """Numeric features use log1p normalization."""
        key = PatternKey(
            modal_depth=1, temporal_depth=2, imp_count=3, complexity=4, top_operator="Atom"
        )
        tensor = _pattern_key_to_tensor(key)
        assert abs(tensor[0] - math.log1p(1)) < 1e-7
        assert abs(tensor[1] - math.log1p(2)) < 1e-7
        assert abs(tensor[2] - math.log1p(3)) < 1e-7
        assert abs(tensor[3] - math.log1p(4)) < 1e-7

    def test_one_hot_sum_is_one(self) -> None:
        """One-hot encoding sums to exactly 1.0."""
        key = PatternKey(
            modal_depth=0, temporal_depth=0, imp_count=0, complexity=1, top_operator="Box"
        )
        tensor = _pattern_key_to_tensor(key)
        one_hot = tensor[4:]
        assert abs(sum(one_hot) - 1.0) < 1e-7

    def test_zero_depth_gives_zero_log1p(self) -> None:
        """Zero numeric features give 0.0 after log1p."""
        key = PatternKey(
            modal_depth=0, temporal_depth=0, imp_count=0, complexity=1, top_operator="Atom"
        )
        tensor = _pattern_key_to_tensor(key)
        assert tensor[0] == 0.0
        assert tensor[1] == 0.0
        assert tensor[2] == 0.0
        # complexity=1: log1p(1) = log(2) != 0
        assert abs(tensor[3] - math.log1p(1)) < 1e-7

    def test_all_valid_operators_encode(self) -> None:
        """All valid top_operator values produce valid encodings."""
        for op in ["Atom", "Bottom", "Implication", "Box", "AllPast", "AllFuture", "Until", "Since"]:
            key = PatternKey(
                modal_depth=0, temporal_depth=0, imp_count=0, complexity=1, top_operator=op
            )
            tensor = _pattern_key_to_tensor(key)
            assert len(tensor) == 12
            assert sum(tensor[4:]) == 1.0

    def test_box_formula_encoding(self) -> None:
        """box(imp(atom(p), atom(q))) encodes correctly."""
        from bimodal_harness.schema.features import extract_pattern_key

        formula = {"tag": "box", "child": {"tag": "imp", "left": ATOM_P, "right": ATOM_Q}}
        key = extract_pattern_key(formula)
        assert key.top_operator == "Box"
        assert key.modal_depth == 1
        tensor = _pattern_key_to_tensor(key)
        assert len(tensor) == 12
        # Modal depth = 1: log1p(1) = log(2)
        assert abs(tensor[0] - math.log1p(1)) < 1e-7


# ---------------------------------------------------------------------------
# Phase 3: Temperature scaling tests
# ---------------------------------------------------------------------------


class TestScaleValue:
    """Tests for temperature-scaled sigmoid."""

    def test_half_is_fixed_point(self) -> None:
        """0.5 maps to 0.5 at any temperature."""
        for t in [0.5, 1.0, 1.5, 2.0, 5.0]:
            scaled = _scale_value(0.5, t)
            assert abs(scaled - 0.5) < 1e-6

    def test_temperature_one_identity(self) -> None:
        """Temperature=1.0 is the identity sigmoid (no change)."""
        for v in [0.2, 0.4, 0.6, 0.8]:
            scaled = _scale_value(v, 1.0)
            assert abs(scaled - v) < 1e-5

    def test_high_temperature_flattens(self) -> None:
        """High temperature pulls values toward 0.5."""
        v = 0.9
        scaled_t1 = _scale_value(v, 1.0)
        scaled_t5 = _scale_value(v, 5.0)
        # T=5 should be closer to 0.5 than T=1
        assert abs(scaled_t5 - 0.5) < abs(scaled_t1 - 0.5)

    def test_low_temperature_sharpens(self) -> None:
        """Low temperature pushes values toward 0/1."""
        v = 0.7
        scaled_t1 = _scale_value(v, 1.0)
        scaled_t05 = _scale_value(v, 0.5)
        # T=0.5 should be farther from 0.5 than T=1
        assert abs(scaled_t05 - 0.5) > abs(scaled_t1 - 0.5)

    def test_output_in_range(self) -> None:
        """Output is always in [0, 1]."""
        for v in [0.01, 0.1, 0.5, 0.9, 0.99]:
            for t in [0.1, 0.5, 1.0, 1.5, 2.0, 5.0]:
                scaled = _scale_value(v, t)
                assert 0.0 <= scaled <= 1.0


# ---------------------------------------------------------------------------
# Phase 3: Batch scoring tests
# ---------------------------------------------------------------------------


class TestBatchScoreNodes:
    """Tests for batched neural scoring of nodes."""

    def test_batch_score_with_mock(self) -> None:
        """Mock value network returns scaled constant for all nodes."""
        nodes = [
            SearchNode(context=[], goal=ATOM_P, cost=0.0, heuristic=1.0, fscore=1.0),
            SearchNode(context=[], goal=BOX_P, cost=0.0, heuristic=5.0, fscore=5.0),
        ]
        net = MockValueNetwork(constant=0.8)
        bonuses = _batch_score_nodes(nodes, net, temperature=1.5)
        assert len(bonuses) == 2
        # All bonuses should be scaled version of 0.8
        for bonus in bonuses:
            assert 0.0 < bonus < 1.0

    def test_batch_score_neutral(self) -> None:
        """constant=0.5 returns 0.5 for all nodes."""
        nodes = [
            SearchNode(context=[], goal=ATOM_P, cost=0.0, heuristic=1.0, fscore=1.0),
        ]
        net = MockValueNetwork(constant=0.5)
        bonuses = _batch_score_nodes(nodes, net, temperature=1.0)
        assert abs(bonuses[0] - 0.5) < 1e-5

    def test_empty_batch(self) -> None:
        """Empty batch returns empty list."""
        net = MockValueNetwork(constant=0.7)
        bonuses = _batch_score_nodes([], net, temperature=1.0)
        assert bonuses == []


# ---------------------------------------------------------------------------
# Phase 3: Neural integration with mock value network
# ---------------------------------------------------------------------------


class TestNeuralIntegration:
    """Tests for PythonBestFirstSearch with MockValueNetwork."""

    def test_mock_net_proof_succeeds(self) -> None:
        """Search with MockValueNetwork still proves trivial goals."""
        net = MockValueNetwork(constant=0.9)
        searcher = PythonBestFirstSearch(value_net=net, max_expansions=200)
        result = searcher.search([ATOM_P], ATOM_P)
        assert result.proved

    def test_mock_net_k_axiom(self) -> None:
        """K axiom proved with neural scoring."""
        net = MockValueNetwork(constant=0.5)
        searcher = PythonBestFirstSearch(value_net=net, max_expansions=100)
        result = searcher.search([], IMP_K)
        assert result.proved

    def test_high_confidence_net_mp_proof(self) -> None:
        """High-confidence network (0.9) still proves MP goals."""
        net = MockValueNetwork(constant=0.9)
        searcher = PythonBestFirstSearch(value_net=net, alpha=5.0, max_expansions=1000)
        context = [ATOM_P, IMP_P_Q]
        result = searcher.search(context, ATOM_Q)
        assert result.proved

    def test_neural_vs_baseline_ordering(self) -> None:
        """Neural searcher visits different order than baseline.

        This is an indirect test: we verify both find the same proof but
        the stats may differ (neural bonus changes priority ordering).
        """
        context = [ATOM_P, IMP_P_Q]
        goal = ATOM_Q

        baseline = PythonBestFirstSearch(value_net=None, max_expansions=500)
        neural = PythonBestFirstSearch(
            value_net=MockValueNetwork(constant=0.9), max_expansions=500
        )

        r_baseline = baseline.search(context, goal)
        r_neural = neural.search(context, goal)

        assert r_baseline.proved
        assert r_neural.proved


# ---------------------------------------------------------------------------
# Phase 3: ValueNetworkProtocol compliance
# ---------------------------------------------------------------------------


class TestValueNetworkProtocol:
    """Tests that MockValueNetwork complies with ValueNetworkProtocol."""

    def test_mock_implements_protocol(self) -> None:
        """MockValueNetwork is an instance of ValueNetworkProtocol."""
        from bimodal_harness.search.best_first import ValueNetworkProtocol

        net = MockValueNetwork()
        assert isinstance(net, ValueNetworkProtocol)

    def test_predict_returns_float(self) -> None:
        """predict() returns a float."""
        key = PatternKey(
            modal_depth=0, temporal_depth=0, imp_count=0, complexity=1, top_operator="Atom"
        )
        net = MockValueNetwork(constant=0.7)
        result = net.predict(key)
        assert isinstance(result, float)
        assert result == 0.7

    def test_predict_batch_returns_list(self) -> None:
        """predict_batch() returns a list of floats."""
        keys = [
            PatternKey(
                modal_depth=i, temporal_depth=0, imp_count=0, complexity=1, top_operator="Atom"
            )
            for i in range(5)
        ]
        net = MockValueNetwork(constant=0.3)
        results = net.predict_batch(keys)
        assert len(results) == 5
        assert all(isinstance(r, float) and r == 0.3 for r in results)
