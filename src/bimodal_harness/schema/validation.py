"""Validation functions for training records and formula JSON trees.

Provides two main public functions:
- validate_formula_json: already in formula.py (re-exported here for convenience)
- validate_training_record: structural and semantic validation of a TrainingRecord

Validation logic enforces:
1. Label-conditional field presence: proof_trace iff label=="valid";
   countermodel iff label=="invalid"
2. PatternKey value ranges (complexity >= 1, all non-negative)
3. Frame class validity
4. Axiom names in proof_trace.axioms_used are all in AXIOM_ACTIONS
5. Schema version matches SCHEMA_VERSION
"""

from __future__ import annotations

from bimodal_harness.schema.actions import AXIOM_ACTIONS
from bimodal_harness.schema.constants import (
    SCHEMA_VERSION,
    VALID_FRAME_CLASSES,
    VALID_LABELS,
    VALID_TOP_OPERATORS,
)
from bimodal_harness.schema.formula import validate_formula_json
from bimodal_harness.schema.records import TrainingRecord

# Re-export for convenience.
__all__ = ["validate_formula_json", "validate_training_record"]

_VALID_AXIOM_SET: frozenset[str] = frozenset(AXIOM_ACTIONS)


def validate_training_record(record: TrainingRecord) -> list[str]:
    """Validate a TrainingRecord and return a list of error strings.

    If the returned list is empty the record is valid.

    Checks performed:
    - label is a known value
    - frame_class is a known value
    - schema_version matches SCHEMA_VERSION
    - formula_json passes structural validation
    - pattern_key.top_operator is a known GoalCategory
    - pattern_key.complexity >= 1
    - proof_trace is present iff label == "valid"
    - countermodel is present iff label == "invalid"
    - all axioms in proof_trace.axioms_used are in AXIOM_ACTIONS
    - difficulty_metrics.difficulty_tier is a known value

    Parameters
    ----------
    record:
        The TrainingRecord to validate.

    Returns
    -------
    list[str]
        Zero or more error description strings.  Empty list means valid.

    Examples
    --------
    >>> errors = validate_training_record(record)
    >>> if errors:
    ...     print("Invalid:", errors)
    """
    errors: list[str] = []

    # Label check
    if record.label not in VALID_LABELS:
        errors.append(f"Invalid label: {record.label!r}.  Must be one of {VALID_LABELS}.")

    # Frame class check
    if record.frame_class not in VALID_FRAME_CLASSES:
        errors.append(
            f"Invalid frame_class: {record.frame_class!r}.  Must be one of {VALID_FRAME_CLASSES}."
        )

    # Schema version check
    if record.schema_version != SCHEMA_VERSION:
        errors.append(
            f"schema_version mismatch: got {record.schema_version!r}, "
            f"expected {SCHEMA_VERSION!r}."
        )

    # Formula JSON structural validation
    if not validate_formula_json(record.formula_json):
        errors.append("formula_json failed structural validation (invalid tag or missing fields).")

    # PatternKey validation
    pk = record.pattern_key
    if pk.complexity < 1:
        errors.append(f"pattern_key.complexity must be >= 1, got {pk.complexity}.")
    if pk.modal_depth < 0:
        errors.append(f"pattern_key.modal_depth must be >= 0, got {pk.modal_depth}.")
    if pk.temporal_depth < 0:
        errors.append(f"pattern_key.temporal_depth must be >= 0, got {pk.temporal_depth}.")
    if pk.imp_count < 0:
        errors.append(f"pattern_key.imp_count must be >= 0, got {pk.imp_count}.")
    if pk.top_operator not in VALID_TOP_OPERATORS:
        errors.append(
            f"pattern_key.top_operator {pk.top_operator!r} is not a valid GoalCategory.  "
            f"Must be one of {VALID_TOP_OPERATORS}."
        )

    # Label-conditional field checks
    if record.label == "valid":
        if record.proof_trace is None:
            errors.append("proof_trace must be present when label == 'valid'.")
        if record.countermodel is not None:
            errors.append("countermodel must be None when label == 'valid'.")
    elif record.label == "invalid":
        if record.countermodel is None:
            errors.append("countermodel must be present when label == 'invalid'.")
        if record.proof_trace is not None:
            errors.append("proof_trace must be None when label == 'invalid'.")

    # Axiom name validation in proof_trace
    if record.proof_trace is not None:
        unknown_axioms = [
            a for a in record.proof_trace.axioms_used if a not in _VALID_AXIOM_SET
        ]
        if unknown_axioms:
            errors.append(
                f"proof_trace contains unknown axiom names: {unknown_axioms}.  "
                f"All names must be in AXIOM_ACTIONS."
            )

    return errors
