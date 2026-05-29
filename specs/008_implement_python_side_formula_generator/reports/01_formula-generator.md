# Research Report: Python Formula Generator

**Task**: 8 — Implement Python-side formula generator
**Date**: 2026-05-29
**Agent**: python-research-agent

---

## 1. Existing Infrastructure

### Formula AST (task 4 output)

`/home/benjamin/Projects/BimodalHarness/src/bimodal_harness/schema/formula.py` defines:

- `FormulaJson = dict[str, Any]` — raw JSON-dict representation (the wire format).
- `AtomRepr` — frozen dataclass with `base: str` and `fresh_index: int | None`.
- `validate_formula_json(data, depth, max_depth)` — recursive validator.
- `formula_json_to_pretty(data)` — pretty-printer matching Lean's `prettyPrint`.

The six constructor shapes are:

| Constructor | JSON keys (besides "tag") |
|-------------|--------------------------|
| `atom`      | `name` (str)             |
| `bot`       | (none)                   |
| `imp`       | `left`, `right`          |
| `box`       | `child`                  |
| `untl`      | `event`, `guard`         |
| `snce`      | `event`, `guard`         |

There is **no Python class hierarchy** for the AST nodes yet — only the dict/JSON representation and a recursive validator. The formula generator must either work with dicts directly (simplest, preserves compatibility) or introduce a thin algebraic type that serializes to the same dict format.

### Metrics Already Defined (Lean → Python)

`PatternKey` in `records.py` tracks:
- `modal_depth` — nesting depth of `box` (max path through `box` nodes).
- `temporal_depth` — nesting depth of `untl`/`snce` (max path through temporal nodes).
- `imp_count` — total implication count.
- `complexity` — total connective count + 1 (leaves = 1, binary/unary = 1 + children).

These mirror the Lean functions `Formula.modalDepth`, `Formula.temporalDepth`, `Formula.countImplications`, and `Formula.complexity` exactly. The Python generator should compute these to tag generated formulas.

---

## 2. Lean Enumeration Strategy

### Formula.complexity (Lean source of truth)

```lean
def complexity : Formula → Nat
  | atom _ => 1
  | bot => 1
  | imp φ ψ => 1 + φ.complexity + ψ.complexity
  | box φ => 1 + φ.complexity
  | untl φ ψ => 1 + φ.complexity + ψ.complexity
  | snce φ ψ => 1 + φ.complexity + ψ.complexity
```

Complexity = number of nodes in the syntax tree. This is the primary bound for enumeration by "size". An atom or bot has complexity 1; each constructor adds 1.

### Subformula Closure (Lean)

`Formula.subformulas` in `Subformulas.lean` collects all subformulas recursively (the formula itself + subformulas of children). `subformulaClosure` converts this to a `Finset`. `closureWithNeg` adds negations. The closure approach is used by the Lean proof system for bounded model checking — it generates the finite set of relevant formulas for a given input formula. This is **not** the approach we need for generation; the Python generator needs to enumerate formulas up to a bound, not derive a closure from a given formula.

### Lean Enumeration Approach (Countable instance)

Lean proves `Countable Formula` via `Denumerable Formula`. This gives an abstract bijection with `Nat` but does not directly provide a practical enumeration procedure. The Lean codebase does not have an explicit formula enumerator — it uses this to prove completeness arguments, not to generate training data.

**Practical conclusion**: Implement a Python-side generator from scratch using the grammar. The Lean closure code confirms the correct complexity metric but the Python generator does not need to mirror the Lean enumeration approach.

---

## 3. Implementation Design

### 3.1 Core Data Type Choice

Two options:

**Option A — pure dict** (wire format throughout):
- Pro: zero conversion overhead, output is already in `FormulaJson` format.
- Con: no type safety, no structural operations without pattern-matching on `"tag"`.

**Option B — frozen dataclass tree + `to_json()` method**:
- Pro: type-safe tree traversal, easy to write recursive generators and mutators.
- Con: adds a class hierarchy that doesn't exist yet.

**Recommendation**: Option B. Introduce a thin algebraic type `Formula` with six frozen dataclasses (`Atom`, `Bot`, `Imp`, `Box`, `Untl`, `Snce`) plus a union type `FormulaNode`. Each has a `to_json()` that produces `FormulaJson`. A classmethod `from_json(data)` enables round-tripping. Place this in `src/bimodal_harness/formula/ast.py` (new module). The existing `schema/formula.py` dict-based API stays for ingestion/validation of Lean exports.

### 3.2 Complexity Metrics (Python mirror of Lean)

```python
def complexity(f: FormulaNode) -> int:
    """Mirror Formula.complexity in Lean."""
    match f:
        case Atom() | Bot(): return 1
        case Imp(l, r): return 1 + complexity(l) + complexity(r)
        case Box(c): return 1 + complexity(c)
        case Untl(e, g) | Snce(e, g): return 1 + complexity(e) + complexity(g)

def modal_depth(f: FormulaNode) -> int:
    match f:
        case Atom() | Bot(): return 0
        case Imp(l, r): return max(modal_depth(l), modal_depth(r))
        case Box(c): return 1 + modal_depth(c)
        case Untl(e, g) | Snce(e, g): return max(modal_depth(e), modal_depth(g))

def temporal_depth(f: FormulaNode) -> int:
    match f:
        case Atom() | Bot(): return 0
        case Imp(l, r): return max(temporal_depth(l), temporal_depth(r))
        case Box(c): return temporal_depth(c)
        case Untl(e, g) | Snce(e, g): return 1 + max(temporal_depth(e), temporal_depth(g))

def imp_count(f: FormulaNode) -> int:
    match f:
        case Atom() | Bot(): return 0
        case Imp(l, r): return 1 + imp_count(l) + imp_count(r)
        case Box(c): return imp_count(c)
        case Untl(e, g) | Snce(e, g): return imp_count(e) + imp_count(g)
```

### 3.3 Enumeration by Complexity

**Strategy**: enumerate all formulas of complexity exactly `n` over an atom set `atoms`.

```
formulas_of_complexity(n, atoms):
    if n == 1:
        yield Bot()
        for a in atoms:
            yield Atom(a)
    else:
        # Binary constructors: imp, untl, snce
        # Each splits as complexity(l) + complexity(r) = n - 1
        for k in range(1, n-1):
            for l in formulas_of_complexity(k, atoms):
                for r in formulas_of_complexity(n-1-k, atoms):
                    yield Imp(l, r)
                    yield Untl(l, r)
                    yield Snce(l, r)
        # Unary constructor: box
        for c in formulas_of_complexity(n-1, atoms):
            yield Box(c)
```

This is exact, non-overlapping, and mirrors a standard Catalan-number enumeration. For training data, enumeration up to complexity 10-12 is practical. The number of formulas grows fast (super-exponential with atoms), so:
- Enumerate exhaustively up to complexity 6-7 for small atom sets (2-3 atoms).
- Use random sampling for larger complexity budgets.

**Depth-bounded enumeration alternative**: bound by tree depth rather than complexity. Complexity is strictly more expressive (a chain of imp has complexity O(n) but depth O(n) too), so complexity bounds are generally preferred for balanced sampling.

### 3.4 Random Formula Generation

```python
def random_formula(
    max_complexity: int,
    atoms: list[str],
    rng: random.Random,
    *,
    op_weights: dict[str, float] | None = None,
) -> FormulaNode:
```

**Algorithm** (top-down stochastic generation):
1. If `max_complexity == 1` or (random and budget low): sample from `{Bot} ∪ Atom(a)`.
2. Otherwise: sample a constructor from `{imp, box, untl, snce}` using `op_weights`.
3. For binary constructors: choose split `k ~ Uniform(1, remaining-1)`.
4. Recurse on each subtree with the assigned complexity budget.

**Default operator weights**: equal weights cause heavy bias toward `bot` and atoms (since many paths terminate early). Better defaults:
- Leaf probability should decrease with remaining budget.
- Weight `box` lower than `imp` to avoid modal-only formulas.
- Balance `untl` and `snce` equally.

A practical schedule: at complexity `c`, leaf probability = `1/(c+1)`, operator probabilities otherwise uniform over `{imp, box, untl, snce}`.

### 3.5 Distribution Control

For balanced training data:
- **Operator histogram target**: aim for roughly equal representation of all 6 constructors across the dataset (counting occurrences, not just top-level operators).
- **Rejection sampling**: generate a batch, compute operator histograms, re-sample underrepresented categories.
- **Stratified generation**: generate a fixed quota per (modal_depth, temporal_depth) stratum.

Avoid trivially true/false formulas:
- `bot` alone is trivially false — skip single-node `bot` unless explicitly needed.
- `imp(bot, X)` is trivially valid (ex falso) — down-weight or label automatically.
- `box(bot→bot)` (i.e., `□⊤`) is a tautology under S5 — flag via Z3 if needed.

For rapid prototyping, a simple strategy is to emit formulas with `complexity >= 3` and `len(atoms) >= 1`.

### 3.6 Near-Miss Mutation for Contrastive Pairs

**Purpose**: Given a formula `f` (known valid or invalid), produce `f'` that differs minimally but has the opposite label — creating hard negative/positive examples for contrastive training.

**Mutation operators** (all produce syntactically valid formulas):

| Mutation | Description | Example |
|----------|-------------|---------|
| `flip_operator` | Replace a binary op at a random node: `imp↔untl`, `untl↔snce`, `imp→box` (wrapping one child) | `U(p,q) → S(p,q)` |
| `flip_temporal_direction` | `untl↔snce` globally via `swap_temporal` | `U(p,q) → S(p,q)` everywhere |
| `weaken_antecedent` | In `imp(A, B)`, replace A with `bot` (makes formula stronger — more likely valid) | `(p→q) → (⊥→q)` |
| `strengthen_antecedent` | In `imp(A, B)`, replace A with `box(A)` or `untl(A, top)` (harder to satisfy) | `(p→q) → (□p→q)` |
| `change_atom` | Replace atom `p` with atom `q` (or fresh atom) | `p → q` |
| `add_box` | Wrap a subformula with `box` | `p → □p` |
| `remove_box` | Strip a `box` wrapper at a random node | `□p → p` |
| `negate_guard` | In `untl(e, g)` or `snce(e, g)`, replace guard with its negation | `U(p,q) → U(p,¬q)` |
| `swap_children` | Swap `left/right` of `imp`, or `event/guard` of `untl`/`snce` | `(p→q) → (q→p)` |
| `drop_modal` | Replace `box(c)` with `c` | `□p → p` |

**Implementation approach**:
1. Walk the formula tree to collect mutable positions (with path coordinates).
2. Sample a random position and a compatible mutation.
3. Apply the mutation by rebuilding the tree from leaves up.
4. Run Z3 or return the pair for later Z3 labeling.

**Validity guarantee**: All mutations listed above produce syntactically valid formulas in the TM grammar. Semantic label change is not guaranteed — some mutations are label-preserving (e.g., swapping identical atoms). For contrastive pairs, run Z3 on both the original and mutant to confirm label difference.

### 3.7 File Layout

```
src/bimodal_harness/
  formula/
    __init__.py
    ast.py          # FormulaNode dataclasses, to_json, from_json, metrics
    generator.py    # enumerate_by_complexity, random_formula, stratified_sample
    mutator.py      # near_miss_mutations, apply_mutation
tests/
  test_formula/
    __init__.py
    test_ast.py
    test_generator.py
    test_mutator.py
```

The existing `schema/formula.py` is unmodified — it remains the dict-based validator for Lean-exported data.

---

## 4. Key Design Decisions

### Why a new `formula/` module rather than extending `schema/formula.py`

`schema/formula.py` is a validator for Lean-exported JSON. Adding generator code there would conflate two responsibilities. The generator needs an algebraic type for tree manipulation; the schema module only needs dict-based validation. Keeping them separate follows the existing boundary between `schema/` (Lean bridge) and new Python-native code.

### Complexity vs. depth as the enumeration bound

Complexity (node count) is strictly superior to tree depth for controlling formula size. At depth `d`, implication chains have complexity `d+1` but a balanced binary tree has complexity `2^(d+1)-1`. Complexity gives a predictable bound on the total number of formulas and ensures diversity across tree shapes.

### Atoms to use

The Lean codebase uses string-named atoms (`"p"`, `"q"`, `"r"`, etc.). For training data, a small atom set (`["p", "q", "r"]` — 3 atoms) provides enough diversity up to complexity 8 while keeping the formula space tractable. Larger sets (`["p", "q", "r", "s", "t"]`) are needed for higher complexity budgets.

---

## 5. Dependencies

No new Python packages are needed. The generator uses:
- `dataclasses` (stdlib) — for the algebraic AST.
- `random` (stdlib) — for stochastic generation.
- `itertools` (stdlib) — for enumeration.
- `typing` (stdlib) — for type annotations.

Optional integration with `z3-solver` (already in `pyproject.toml`) for semantic labeling of generated formulas and mutation pairs.

---

## 6. Testing Strategy

- **Unit tests for metrics**: verify `complexity`, `modal_depth`, `temporal_depth`, `imp_count` on known formulas, cross-checking against Lean definitions.
- **Enumeration tests**: verify counts match the closed-form expectation for small complexity levels and small atom sets. For 2 atoms and complexity 1: 3 formulas (bot, atom_p, atom_q). For complexity 2: 4 constructors × 1 split × 3² options for binary + 3 for unary = 39 formulas (verifiable by exhaustion).
- **Round-trip tests**: `FormulaNode.to_json()` → `from_json()` → identity; also validate output with `validate_formula_json`.
- **Mutation tests**: verify each mutation produces a valid formula; verify that a sample of mutations produces syntactically distinct outputs.
- **Distribution tests**: verify that stratified sampling produces the requested operator histogram within tolerance.
