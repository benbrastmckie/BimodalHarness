"""Data ingestion pipelines for loading proof search datasets.

Provides two API layers:

**Layer 1: LabeledFormula -> TrainingRecord bridge** (data.schema -> schema.records).
Translates the legacy Lean-export format (uppercase labels, integer tiers, etc.)
to the richer ML-training format:

1. label casing: "VALID"/"INVALID" -> "valid"/"invalid"
2. difficulty_tier: int (1-5) -> string ("easy".."very_hard")
3. top_operator: lowercase -> PascalCase
4. record_id: generated via TrainingRecord.make_id() (absent in source)
5. formula_pretty: derived via formula_json_to_pretty() (absent in source)
6. search_depth: derived from proof_trace.height or 0 (absent in source)
7. countermodel format: {true_atoms, false_atoms, formula (str)} -> {true/false_atoms (tuples), formula_json (dict)}

**Layer 2: Lean JSONL dict -> TrainingRecord** (direct adapter for BimodalLogic exports).
Handles all field-name translations between the Lean dataset_generator output
and schema.records.TrainingRecord:

- ``id`` -> ``record_id``  (auto-generated UUID if absent)
- ``formula_ast`` -> ``formula_json``
- ``formula_str`` -> ``formula_pretty``
- ``label``: already lowercase; passed through
- ``pattern_key.*``: camelCase -> PatternKey.from_dict
- ``metrics.*``: camelCase -> DifficultyMetrics.from_dict (updated in Phase 1)
- ``proof_trace``: both formats handled by ProofTrace.from_dict (updated in Phase 1)
- ``countermodel``: Atom-object format -> SimpleCountermodel.from_dict
- ``frame_class``: passthrough (defaults to "Base" if absent)

TIMEOUT records return None and are skipped during ingestion.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from bimodal_harness.data.schema import Label, LabeledFormula, load_jsonl
from bimodal_harness.schema.formula import formula_json_to_pretty
from bimodal_harness.schema.records import (
    DifficultyMetrics,
    PatternKey,
    ProofTrace,
    RuleProfile,
    SimpleCountermodel,
    TrainingRecord,
)

if TYPE_CHECKING:
    pass

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Translation constants
# ---------------------------------------------------------------------------

#: Maps integer difficulty_tier values (1-5) from data.schema to string values
#: expected by schema.records.DifficultyMetrics.
#: Note: tier 1 maps to "easy" (not "trivial") because VALID_DIFFICULTY_TIERS
#: does not include "trivial" -- the Lean dataset_generator does not emit it.
#: Tiers 1 and 2 both collapse to "easy"; tiers 3-5 map to medium/hard/very_hard.
DIFFICULTY_TIER_MAP: dict[int, str] = {
    1: "easy",
    2: "easy",
    3: "medium",
    4: "hard",
    5: "very_hard",
}

#: Maps lowercase top_operator values from data.schema.PatternKey to PascalCase
#: GoalCategory names expected by schema.records.PatternKey.
TOP_OPERATOR_MAP: dict[str, str] = {
    "atom": "Atom",
    "bot": "Bottom",
    "imp": "Implication",
    "box": "Box",
    "untl": "Until",
    "snce": "Since",
}


# ---------------------------------------------------------------------------
# Core translation function
# ---------------------------------------------------------------------------


def labeled_formula_to_training_record(lf: LabeledFormula) -> TrainingRecord | None:
    """Translate a LabeledFormula (Lean-export schema) to a TrainingRecord (ML schema).

    Handles the 7 field-level mismatches between the two schemas. Returns None
    for TIMEOUT records (they lack the evidence fields required for training).

    Parameters
    ----------
    lf:
        A LabeledFormula loaded from BimodalLogic JSONL export.

    Returns
    -------
    TrainingRecord | None
        Translated ML training record, or None if the record is a TIMEOUT.

    Raises
    ------
    KeyError
        If difficulty_tier or top_operator values are not in the known mapping
        tables. This indicates a schema mismatch that requires manual intervention.
    """
    # 1. Skip TIMEOUT records -- they lack proof/countermodel evidence.
    if lf.label == Label.TIMEOUT:
        return None

    # 2. Translate label: uppercase -> lowercase.
    label = lf.label.value.lower()  # "VALID" -> "valid", "INVALID" -> "invalid"

    # 3. Get the formula as a JSON dict (from the FormulaNode).
    formula_json = lf.formula.to_json()

    # 4. Derive formula_pretty from the formula JSON tree.
    formula_pretty = formula_json_to_pretty(formula_json)

    # 5. Translate difficulty_tier: int -> string.
    difficulty_tier_int = lf.metrics.difficulty_tier
    if difficulty_tier_int not in DIFFICULTY_TIER_MAP:
        raise KeyError(
            f"Unknown difficulty_tier value: {difficulty_tier_int!r}. "
            f"Expected one of {sorted(DIFFICULTY_TIER_MAP.keys())}."
        )
    difficulty_tier = DIFFICULTY_TIER_MAP[difficulty_tier_int]

    # 6. Translate top_operator: lowercase -> PascalCase.
    top_operator_raw = lf.pattern_key.top_operator
    if top_operator_raw not in TOP_OPERATOR_MAP:
        raise KeyError(
            f"Unknown top_operator value: {top_operator_raw!r}. "
            f"Expected one of {sorted(TOP_OPERATOR_MAP.keys())}."
        )
    top_operator = TOP_OPERATOR_MAP[top_operator_raw]

    # 7. Build PatternKey (ML schema).
    pattern_key = PatternKey(
        modal_depth=lf.pattern_key.modal_depth,
        temporal_depth=lf.pattern_key.temporal_depth,
        imp_count=lf.pattern_key.imp_count,
        complexity=lf.pattern_key.complexity,
        top_operator=top_operator,
    )

    # 8. Derive search_depth from proof_trace.height if available; default 0.
    search_depth = lf.proof_trace.height if lf.proof_trace is not None else 0

    # 9. Build DifficultyMetrics (ML schema).
    difficulty_metrics = DifficultyMetrics(
        atom_count=lf.metrics.atom_count,
        modal_depth=lf.metrics.modal_depth,
        temporal_depth=lf.metrics.temporal_depth,
        complexity=lf.metrics.complexity,
        decision_time_ms=int(lf.metrics.decision_time_ms),
        search_depth=search_depth,
        difficulty_tier=difficulty_tier,
    )

    # 10. Translate proof_trace if present.
    proof_trace: ProofTrace | None = None
    if lf.proof_trace is not None:
        # data.schema RuleProfile uses different keys (imp_left, etc.) vs
        # schema.records.RuleProfile (axiom_count, etc.).  The two schemas have
        # divergent rule naming -- default ML RuleProfile to all zeros and
        # forward the axiom names (compatible) directly.
        proof_trace = ProofTrace(
            height=lf.proof_trace.height,
            rule_profile=RuleProfile(),  # all-zeros default (see plan risk table)
            axioms_used=tuple(lf.proof_trace.axioms_used),
        )

    # 11. Translate countermodel if present.
    countermodel: SimpleCountermodel | None = None
    if lf.countermodel is not None:
        countermodel = SimpleCountermodel(
            true_atoms=tuple(lf.countermodel.true_atoms),
            false_atoms=tuple(lf.countermodel.false_atoms),
            formula_json=formula_json,  # use the formula dict (not the string)
        )

    # 12. Generate a fresh record_id.
    record_id = TrainingRecord.make_id()

    return TrainingRecord(
        record_id=record_id,
        formula_json=formula_json,
        formula_pretty=formula_pretty,
        label=label,
        pattern_key=pattern_key,
        difficulty_metrics=difficulty_metrics,
        proof_trace=proof_trace,
        countermodel=countermodel,
        frame_class="Base",  # default; no frame class info in source
        source="lean_export",
        logic_system="TM_BX",
    )


# ---------------------------------------------------------------------------
# Pipeline entry points
# ---------------------------------------------------------------------------


def ingest_jsonl(path: Path, *, skip_timeout: bool = True) -> list[TrainingRecord]:
    """Load and translate a JSONL file of LabeledFormula records.

    Reads each line, translates it to a TrainingRecord, and collects results.
    TIMEOUT records are skipped by default.

    Parameters
    ----------
    path:
        Path to a JSONL file exported by BimodalLogic.
    skip_timeout:
        If True (default), TIMEOUT records are silently dropped. If False,
        a ValueError is raised when a TIMEOUT record is encountered.

    Returns
    -------
    list[TrainingRecord]
        Translated training records in file order (TIMEOUT records excluded).

    Raises
    ------
    FileNotFoundError
        If path does not exist.
    ValueError
        If skip_timeout=False and a TIMEOUT record is encountered.
    """
    records: list[TrainingRecord] = []
    skipped = 0
    total = 0

    for lf in load_jsonl(path):
        total += 1
        result = labeled_formula_to_training_record(lf)
        if result is None:
            if not skip_timeout:
                raise ValueError(
                    f"TIMEOUT record encountered in {path} (record {total}). "
                    "Set skip_timeout=True to skip TIMEOUT records."
                )
            skipped += 1
        else:
            records.append(result)

    log.info(
        "ingest_jsonl: %s -> %d records (%d skipped TIMEOUT)",
        path,
        len(records),
        skipped,
    )
    return records


def ingest_directory(
    data_dir: Path,
    *,
    glob: str = "*.jsonl",
    skip_timeout: bool = True,
) -> list[TrainingRecord]:
    """Load and translate all JSONL files in a directory.

    Recursively finds files matching glob pattern, loads each with ingest_jsonl(),
    and concatenates all records into a single list.

    Parameters
    ----------
    data_dir:
        Directory to search for JSONL files.
    glob:
        Glob pattern for file discovery (default: "*.jsonl").
    skip_timeout:
        Passed through to ingest_jsonl().

    Returns
    -------
    list[TrainingRecord]
        All translated records from all matched files, in alphabetical file order.

    Raises
    ------
    FileNotFoundError
        If data_dir does not exist.
    """
    if not data_dir.exists():
        raise FileNotFoundError(f"Directory not found: {data_dir}")

    files = sorted(data_dir.glob(glob))
    all_records: list[TrainingRecord] = []

    for file_path in files:
        file_records = ingest_jsonl(file_path, skip_timeout=skip_timeout)
        all_records.extend(file_records)

    log.info(
        "ingest_directory: %s (%d files) -> %d records total",
        data_dir,
        len(files),
        len(all_records),
    )
    return all_records


# ---------------------------------------------------------------------------
# Parquet cache functions
# ---------------------------------------------------------------------------


def ingest_and_cache(jsonl_dir: Path, cache_path: Path) -> list[TrainingRecord]:
    """Ingest all JSONL files in a directory and write a Parquet cache.

    Loads all JSONL files from jsonl_dir, translates them to TrainingRecords,
    writes the results to cache_path as a Parquet file, and returns the records.

    Cache freshness is not checked here -- the cache is always overwritten.
    Use load_cached() with a freshness check for repeated training runs.

    Parameters
    ----------
    jsonl_dir:
        Directory containing JSONL files exported by BimodalLogic.
    cache_path:
        Destination Parquet file path (created or overwritten).

    Returns
    -------
    list[TrainingRecord]
        All translated records written to cache.
    """
    from bimodal_harness.schema.parquet import records_to_parquet

    records = ingest_directory(jsonl_dir)
    records_to_parquet(records, cache_path)
    log.info(
        "ingest_and_cache: wrote %d records to %s",
        len(records),
        cache_path,
    )
    return records


def load_cached(cache_path: Path) -> list[TrainingRecord]:
    """Load training records from a Parquet cache file.

    Parameters
    ----------
    cache_path:
        Path to a Parquet file written by ingest_and_cache().

    Returns
    -------
    list[TrainingRecord]
        Parsed training records from the cache.

    Raises
    ------
    FileNotFoundError
        If cache_path does not exist.
    """
    from bimodal_harness.schema.parquet import parquet_to_records

    if not cache_path.exists():
        raise FileNotFoundError(f"Cache file not found: {cache_path}")

    records = parquet_to_records(cache_path)
    log.info("load_cached: loaded %d records from %s", len(records), cache_path)
    return records


def is_cache_fresh(jsonl_dir: Path, cache_path: Path, *, glob: str = "*.jsonl") -> bool:
    """Check whether a Parquet cache is up to date with its JSONL source files.

    Compares the modification time of the cache file against the newest JSONL
    file in jsonl_dir. Returns True if the cache is newer than all source files.

    Parameters
    ----------
    jsonl_dir:
        Directory containing the source JSONL files.
    cache_path:
        Path to the Parquet cache file.
    glob:
        Glob pattern for JSONL files (default: "*.jsonl").

    Returns
    -------
    bool
        True if cache_path exists and is newer than all JSONL files in jsonl_dir;
        False otherwise (including if cache_path does not exist).
    """
    if not cache_path.exists():
        return False

    cache_mtime = cache_path.stat().st_mtime
    jsonl_files = list(jsonl_dir.glob(glob))
    if not jsonl_files:
        return True  # No source files -> cache is vacuously fresh

    newest_source_mtime = max(f.stat().st_mtime for f in jsonl_files)
    return cache_mtime > newest_source_mtime
