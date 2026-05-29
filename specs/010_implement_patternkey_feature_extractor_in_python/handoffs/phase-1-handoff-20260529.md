# Phase 1 Handoff — Core Feature Extraction Module

**Task**: 10 — PatternKey Feature Extractor
**Phase**: 1 of 3
**Status**: COMPLETED
**Date**: 2026-05-29

## What Was Done

Created `src/bimodal_harness/schema/features.py` implementing all five feature extractors:
- `_complexity` — connective count + 1 (Lean: Formula.complexity)
- `_modal_depth` — max box nesting (Lean: Formula.modalDepth)
- `_temporal_depth` — max untl/snce nesting; box passes through (Lean: Formula.temporalDepth)
- `_imp_count` — total imp node count (Lean: Formula.countImplications)
- `_top_operator` — tag-to-GoalCategory mapping (Lean: goalCategory)

Public API:
- `extract_pattern_key(formula_json) -> PatternKey`
- `extract_atom_count(formula_json) -> int`

## Key Design Decisions

- `_get_tag()` helper supports both dict (FormulaJson) and duck-typed algebraic AST objects (for task 8 compatibility)
- Max depth guard (500) matches `validate_formula_json` convention
- ValueError on unrecognized tags with descriptive message including valid choices

## Verification

- Module imports without error
- Spot-check: `extract_pattern_key({"tag": "atom", "name": "p"})` returns `PatternKey(modal_depth=0, temporal_depth=0, imp_count=0, complexity=1, top_operator='Atom')`

## Next Phase

Phase 2: Create comprehensive unit tests in `tests/test_schema/test_features.py`
