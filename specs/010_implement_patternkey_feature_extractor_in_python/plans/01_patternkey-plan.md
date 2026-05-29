# Implementation Plan: PatternKey Feature Extractor

- **Task**: 10 - Implement PatternKey feature extractor in Python
- **Status**: [NOT STARTED]
- **Effort**: 3 hours
- **Dependencies**: None (schema package and PatternKey dataclass already exist)
- **Research Inputs**: specs/010_implement_patternkey_feature_extractor_in_python/reports/01_patternkey-extractor.md
- **Artifacts**: plans/01_patternkey-plan.md (this file)
- **Standards**: plan-format.md, status-markers.md, artifact-management.md, tasks.md
- **Type**: python
- **Lean Intent**: false

## Overview

Port the five PatternKey feature extraction algorithms from Lean (Formula.lean and SuccessPatterns.lean) into a new Python module `schema/features.py`. The research report fully specifies the recursive algorithms for `complexity`, `modalDepth`, `temporalDepth`, `countImplications`, and `goalCategory` over the 6-constructor formula JSON tree. The implementation creates `extract_pattern_key(formula_json) -> PatternKey` and `extract_atom_count(formula_json) -> int` as the public API, with comprehensive tests covering all formula constructors and edge cases.

### Research Integration

The research report (01_patternkey-extractor.md) provides:
- Exact recursive definitions for all 5 features, transcribed from Formula.lean lines 162-303 and SuccessPatterns.lean line 76
- Complete JSON tag-to-field mapping for all 6 formula constructors (atom, bot, imp, box, untl, snce)
- Tag-to-GoalCategory mapping dictionary for `_top_operator`
- Seven concrete test vectors with expected PatternKey tuples
- Design for neural network tensor encoding (12-dim: 4 numeric + 8 one-hot), deferred to a later task
- `extract_atom_count` helper for DifficultyMetrics population

### Prior Plan Reference

No prior plan.

### Roadmap Alignment

No ROADMAP.md found.

## Goals & Non-Goals

**Goals**:
- Implement `extract_pattern_key()` that faithfully ports `PatternKey.fromFormula` from SuccessPatterns.lean
- Implement `extract_atom_count()` for DifficultyMetrics support
- Achieve full test coverage for all 6 formula constructors and nested combinations
- Export public API from `schema/__init__.py`
- Handle invalid/malformed formula JSON gracefully with clear errors

**Non-Goals**:
- Neural network tensor encoding (12-dim vector) -- separate task
- Normalization or log1p scaling of feature values -- handled at training time
- Extended feature engineering (tag histograms, branching depth) -- future enhancement
- Modifying existing `records.py`, `formula.py`, or `constants.py`

## Risks & Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Algorithm divergence from Lean source | H | L | Research report transcribed exact recursive definitions; verify against test vectors from report |
| Stack overflow on deeply nested formulas | M | L | Use max_depth guard (500) matching existing validate_formula_json pattern |
| Unrecognized formula tag in production data | M | L | Raise ValueError with clear message; callers can pre-validate with validate_formula_json |
| temporalDepth box pass-through error | M | M | Explicit test case: box(untl(p,q)) must yield temporalDepth=1, not 2 |

## Implementation Phases

**Dependency Analysis**:
| Wave | Phases | Blocked by |
|------|--------|------------|
| 1 | 1 | -- |
| 2 | 2 | 1 |
| 3 | 3 | 2 |

Phases within the same wave can execute in parallel.

### Phase 1: Core Feature Extraction Module [NOT STARTED]

**Goal**: Create `schema/features.py` with all five feature extraction helpers and the two public functions.

**Tasks**:
- [ ] Create `src/bimodal_harness/schema/features.py` with module docstring and imports
- [ ] Implement `_complexity(data: FormulaJson) -> int` -- recursive connective count + 1
- [ ] Implement `_modal_depth(data: FormulaJson) -> int` -- max box nesting depth
- [ ] Implement `_temporal_depth(data: FormulaJson) -> int` -- max untl/snce nesting depth (box passes through)
- [ ] Implement `_imp_count(data: FormulaJson) -> int` -- total imp node count
- [ ] Implement `_top_operator(data: FormulaJson) -> str` -- tag-to-GoalCategory mapping via `_TAG_TO_GOAL_CATEGORY` dict
- [ ] Implement `extract_pattern_key(formula_json: FormulaJson) -> PatternKey` -- calls all 5 helpers, returns PatternKey
- [ ] Implement `extract_atom_count(formula_json: FormulaJson) -> int` -- count distinct atom base names
- [ ] Add max_depth guard (500) to all recursive helpers matching validate_formula_json convention
- [ ] Add ValueError on unrecognized tags with descriptive message

**Timing**: 1 hour

**Depends on**: none

**Files to modify**:
- `src/bimodal_harness/schema/features.py` - create new module

**Verification**:
- Module imports without error: `python -c "from bimodal_harness.schema.features import extract_pattern_key, extract_atom_count"`
- Type annotations pass: `mypy src/bimodal_harness/schema/features.py`

---

### Phase 2: Unit Tests [NOT STARTED]

**Goal**: Create comprehensive test suite covering all formula constructors, nested combinations, edge cases, and error conditions.

**Tasks**:
- [ ] Create `tests/test_schema/test_features.py` with test class structure
- [ ] Test `extract_pattern_key` on all 7 test vectors from research report:
  - `{"tag": "atom", "name": "p"}` -> (0, 0, 0, 1, "Atom")
  - `{"tag": "bot"}` -> (0, 0, 0, 1, "Bottom")
  - `{"tag": "box", "child": {"tag": "atom", "name": "p"}}` -> (1, 0, 0, 2, "Box")
  - `imp(box(p), box(q))` -> (1, 0, 1, 4, "Implication")
  - `untl(untl(p, q), r)` -> (0, 2, 0, 4, "Until")
  - `box(untl(p, q))` -> (1, 1, 0, 3, "Box")
  - `box(box(atom))` -> (2, 0, 0, 3, "Box")
- [ ] Test `_temporal_depth` box pass-through: box does NOT increment temporal depth
- [ ] Test `_imp_count` accumulation through box and temporal operators
- [ ] Test mixed formulas with both box and temporal operators at different branches
- [ ] Test `extract_atom_count` with formulas containing duplicate and distinct atoms
- [ ] Test error handling: unrecognized tag raises ValueError
- [ ] Test `snce` constructor produces GoalCategory "Since" and increments temporal depth

**Timing**: 1 hour

**Depends on**: 1

**Files to modify**:
- `tests/test_schema/test_features.py` - create new test module

**Verification**:
- All tests pass: `pytest tests/test_schema/test_features.py -v`
- No test failures or errors

---

### Phase 3: Package Integration and Final Validation [NOT STARTED]

**Goal**: Export public API from `schema/__init__.py`, run full test suite, and verify type checking.

**Tasks**:
- [ ] Add `extract_pattern_key` and `extract_atom_count` imports to `src/bimodal_harness/schema/__init__.py`
- [ ] Add both names to the `__all__` list in `__init__.py`
- [ ] Run full test suite to verify no regressions: `pytest tests/`
- [ ] Run type checking: `mypy src/bimodal_harness/schema/features.py`
- [ ] Run linting: `ruff check src/bimodal_harness/schema/features.py`
- [ ] Verify public import path works: `python -c "from bimodal_harness.schema import extract_pattern_key, extract_atom_count"`

**Timing**: 30 minutes

**Depends on**: 2

**Files to modify**:
- `src/bimodal_harness/schema/__init__.py` - add imports and __all__ entries

**Verification**:
- Full test suite passes: `pytest tests/ -v`
- No mypy errors
- No ruff violations
- Public API importable from package root

## Testing & Validation

- [ ] All 7 research report test vectors produce correct PatternKey values
- [ ] `temporalDepth` passes through `box` without incrementing (box(untl(p,q)) -> 1)
- [ ] `extract_atom_count` correctly deduplicates repeated atom names
- [ ] ValueError raised for unrecognized formula tags
- [ ] Full test suite passes with no regressions
- [ ] Type checking passes (mypy)
- [ ] Linting passes (ruff)
- [ ] Public API accessible via `from bimodal_harness.schema import extract_pattern_key`

## Artifacts & Outputs

- `src/bimodal_harness/schema/features.py` - feature extraction module
- `tests/test_schema/test_features.py` - unit test suite
- `src/bimodal_harness/schema/__init__.py` - updated package exports
- `specs/010_implement_patternkey_feature_extractor_in_python/plans/01_patternkey-plan.md` - this plan

## Rollback/Contingency

Rollback is straightforward since this task creates new files and makes additive changes only:
1. Delete `src/bimodal_harness/schema/features.py`
2. Delete `tests/test_schema/test_features.py`
3. Revert the import additions in `src/bimodal_harness/schema/__init__.py`
4. No existing files are modified beyond `__init__.py` imports
