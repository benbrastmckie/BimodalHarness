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

**Layer 3: Proof step JSONL -> ProofStepRecord** (for supervised training data).
Loads step-level proof data emitted by the ``lake exe proof_extractor`` executable
(or any conforming JSONL producer) and returns a list of ``ProofStepRecord`` objects.
Validates action_index consistency against ``step_to_action_index`` and attaches
frame_class_mask metadata.  See ``load_proof_steps`` for details.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from bimodal_harness.data.schema import Label, LabeledFormula, load_jsonl
from bimodal_harness.schema.actions import FRAME_CLASS_MASKS, RULE_ACTIONS, step_to_action_index
from bimodal_harness.schema.formula import formula_json_to_pretty
from bimodal_harness.schema.records import (
    DifficultyMetrics,
    PatternKey,
    ProofStepRecord,
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


# ---------------------------------------------------------------------------
# Layer 2: Lean JSONL dict -> TrainingRecord (direct Lean export adapter)
# ---------------------------------------------------------------------------


def lean_export_to_training_record(data: dict) -> TrainingRecord:
    """Translate a raw Lean-exported JSONL dict to a ``TrainingRecord``.

    This is the canonical adapter for BimodalLogic's ``lake exe dataset_generator``
    output.  It handles all 12 field-level mismatches identified in the research
    report between the Lean JSONL format and ``schema.records.TrainingRecord``.

    Field-name translations performed:

    - ``id``           -> ``record_id``  (auto-generated UUID if absent)
    - ``formula_ast``  -> ``formula_json``  (also accepts ``formula_json``)
    - ``formula_str``  -> ``formula_pretty``  (also accepts ``formula_pretty``)
    - ``label``        -> ``label``  (passthrough; already lowercase in Lean)
    - ``pattern_key``  -> ``PatternKey.from_dict``  (camelCase keys)
    - ``metrics``      -> ``DifficultyMetrics.from_dict``  (camelCase keys)
    - ``proof_trace``  -> ``ProofTrace.from_dict``  (both ``rules`` dict and ``rules_applied`` list)
    - ``countermodel`` -> ``SimpleCountermodel.from_dict``  (Atom-object format)
    - ``frame_class``  -> ``frame_class``  (passthrough; defaults to ``"Base"`` if absent)

    Parameters
    ----------
    data:
        A Python dict decoded from a single JSONL line written by
        ``lake exe dataset_generator``.

    Returns
    -------
    TrainingRecord
        Fully populated training record.
    """
    import uuid as _uuid  # local import to avoid module-level dependency

    record_id = data.get("id") or str(_uuid.uuid4())
    formula_json = data.get("formula_ast", data.get("formula_json", {}))
    formula_pretty = data.get("formula_str", data.get("formula_pretty", ""))
    label = str(data.get("label", "")).lower()
    frame_class = str(data.get("frame_class", "Base"))

    pattern_key = PatternKey.from_dict(data["pattern_key"])
    difficulty_metrics = DifficultyMetrics.from_dict(data.get("metrics", {}))

    proof_trace: ProofTrace | None = None
    if data.get("proof_trace") is not None:
        proof_trace = ProofTrace.from_dict(data["proof_trace"])

    countermodel: SimpleCountermodel | None = None
    if data.get("countermodel") is not None:
        countermodel = SimpleCountermodel.from_dict(data["countermodel"])

    return TrainingRecord(
        record_id=record_id,
        formula_json=formula_json,
        formula_pretty=formula_pretty,
        label=label,
        pattern_key=pattern_key,
        difficulty_metrics=difficulty_metrics,
        proof_trace=proof_trace,
        countermodel=countermodel,
        frame_class=frame_class,
        source="lean_export",
        logic_system="TM_BX",
    )


def load_lean_jsonl(
    path: Path,
    *,
    skip_timeout: bool = True,
) -> list[TrainingRecord]:
    """Load a Lean-exported JSONL file directly into ``TrainingRecord`` objects.

    Each line must be a JSON object matching the ``lake exe dataset_generator``
    output format.  Uses ``lean_export_to_training_record`` for field translation.

    Unlike ``ingest_jsonl`` (which bridges via the legacy ``data.schema`` types),
    this function operates directly on the raw Lean JSONL format, handling
    camelCase keys and other Lean-specific format differences natively.

    Parameters
    ----------
    path:
        Path to a JSONL file produced by ``lake exe dataset_generator``.
    skip_timeout:
        If ``True`` (default), records with label ``"timeout"`` are silently
        dropped.  If ``False``, all records are returned (note that
        ``TrainingRecord`` now accepts ``"timeout"`` as a valid label per
        Phase 1 changes).

    Returns
    -------
    list[TrainingRecord]
        Translated records in file order.

    Raises
    ------
    FileNotFoundError
        If ``path`` does not exist.
    """
    import json as _json  # local import to keep module-level imports minimal

    if not path.exists():
        raise FileNotFoundError(f"JSONL file not found: {path}")

    records: list[TrainingRecord] = []
    with path.open("r", encoding="utf-8") as fh:
        for _line_no, line in enumerate(fh, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            data = _json.loads(stripped)
            rec = lean_export_to_training_record(data)
            if skip_timeout and rec.label == "timeout":
                continue
            records.append(rec)

    log.info("load_lean_jsonl: %s -> %d records", path, len(records))
    return records


def filter_timeout_records(records: list[TrainingRecord]) -> list[TrainingRecord]:
    """Return a copy of ``records`` with all ``"timeout"`` label entries removed.

    Convenience utility for post-ingest filtering when records were loaded
    with ``skip_timeout=False``.

    Parameters
    ----------
    records:
        List of ``TrainingRecord`` objects potentially including timeouts.

    Returns
    -------
    list[TrainingRecord]
        New list with all ``label == "timeout"`` records excluded.
    """
    return [r for r in records if r.label != "timeout"]


# ---------------------------------------------------------------------------
# Layer 3: Proof step JSONL -> ProofStepRecord
# ---------------------------------------------------------------------------


def load_proof_steps(
    path: "Path",
    *,
    validate_action_index: bool = True,
) -> list[ProofStepRecord]:
    """Load a proof step JSONL file and return a list of ProofStepRecord objects.

    Each line in the file must be a JSON object whose fields match the
    ``ProofStepRecord`` schema (as emitted by ``lake exe proof_extractor`` or
    any conforming producer).  Records are deserialized via
    ``ProofStepRecord.from_dict``.

    When ``validate_action_index=True`` (default), each record's
    ``action_index`` field is cross-checked against ``step_to_action_index``
    to ensure Lean-side and Python-side action mappings agree.  A mismatch
    raises ``ValueError``.

    Parameters
    ----------
    path:
        Path to a JSONL file produced by ``lake exe proof_extractor``.
    validate_action_index:
        If True (default), validate every record's ``action_index`` against
        ``step_to_action_index(record.rule, record.axiom_name)``.

    Returns
    -------
    list[ProofStepRecord]
        Deserialized and validated proof step records in file order.

    Raises
    ------
    FileNotFoundError
        If ``path`` does not exist.
    ValueError
        If ``validate_action_index=True`` and a record's ``action_index``
        does not match the expected value from ``step_to_action_index``.
    json.JSONDecodeError
        If a line cannot be parsed as JSON.
    """
    import json as _json

    if not path.exists():
        raise FileNotFoundError(f"Proof step JSONL file not found: {path}")

    records: list[ProofStepRecord] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            data = _json.loads(stripped)
            record = ProofStepRecord.from_dict(data)

            if validate_action_index:
                expected_idx = step_to_action_index(record.rule, record.axiom_name)
                if record.action_index != expected_idx:
                    raise ValueError(
                        f"Line {line_no}: action_index mismatch for step {record.step_id!r}. "
                        f"Got action_index={record.action_index}, but "
                        f"step_to_action_index({record.rule!r}, {record.axiom_name!r}) "
                        f"= {expected_idx}."
                    )

            records.append(record)

    log.info("load_proof_steps: %s -> %d records", path, len(records))
    return records


def get_frame_class_mask(record: ProofStepRecord) -> list[bool]:
    """Return the frame-class boolean mask for a ProofStepRecord.

    Looks up the appropriate mask from FRAME_CLASS_MASKS using the record's
    ``frame_class`` field.

    Parameters
    ----------
    record:
        A ProofStepRecord with a valid ``frame_class`` field.

    Returns
    -------
    list[bool]
        Boolean mask of length 49 (one entry per action in ALL_ACTIONS).
        True for actions valid in ``record.frame_class``, False otherwise.

    Raises
    ------
    KeyError
        If ``record.frame_class`` is not in FRAME_CLASS_MASKS.
    """
    return FRAME_CLASS_MASKS[record.frame_class]


def proof_step_statistics(records: list[ProofStepRecord]) -> dict:
    """Compute and return summary statistics for a list of ProofStepRecord objects.

    Computes:
    - Total step count
    - Number of distinct theorems
    - Depth distribution (min, max, mean)
    - Rule distribution (count per rule name)
    - Axiom distribution (count per axiom name, when rule == "axiom")
    - Action index coverage (number of distinct action indices)

    Parameters
    ----------
    records:
        List of ProofStepRecord objects (may be empty).

    Returns
    -------
    dict
        Statistics dictionary with keys: ``total_steps``, ``theorem_count``,
        ``depth_min``, ``depth_max``, ``depth_mean``, ``rule_distribution``,
        ``axiom_distribution``, ``action_index_coverage``.
    """
    if not records:
        return {
            "total_steps": 0,
            "theorem_count": 0,
            "depth_min": None,
            "depth_max": None,
            "depth_mean": None,
            "rule_distribution": {},
            "axiom_distribution": {},
            "action_index_coverage": 0,
        }

    depths = [r.depth for r in records]
    theorems = set(r.theorem_name for r in records)

    rule_dist: dict[str, int] = {}
    for r in records:
        rule_dist[r.rule] = rule_dist.get(r.rule, 0) + 1

    axiom_dist: dict[str, int] = {}
    for r in records:
        if r.rule == "axiom" and r.axiom_name is not None:
            axiom_dist[r.axiom_name] = axiom_dist.get(r.axiom_name, 0) + 1

    action_indices = set(r.action_index for r in records)

    return {
        "total_steps": len(records),
        "theorem_count": len(theorems),
        "depth_min": min(depths),
        "depth_max": max(depths),
        "depth_mean": sum(depths) / len(depths),
        "rule_distribution": dict(sorted(rule_dist.items())),
        "axiom_distribution": dict(sorted(axiom_dist.items())),
        "action_index_coverage": len(action_indices),
    }


def print_proof_step_statistics(records: list[ProofStepRecord]) -> None:
    """Print human-readable statistics for a list of ProofStepRecord objects.

    Prints to stdout: theorem count, total steps, depth distribution,
    rule distribution, axiom distribution, and action index coverage.

    Parameters
    ----------
    records:
        List of ProofStepRecord objects.
    """
    stats = proof_step_statistics(records)
    print(f"Proof Step Statistics")
    print(f"=====================")
    print(f"Total steps:            {stats['total_steps']}")
    print(f"Distinct theorems:      {stats['theorem_count']}")
    if stats["depth_min"] is not None:
        print(
            f"Depth (min/max/mean):   "
            f"{stats['depth_min']} / {stats['depth_max']} / "
            f"{stats['depth_mean']:.2f}"
        )
    print(f"Action index coverage:  {stats['action_index_coverage']} / 49")
    print()
    print("Rule distribution:")
    for rule, count in stats["rule_distribution"].items():
        print(f"  {rule:<30} {count}")
    if stats["axiom_distribution"]:
        print()
        print("Axiom distribution (top 10 by count):")
        top_axioms = sorted(
            stats["axiom_distribution"].items(), key=lambda x: x[1], reverse=True
        )[:10]
        for axiom, count in top_axioms:
            print(f"  {axiom:<30} {count}")
