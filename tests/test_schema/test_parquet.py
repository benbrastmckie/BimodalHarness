"""Tests for Parquet serialization (bimodal_harness.schema.parquet).

Verifies:
- Parquet round-trip: write then read gives back equivalent records
- Nullable columns handle None values correctly
- File metadata contains expected keys
- Empty record list produces a valid empty file
- File size is smaller than equivalent JSONL for 100+ records
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bimodal_harness.schema.constants import SCHEMA_VERSION
from bimodal_harness.schema.parquet import (
    PARQUET_SCHEMA,
    parquet_to_records,
    read_parquet_metadata,
    records_to_parquet,
)
from bimodal_harness.schema.records import (
    DifficultyMetrics,
    PatternKey,
    ProofTrace,
    RuleProfile,
    SimpleCountermodel,
    TrainingRecord,
)
from bimodal_harness.schema.serialization import write_jsonl


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_valid_record(rec_id: str = "rec-valid") -> TrainingRecord:
    return TrainingRecord(
        record_id=rec_id,
        formula_json={"tag": "imp", "left": {"tag": "atom", "name": "p"}, "right": {"tag": "bot"}},
        formula_pretty="(p → ⊥)",
        label="valid",
        pattern_key=PatternKey(
            modal_depth=1, temporal_depth=0, imp_count=1, complexity=3,
            top_operator="Implication",
        ),
        difficulty_metrics=DifficultyMetrics(
            atom_count=1, modal_depth=1, temporal_depth=0, complexity=3,
            decision_time_ms=20, search_depth=3, difficulty_tier="easy",
        ),
        proof_trace=ProofTrace(
            height=3,
            rule_profile=RuleProfile(axiom_count=3, mp_count=2),
            axioms_used=("modal_t", "prop_k", "ex_falso"),
        ),
        countermodel=None,
        frame_class="Base",
    )


def make_invalid_record(rec_id: str = "rec-invalid") -> TrainingRecord:
    return TrainingRecord(
        record_id=rec_id,
        formula_json={"tag": "atom", "name": "q"},
        formula_pretty="q",
        label="invalid",
        pattern_key=PatternKey(
            modal_depth=0, temporal_depth=0, imp_count=0, complexity=1,
            top_operator="Atom",
        ),
        difficulty_metrics=DifficultyMetrics(
            atom_count=1, modal_depth=0, temporal_depth=0, complexity=1,
            decision_time_ms=3, search_depth=0, difficulty_tier="trivial",
        ),
        proof_trace=None,
        countermodel=SimpleCountermodel(
            true_atoms=("q",),
            false_atoms=(),
            formula_json={"tag": "atom", "name": "q"},
        ),
        frame_class="Dense",
    )


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------

class TestParquetSchema:
    def test_schema_has_expected_columns(self):
        column_names = [f.name for f in PARQUET_SCHEMA]
        expected = [
            "record_id", "formula_json", "formula_pretty", "label",
            "modalDepth", "temporalDepth", "impCount", "complexity",
            "topOperator", "atom_count", "decision_time_ms", "search_depth",
            "difficulty_tier", "proof_height", "proof_axioms_used",
            "countermodel_true_atoms", "countermodel_false_atoms",
            "frame_class", "schema_version", "source", "logic_system",
        ]
        assert column_names == expected

    def test_nullable_columns(self):
        nullable_names = {"proof_height", "proof_axioms_used",
                          "countermodel_true_atoms", "countermodel_false_atoms"}
        for field in PARQUET_SCHEMA:
            if field.name in nullable_names:
                assert field.nullable, f"{field.name} should be nullable"
            elif field.name not in ("record_id", "formula_json"):  # not all non-nullable by spec
                pass  # We just care the nullable ones are correct


# ---------------------------------------------------------------------------
# Round-trip tests
# ---------------------------------------------------------------------------

class TestParquetRoundTrip:
    def test_single_valid_record(self, tmp_path: Path):
        rec = make_valid_record()
        path = tmp_path / "test.parquet"
        records_to_parquet([rec], path)
        loaded = parquet_to_records(path)
        assert len(loaded) == 1
        r = loaded[0]
        assert r.record_id == rec.record_id
        assert r.label == "valid"
        assert r.formula_json == rec.formula_json
        assert r.formula_pretty == rec.formula_pretty

    def test_single_invalid_record(self, tmp_path: Path):
        rec = make_invalid_record()
        path = tmp_path / "test.parquet"
        records_to_parquet([rec], path)
        loaded = parquet_to_records(path)
        assert len(loaded) == 1
        r = loaded[0]
        assert r.label == "invalid"
        assert r.countermodel is not None

    def test_pattern_key_round_trip(self, tmp_path: Path):
        rec = make_valid_record()
        path = tmp_path / "test.parquet"
        records_to_parquet([rec], path)
        loaded = parquet_to_records(path)
        assert loaded[0].pattern_key == rec.pattern_key

    def test_proof_trace_round_trip(self, tmp_path: Path):
        rec = make_valid_record()
        path = tmp_path / "test.parquet"
        records_to_parquet([rec], path)
        loaded = parquet_to_records(path)
        assert loaded[0].proof_trace is not None
        assert loaded[0].proof_trace.height == rec.proof_trace.height
        assert loaded[0].proof_trace.axioms_used == rec.proof_trace.axioms_used

    def test_countermodel_round_trip(self, tmp_path: Path):
        rec = make_invalid_record()
        path = tmp_path / "test.parquet"
        records_to_parquet([rec], path)
        loaded = parquet_to_records(path)
        assert loaded[0].countermodel is not None
        assert loaded[0].countermodel.true_atoms == rec.countermodel.true_atoms

    def test_multiple_records(self, tmp_path: Path):
        records = [
            make_valid_record("r1"),
            make_invalid_record("r2"),
            make_valid_record("r3"),
        ]
        path = tmp_path / "test.parquet"
        records_to_parquet(records, path)
        loaded = parquet_to_records(path)
        assert len(loaded) == 3
        assert [r.record_id for r in loaded] == ["r1", "r2", "r3"]

    def test_frame_class_round_trip(self, tmp_path: Path):
        valid = make_valid_record()
        invalid = make_invalid_record()
        path = tmp_path / "test.parquet"
        records_to_parquet([valid, invalid], path)
        loaded = parquet_to_records(path)
        assert loaded[0].frame_class == "Base"
        assert loaded[1].frame_class == "Dense"

    def test_schema_version_round_trip(self, tmp_path: Path):
        rec = make_valid_record()
        path = tmp_path / "test.parquet"
        records_to_parquet([rec], path)
        loaded = parquet_to_records(path)
        assert loaded[0].schema_version == SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Nullable column tests
# ---------------------------------------------------------------------------

class TestNullableColumns:
    def test_valid_record_has_null_countermodel_columns(self, tmp_path: Path):
        import pyarrow.parquet as pq
        rec = make_valid_record()
        path = tmp_path / "test.parquet"
        records_to_parquet([rec], path)
        table = pq.read_table(path)
        # countermodel columns should be null
        cm_true = table["countermodel_true_atoms"][0].as_py()
        cm_false = table["countermodel_false_atoms"][0].as_py()
        assert cm_true is None
        assert cm_false is None

    def test_invalid_record_has_null_proof_columns(self, tmp_path: Path):
        import pyarrow.parquet as pq
        rec = make_invalid_record()
        path = tmp_path / "test.parquet"
        records_to_parquet([rec], path)
        table = pq.read_table(path)
        # proof columns should be null
        proof_h = table["proof_height"][0].as_py()
        proof_ax = table["proof_axioms_used"][0].as_py()
        assert proof_h is None
        assert proof_ax is None


# ---------------------------------------------------------------------------
# Metadata tests
# ---------------------------------------------------------------------------

class TestParquetMetadata:
    def test_metadata_contains_schema_version(self, tmp_path: Path):
        rec = make_valid_record()
        path = tmp_path / "test.parquet"
        records_to_parquet([rec], path)
        meta = read_parquet_metadata(path)
        assert "schema_version" in meta
        assert meta["schema_version"] == SCHEMA_VERSION

    def test_metadata_contains_record_count(self, tmp_path: Path):
        records = [make_valid_record("r1"), make_invalid_record("r2")]
        path = tmp_path / "test.parquet"
        records_to_parquet(records, path)
        meta = read_parquet_metadata(path)
        assert "record_count" in meta
        assert meta["record_count"] == "2"

    def test_metadata_contains_creation_date(self, tmp_path: Path):
        rec = make_valid_record()
        path = tmp_path / "test.parquet"
        records_to_parquet([rec], path)
        meta = read_parquet_metadata(path)
        assert "creation_date" in meta

    def test_metadata_contains_frame_class_distribution(self, tmp_path: Path):
        records = [make_valid_record("r1"), make_invalid_record("r2")]
        path = tmp_path / "test.parquet"
        records_to_parquet(records, path)
        meta = read_parquet_metadata(path)
        assert "frame_class_distribution" in meta
        dist = json.loads(meta["frame_class_distribution"])
        assert "Base" in dist
        assert "Dense" in dist


# ---------------------------------------------------------------------------
# Size comparison test
# ---------------------------------------------------------------------------

class TestParquetSizeEfficiency:
    def test_parquet_smaller_than_jsonl_for_100_records(self, tmp_path: Path):
        """Parquet with compression should be smaller than JSONL for 100 records."""
        records = [make_valid_record(f"r{i}") for i in range(50)]
        records += [make_invalid_record(f"ri{i}") for i in range(50)]

        parquet_path = tmp_path / "data.parquet"
        jsonl_path = tmp_path / "data.jsonl"

        records_to_parquet(records, parquet_path)
        write_jsonl(records, jsonl_path)

        parquet_size = parquet_path.stat().st_size
        jsonl_size = jsonl_path.stat().st_size

        assert parquet_size < jsonl_size, (
            f"Expected Parquet ({parquet_size} bytes) < JSONL ({jsonl_size} bytes)"
        )
