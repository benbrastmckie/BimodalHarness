"""Tests for JSONL serialization (bimodal_harness.schema.serialization).

Verifies:
- JSONL round-trip: write_jsonl then read_jsonl gives back equivalent records
- record_to_jsonl_dict produces expected keys and camelCase PatternKey fields
- jsonl_dict_to_record handles camelCase Lean-exported field names
- jsonl_dict_to_record handles snake_case Python field names
- Blank lines and comment lines in JSONL are skipped
- Records with proof_trace vs countermodel serialize correctly
"""

from __future__ import annotations

import json
from pathlib import Path

from bimodal_harness.schema.constants import SCHEMA_VERSION
from bimodal_harness.schema.records import (
    DifficultyMetrics,
    PatternKey,
    ProofTrace,
    RuleProfile,
    SimpleCountermodel,
    TrainingRecord,
)
from bimodal_harness.schema.serialization import (
    jsonl_dict_to_record,
    read_jsonl,
    record_to_jsonl_dict,
    write_jsonl,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_valid_record() -> TrainingRecord:
    return TrainingRecord(
        record_id="test-valid-001",
        formula_json={"tag": "imp", "left": {"tag": "atom", "name": "p"}, "right": {"tag": "bot"}},
        formula_pretty="(p → ⊥)",
        label="valid",
        pattern_key=PatternKey(
            modal_depth=0,
            temporal_depth=0,
            imp_count=1,
            complexity=3,
            top_operator="Implication",
        ),
        difficulty_metrics=DifficultyMetrics(
            atom_count=1,
            modal_depth=0,
            temporal_depth=0,
            complexity=3,
            decision_time_ms=15,
            search_depth=2,
            difficulty_tier="easy",
        ),
        proof_trace=ProofTrace(
            height=2,
            rule_profile=RuleProfile(axiom_count=2, mp_count=1),
            axioms_used=("prop_k", "ex_falso"),
        ),
        countermodel=None,
    )


def make_invalid_record() -> TrainingRecord:
    return TrainingRecord(
        record_id="test-invalid-001",
        formula_json={"tag": "atom", "name": "p"},
        formula_pretty="p",
        label="invalid",
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
            search_depth=0,
            difficulty_tier="trivial",
        ),
        proof_trace=None,
        countermodel=SimpleCountermodel(
            true_atoms=("p",),
            false_atoms=(),
            formula_json={"tag": "atom", "name": "p"},
        ),
    )


# ---------------------------------------------------------------------------
# record_to_jsonl_dict tests
# ---------------------------------------------------------------------------


class TestRecordToJsonlDict:
    def test_returns_dict(self):
        rec = make_valid_record()
        d = record_to_jsonl_dict(rec)
        assert isinstance(d, dict)

    def test_label_present(self):
        rec = make_valid_record()
        d = record_to_jsonl_dict(rec)
        assert d["label"] == "valid"

    def test_formula_json_present(self):
        rec = make_valid_record()
        d = record_to_jsonl_dict(rec)
        assert "formula_json" in d
        assert d["formula_json"]["tag"] == "imp"

    def test_pattern_key_camel_case(self):
        rec = make_valid_record()
        d = record_to_jsonl_dict(rec)
        assert "modalDepth" in d
        assert "temporalDepth" in d
        assert "impCount" in d
        assert "topOperator" in d

    def test_proof_trace_for_valid(self):
        rec = make_valid_record()
        d = record_to_jsonl_dict(rec)
        assert d["proof_trace"] is not None
        assert d["countermodel"] is None

    def test_countermodel_for_invalid(self):
        rec = make_invalid_record()
        d = record_to_jsonl_dict(rec)
        assert d["countermodel"] is not None
        assert d["proof_trace"] is None

    def test_schema_version_present(self):
        rec = make_valid_record()
        d = record_to_jsonl_dict(rec)
        assert d["schema_version"] == SCHEMA_VERSION

    def test_dict_is_json_serializable(self):
        rec = make_valid_record()
        d = record_to_jsonl_dict(rec)
        # Should not raise
        json_str = json.dumps(d)
        assert len(json_str) > 0


# ---------------------------------------------------------------------------
# jsonl_dict_to_record tests
# ---------------------------------------------------------------------------


class TestJsonlDictToRecord:
    def test_round_trip_valid(self):
        rec = make_valid_record()
        d = record_to_jsonl_dict(rec)
        rec2 = jsonl_dict_to_record(d)
        assert rec2.label == rec.label
        assert rec2.formula_json == rec.formula_json
        assert rec2.pattern_key == rec.pattern_key
        assert rec2.proof_trace is not None
        assert rec2.proof_trace.height == rec.proof_trace.height
        assert rec2.countermodel is None

    def test_round_trip_invalid(self):
        rec = make_invalid_record()
        d = record_to_jsonl_dict(rec)
        rec2 = jsonl_dict_to_record(d)
        assert rec2.label == rec.label
        assert rec2.countermodel is not None
        assert rec2.countermodel.true_atoms == rec.countermodel.true_atoms
        assert rec2.proof_trace is None

    def test_camel_case_pattern_key_fields(self):
        """Test that camelCase keys from Lean export are handled correctly."""
        data = {
            "record_id": "abc",
            "formula_json": {"tag": "bot"},
            "formula_pretty": "⊥",
            "label": "invalid",
            "modalDepth": 1,
            "temporalDepth": 2,
            "impCount": 3,
            "complexity": 5,
            "topOperator": "Box",
            "atom_count": 0,
            "decision_time_ms": 10,
            "search_depth": 0,
            "difficulty_tier": "easy",
            "proof_trace": None,
            "countermodel": {
                "trueAtoms": [],
                "falseAtoms": [],
                "formula": {"tag": "bot"},
            },
        }
        rec = jsonl_dict_to_record(data)
        assert rec.pattern_key.modal_depth == 1
        assert rec.pattern_key.temporal_depth == 2
        assert rec.pattern_key.imp_count == 3
        assert rec.pattern_key.complexity == 5
        assert rec.pattern_key.top_operator == "Box"

    def test_snake_case_pattern_key_fields(self):
        """Test that snake_case keys from Python export are handled correctly."""
        data = {
            "record_id": "abc",
            "formula_json": {"tag": "bot"},
            "formula_pretty": "⊥",
            "label": "invalid",
            "modal_depth": 2,
            "temporal_depth": 0,
            "imp_count": 1,
            "complexity": 3,
            "top_operator": "Implication",
            "atom_count": 0,
            "decision_time_ms": 10,
            "search_depth": 0,
            "difficulty_tier": "easy",
            "proof_trace": None,
            "countermodel": {
                "trueAtoms": [],
                "falseAtoms": [],
                "formula": {"tag": "bot"},
            },
        }
        rec = jsonl_dict_to_record(data)
        assert rec.pattern_key.modal_depth == 2
        assert rec.pattern_key.imp_count == 1


# ---------------------------------------------------------------------------
# write_jsonl / read_jsonl tests
# ---------------------------------------------------------------------------


class TestJsonlRoundTrip:
    def test_write_and_read_single_record(self, tmp_path: Path):
        rec = make_valid_record()
        path = tmp_path / "test.jsonl"
        write_jsonl([rec], path)
        records = read_jsonl(path)
        assert len(records) == 1
        assert records[0].label == "valid"
        assert records[0].formula_json == rec.formula_json

    def test_write_and_read_multiple_records(self, tmp_path: Path):
        records = [make_valid_record(), make_invalid_record()]
        path = tmp_path / "test.jsonl"
        write_jsonl(records, path)
        loaded = read_jsonl(path)
        assert len(loaded) == 2
        assert loaded[0].label == "valid"
        assert loaded[1].label == "invalid"

    def test_file_is_one_line_per_record(self, tmp_path: Path):
        records = [make_valid_record(), make_invalid_record()]
        path = tmp_path / "test.jsonl"
        write_jsonl(records, path)
        lines = [ln for ln in path.read_text().splitlines() if ln.strip()]
        assert len(lines) == 2

    def test_empty_list_writes_empty_file(self, tmp_path: Path):
        path = tmp_path / "empty.jsonl"
        write_jsonl([], path)
        assert path.exists()
        content = path.read_text().strip()
        assert content == ""

    def test_proof_trace_round_trip(self, tmp_path: Path):
        rec = make_valid_record()
        path = tmp_path / "test.jsonl"
        write_jsonl([rec], path)
        loaded = read_jsonl(path)
        assert loaded[0].proof_trace is not None
        assert loaded[0].proof_trace.height == 2
        assert loaded[0].proof_trace.axioms_used == ("prop_k", "ex_falso")

    def test_countermodel_round_trip(self, tmp_path: Path):
        rec = make_invalid_record()
        path = tmp_path / "test.jsonl"
        write_jsonl([rec], path)
        loaded = read_jsonl(path)
        assert loaded[0].countermodel is not None
        assert loaded[0].countermodel.true_atoms == ("p",)

    def test_creates_parent_directories(self, tmp_path: Path):
        path = tmp_path / "a" / "b" / "c" / "test.jsonl"
        write_jsonl([make_valid_record()], path)
        assert path.exists()

    def test_read_skips_blank_lines(self, tmp_path: Path):
        rec = make_valid_record()
        path = tmp_path / "test.jsonl"
        d = record_to_jsonl_dict(rec)
        path.write_text("\n" + json.dumps(d) + "\n\n")
        loaded = read_jsonl(path)
        assert len(loaded) == 1

    def test_read_skips_comment_lines(self, tmp_path: Path):
        rec = make_valid_record()
        path = tmp_path / "test.jsonl"
        d = record_to_jsonl_dict(rec)
        path.write_text("# This is a comment\n" + json.dumps(d) + "\n")
        loaded = read_jsonl(path)
        assert len(loaded) == 1

    def test_pattern_key_survives_round_trip(self, tmp_path: Path):
        rec = make_valid_record()
        path = tmp_path / "test.jsonl"
        write_jsonl([rec], path)
        loaded = read_jsonl(path)
        assert loaded[0].pattern_key == rec.pattern_key

    def test_schema_version_survives_round_trip(self, tmp_path: Path):
        rec = make_valid_record()
        path = tmp_path / "test.jsonl"
        write_jsonl([rec], path)
        loaded = read_jsonl(path)
        assert loaded[0].schema_version == SCHEMA_VERSION
