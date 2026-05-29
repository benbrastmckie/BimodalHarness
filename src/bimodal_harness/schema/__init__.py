"""BimodalHarness schema package: training data schema and action space.

Public API for defining, validating, and serializing training records
for the AlphaZero proof search system.

Submodules:
- constants:     Schema version, valid value sets, and enumeration constants
- formula:       Formula JSON type aliases and validation
- actions:       42-axiom + 7-rule action space with frame-class masks
- records:       TrainingRecord and component dataclasses
- validation:    Record and formula validation functions
- serialization: JSONL read/write matching DataExport.lean format
- parquet:       Parquet read/write with PyArrow for ML training batches
"""

from __future__ import annotations

from bimodal_harness.schema.actions import (
    ACTION_TO_INDEX,
    ALL_ACTIONS,
    AXIOM_ACTIONS,
    BASE_MASK,
    DENSE_MASK,
    DISCRETE_MASK,
    FRAME_CLASS_MASKS,
    RULE_ACTIONS,
    FrameClass,
    get_mask_for_frame_class,
)
from bimodal_harness.schema.constants import (
    ACTION_SPACE_VERSION,
    SCHEMA_VERSION,
    VALID_DIFFICULTY_TIERS,
    VALID_FORMULA_TAGS,
    VALID_FRAME_CLASSES,
    VALID_LABELS,
    VALID_SOURCES,
    VALID_TOP_OPERATORS,
)
from bimodal_harness.schema.formula import (
    AtomRepr,
    FormulaJson,
    formula_json_to_pretty,
    validate_formula_json,
)
from bimodal_harness.schema.features import (
    extract_atom_count,
    extract_pattern_key,
)
from bimodal_harness.schema.records import (
    DifficultyMetrics,
    PatternKey,
    ProofTrace,
    RuleProfile,
    SimpleCountermodel,
    TrainingRecord,
)

__all__ = [
    # Actions
    "ACTION_TO_INDEX",
    "ACTION_SPACE_VERSION",
    "ALL_ACTIONS",
    "AXIOM_ACTIONS",
    "BASE_MASK",
    "DENSE_MASK",
    "DISCRETE_MASK",
    "FRAME_CLASS_MASKS",
    "RULE_ACTIONS",
    "FrameClass",
    "get_mask_for_frame_class",
    # Constants
    "SCHEMA_VERSION",
    "VALID_DIFFICULTY_TIERS",
    "VALID_FORMULA_TAGS",
    "VALID_FRAME_CLASSES",
    "VALID_LABELS",
    "VALID_SOURCES",
    "VALID_TOP_OPERATORS",
    # Formula
    "AtomRepr",
    "FormulaJson",
    "formula_json_to_pretty",
    "validate_formula_json",
    # Features
    "extract_atom_count",
    "extract_pattern_key",
    # Records
    "DifficultyMetrics",
    "PatternKey",
    "ProofTrace",
    "RuleProfile",
    "SimpleCountermodel",
    "TrainingRecord",
]
