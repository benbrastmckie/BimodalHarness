"""JSONL serialization and deserialization for BimodalHarness training records.

Implements read/write of JSONL files (one JSON object per line) in the format
produced by Bimodal.Automation.DataExport.  Field names use the camelCase
convention of the Lean export; deserialization maps them to snake_case Python.

Public API:
- record_to_jsonl_dict: TrainingRecord -> flat JSON-serializable dict
- jsonl_dict_to_record: flat dict -> TrainingRecord  (handles camelCase mapping)
- write_jsonl: write a list of TrainingRecord to a JSONL file
- read_jsonl: read a JSONL file into a list of TrainingRecord
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from bimodal_harness.schema.constants import SCHEMA_VERSION
from bimodal_harness.schema.records import (
    DifficultyMetrics,
    PatternKey,
    ProofTrace,
    SimpleCountermodel,
    TrainingRecord,
)


def record_to_jsonl_dict(record: TrainingRecord) -> dict[str, Any]:
    """Flatten a TrainingRecord to a JSON-serializable dict for JSONL export.

    The output format uses camelCase field names where they correspond to Lean
    DataExport.lean field names, and snake_case where they are Python-only.

    Parameters
    ----------
    record:
        The training record to serialize.

    Returns
    -------
    dict[str, Any]
        A flat JSON-serializable dict suitable for json.dumps.
    """
    d: dict[str, Any] = {
        # Identity
        "record_id": record.record_id,
        "formula_json": record.formula_json,
        "formula_pretty": record.formula_pretty,
        "label": record.label,
        # Pattern key (camelCase to match Lean PatternKey.toJson)
        "modalDepth": record.pattern_key.modal_depth,
        "temporalDepth": record.pattern_key.temporal_depth,
        "impCount": record.pattern_key.imp_count,
        "complexity": record.pattern_key.complexity,
        "topOperator": record.pattern_key.top_operator,
        # Difficulty metrics
        "atom_count": record.difficulty_metrics.atom_count,
        "decision_time_ms": record.difficulty_metrics.decision_time_ms,
        "search_depth": record.difficulty_metrics.search_depth,
        "difficulty_tier": record.difficulty_metrics.difficulty_tier,
        # Metadata
        "schema_version": record.schema_version,
        "frame_class": record.frame_class,
        "source": record.source,
        "logic_system": record.logic_system,
        # Evidence (may be null)
        "proof_trace": None,
        "countermodel": None,
    }

    if record.proof_trace is not None:
        d["proof_trace"] = record.proof_trace.to_dict()

    if record.countermodel is not None:
        d["countermodel"] = record.countermodel.to_dict()

    return d


def jsonl_dict_to_record(data: dict[str, Any]) -> TrainingRecord:
    """Parse a flat JSONL dict (from DataExport.lean or write_jsonl) into a TrainingRecord.

    Handles both camelCase Lean-exported field names and snake_case Python field names.

    Parameters
    ----------
    data:
        A dict as produced by json.loads on a JSONL line.

    Returns
    -------
    TrainingRecord
        The parsed training record.

    Raises
    ------
    KeyError
        If required fields are missing.
    ValueError
        If field values are out of range or invalid.
    """
    # Pattern key -- supports both camelCase (Lean export) and snake_case (Python)
    modal_depth = data.get("modalDepth", data.get("modal_depth", 0))
    temporal_depth = data.get("temporalDepth", data.get("temporal_depth", 0))
    imp_count = data.get("impCount", data.get("imp_count", 0))
    complexity = data.get("complexity", 1)
    top_operator = data.get("topOperator", data.get("top_operator", "Atom"))

    pattern_key = PatternKey(
        modal_depth=int(modal_depth),
        temporal_depth=int(temporal_depth),
        imp_count=int(imp_count),
        complexity=int(complexity),
        top_operator=str(top_operator),
    )

    # Difficulty metrics
    difficulty_metrics = DifficultyMetrics(
        atom_count=int(data.get("atom_count", 0)),
        modal_depth=int(modal_depth),
        temporal_depth=int(temporal_depth),
        complexity=int(complexity),
        decision_time_ms=int(data.get("decision_time_ms", 0)),
        search_depth=int(data.get("search_depth", 0)),
        difficulty_tier=str(data.get("difficulty_tier", "easy")),
    )

    # Evidence
    proof_trace: ProofTrace | None = None
    raw_proof = data.get("proof_trace")
    if raw_proof is not None:
        proof_trace = ProofTrace.from_dict(raw_proof)

    countermodel: SimpleCountermodel | None = None
    raw_cm = data.get("countermodel")
    if raw_cm is not None:
        countermodel = SimpleCountermodel.from_dict(raw_cm)

    return TrainingRecord(
        record_id=str(data.get("record_id", TrainingRecord.make_id())),
        formula_json=data["formula_json"],
        formula_pretty=str(data.get("formula_pretty", "")),
        label=str(data["label"]),
        pattern_key=pattern_key,
        difficulty_metrics=difficulty_metrics,
        proof_trace=proof_trace,
        countermodel=countermodel,
        schema_version=str(data.get("schema_version", SCHEMA_VERSION)),
        frame_class=str(data.get("frame_class", "Base")),
        source=str(data.get("source", "lean_export")),
        logic_system=str(data.get("logic_system", "TM_BX")),
    )


def write_jsonl(records: list[TrainingRecord], path: Path) -> None:
    """Write a list of TrainingRecord objects to a JSONL file.

    Each record is serialized as one JSON object per line.  The file is
    overwritten if it exists.

    Parameters
    ----------
    records:
        List of training records to write.
    path:
        Destination file path (will be created if it does not exist).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            d = record_to_jsonl_dict(record)
            f.write(json.dumps(d, ensure_ascii=False))
            f.write("\n")


def read_jsonl(path: Path) -> list[TrainingRecord]:
    """Read a JSONL file and parse each line into a TrainingRecord.

    Blank lines and lines starting with '#' are silently skipped.

    Parameters
    ----------
    path:
        Source JSONL file path.

    Returns
    -------
    list[TrainingRecord]
        Parsed training records.

    Raises
    ------
    FileNotFoundError
        If path does not exist.
    json.JSONDecodeError
        If a line is not valid JSON.
    """
    records: list[TrainingRecord] = []
    with path.open("r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError as exc:
                raise json.JSONDecodeError(
                    f"JSONL parse error at line {lineno}: {exc.msg}", exc.doc, exc.pos
                ) from exc
            records.append(jsonl_dict_to_record(data))
    return records
