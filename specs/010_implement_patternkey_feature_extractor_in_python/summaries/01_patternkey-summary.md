# Implementation Summary: PatternKey Feature Extractor

- **Task**: 10 — Implement PatternKey feature extractor in Python
- **Status**: [COMPLETED]
- **Session**: sess_1780081000_c525c7
- **Date**: 2026-05-29

## What Was Built

Ported the five PatternKey structural feature algorithms from Lean
(Bimodal.Syntax.Formula and Bimodal.Automation.SuccessPatterns) into a new
Python module `src/bimodal_harness/schema/features.py`.

### Files Created

- `src/bimodal_harness/schema/features.py` — core feature extraction module
- `tests/test_schema/test_features.py` — 41-test unit suite

### Files Modified

- `src/bimodal_harness/schema/__init__.py` — added `extract_pattern_key` and
  `extract_atom_count` to imports and `__all__`

### Public API

```python
from bimodal_harness.schema import extract_pattern_key, extract_atom_count

# Extract all 5 PatternKey features from a formula JSON tree
pk = extract_pattern_key({"tag": "box", "child": {"tag": "atom", "name": "p"}})
# PatternKey(modal_depth=1, temporal_depth=0, imp_count=0, complexity=2, top_operator='Box')

# Count distinct atom base names (for DifficultyMetrics)
n = extract_atom_count({"tag": "imp", "left": {"tag": "atom", "name": "p"},
                         "right": {"tag": "atom", "name": "q"}})
# 2
```

## Algorithm Accuracy

All five helpers faithfully port the Lean definitions:

| Python helper | Lean source | Location |
|---|---|---|
| `_complexity` | `Formula.complexity` | Formula.lean lines 162-168 |
| `_modal_depth` | `Formula.modalDepth` | Formula.lean lines 262-268 |
| `_temporal_depth` | `Formula.temporalDepth` | Formula.lean lines 283-289 |
| `_imp_count` | `Formula.countImplications` | Formula.lean lines 303-309 |
| `_top_operator` | `goalCategory` | SuccessPatterns.lean lines 76-83 |

Key rule verified: `box` does NOT increment temporal depth (passes through).
This matches `temporalDepth(box φ) = φ.temporalDepth` in Formula.lean line 287.

## Test Results

- 41 new tests: all pass
- 186 schema tests: all pass
- No regressions in existing test suite (347 total tests pass)
- Linting: `ruff check` — all checks passed

## Plan Deviations

- **Complexity values in research report test vectors 4 and 5 were incorrect.**
  The research report listed `complexity=4` for `imp(box(p), box(q))` and
  `untl(untl(p,q), r)`. The correct values per Lean `Formula.complexity` are
  both 5. The implementation follows the Lean definition exactly; tests use
  the correct values with inline documentation explaining the discrepancy.

- **Module placement**: Plan referenced `schema/features.py` (which was
  implemented). The delegation context mentioned a `features/` package, but
  the plan's explicit artifact list specifies `schema/features.py` — the
  plan was followed.

- **mypy type checking**: mypy was not available in the environment. Type
  annotations are complete and correct; verification was via ruff (which
  passed) and successful module import/operation.
