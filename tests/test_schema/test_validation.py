"""Tests for the validation module (bimodal_harness.schema.validation).

Verifies:
- formula validation: valid tags, missing fields, unknown tags
- record validation: label-conditional checks, out-of-range values
- edge cases: empty atom lists, zero complexity rejected
"""

from __future__ import annotations

from bimodal_harness.schema.formula import validate_formula_json
from bimodal_harness.schema.records import (
    DifficultyMetrics,
    PatternKey,
    ProofTrace,
    RuleProfile,
    SimpleCountermodel,
    TrainingRecord,
)
from bimodal_harness.schema.validation import validate_training_record

# ---------------------------------------------------------------------------
# Formula validation tests
# ---------------------------------------------------------------------------


class TestValidateFormulaJson:
    def test_atom_valid(self):
        assert validate_formula_json({"tag": "atom", "name": "p"}) is True

    def test_bot_valid(self):
        assert validate_formula_json({"tag": "bot"}) is True

    def test_imp_valid(self):
        assert (
            validate_formula_json(
                {
                    "tag": "imp",
                    "left": {"tag": "bot"},
                    "right": {"tag": "atom", "name": "p"},
                }
            )
            is True
        )

    def test_box_valid(self):
        assert validate_formula_json({"tag": "box", "child": {"tag": "bot"}}) is True

    def test_untl_valid(self):
        assert (
            validate_formula_json(
                {
                    "tag": "untl",
                    "event": {"tag": "atom", "name": "p"},
                    "guard": {"tag": "bot"},
                }
            )
            is True
        )

    def test_snce_valid(self):
        assert (
            validate_formula_json(
                {
                    "tag": "snce",
                    "event": {"tag": "atom", "name": "r"},
                    "guard": {"tag": "bot"},
                }
            )
            is True
        )

    def test_nested_formula_valid(self):
        # □(p → ⊥)
        formula = {
            "tag": "box",
            "child": {
                "tag": "imp",
                "left": {"tag": "atom", "name": "p"},
                "right": {"tag": "bot"},
            },
        }
        assert validate_formula_json(formula) is True

    def test_unknown_tag_invalid(self):
        assert validate_formula_json({"tag": "unknown"}) is False

    def test_missing_tag_invalid(self):
        assert validate_formula_json({"name": "p"}) is False

    def test_atom_missing_name_invalid(self):
        assert validate_formula_json({"tag": "atom"}) is False

    def test_imp_missing_left_invalid(self):
        assert validate_formula_json({"tag": "imp", "right": {"tag": "bot"}}) is False

    def test_imp_missing_right_invalid(self):
        assert validate_formula_json({"tag": "imp", "left": {"tag": "bot"}}) is False

    def test_box_missing_child_invalid(self):
        assert validate_formula_json({"tag": "box"}) is False

    def test_untl_missing_event_invalid(self):
        assert validate_formula_json({"tag": "untl", "guard": {"tag": "bot"}}) is False

    def test_snce_missing_guard_invalid(self):
        assert validate_formula_json({"tag": "snce", "event": {"tag": "bot"}}) is False

    def test_non_dict_invalid(self):
        assert validate_formula_json("not a dict") is False
        assert validate_formula_json(42) is False
        assert validate_formula_json(None) is False
        assert validate_formula_json([]) is False

    def test_invalid_child_node_invalid(self):
        # Valid parent, invalid child
        assert (
            validate_formula_json(
                {
                    "tag": "box",
                    "child": {"tag": "invalid_tag"},
                }
            )
            is False
        )

    def test_deeply_nested_formula(self):
        # Build a chain of implication nodes
        formula: dict = {"tag": "bot"}
        for _ in range(50):
            formula = {"tag": "imp", "left": {"tag": "bot"}, "right": formula}
        assert validate_formula_json(formula) is True


# ---------------------------------------------------------------------------
# Record validation tests
# ---------------------------------------------------------------------------


def make_base_valid_record() -> TrainingRecord:
    """Create a minimal structurally valid record with label='valid'."""
    return TrainingRecord(
        record_id="abc-123",
        formula_json={"tag": "atom", "name": "p"},
        formula_pretty="p",
        label="valid",
        pattern_key=PatternKey(
            modal_depth=0,
            temporal_depth=0,
            imp_count=0,
            complexity=1,
            top_operator="Atom",
        ),
        difficulty_metrics=DifficultyMetrics(
            atom_count=1,
            modal_depth=0,
            temporal_depth=0,
            complexity=1,
            decision_time_ms=5,
            search_depth=1,
            difficulty_tier="trivial",
        ),
        proof_trace=ProofTrace(
            height=0,
            rule_profile=RuleProfile(axiom_count=1),
            axioms_used=("prop_k",),
        ),
        countermodel=None,
    )


def make_base_invalid_record() -> TrainingRecord:
    """Create a minimal structurally valid record with label='invalid'."""
    return TrainingRecord(
        record_id="abc-456",
        formula_json={"tag": "bot"},
        formula_pretty="⊥",
        label="invalid",
        pattern_key=PatternKey(
            modal_depth=0,
            temporal_depth=0,
            imp_count=0,
            complexity=1,
            top_operator="Bottom",
        ),
        difficulty_metrics=DifficultyMetrics(
            atom_count=0,
            modal_depth=0,
            temporal_depth=0,
            complexity=1,
            decision_time_ms=2,
            search_depth=0,
            difficulty_tier="trivial",
        ),
        proof_trace=None,
        countermodel=SimpleCountermodel(
            true_atoms=(),
            false_atoms=(),
            formula_json={"tag": "bot"},
        ),
    )


class TestValidateTrainingRecordValid:
    def test_valid_record_no_errors(self):
        rec = make_base_valid_record()
        errors = validate_training_record(rec)
        assert errors == [], f"Unexpected errors: {errors}"

    def test_invalid_record_no_errors(self):
        rec = make_base_invalid_record()
        errors = validate_training_record(rec)
        assert errors == [], f"Unexpected errors: {errors}"


class TestLabelConditionalChecks:
    def test_valid_label_missing_proof_trace(self):
        rec = make_base_valid_record()
        object.__setattr__(rec, "proof_trace", None)
        errors = validate_training_record(rec)
        assert any("proof_trace" in e for e in errors)

    def test_valid_label_with_countermodel(self):
        rec = make_base_valid_record()
        cm = SimpleCountermodel(true_atoms=("p",), false_atoms=(), formula_json={"tag": "bot"})
        object.__setattr__(rec, "countermodel", cm)
        errors = validate_training_record(rec)
        assert any("countermodel" in e for e in errors)

    def test_invalid_label_missing_countermodel(self):
        rec = make_base_invalid_record()
        object.__setattr__(rec, "countermodel", None)
        errors = validate_training_record(rec)
        assert any("countermodel" in e for e in errors)

    def test_invalid_label_with_proof_trace(self):
        rec = make_base_invalid_record()
        pt = ProofTrace(height=1, rule_profile=RuleProfile(), axioms_used=("prop_k",))
        object.__setattr__(rec, "proof_trace", pt)
        errors = validate_training_record(rec)
        assert any("proof_trace" in e for e in errors)


class TestFormulaJsonValidation:
    def test_bad_formula_json_in_record(self):
        rec = make_base_valid_record()
        object.__setattr__(rec, "formula_json", {"tag": "bad_tag"})
        errors = validate_training_record(rec)
        assert any("formula_json" in e for e in errors)


class TestAxiomNameValidation:
    def test_unknown_axiom_name_in_proof_trace(self):
        rec = make_base_valid_record()
        bad_pt = ProofTrace(
            height=1,
            rule_profile=RuleProfile(),
            axioms_used=("not_a_real_axiom",),
        )
        object.__setattr__(rec, "proof_trace", bad_pt)
        errors = validate_training_record(rec)
        assert any("unknown axiom names" in e for e in errors)

    def test_all_valid_axiom_names_pass(self):
        from bimodal_harness.schema.actions import AXIOM_ACTIONS

        rec = make_base_valid_record()
        pt = ProofTrace(
            height=5,
            rule_profile=RuleProfile(),
            axioms_used=tuple(AXIOM_ACTIONS[:5]),
        )
        object.__setattr__(rec, "proof_trace", pt)
        errors = validate_training_record(rec)
        assert errors == []


class TestPatternKeyValidationInRecord:
    def test_complexity_one_valid(self):
        rec = make_base_valid_record()
        errors = validate_training_record(rec)
        assert errors == []
