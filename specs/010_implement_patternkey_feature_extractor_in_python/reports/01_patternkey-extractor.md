# PatternKey Feature Extractor Research Report

**Task**: 10 — Implement PatternKey feature extractor in Python
**Date**: 2026-05-29
**Agent**: python-research-agent

---

## Summary

All five PatternKey features are fully specified in the Lean source. The Python
`PatternKey` dataclass already exists in `schema/records.py`. The implementation
requires a new `schema/features.py` module with a single public function
`extract_pattern_key(formula_json)` plus helpers, and a supplementary
`extract_atom_count(formula_json)` for `DifficultyMetrics`.

---

## 1. Lean Source — Algorithm Specification

### Source files

- `/home/benjamin/Projects/BimodalLogic/Theories/Bimodal/Syntax/Formula.lean` — defines `complexity`, `modalDepth`, `temporalDepth`, `countImplications`
- `/home/benjamin/Projects/BimodalLogic/Theories/Bimodal/Automation/SuccessPatterns.lean` — defines `GoalCategory`, `goalCategory`, `PatternKey`, `PatternKey.fromFormula`

### Formula constructors (6 primitives)

| Lean constructor | JSON tag | Children |
|-----------------|----------|----------|
| `atom _` | `"atom"` | `name: str` |
| `bot` | `"bot"` | none |
| `imp phi psi` | `"imp"` | `left`, `right` |
| `box phi` | `"box"` | `child` |
| `untl phi psi` | `"untl"` | `event`, `guard` |
| `snce phi psi` | `"snce"` | `event`, `guard` |

`all_past` (H) and `all_future` (G) are derived `def`s that expand into
`imp`/`snce`/`untl`/`bot` trees — they have no dedicated JSON tag.

### Feature algorithms

**complexity** (Formula.lean line 162): Total connective count + 1, always >= 1.
```
complexity(atom _)     = 1
complexity(bot)        = 1
complexity(imp φ ψ)    = 1 + complexity(φ) + complexity(ψ)
complexity(box φ)      = 1 + complexity(φ)
complexity(untl φ ψ)   = 1 + complexity(φ) + complexity(ψ)
complexity(snce φ ψ)   = 1 + complexity(φ) + complexity(ψ)
```

**modalDepth** (Formula.lean line 262): Maximum nesting depth of `box`.
```
modalDepth(atom _)     = 0
modalDepth(bot)        = 0
modalDepth(imp φ ψ)    = max(modalDepth(φ), modalDepth(ψ))
modalDepth(box φ)      = 1 + modalDepth(φ)
modalDepth(untl φ ψ)   = max(modalDepth(φ), modalDepth(ψ))
modalDepth(snce φ ψ)   = max(modalDepth(φ), modalDepth(ψ))
```

**temporalDepth** (Formula.lean line 283): Maximum nesting depth of `untl`/`snce`.
Note: `box` does NOT increment temporal depth — it passes through.
```
temporalDepth(atom _)  = 0
temporalDepth(bot)     = 0
temporalDepth(imp φ ψ) = max(temporalDepth(φ), temporalDepth(ψ))
temporalDepth(box φ)   = temporalDepth(φ)         ← passes through
temporalDepth(untl φ ψ)= 1 + max(temporalDepth(φ), temporalDepth(ψ))
temporalDepth(snce φ ψ)= 1 + max(temporalDepth(φ), temporalDepth(ψ))
```

**countImplications** (Formula.lean line 303): Total count of `imp` nodes.
```
countImplications(atom _)  = 0
countImplications(bot)     = 0
countImplications(imp φ ψ) = 1 + countImplications(φ) + countImplications(ψ)
countImplications(box φ)   = countImplications(φ)
countImplications(untl φ ψ)= countImplications(φ) + countImplications(ψ)
countImplications(snce φ ψ)= countImplications(φ) + countImplications(ψ)
```

**goalCategory / topOperator** (SuccessPatterns.lean line 76): Outermost constructor only.
```
goalCategory(atom _)   = Atom
goalCategory(bot)      = Bottom
goalCategory(imp _ _)  = Implication
goalCategory(box _)    = Box
goalCategory(untl _ _) = Until
goalCategory(snce _ _) = Since
```

---

## 2. GoalCategory Enum — 8 Values

```
Atom        -- propositional variable
Bottom      -- ⊥
Implication -- φ → ψ
Box         -- □φ
AllPast     -- Hφ (derived, not a primitive constructor)
AllFuture   -- Gφ (derived, not a primitive constructor)
Until       -- φ U ψ
Since       -- φ S ψ
```

`AllPast` and `AllFuture` are in `VALID_TOP_OPERATORS` but cannot appear as
`goalCategory` output because they are derived definitions, not constructors.
The Python `top_operator` field will only ever be one of the 6 primitive values
when computed from raw formula JSON. `AllPast`/`AllFuture` are reserved for
records where the Lean exporter has pre-classified the formula at a higher level.

---

## 3. Existing Python Schema

### Canonical PatternKey: `schema/records.py` (lines 32–91)

```python
@dataclass(frozen=True, slots=True)
class PatternKey:
    modal_depth: int
    temporal_depth: int
    imp_count: int
    complexity: int
    top_operator: str   # one of VALID_TOP_OPERATORS
```

Validated in `__post_init__`: complexity >= 1, depths >= 0, top_operator in set.
Serialized via `to_dict()` (camelCase) / `from_dict()` (camelCase).

### Formula JSON types: `schema/formula.py`

`FormulaJson = dict[str, Any]` — raw dict from `json.loads()`.
Field names per tag: `atom` has `name`; `imp` has `left`/`right`; `box` has
`child`; `untl`/`snce` have `event`/`guard`.

### Constants: `schema/constants.py`

`VALID_TOP_OPERATORS` frozenset of 8 strings.
`VALID_FORMULA_TAGS` frozenset of 6 strings.

### Legacy schema: `data/schema.py`

Older `PatternKey` and `FormulaNode` dataclasses from task 2. Not authoritative.
The canonical schema is `schema/records.py`.

---

## 4. Implementation Design

### Module placement

Create: `/home/benjamin/Projects/BimodalHarness/src/bimodal_harness/schema/features.py`

### Public API

```python
def extract_pattern_key(formula_json: FormulaJson) -> PatternKey:
    """Extract PatternKey features from a formula JSON tree.

    Direct port of PatternKey.fromFormula from SuccessPatterns.lean.
    Calls modalDepth, temporalDepth, countImplications, complexity,
    and goalCategory on the formula JSON tree.
    """

def extract_atom_count(formula_json: FormulaJson) -> int:
    """Count distinct atom base names in a formula JSON tree.

    Used to populate DifficultyMetrics.atom_count.
    """
```

### Internal helpers (module-private)

```python
def _complexity(data: FormulaJson) -> int: ...
def _modal_depth(data: FormulaJson) -> int: ...
def _temporal_depth(data: FormulaJson) -> int: ...
def _imp_count(data: FormulaJson) -> int: ...
def _top_operator(data: FormulaJson) -> str: ...
```

### Tag-to-GoalCategory mapping

```python
_TAG_TO_GOAL_CATEGORY: dict[str, str] = {
    "atom": "Atom",
    "bot":  "Bottom",
    "imp":  "Implication",
    "box":  "Box",
    "untl": "Until",
    "snce": "Since",
}
```

### Stack safety

Recursive traversal is safe for typical formula depths (< 100). For adversarial
input, use the same `max_depth=500` guard pattern as `validate_formula_json`.
Alternatively, implement as iterative post-order traversal using an explicit
stack — preferred for the `complexity`/`imp_count`/`atom_count` accumulators.

---

## 5. Neural Network Encoding

### PatternKey as tensor — 12 dimensions

| Indices | Feature | Encoding |
|---------|---------|----------|
| 0 | modal_depth | float (raw or log1p-normalized) |
| 1 | temporal_depth | float |
| 2 | imp_count | float (log1p for large counts) |
| 3 | complexity | float (log1p recommended) |
| 4–11 | top_operator | one-hot over 8 GoalCategory values |

One-hot ordering (alphabetical for determinism):
```python
GOAL_CATEGORY_ORDER = [
    "AllFuture", "AllPast", "Atom", "Bottom",
    "Box", "Implication", "Since", "Until",
]
```

### Recommended normalization

- `modal_depth`: divide by empirical max (e.g. 10), clip at 1.0
- `temporal_depth`: same
- `imp_count`: `log1p(x) / log1p(max_imp_count)` — skewed distribution
- `complexity`: `log1p(x) / log1p(max_complexity)` — exponential range

### Extended feature engineering (optional)

Beyond PatternKey (12-dim), richer features can be extracted directly from
`formula_json` in the same traversal:

| Feature | Dim | Description |
|---------|-----|-------------|
| Tag histogram | 6 | Count per tag type (normalized) |
| Distinct atoms | 1 | len(atom_names) |
| Max branching depth | 1 | Depth of deepest non-leaf node |
| Total nodes | 1 | Same as complexity - 1 |

These can be concatenated to form a 21-dim extended feature vector, which may
help the value network for formulas with high complexity but low modal depth.

---

## 6. Test Coverage

Place tests in:
`/home/benjamin/Projects/BimodalHarness/tests/test_schema/test_features.py`

### Key test cases

| Formula JSON | Expected PatternKey |
|---|---|
| `{"tag": "atom", "name": "p"}` | `(0, 0, 0, 1, "Atom")` |
| `{"tag": "bot"}` | `(0, 0, 0, 1, "Bottom")` |
| `{"tag": "box", "child": {"tag": "atom", "name": "p"}}` | `(1, 0, 0, 2, "Box")` |
| `imp(box(p), box(q))` | `(1, 0, 1, 4, "Implication")` |
| `untl(untl(p, q), r)` | `(0, 2, 0, 4, "Until")` |
| `box(untl(p, q))` | `(1, 1, 0, 3, "Box")` |
| `box(box(atom))` | `(2, 0, 0, 3, "Box")` |

### Edge cases

- Formula with both `box` and `untl` at different branches
- `temporalDepth` passes through `box` (box(untl(p,q)) -> temporalDepth=1)
- `imp_count` accumulates through all branches including `box`

---

## 7. Files to Create

1. **`src/bimodal_harness/schema/features.py`** — main extractor module
2. **`tests/test_schema/test_features.py`** — unit tests
3. Export `extract_pattern_key` from `src/bimodal_harness/schema/__init__.py`

No modifications needed to `records.py`, `formula.py`, or `constants.py`.
