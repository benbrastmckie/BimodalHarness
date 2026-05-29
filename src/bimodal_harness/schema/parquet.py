"""Parquet serialization for BimodalHarness training records using PyArrow.

Provides efficient columnar storage of TrainingRecord lists for ML training.
The Parquet layout flattens nested fields:
- formula_json is stored as a JSON string (not nested)
- PatternKey fields become individual int64 columns
- Nullable fields use PyArrow null-aware types

Column layout (matches plan D3 / R7):
  record_id         string
  formula_json      string (JSON-encoded)
  formula_pretty    string
  label             dictionary<string>   ("valid" | "invalid")
  modalDepth        int64
  temporalDepth     int64
  impCount          int64
  complexity        int64
  topOperator       dictionary<string>   (GoalCategory name)
  atom_count        int64
  decision_time_ms  int64
  search_depth      int64
  difficulty_tier   dictionary<string>
  proof_height      int64 (nullable)
  proof_axioms_used string (JSON-encoded list, nullable)
  countermodel_true_atoms   string (JSON-encoded list, nullable)
  countermodel_false_atoms  string (JSON-encoded list, nullable)
  frame_class       dictionary<string>
  schema_version    string
  source            string
  logic_system      string

Parquet file metadata (stored in schema metadata dict):
  schema_version, creation_date, record_count, frame_class_distribution
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from bimodal_harness.schema.records import (
    DifficultyMetrics,
    PatternKey,
    ProofTrace,
    RuleProfile,
    SimpleCountermodel,
    TrainingRecord,
)

# ---------------------------------------------------------------------------
# PyArrow Schema Definition
# ---------------------------------------------------------------------------

PARQUET_SCHEMA: pa.Schema = pa.schema(
    [
        pa.field("record_id", pa.string(), nullable=False),
        pa.field("formula_json", pa.string(), nullable=False),
        pa.field("formula_pretty", pa.string(), nullable=False),
        pa.field("label", pa.dictionary(pa.int8(), pa.string()), nullable=False),
        # PatternKey columns
        pa.field("modalDepth", pa.int64(), nullable=False),
        pa.field("temporalDepth", pa.int64(), nullable=False),
        pa.field("impCount", pa.int64(), nullable=False),
        pa.field("complexity", pa.int64(), nullable=False),
        pa.field("topOperator", pa.dictionary(pa.int8(), pa.string()), nullable=False),
        # DifficultyMetrics columns
        pa.field("atom_count", pa.int64(), nullable=False),
        pa.field("decision_time_ms", pa.int64(), nullable=False),
        pa.field("search_depth", pa.int64(), nullable=False),
        pa.field("difficulty_tier", pa.dictionary(pa.int8(), pa.string()), nullable=False),
        # ProofTrace columns (nullable -- None when label=="invalid")
        pa.field("proof_height", pa.int64(), nullable=True),
        pa.field("proof_axioms_used", pa.string(), nullable=True),
        # Countermodel columns (nullable -- None when label=="valid")
        pa.field("countermodel_true_atoms", pa.string(), nullable=True),
        pa.field("countermodel_false_atoms", pa.string(), nullable=True),
        # Metadata columns
        pa.field("frame_class", pa.dictionary(pa.int8(), pa.string()), nullable=False),
        pa.field("schema_version", pa.string(), nullable=False),
        pa.field("source", pa.string(), nullable=False),
        pa.field("logic_system", pa.string(), nullable=False),
    ]
)
"""PyArrow schema for the Parquet file layout."""


def _record_to_row(record: TrainingRecord) -> dict[str, Any]:
    """Convert a TrainingRecord to a flat dict for building a PyArrow table row."""
    return {
        "record_id": record.record_id,
        "formula_json": json.dumps(record.formula_json, ensure_ascii=False),
        "formula_pretty": record.formula_pretty,
        "label": record.label,
        "modalDepth": record.pattern_key.modal_depth,
        "temporalDepth": record.pattern_key.temporal_depth,
        "impCount": record.pattern_key.imp_count,
        "complexity": record.pattern_key.complexity,
        "topOperator": record.pattern_key.top_operator,
        "atom_count": record.difficulty_metrics.atom_count,
        "decision_time_ms": record.difficulty_metrics.decision_time_ms,
        "search_depth": record.difficulty_metrics.search_depth,
        "difficulty_tier": record.difficulty_metrics.difficulty_tier,
        "proof_height": (record.proof_trace.height if record.proof_trace is not None else None),
        "proof_axioms_used": (
            json.dumps(list(record.proof_trace.axioms_used))
            if record.proof_trace is not None
            else None
        ),
        "countermodel_true_atoms": (
            json.dumps(list(record.countermodel.true_atoms))
            if record.countermodel is not None
            else None
        ),
        "countermodel_false_atoms": (
            json.dumps(list(record.countermodel.false_atoms))
            if record.countermodel is not None
            else None
        ),
        "frame_class": record.frame_class,
        "schema_version": record.schema_version,
        "source": record.source,
        "logic_system": record.logic_system,
    }


def _rows_to_table(rows: list[dict[str, Any]]) -> pa.Table:
    """Build a PyArrow Table from a list of row dicts."""
    if not rows:
        return pa.table(
            {field.name: pa.array([], type=field.type) for field in PARQUET_SCHEMA},
            schema=PARQUET_SCHEMA,
        )

    # Collect column arrays
    columns: dict[str, list[Any]] = {field.name: [] for field in PARQUET_SCHEMA}
    for row in rows:
        for col_name in columns:
            columns[col_name].append(row[col_name])

    # Build typed arrays
    arrays: list[pa.Array] = []
    for field in PARQUET_SCHEMA:
        col_data = columns[field.name]
        arrays.append(pa.array(col_data, type=field.type))

    return pa.table(
        dict(zip([f.name for f in PARQUET_SCHEMA], arrays, strict=True)), schema=PARQUET_SCHEMA
    )


def _build_metadata(records: list[TrainingRecord]) -> dict[bytes, bytes]:
    """Build Parquet file metadata dict from records."""
    from bimodal_harness.schema.constants import SCHEMA_VERSION

    fc_counts = Counter(r.frame_class for r in records)
    return {
        b"schema_version": SCHEMA_VERSION.encode(),
        b"creation_date": datetime.now(UTC).isoformat().encode(),
        b"record_count": str(len(records)).encode(),
        b"frame_class_distribution": json.dumps(dict(fc_counts)).encode(),
    }


def records_to_parquet(records: list[TrainingRecord], path: Path) -> None:
    """Write a list of TrainingRecord objects to a Parquet file.

    The file is overwritten if it exists.  Parquet file footer metadata
    includes schema_version, creation_date, record_count, and
    frame_class_distribution.

    Parameters
    ----------
    records:
        List of training records to write.
    path:
        Destination file path (will be created if it does not exist).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [_record_to_row(r) for r in records]
    table = _rows_to_table(rows)

    # Attach file-level metadata
    meta = _build_metadata(records)
    existing_meta = table.schema.metadata or {}
    combined_meta = {**existing_meta, **meta}
    table = table.replace_schema_metadata(combined_meta)

    pq.write_table(table, path, compression="snappy")


def parquet_to_records(path: Path) -> list[TrainingRecord]:
    """Read a Parquet file and parse its rows into TrainingRecord objects.

    Parameters
    ----------
    path:
        Source Parquet file path.

    Returns
    -------
    list[TrainingRecord]
        Parsed training records.

    Raises
    ------
    FileNotFoundError
        If path does not exist.
    """
    table = pq.read_table(path)
    records: list[TrainingRecord] = []

    # Convert to Python dicts
    rows = table.to_pydict()
    n = table.num_rows

    for i in range(n):
        row = {col: rows[col][i] for col in rows}

        # Parse formula_json back from string
        formula_json = json.loads(row["formula_json"])

        # Parse nullable JSON-encoded list fields
        proof_trace = None
        if row.get("proof_height") is not None:
            axioms_used_raw = row.get("proof_axioms_used") or "[]"
            axioms_used = tuple(json.loads(axioms_used_raw))
            proof_trace = ProofTrace(
                height=int(row["proof_height"]),
                rule_profile=RuleProfile(),
                axioms_used=axioms_used,
            )

        countermodel = None
        if row.get("countermodel_true_atoms") is not None:
            true_atoms = tuple(json.loads(row["countermodel_true_atoms"]))
            false_atoms = tuple(json.loads(row.get("countermodel_false_atoms") or "[]"))
            countermodel = SimpleCountermodel(
                true_atoms=true_atoms,
                false_atoms=false_atoms,
                formula_json=formula_json,
            )

        pattern_key = PatternKey(
            modal_depth=int(row["modalDepth"]),
            temporal_depth=int(row["temporalDepth"]),
            imp_count=int(row["impCount"]),
            complexity=int(row["complexity"]),
            top_operator=str(row["topOperator"]),
        )

        difficulty_metrics = DifficultyMetrics(
            atom_count=int(row["atom_count"]),
            modal_depth=int(row["modalDepth"]),
            temporal_depth=int(row["temporalDepth"]),
            complexity=int(row["complexity"]),
            decision_time_ms=int(row["decision_time_ms"]),
            search_depth=int(row["search_depth"]),
            difficulty_tier=str(row["difficulty_tier"]),
        )

        records.append(
            TrainingRecord(
                record_id=str(row["record_id"]),
                formula_json=formula_json,
                formula_pretty=str(row["formula_pretty"]),
                label=str(row["label"]),
                pattern_key=pattern_key,
                difficulty_metrics=difficulty_metrics,
                proof_trace=proof_trace,
                countermodel=countermodel,
                schema_version=str(row["schema_version"]),
                frame_class=str(row["frame_class"]),
                source=str(row["source"]),
                logic_system=str(row["logic_system"]),
            )
        )

    return records


def read_parquet_metadata(path: Path) -> dict[str, str]:
    """Read the file-level metadata from a Parquet file without loading data.

    Parameters
    ----------
    path:
        Parquet file path.

    Returns
    -------
    dict[str, str]
        Metadata dict with string keys and values (decoded from bytes).
    """
    meta = pq.read_metadata(path)
    result: dict[str, str] = {}
    raw_meta = meta.metadata or {}
    for k, v in raw_meta.items():
        key = k.decode() if isinstance(k, bytes) else str(k)
        val = v.decode() if isinstance(v, bytes) else str(v)
        result[key] = val
    return result
