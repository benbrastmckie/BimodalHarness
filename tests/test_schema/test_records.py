"""Tests for the record dataclasses (bimodal_harness.schema.records).

Verifies:
- TrainingRecord instantiation with valid data (valid and invalid labels)
- Optional field handling (None proof_trace when invalid, None countermodel when valid)
- PatternKey value range enforcement
- DifficultyMetrics validation
- RuleProfile and ProofTrace serialization
- SimpleCountermodel serialization
"""

from __future__ import annotations

import pytest

from bimodal_harness.schema.constants import SCHEMA_VERSION
from bimodal_harness.schema.records import (
    DifficultyMetrics,
    PatternKey,
    ProofTrace,
    RuleProfile,
    SimpleCountermodel,
    TrainingRecord,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

FORMULA_BOT = {"tag": "bot"}
FORMULA_ATOM_P = {"tag": "atom", "name": "p"}
FORMULA_IMP = {"tag": "imp", "left": FORMULA_ATOM_P, "right": FORMULA_BOT}


def make_pattern_key(**kwargs) -> PatternKey:
    defaults = {
        "modal_depth": 0,
        "temporal_depth": 0,
        "imp_count": 0,
        "complexity": 1,
        "top_operator": "Atom",
    }
    defaults.update(kwargs)
    return PatternKey(**defaults)


def make_difficulty(**kwargs) -> DifficultyMetrics:
    defaults = {
        "atom_count": 1,
        "modal_depth": 0,
        "temporal_depth": 0,
        "complexity": 1,
        "decision_time_ms": 10,
        "search_depth": 1,
        "difficulty_tier": "easy",
    }
    defaults.update(kwargs)
    return DifficultyMetrics(**defaults)


def make_rule_profile(**kwargs) -> RuleProfile:
    return RuleProfile(**kwargs)


def make_proof_trace(axioms: tuple[str, ...] = ("prop_k",)) -> ProofTrace:
    return ProofTrace(
        height=1,
        rule_profile=make_rule_profile(axiom_count=1, mp_count=1),
        axioms_used=axioms,
    )


def make_countermodel() -> SimpleCountermodel:
    return SimpleCountermodel(
        true_atoms=("p",),
        false_atoms=("q",),
        formula_json=FORMULA_ATOM_P,
    )


def make_valid_record(formula_json=None, **kwargs) -> TrainingRecord:
    if formula_json is None:
        formula_json = FORMULA_IMP
    return TrainingRecord(
        record_id="test-id-1",
        formula_json=formula_json,
        formula_pretty="(p → ⊥)",
        label="valid",
        pattern_key=make_pattern_key(imp_count=1, complexity=3),
        difficulty_metrics=make_difficulty(complexity=3),
        proof_trace=make_proof_trace(),
        countermodel=None,
        **kwargs,
    )


def make_invalid_record(formula_json=None, **kwargs) -> TrainingRecord:
    if formula_json is None:
        formula_json = FORMULA_ATOM_P
    return TrainingRecord(
        record_id="test-id-2",
        formula_json=formula_json,
        formula_pretty="p",
        label="invalid",
        pattern_key=make_pattern_key(),
        difficulty_metrics=make_difficulty(),
        proof_trace=None,
        countermodel=make_countermodel(),
        **kwargs,
    )


# ---------------------------------------------------------------------------
# PatternKey tests
# ---------------------------------------------------------------------------


class TestPatternKey:
    def test_valid_pattern_key(self):
        pk = make_pattern_key(modal_depth=2, temporal_depth=1, imp_count=3, complexity=7)
        assert pk.modal_depth == 2
        assert pk.temporal_depth == 1
        assert pk.imp_count == 3
        assert pk.complexity == 7

    def test_minimum_complexity(self):
        pk = make_pattern_key(complexity=1)
        assert pk.complexity == 1

    def test_zero_values_valid(self):
        pk = make_pattern_key(modal_depth=0, temporal_depth=0, imp_count=0)
        assert pk.modal_depth == 0

    def test_complexity_zero_raises(self):
        with pytest.raises(ValueError, match="complexity must be >= 1"):
            make_pattern_key(complexity=0)

    def test_negative_modal_depth_raises(self):
        with pytest.raises(ValueError, match="modal_depth must be >= 0"):
            make_pattern_key(modal_depth=-1)

    def test_negative_temporal_depth_raises(self):
        with pytest.raises(ValueError, match="temporal_depth must be >= 0"):
            make_pattern_key(temporal_depth=-1)

    def test_negative_imp_count_raises(self):
        with pytest.raises(ValueError, match="imp_count must be >= 0"):
            make_pattern_key(imp_count=-1)

    def test_unknown_top_operator_raises(self):
        with pytest.raises(ValueError, match="top_operator must be one of"):
            make_pattern_key(top_operator="UnknownOp")

    def test_all_valid_top_operators(self):
        valid_ops = [
            "Atom",
            "Bottom",
            "Implication",
            "Box",
            "AllPast",
            "AllFuture",
            "Until",
            "Since",
        ]
        for op in valid_ops:
            pk = make_pattern_key(top_operator=op)
            assert pk.top_operator == op

    def test_to_dict_camel_case(self):
        pk = make_pattern_key(
            modal_depth=1, temporal_depth=2, imp_count=3, complexity=5, top_operator="Box"
        )
        d = pk.to_dict()
        assert d["modalDepth"] == 1
        assert d["temporalDepth"] == 2
        assert d["impCount"] == 3
        assert d["complexity"] == 5
        assert d["topOperator"] == "Box"

    def test_from_dict_round_trip(self):
        pk = make_pattern_key(
            modal_depth=1, temporal_depth=2, imp_count=3, complexity=5, top_operator="Box"
        )
        pk2 = PatternKey.from_dict(pk.to_dict())
        assert pk == pk2


# ---------------------------------------------------------------------------
# RuleProfile tests
# ---------------------------------------------------------------------------


class TestRuleProfile:
    def test_default_zero_counts(self):
        rp = RuleProfile()
        assert rp.axiom_count == 0
        assert rp.mp_count == 0
        assert rp.weakening_count == 0

    def test_all_seven_fields(self):
        rp = RuleProfile(
            axiom_count=1,
            assumption_count=2,
            mp_count=3,
            necessitation_count=4,
            temporal_necessitation_count=5,
            temporal_duality_count=6,
            weakening_count=7,
        )
        d = rp.to_dict()
        assert d["axiom"] == 1
        assert d["assumption"] == 2
        assert d["modus_ponens"] == 3
        assert d["necessitation"] == 4
        assert d["temporal_necessitation"] == 5
        assert d["temporal_duality"] == 6
        assert d["weakening"] == 7

    def test_from_dict_round_trip(self):
        rp = RuleProfile(axiom_count=2, mp_count=5)
        rp2 = RuleProfile.from_dict(rp.to_dict())
        assert rp == rp2

    def test_from_dict_with_empty_dict(self):
        rp = RuleProfile.from_dict({})
        assert rp.axiom_count == 0


# ---------------------------------------------------------------------------
# ProofTrace tests
# ---------------------------------------------------------------------------


class TestProofTrace:
    def test_valid_proof_trace(self):
        pt = make_proof_trace(axioms=("modal_t", "prop_k"))
        assert pt.height == 1
        assert pt.axioms_used == ("modal_t", "prop_k")

    def test_negative_height_raises(self):
        with pytest.raises(ValueError, match="height must be >= 0"):
            ProofTrace(
                height=-1,
                rule_profile=RuleProfile(),
                axioms_used=(),
            )

    def test_zero_height_valid(self):
        pt = ProofTrace(height=0, rule_profile=RuleProfile(), axioms_used=("prop_k",))
        assert pt.height == 0

    def test_to_dict_structure(self):
        pt = make_proof_trace()
        d = pt.to_dict()
        assert "height" in d
        assert "rules" in d
        assert "axioms_used" in d
        assert isinstance(d["axioms_used"], list)

    def test_from_dict_round_trip(self):
        pt = make_proof_trace(axioms=("modal_t", "ex_falso"))
        pt2 = ProofTrace.from_dict(pt.to_dict())
        assert pt2.height == pt.height
        assert pt2.axioms_used == pt.axioms_used


# ---------------------------------------------------------------------------
# SimpleCountermodel tests
# ---------------------------------------------------------------------------


class TestSimpleCountermodel:
    def test_basic_countermodel(self):
        cm = make_countermodel()
        assert cm.true_atoms == ("p",)
        assert cm.false_atoms == ("q",)

    def test_empty_atom_lists(self):
        cm = SimpleCountermodel(
            true_atoms=(),
            false_atoms=(),
            formula_json=FORMULA_BOT,
        )
        assert cm.true_atoms == ()
        assert cm.false_atoms == ()

    def test_to_dict_format(self):
        cm = make_countermodel()
        d = cm.to_dict()
        assert "trueAtoms" in d
        assert "falseAtoms" in d
        assert "formula" in d
        assert d["trueAtoms"][0]["base"] == "p"

    def test_from_dict_round_trip(self):
        cm = make_countermodel()
        cm2 = SimpleCountermodel.from_dict(cm.to_dict())
        assert cm2.true_atoms == cm.true_atoms
        assert cm2.false_atoms == cm.false_atoms


# ---------------------------------------------------------------------------
# DifficultyMetrics tests
# ---------------------------------------------------------------------------


class TestDifficultyMetrics:
    def test_valid_metrics(self):
        dm = make_difficulty(difficulty_tier="hard")
        assert dm.difficulty_tier == "hard"

    def test_all_valid_tiers(self):
        for tier in ["easy", "medium", "hard", "very_hard"]:
            dm = make_difficulty(difficulty_tier=tier)
            assert dm.difficulty_tier == tier

    def test_invalid_tier_raises(self):
        with pytest.raises(ValueError, match="difficulty_tier must be one of"):
            make_difficulty(difficulty_tier="impossible")

    def test_to_dict(self):
        dm = make_difficulty(atom_count=3, decision_time_ms=50)
        d = dm.to_dict()
        assert d["atom_count"] == 3
        assert d["decision_time_ms"] == 50


# ---------------------------------------------------------------------------
# TrainingRecord tests
# ---------------------------------------------------------------------------


class TestTrainingRecordValid:
    def test_valid_record_instantiation(self):
        rec = make_valid_record()
        assert rec.label == "valid"
        assert rec.proof_trace is not None
        assert rec.countermodel is None

    def test_schema_version_default(self):
        rec = make_valid_record()
        assert rec.schema_version == SCHEMA_VERSION

    def test_frame_class_default(self):
        rec = make_valid_record()
        assert rec.frame_class == "Base"

    def test_source_default(self):
        rec = make_valid_record()
        assert rec.source == "lean_export"

    def test_logic_system_default(self):
        rec = make_valid_record()
        assert rec.logic_system == "TM_BX"

    def test_dense_frame_class(self):
        rec = make_valid_record(frame_class="Dense")
        assert rec.frame_class == "Dense"

    def test_discrete_frame_class(self):
        rec = make_valid_record(frame_class="Discrete")
        assert rec.frame_class == "Discrete"


class TestTrainingRecordInvalid:
    def test_invalid_record_instantiation(self):
        rec = make_invalid_record()
        assert rec.label == "invalid"
        assert rec.proof_trace is None
        assert rec.countermodel is not None

    def test_countermodel_present(self):
        rec = make_invalid_record()
        assert rec.countermodel.true_atoms == ("p",)


class TestTrainingRecordValidation:
    def test_bad_label_raises(self):
        with pytest.raises(ValueError, match="label must be one of"):
            TrainingRecord(
                record_id="x",
                formula_json=FORMULA_BOT,
                formula_pretty="⊥",
                label="UNKNOWN_BAD_LABEL",  # invalid
                pattern_key=make_pattern_key(),
                difficulty_metrics=make_difficulty(),
                proof_trace=None,
                countermodel=None,
            )

    def test_bad_frame_class_raises(self):
        with pytest.raises(ValueError, match="frame_class must be one of"):
            TrainingRecord(
                record_id="x",
                formula_json=FORMULA_BOT,
                formula_pretty="⊥",
                label="valid",
                pattern_key=make_pattern_key(),
                difficulty_metrics=make_difficulty(),
                proof_trace=make_proof_trace(),
                countermodel=None,
                frame_class="BadClass",
            )

    def test_make_id_produces_uuid(self):
        rid = TrainingRecord.make_id()
        assert len(rid) == 36  # UUID4 format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
        assert rid.count("-") == 4
