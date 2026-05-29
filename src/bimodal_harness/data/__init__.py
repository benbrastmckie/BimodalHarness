"""
Data contract module for BimodalHarness.

This package defines the Python schema types that mirror the Lean 4 JSON export
format from BimodalLogic. It provides type-safe loading of JSONL records exported
by BimodalLogic's DatasetGenerator.lean, as well as a full ingestion pipeline
for translating Lean-export records to ML-training records.

Integration boundary:
- BimodalLogic exports JSONL via `lake exe dataset_generator`
- BimodalHarness reads static JSONL from data/ directory
- No live Lean dependency at runtime

Key types (legacy Lean-export schema -- from data.schema):
- FormulaNode: Recursive AST for bimodal formulas
- LabeledFormula: Top-level training record with label and metadata
- PatternKey: Structural fingerprint for formula categorization
- SimpleCountermodel: Counterexample for INVALID formulas
- ProofTrace: Proof structure metadata for VALID formulas
- DifficultyMetrics: Complexity indicators for curriculum learning

Ingestion pipeline:
- labeled_formula_to_training_record: Translate LabeledFormula to TrainingRecord
- ingest_jsonl: Load and translate a JSONL file
- ingest_directory: Load all JSONL files in a directory
- ingest_and_cache: Ingest + write Parquet cache
- load_cached: Load from Parquet cache
- is_cache_fresh: Check cache freshness

Deprecation notice
------------------
``data.schema`` types (LabeledFormula, FormulaNode, PatternKey, etc.) are
the legacy JSONL-deserialization layer and are being superseded by
``schema.records.TrainingRecord`` for all new ML-pipeline code.  The
``data.ingestion`` module provides the canonical bridge between the two layers.
"""

from __future__ import annotations

import warnings as _warnings

from bimodal_harness.data.schema import (
    DifficultyMetrics,
    FormulaNode,
    FormulaTag,
    Label,
    LabeledFormula,
    PatternKey,
    ProofTrace,
    RuleProfile,
    SimpleCountermodel,
    load_jsonl,
)
from bimodal_harness.data.ingestion import (
    DIFFICULTY_TIER_MAP,
    TOP_OPERATOR_MAP,
    ingest_and_cache,
    ingest_directory,
    ingest_jsonl,
    is_cache_fresh,
    labeled_formula_to_training_record,
    load_cached,
)
from bimodal_harness.data.dataset import (
    BimodalDataset,
    CurriculumSampler,
    split_dataset,
)

__all__ = [
    # Raw schema types (Lean export format)
    "FormulaTag",
    "FormulaNode",
    "Label",
    "PatternKey",
    "SimpleCountermodel",
    "RuleProfile",
    "ProofTrace",
    "DifficultyMetrics",
    "LabeledFormula",
    "load_jsonl",
    # Translation constants
    "DIFFICULTY_TIER_MAP",
    "TOP_OPERATOR_MAP",
    # Ingestion pipeline
    "labeled_formula_to_training_record",
    "ingest_jsonl",
    "ingest_directory",
    "ingest_and_cache",
    "load_cached",
    "is_cache_fresh",
    # ML dataset
    "BimodalDataset",
    "split_dataset",
    "CurriculumSampler",
]
