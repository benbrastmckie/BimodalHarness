"""Formula generation package for BimodalHarness.

Provides three capabilities:
1. Algebraic AST types mirroring the 6 Lean Formula constructors
2. Exhaustive enumeration and random generation of formulas
3. Near-miss mutation operators for contrastive training pair generation

Public API
----------
AST types:
    Atom, Bot, Imp, Box, Untl, Snce, FormulaNode

Serialization:
    from_json

Metric functions (mirror Lean Formula definitions):
    complexity, modal_depth, temporal_depth, imp_count, top_operator

Generator functions:
    enumerate_by_complexity, enumerate_up_to_complexity, random_formula,
    count_formulas

Mutation operators:
    mutate, generate_contrastive_pair
"""

from __future__ import annotations

from bimodal_harness.formula.ast import (
    Atom,
    Bot,
    Box,
    FormulaNode,
    Imp,
    Snce,
    Untl,
    complexity,
    from_json,
    imp_count,
    modal_depth,
    temporal_depth,
    top_operator,
)
from bimodal_harness.formula.generator import (
    count_formulas,
    enumerate_by_complexity,
    enumerate_up_to_complexity,
    random_formula,
)
from bimodal_harness.formula.mutator import (
    generate_contrastive_pair,
    mutate,
)

__all__ = [
    # AST types
    "Atom",
    "Bot",
    "Imp",
    "Box",
    "Untl",
    "Snce",
    "FormulaNode",
    # Serialization
    "from_json",
    # Metrics
    "complexity",
    "modal_depth",
    "temporal_depth",
    "imp_count",
    "top_operator",
    # Generators
    "enumerate_by_complexity",
    "enumerate_up_to_complexity",
    "random_formula",
    "count_formulas",
    # Mutators
    "mutate",
    "generate_contrastive_pair",
]
