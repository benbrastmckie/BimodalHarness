"""
Unit tests for BimodalHarness data schema (bimodal_harness.data.schema).

Tests cover:
- All six FormulaTag variants (atom, bot, imp, box, untl, snce)
- Round-trip serialization: from_json(to_json(x)) == x
- LabeledFormula with VALID (proof_trace), INVALID (countermodel), TIMEOUT records
- PatternKey, SimpleCountermodel, RuleProfile, ProofTrace, DifficultyMetrics
"""

from __future__ import annotations

import pytest

from bimodal_harness.data.schema import (
    DifficultyMetrics,
    FormulaNode,
    FormulaTag,
    Label,
    LabeledFormula,
    PatternKey,
    ProofTrace,
    RuleProfile,
    SimpleCountermodel,
)

# ---------------------------------------------------------------------------
# FormulaNode fixtures
# ---------------------------------------------------------------------------

ATOM_JSON = {"tag": "atom", "name": "p"}
BOT_JSON = {"tag": "bot"}
IMP_JSON = {
    "tag": "imp",
    "left": ATOM_JSON,
    "right": BOT_JSON,
}
BOX_JSON = {
    "tag": "box",
    "child": ATOM_JSON,
    "event": {"tag": "atom", "name": "e"},
}
UNTL_JSON = {
    "tag": "untl",
    "guard": ATOM_JSON,
    "child": {"tag": "atom", "name": "q"},
}
SNCE_JSON = {
    "tag": "snce",
    "guard": {"tag": "atom", "name": "r"},
    "child": ATOM_JSON,
}


# ---------------------------------------------------------------------------
# FormulaNode tests
# ---------------------------------------------------------------------------


class TestFormulaNodeAtom:
    def test_from_json(self):
        node = FormulaNode.from_json(ATOM_JSON)
        assert node.tag == FormulaTag.ATOM
        assert node.name == "p"
        assert node.child is None
        assert node.left is None

    def test_round_trip(self):
        node = FormulaNode.from_json(ATOM_JSON)
        assert node.to_json() == ATOM_JSON


class TestFormulaNodeBot:
    def test_from_json(self):
        node = FormulaNode.from_json(BOT_JSON)
        assert node.tag == FormulaTag.BOT
        assert node.name is None

    def test_round_trip(self):
        node = FormulaNode.from_json(BOT_JSON)
        assert node.to_json() == BOT_JSON


class TestFormulaNodeImp:
    def test_from_json(self):
        node = FormulaNode.from_json(IMP_JSON)
        assert node.tag == FormulaTag.IMP
        assert node.left is not None
        assert node.left.tag == FormulaTag.ATOM
        assert node.right is not None
        assert node.right.tag == FormulaTag.BOT

    def test_round_trip(self):
        node = FormulaNode.from_json(IMP_JSON)
        assert node.to_json() == IMP_JSON


class TestFormulaNodeBox:
    def test_from_json(self):
        node = FormulaNode.from_json(BOX_JSON)
        assert node.tag == FormulaTag.BOX
        assert node.child is not None
        assert node.child.name == "p"
        assert node.event is not None
        assert node.event.name == "e"

    def test_round_trip(self):
        node = FormulaNode.from_json(BOX_JSON)
        assert node.to_json() == BOX_JSON


class TestFormulaNodeUntl:
    def test_from_json(self):
        node = FormulaNode.from_json(UNTL_JSON)
        assert node.tag == FormulaTag.UNTL
        assert node.guard is not None
        assert node.guard.name == "p"
        assert node.child is not None
        assert node.child.name == "q"

    def test_round_trip(self):
        node = FormulaNode.from_json(UNTL_JSON)
        assert node.to_json() == UNTL_JSON


class TestFormulaNodeSnce:
    def test_from_json(self):
        node = FormulaNode.from_json(SNCE_JSON)
        assert node.tag == FormulaTag.SNCE
        assert node.guard is not None
        assert node.guard.name == "r"
        assert node.child is not None
        assert node.child.name == "p"

    def test_round_trip(self):
        node = FormulaNode.from_json(SNCE_JSON)
        assert node.to_json() == SNCE_JSON


class TestFormulaNodeErrors:
    def test_invalid_tag_raises(self):
        with pytest.raises(ValueError):
            FormulaNode.from_json({"tag": "unknown_tag"})


# ---------------------------------------------------------------------------
# PatternKey tests
# ---------------------------------------------------------------------------

PATTERN_KEY_JSON = {
    "modal_depth": 2,
    "temporal_depth": 1,
    "imp_count": 3,
    "complexity": 8,
    "top_operator": "imp",
}


class TestPatternKey:
    def test_from_json(self):
        pk = PatternKey.from_json(PATTERN_KEY_JSON)
        assert pk.modal_depth == 2
        assert pk.temporal_depth == 1
        assert pk.imp_count == 3
        assert pk.complexity == 8
        assert pk.top_operator == "imp"

    def test_round_trip(self):
        pk = PatternKey.from_json(PATTERN_KEY_JSON)
        assert pk.to_json() == PATTERN_KEY_JSON


# ---------------------------------------------------------------------------
# SimpleCountermodel tests
# ---------------------------------------------------------------------------

COUNTERMODEL_JSON = {
    "true_atoms": ["p", "r"],
    "false_atoms": ["q"],
    "formula": "p -> q",
}


class TestSimpleCountermodel:
    def test_from_json(self):
        cm = SimpleCountermodel.from_json(COUNTERMODEL_JSON)
        assert cm.true_atoms == ["p", "r"]
        assert cm.false_atoms == ["q"]
        assert cm.formula == "p -> q"

    def test_round_trip(self):
        cm = SimpleCountermodel.from_json(COUNTERMODEL_JSON)
        assert cm.to_json() == COUNTERMODEL_JSON


# ---------------------------------------------------------------------------
# RuleProfile tests
# ---------------------------------------------------------------------------

RULE_PROFILE_JSON = {
    "imp_left": 2,
    "imp_right": 1,
    "box_left": 3,
    "box_right": 0,
    "untl_left": 1,
    "untl_right": 0,
    "snce_left": 0,
}


class TestRuleProfile:
    def test_from_json(self):
        rp = RuleProfile.from_json(RULE_PROFILE_JSON)
        assert rp.imp_left == 2
        assert rp.imp_right == 1
        assert rp.box_left == 3
        assert rp.snce_left == 0

    def test_from_json_defaults(self):
        rp = RuleProfile.from_json({})
        assert rp.imp_left == 0
        assert rp.snce_left == 0

    def test_round_trip(self):
        rp = RuleProfile.from_json(RULE_PROFILE_JSON)
        assert rp.to_json() == RULE_PROFILE_JSON


# ---------------------------------------------------------------------------
# ProofTrace tests
# ---------------------------------------------------------------------------

PROOF_TRACE_JSON = {
    "height": 5,
    "axioms_used": ["id", "bot"],
    "rules_applied": RULE_PROFILE_JSON,
}


class TestProofTrace:
    def test_from_json(self):
        pt = ProofTrace.from_json(PROOF_TRACE_JSON)
        assert pt.height == 5
        assert pt.axioms_used == ["id", "bot"]
        assert pt.rules_applied.imp_left == 2

    def test_round_trip(self):
        pt = ProofTrace.from_json(PROOF_TRACE_JSON)
        assert pt.to_json() == PROOF_TRACE_JSON


# ---------------------------------------------------------------------------
# DifficultyMetrics tests
# ---------------------------------------------------------------------------

METRICS_JSON = {
    "complexity": 8,
    "modal_depth": 2,
    "temporal_depth": 1,
    "imp_count": 3,
    "atom_count": 4,
    "decision_time_ms": 12.5,
    "difficulty_tier": 2,
}


class TestDifficultyMetrics:
    def test_from_json(self):
        dm = DifficultyMetrics.from_json(METRICS_JSON)
        assert dm.complexity == 8
        assert dm.modal_depth == 2
        assert dm.decision_time_ms == 12.5
        assert dm.difficulty_tier == 2

    def test_round_trip(self):
        dm = DifficultyMetrics.from_json(METRICS_JSON)
        assert dm.to_json() == METRICS_JSON


# ---------------------------------------------------------------------------
# LabeledFormula tests
# ---------------------------------------------------------------------------

VALID_RECORD = {
    "formula": IMP_JSON,
    "label": "VALID",
    "proof_trace": PROOF_TRACE_JSON,
    "metrics": METRICS_JSON,
    "pattern_key": PATTERN_KEY_JSON,
}

INVALID_RECORD = {
    "formula": ATOM_JSON,
    "label": "INVALID",
    "countermodel": COUNTERMODEL_JSON,
    "metrics": METRICS_JSON,
    "pattern_key": PATTERN_KEY_JSON,
}

TIMEOUT_RECORD = {
    "formula": BOX_JSON,
    "label": "TIMEOUT",
    "metrics": METRICS_JSON,
    "pattern_key": PATTERN_KEY_JSON,
}


class TestLabeledFormulaValid:
    def test_from_json(self):
        lf = LabeledFormula.from_json(VALID_RECORD)
        assert lf.label == Label.VALID
        assert lf.proof_trace is not None
        assert lf.proof_trace.height == 5
        assert lf.countermodel is None

    def test_round_trip(self):
        lf = LabeledFormula.from_json(VALID_RECORD)
        result = lf.to_json()
        assert result["label"] == "VALID"
        assert "proof_trace" in result
        assert "countermodel" not in result
        # Verify re-parsing gives same data
        lf2 = LabeledFormula.from_json(result)
        assert lf2.label == lf.label
        assert lf2.proof_trace is not None
        assert lf2.proof_trace.height == lf.proof_trace.height


class TestLabeledFormulaInvalid:
    def test_from_json(self):
        lf = LabeledFormula.from_json(INVALID_RECORD)
        assert lf.label == Label.INVALID
        assert lf.countermodel is not None
        assert lf.countermodel.true_atoms == ["p", "r"]
        assert lf.proof_trace is None

    def test_round_trip(self):
        lf = LabeledFormula.from_json(INVALID_RECORD)
        result = lf.to_json()
        assert result["label"] == "INVALID"
        assert "countermodel" in result
        assert "proof_trace" not in result
        lf2 = LabeledFormula.from_json(result)
        assert lf2.label == lf.label
        assert lf2.countermodel is not None


class TestLabeledFormulaTimeout:
    def test_from_json(self):
        lf = LabeledFormula.from_json(TIMEOUT_RECORD)
        assert lf.label == Label.TIMEOUT
        assert lf.proof_trace is None
        assert lf.countermodel is None

    def test_round_trip(self):
        lf = LabeledFormula.from_json(TIMEOUT_RECORD)
        result = lf.to_json()
        assert result["label"] == "TIMEOUT"
        assert "proof_trace" not in result
        assert "countermodel" not in result
