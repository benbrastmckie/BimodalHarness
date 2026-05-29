"""Tests for the Lean-export -> TrainingRecord ingestion adapter (Layer 2).

Covers:
- lean_export_to_training_record(): all 12 field-level mismatches from research
- load_lean_jsonl(): loading the Lean-format JSONL fixture
- filter_timeout_records(): filtering by label
- DifficultyMetrics.from_dict camelCase key translation
- ProofTrace.from_dict: rules_applied list format
- SimpleCountermodel.from_dict: Atom-object format
- PatternKey.from_dict: camelCase format
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bimodal_harness.data.ingestion import (
    filter_timeout_records,
    lean_export_to_training_record,
    load_lean_jsonl,
)
from bimodal_harness.schema.records import TrainingRecord

# Path to the Lean-format JSONL fixture
LEAN_FIXTURE = Path(__file__).parent.parent.parent / "data" / "samples" / "test_lean_export.jsonl"


# ---------------------------------------------------------------------------
# Minimal Lean-format dict helpers
# ---------------------------------------------------------------------------


def _lean_invalid_dict(**overrides) -> dict:
    """Minimal Lean-format invalid record (atom p)."""
    base = {
        "id": "test-001",
        "formula_ast": {"tag": "atom", "name": "p"},
        "formula_str": "p",
        "label": "invalid",
        "frame_class": "Base",
        "proof_trace": None,
        "countermodel": {
            "trueAtoms": [],
            "falseAtoms": [{"base": "p", "fresh_index": None}],
            "formula": {"tag": "atom", "name": "p"},
        },
        "pattern_key": {
            "modalDepth": 0,
            "temporalDepth": 0,
            "impCount": 0,
            "complexity": 1,
            "topOperator": "Atom",
        },
        "metrics": {
            "atomCount": 1,
            "modalDepth": 0,
            "temporalDepth": 0,
            "decisionTimeMs": 5,
            "difficultyTier": "easy",
        },
    }
    base.update(overrides)
    return base


def _lean_valid_dict(**overrides) -> dict:
    """Minimal Lean-format valid record (bot)."""
    base = {
        "id": "test-002",
        "formula_ast": {"tag": "bot"},
        "formula_str": "⊥",
        "label": "valid",
        "frame_class": "Base",
        "proof_trace": {
            "height": 1,
            "axioms_used": ["ex_falso"],
            "rules_applied": ["axiom"],
        },
        "countermodel": None,
        "pattern_key": {
            "modalDepth": 0,
            "temporalDepth": 0,
            "impCount": 0,
            "complexity": 1,
            "topOperator": "Bottom",
        },
        "metrics": {
            "atomCount": 0,
            "modalDepth": 0,
            "temporalDepth": 0,
            "decisionTimeMs": 2,
            "difficultyTier": "easy",
        },
    }
    base.update(overrides)
    return base


def _lean_timeout_dict(**overrides) -> dict:
    """Minimal Lean-format timeout record."""
    base = {
        "id": "test-003",
        "formula_ast": {"tag": "bot"},
        "formula_str": "⊥",
        "label": "timeout",
        "frame_class": "Base",
        "proof_trace": None,
        "countermodel": None,
        "pattern_key": {
            "modalDepth": 0,
            "temporalDepth": 0,
            "impCount": 0,
            "complexity": 1,
            "topOperator": "Bottom",
        },
        "metrics": {
            "atomCount": 0,
            "modalDepth": 0,
            "temporalDepth": 0,
            "decisionTimeMs": 5000,
            "difficultyTier": "hard",
        },
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# lean_export_to_training_record: field-name translation tests
# ---------------------------------------------------------------------------


class TestLeanExportFieldTranslation:
    """Test all 12 field-level mismatches from the research report."""

    # Mismatch 1: id -> record_id
    def test_id_mapped_to_record_id(self):
        data = _lean_invalid_dict()
        rec = lean_export_to_training_record(data)
        assert rec.record_id == "test-001"

    def test_missing_id_generates_uuid(self):
        import uuid
        data = _lean_invalid_dict()
        del data["id"]
        rec = lean_export_to_training_record(data)
        assert len(rec.record_id) == 36
        uuid.UUID(rec.record_id)  # raises if not valid UUID

    # Mismatch 2: formula_ast -> formula_json
    def test_formula_ast_mapped_to_formula_json(self):
        data = _lean_invalid_dict()
        rec = lean_export_to_training_record(data)
        assert rec.formula_json == {"tag": "atom", "name": "p"}

    # Mismatch 3: formula_str -> formula_pretty
    def test_formula_str_mapped_to_formula_pretty(self):
        data = _lean_invalid_dict()
        rec = lean_export_to_training_record(data)
        assert rec.formula_pretty == "p"

    # Mismatch 4: label lowercase passthrough
    def test_label_invalid_passthrough(self):
        data = _lean_invalid_dict()
        rec = lean_export_to_training_record(data)
        assert rec.label == "invalid"

    def test_label_valid_passthrough(self):
        data = _lean_valid_dict()
        rec = lean_export_to_training_record(data)
        assert rec.label == "valid"

    def test_label_timeout_passthrough(self):
        data = _lean_timeout_dict()
        rec = lean_export_to_training_record(data)
        assert rec.label == "timeout"

    # Mismatch 5: PatternKey camelCase keys
    def test_pattern_key_camel_case_modal_depth(self):
        data = _lean_invalid_dict()
        data["pattern_key"]["modalDepth"] = 2
        rec = lean_export_to_training_record(data)
        assert rec.pattern_key.modal_depth == 2

    def test_pattern_key_camel_case_temporal_depth(self):
        data = _lean_invalid_dict()
        data["pattern_key"]["temporalDepth"] = 1
        rec = lean_export_to_training_record(data)
        assert rec.pattern_key.temporal_depth == 1

    def test_pattern_key_camel_case_imp_count(self):
        data = _lean_invalid_dict()
        data["pattern_key"]["impCount"] = 3
        rec = lean_export_to_training_record(data)
        assert rec.pattern_key.imp_count == 3

    def test_pattern_key_top_operator_pascal_case(self):
        data = _lean_invalid_dict()
        rec = lean_export_to_training_record(data)
        assert rec.pattern_key.top_operator == "Atom"

    # Mismatch 6: DifficultyMetrics camelCase keys
    def test_metrics_atom_count_camel_case(self):
        data = _lean_invalid_dict()
        data["metrics"]["atomCount"] = 3
        rec = lean_export_to_training_record(data)
        assert rec.difficulty_metrics.atom_count == 3

    def test_metrics_modal_depth_camel_case(self):
        data = _lean_invalid_dict()
        data["metrics"]["modalDepth"] = 1
        rec = lean_export_to_training_record(data)
        assert rec.difficulty_metrics.modal_depth == 1

    def test_metrics_decision_time_ms_camel_case(self):
        data = _lean_invalid_dict()
        data["metrics"]["decisionTimeMs"] = 42
        rec = lean_export_to_training_record(data)
        assert rec.difficulty_metrics.decision_time_ms == 42

    def test_metrics_difficulty_tier_string(self):
        data = _lean_invalid_dict()
        rec = lean_export_to_training_record(data)
        assert rec.difficulty_metrics.difficulty_tier == "easy"

    def test_metrics_search_depth_defaults_zero(self):
        """search_depth has no Lean counterpart; defaults to 0."""
        data = _lean_invalid_dict()
        rec = lean_export_to_training_record(data)
        assert rec.difficulty_metrics.search_depth == 0

    # Mismatch 7: ProofTrace rules_applied as list of strings
    def test_proof_trace_rules_applied_list(self):
        data = _lean_valid_dict()
        data["proof_trace"]["rules_applied"] = ["axiom", "modus_ponens", "axiom"]
        rec = lean_export_to_training_record(data)
        assert rec.proof_trace is not None
        assert rec.proof_trace.rule_profile.axiom_count == 2
        assert rec.proof_trace.rule_profile.mp_count == 1

    def test_proof_trace_height_preserved(self):
        data = _lean_valid_dict()
        rec = lean_export_to_training_record(data)
        assert rec.proof_trace is not None
        assert rec.proof_trace.height == 1

    def test_proof_trace_axioms_used_preserved(self):
        data = _lean_valid_dict()
        rec = lean_export_to_training_record(data)
        assert rec.proof_trace is not None
        assert rec.proof_trace.axioms_used == ("ex_falso",)

    def test_proof_trace_none_for_invalid(self):
        data = _lean_invalid_dict()
        rec = lean_export_to_training_record(data)
        assert rec.proof_trace is None

    # Mismatch 8: SimpleCountermodel trueAtoms/falseAtoms as Atom objects
    def test_countermodel_atom_objects(self):
        data = _lean_invalid_dict()
        data["countermodel"]["trueAtoms"] = [{"base": "r", "fresh_index": None}]
        rec = lean_export_to_training_record(data)
        assert rec.countermodel is not None
        assert rec.countermodel.true_atoms == ("r",)

    def test_countermodel_false_atoms(self):
        data = _lean_invalid_dict()
        rec = lean_export_to_training_record(data)
        assert rec.countermodel is not None
        assert rec.countermodel.false_atoms == ("p",)

    def test_countermodel_none_for_valid(self):
        data = _lean_valid_dict()
        rec = lean_export_to_training_record(data)
        assert rec.countermodel is None

    # Mismatch 9: frame_class passthrough
    def test_frame_class_passthrough(self):
        data = _lean_invalid_dict()
        rec = lean_export_to_training_record(data)
        assert rec.frame_class == "Base"

    def test_frame_class_dense(self):
        data = _lean_invalid_dict()
        data["frame_class"] = "Dense"
        rec = lean_export_to_training_record(data)
        assert rec.frame_class == "Dense"

    def test_frame_class_defaults_base(self):
        data = _lean_invalid_dict()
        del data["frame_class"]
        rec = lean_export_to_training_record(data)
        assert rec.frame_class == "Base"

    # Mismatch 10-12: source and logic_system always set
    def test_source_always_lean_export(self):
        data = _lean_invalid_dict()
        rec = lean_export_to_training_record(data)
        assert rec.source == "lean_export"

    def test_logic_system_always_tm_bx(self):
        data = _lean_invalid_dict()
        rec = lean_export_to_training_record(data)
        assert rec.logic_system == "TM_BX"

    def test_result_is_training_record(self):
        data = _lean_invalid_dict()
        rec = lean_export_to_training_record(data)
        assert isinstance(rec, TrainingRecord)


# ---------------------------------------------------------------------------
# Box formula: Lean emits only 'child', no 'event'
# ---------------------------------------------------------------------------


class TestBoxFormulaFormat:
    """Box in Lean format: only 'child' field, no 'event'."""

    def test_box_with_child_only(self):
        data = _lean_invalid_dict()
        data["formula_ast"] = {"tag": "box", "child": {"tag": "atom", "name": "p"}}
        data["pattern_key"]["topOperator"] = "Box"
        data["pattern_key"]["modalDepth"] = 1
        rec = lean_export_to_training_record(data)
        assert rec.formula_json == {"tag": "box", "child": {"tag": "atom", "name": "p"}}

    def test_box_pretty_printed(self):
        data = _lean_invalid_dict()
        data["formula_ast"] = {"tag": "box", "child": {"tag": "atom", "name": "p"}}
        data["formula_str"] = "□p"
        data["pattern_key"]["topOperator"] = "Box"
        rec = lean_export_to_training_record(data)
        assert rec.formula_pretty == "□p"


# ---------------------------------------------------------------------------
# All 6 formula tags
# ---------------------------------------------------------------------------


class TestAllFormulaTags:
    def test_atom_tag(self):
        data = _lean_invalid_dict()
        rec = lean_export_to_training_record(data)
        assert rec.formula_json["tag"] == "atom"

    def test_bot_tag(self):
        data = _lean_valid_dict()
        rec = lean_export_to_training_record(data)
        assert rec.formula_json["tag"] == "bot"

    def test_imp_tag(self):
        data = _lean_invalid_dict()
        data["formula_ast"] = {
            "tag": "imp",
            "left": {"tag": "atom", "name": "p"},
            "right": {"tag": "atom", "name": "q"},
        }
        data["pattern_key"]["topOperator"] = "Implication"
        rec = lean_export_to_training_record(data)
        assert rec.formula_json["tag"] == "imp"

    def test_box_tag(self):
        data = _lean_invalid_dict()
        data["formula_ast"] = {"tag": "box", "child": {"tag": "atom", "name": "p"}}
        data["pattern_key"]["topOperator"] = "Box"
        rec = lean_export_to_training_record(data)
        assert rec.formula_json["tag"] == "box"

    def test_untl_tag(self):
        data = _lean_invalid_dict()
        data["formula_ast"] = {
            "tag": "untl",
            "event": {"tag": "atom", "name": "p"},
            "guard": {"tag": "atom", "name": "q"},
        }
        data["pattern_key"]["topOperator"] = "Until"
        rec = lean_export_to_training_record(data)
        assert rec.formula_json["tag"] == "untl"

    def test_snce_tag(self):
        data = _lean_invalid_dict()
        data["formula_ast"] = {
            "tag": "snce",
            "event": {"tag": "atom", "name": "r"},
            "guard": {"tag": "atom", "name": "p"},
        }
        data["pattern_key"]["topOperator"] = "Since"
        rec = lean_export_to_training_record(data)
        assert rec.formula_json["tag"] == "snce"


# ---------------------------------------------------------------------------
# Difficulty tier values
# ---------------------------------------------------------------------------


class TestDifficultyTierMapping:
    @pytest.mark.parametrize("tier", ["easy", "medium", "hard", "very_hard"])
    def test_valid_string_tiers(self, tier: str):
        data = _lean_invalid_dict()
        data["metrics"]["difficultyTier"] = tier
        rec = lean_export_to_training_record(data)
        assert rec.difficulty_metrics.difficulty_tier == tier

    def test_no_trivial_tier(self):
        """Lean does not emit 'trivial' -- it should not be accepted."""
        from bimodal_harness.schema.constants import VALID_DIFFICULTY_TIERS

        assert "trivial" not in VALID_DIFFICULTY_TIERS


# ---------------------------------------------------------------------------
# load_lean_jsonl fixture tests
# ---------------------------------------------------------------------------


class TestLoadLeanJsonl:
    def test_fixture_file_exists(self):
        assert LEAN_FIXTURE.exists(), f"Lean fixture not found at {LEAN_FIXTURE}"

    def test_loads_all_non_timeout_records(self):
        records = load_lean_jsonl(LEAN_FIXTURE)
        assert len(records) == 7  # 8 total, 1 timeout skipped

    def test_all_records_are_training_records(self):
        records = load_lean_jsonl(LEAN_FIXTURE)
        assert all(isinstance(r, TrainingRecord) for r in records)

    def test_no_timeout_labels_when_skip_true(self):
        records = load_lean_jsonl(LEAN_FIXTURE, skip_timeout=True)
        assert all(r.label != "timeout" for r in records)

    def test_includes_timeout_when_skip_false(self):
        records = load_lean_jsonl(LEAN_FIXTURE, skip_timeout=False)
        timeout_recs = [r for r in records if r.label == "timeout"]
        assert len(timeout_recs) == 1

    def test_all_labels_present_when_not_skipping(self):
        records = load_lean_jsonl(LEAN_FIXTURE, skip_timeout=False)
        labels = {r.label for r in records}
        assert "valid" in labels
        assert "invalid" in labels
        assert "timeout" in labels

    def test_file_not_found_raises(self):
        with pytest.raises(FileNotFoundError):
            load_lean_jsonl(Path("/nonexistent/file.jsonl"))

    def test_valid_records_have_proof_trace(self):
        records = load_lean_jsonl(LEAN_FIXTURE)
        for rec in records:
            if rec.label == "valid":
                assert rec.proof_trace is not None

    def test_invalid_records_have_countermodel(self):
        records = load_lean_jsonl(LEAN_FIXTURE)
        for rec in records:
            if rec.label == "invalid":
                assert rec.countermodel is not None

    def test_box_record_loads_correctly(self):
        records = load_lean_jsonl(LEAN_FIXTURE)
        box_recs = [r for r in records if r.formula_json.get("tag") == "box"]
        assert len(box_recs) == 1
        box = box_recs[0]
        assert box.pattern_key.top_operator == "Box"
        assert "child" in box.formula_json
        assert "event" not in box.formula_json  # Lean emits only 'child' for box

    def test_id_field_used_as_record_id(self):
        records = load_lean_jsonl(LEAN_FIXTURE)
        # All records in fixture have id fields
        assert all(r.record_id.startswith("bmlogic-") for r in records)

    def test_frame_class_passthrough(self):
        records = load_lean_jsonl(LEAN_FIXTURE)
        assert all(r.frame_class == "Base" for r in records)

    def test_source_is_lean_export(self):
        records = load_lean_jsonl(LEAN_FIXTURE)
        assert all(r.source == "lean_export" for r in records)

    def test_proof_trace_rules_applied_list(self):
        """Verify rules_applied list is converted to RuleProfile correctly."""
        records = load_lean_jsonl(LEAN_FIXTURE)
        valid_recs = [r for r in records if r.label == "valid"]
        for rec in valid_recs:
            assert rec.proof_trace is not None
            # axiom_count should be >= 1 for axiom rule
            assert rec.proof_trace.rule_profile.axiom_count >= 1

    def test_countermodel_atom_objects(self):
        """Verify trueAtoms/falseAtoms Atom-object format is handled."""
        records = load_lean_jsonl(LEAN_FIXTURE)
        invalid_recs = [r for r in records if r.label == "invalid"]
        for rec in invalid_recs:
            assert rec.countermodel is not None
            # Atoms should be strings (base names), not dicts
            for atom in rec.countermodel.true_atoms:
                assert isinstance(atom, str)
            for atom in rec.countermodel.false_atoms:
                assert isinstance(atom, str)


# ---------------------------------------------------------------------------
# filter_timeout_records
# ---------------------------------------------------------------------------


class TestFilterTimeoutRecords:
    def test_filters_timeout_records(self):
        records = load_lean_jsonl(LEAN_FIXTURE, skip_timeout=False)
        filtered = filter_timeout_records(records)
        assert all(r.label != "timeout" for r in filtered)

    def test_count_decreases(self):
        records = load_lean_jsonl(LEAN_FIXTURE, skip_timeout=False)
        filtered = filter_timeout_records(records)
        assert len(filtered) < len(records)

    def test_no_change_when_no_timeouts(self):
        records = load_lean_jsonl(LEAN_FIXTURE, skip_timeout=True)
        filtered = filter_timeout_records(records)
        assert len(filtered) == len(records)

    def test_empty_list_returns_empty(self):
        assert filter_timeout_records([]) == []
