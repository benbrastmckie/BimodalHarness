"""
Data contract module for BimodalHarness.

This package defines the Python schema types that mirror the Lean 4 JSON export
format from BimodalLogic. It provides type-safe loading of JSONL records exported
by BimodalLogic's DatasetGenerator.lean.

Integration boundary:
- BimodalLogic exports JSONL via `lake exe dataset_generator`
- BimodalHarness reads static JSONL from data/ directory
- No live Lean dependency at runtime

Key types:
- FormulaNode: Recursive AST for bimodal formulas
- LabeledFormula: Top-level training record with label and metadata
- PatternKey: Structural fingerprint for formula categorization
- SimpleCountermodel: Counterexample for INVALID formulas
- ProofTrace: Proof structure metadata for VALID formulas
- DifficultyMetrics: Complexity indicators for curriculum learning
"""

from __future__ import annotations

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

__all__ = [
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
]
