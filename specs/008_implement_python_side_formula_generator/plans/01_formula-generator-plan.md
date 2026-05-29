# Implementation Plan: Python Formula Generator

- **Task**: 8 - Implement Python-side formula generator
- **Status**: [IMPLEMENTING]
- **Effort**: 5 hours
- **Dependencies**: Task 4 (training data schema)
- **Research Inputs**: specs/008_implement_python_side_formula_generator/reports/01_formula-generator.md
- **Artifacts**: plans/01_formula-generator-plan.md (this file)
- **Standards**: plan-format.md, status-markers.md, artifact-management.md, tasks.md
- **Type**: python
- **Lean Intent**: false

## Overview

Build a Python formula generator module (`src/bimodal_harness/formula/`) that provides three capabilities: (1) an algebraic AST type hierarchy mirroring the 6 Lean Formula constructors with complexity metrics, (2) exhaustive enumeration by complexity and random weighted generation, and (3) near-miss mutation operators for contrastive training pair generation. The module produces `FormulaJson` dicts compatible with the existing `schema/formula.py` validation layer while adding type-safe tree manipulation via frozen dataclasses.

### Research Integration

The research report (01_formula-generator.md) provided the complete design:
- **AST choice**: Option B (frozen dataclass tree with `to_json()`/`from_json()`) over pure dict, for type-safe tree traversal and recursive generators.
- **Complexity metric**: Mirrors Lean `Formula.complexity` exactly (node count). Primary bound for enumeration.
- **Enumeration strategy**: Catalan-number-style decomposition splitting complexity budget across children. Exhaustive up to complexity 6-7 for small atom sets; random sampling above.
- **Random generation**: Top-down stochastic with configurable operator weights and leaf-probability schedule `1/(c+1)`.
- **Mutation operators**: 10 operators identified (flip_operator, flip_temporal_direction, weaken_antecedent, strengthen_antecedent, change_atom, add_box, remove_box, negate_guard, swap_children, drop_modal).
- **File layout**: New `formula/` package separate from `schema/` (preserves separation of concerns).

### Prior Plan Reference

No prior plan.

### Roadmap Alignment

No ROADMAP.md found.

## Goals & Non-Goals

**Goals**:
- Implement 6 frozen dataclasses (`Atom`, `Bot`, `Imp`, `Box`, `Untl`, `Snce`) with `to_json()`/`from_json()` round-tripping
- Implement 4 complexity metrics (`complexity`, `modal_depth`, `temporal_depth`, `imp_count`) matching Lean definitions exactly
- Implement exhaustive enumeration by complexity over a configurable atom set
- Implement random formula generation with weighted operator sampling
- Implement 10 near-miss mutation operators for contrastive pair generation
- Achieve full test coverage with cross-validation against Lean metric definitions

**Non-Goals**:
- Z3 semantic labeling of generated formulas (deferred to task 19)
- Distribution control via rejection sampling or stratified generation (can be added later)
- Modifying the existing `schema/formula.py` validator
- GPU-dependent operations or neural network integration

## Risks & Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Combinatorial explosion at high complexity | M | H | Cap exhaustive enumeration at complexity 8; use generators (lazy iteration) throughout |
| Metric mismatch with Lean definitions | H | L | Unit tests with hand-computed values; cross-reference Lean source comments |
| Mutation operators producing semantically equivalent formulas | M | M | Accept syntactic mutations only; semantic filtering deferred to Z3 task |
| Deep recursion on complex formulas | M | L | Use itertools-based iteration; set max_depth guards on recursive functions |

## Implementation Phases

**Dependency Analysis**:
| Wave | Phases | Blocked by |
|------|--------|------------|
| 1 | 1 | -- |
| 2 | 2, 3 | 1 |
| 3 | 4 | 2, 3 |

Phases within the same wave can execute in parallel.

### Phase 1: AST Types and Complexity Metrics [COMPLETED]

**Goal**: Create the foundational `formula/` package with 6 frozen dataclass node types, a `FormulaNode` union type, `to_json()`/`from_json()` serialization, and 4 metric functions mirroring Lean.

**Tasks**:
- [ ] Create `src/bimodal_harness/formula/__init__.py` with public API exports
- [ ] Create `src/bimodal_harness/formula/ast.py` with 6 frozen dataclasses (`Atom`, `Bot`, `Imp`, `Box`, `Untl`, `Snce`)
- [ ] Define `FormulaNode = Atom | Bot | Imp | Box | Untl | Snce` union type
- [ ] Implement `to_json()` method on each dataclass returning `FormulaJson` dict
- [ ] Implement `from_json(data: FormulaJson) -> FormulaNode` classmethod for round-tripping
- [ ] Implement `complexity(f)`, `modal_depth(f)`, `temporal_depth(f)`, `imp_count(f)` as module-level functions using structural pattern matching
- [ ] Implement `top_operator(f) -> str` returning the GoalCategory name for PatternKey compatibility
- [ ] Create `tests/test_formula/__init__.py`
- [ ] Create `tests/test_formula/test_ast.py` with unit tests for all 6 constructors, round-trip serialization, and metric functions on known formulas
- [ ] Verify `validate_formula_json(node.to_json())` returns True for all generated nodes

**Timing**: 1.5 hours

**Depends on**: none

**Files to modify**:
- `src/bimodal_harness/formula/__init__.py` - new package init with exports
- `src/bimodal_harness/formula/ast.py` - AST types, serialization, metrics
- `tests/test_formula/__init__.py` - new test package
- `tests/test_formula/test_ast.py` - AST and metrics tests

**Verification**:
- `pytest tests/test_formula/test_ast.py` passes
- Round-trip: `from_json(node.to_json()) == node` for all constructor types
- Metrics match hand-computed values for `imp(atom("p"), box(atom("q")))`: complexity=4, modal_depth=1, temporal_depth=0, imp_count=1
- `ruff check src/bimodal_harness/formula/` passes
- `mypy src/bimodal_harness/formula/` passes

---

### Phase 2: Exhaustive Enumerator and Random Generator [COMPLETED]

**Goal**: Implement exhaustive enumeration of all formulas at a given complexity level over a configurable atom set, plus a random formula generator with weighted operator sampling.

**Tasks**:
- [ ] Create `src/bimodal_harness/formula/generator.py`
- [ ] Implement `enumerate_by_complexity(n: int, atoms: list[str]) -> Iterator[FormulaNode]` using Catalan-style decomposition
- [ ] Implement `enumerate_up_to_complexity(max_n: int, atoms: list[str]) -> Iterator[FormulaNode]` convenience wrapper
- [ ] Implement `random_formula(max_complexity: int, atoms: list[str], rng: random.Random, *, op_weights: dict[str, float] | None = None) -> FormulaNode`
- [ ] Implement leaf-probability schedule: `1/(remaining_budget + 1)` for balanced generation
- [ ] Add `count_formulas(n: int, num_atoms: int) -> int` helper for expected formula counts
- [ ] Create `tests/test_formula/test_generator.py` with enumeration count tests and random generation property tests
- [ ] Test: complexity-1 over 2 atoms yields exactly 3 formulas (bot, atom_p, atom_q)
- [ ] Test: all enumerated formulas have exactly the requested complexity
- [ ] Test: random_formula always returns formulas with complexity <= max_complexity

**Timing**: 1.5 hours

**Depends on**: 1

**Files to modify**:
- `src/bimodal_harness/formula/generator.py` - enumerator and random generator
- `src/bimodal_harness/formula/__init__.py` - add generator exports
- `tests/test_formula/test_generator.py` - enumeration and generation tests

**Verification**:
- `pytest tests/test_formula/test_generator.py` passes
- `enumerate_by_complexity(1, ["p", "q"])` yields exactly 3 formulas
- `enumerate_by_complexity(2, ["p", "q"])` yields correct count (verify by hand: 3 binary ops * 3 * 3 partitions + 3 unary = 12 formulas)
- All enumerated formulas pass `validate_formula_json(f.to_json())`
- Random generator respects complexity budget across 1000 samples

---

### Phase 3: Near-Miss Mutation Operators [COMPLETED]

**Goal**: Implement 10 mutation operators that produce syntactically valid formulas differing minimally from the input, for contrastive training pair generation.

**Tasks**:
- [ ] Create `src/bimodal_harness/formula/mutator.py`
- [ ] Implement tree position collection: `collect_positions(f: FormulaNode) -> list[tuple[tuple[int, ...], FormulaNode]]` to find mutable subtrees with path coordinates
- [ ] Implement `rebuild_at(f: FormulaNode, path: tuple[int, ...], replacement: FormulaNode) -> FormulaNode` for non-destructive tree surgery
- [ ] Implement 10 mutation operators as functions: `flip_operator`, `flip_temporal_direction`, `weaken_antecedent`, `strengthen_antecedent`, `change_atom`, `add_box`, `remove_box`, `negate_guard`, `swap_children`, `drop_modal`
- [ ] Implement `mutate(f: FormulaNode, rng: random.Random, *, operators: list[str] | None = None) -> FormulaNode` that samples a random compatible mutation
- [ ] Implement `generate_contrastive_pair(f: FormulaNode, rng: random.Random) -> tuple[FormulaNode, FormulaNode]` returning (original, mutant)
- [ ] Create `tests/test_formula/test_mutator.py` with tests for each mutation operator
- [ ] Test: every mutation produces a valid formula (passes `validate_formula_json`)
- [ ] Test: mutations on complex formulas produce syntactically distinct outputs

**Timing**: 1.5 hours

**Depends on**: 1

**Files to modify**:
- `src/bimodal_harness/formula/mutator.py` - mutation operators and contrastive pair generation
- `src/bimodal_harness/formula/__init__.py` - add mutator exports
- `tests/test_formula/test_mutator.py` - mutation operator tests

**Verification**:
- `pytest tests/test_formula/test_mutator.py` passes
- Each of the 10 mutation operators is tested independently
- All mutated formulas pass `validate_formula_json(mutant.to_json())`
- `mutate()` never raises on valid input formulas of complexity >= 2
- At least 8 of 10 operators produce a formula different from the input on `imp(atom("p"), box(untl(atom("q"), atom("r"))))`

---

### Phase 4: Integration Tests and Package Verification [NOT STARTED]

**Goal**: Add cross-module integration tests, verify package exports, and confirm compatibility with the existing `schema/formula.py` validation layer.

**Tasks**:
- [ ] Add integration test: generate N random formulas, mutate each, verify both original and mutant pass `validate_formula_json`
- [ ] Add integration test: enumerate all complexity-4 formulas over 2 atoms, verify count, verify all have correct complexity via `complexity()` function
- [ ] Add integration test: `from_json(to_json(f)) == f` for 100 random formulas
- [ ] Add integration test: `formula_json_to_pretty(f.to_json())` produces valid strings for generated formulas
- [ ] Verify `__init__.py` exports all public API: `Atom, Bot, Imp, Box, Untl, Snce, FormulaNode, complexity, modal_depth, temporal_depth, imp_count, enumerate_by_complexity, random_formula, mutate, generate_contrastive_pair`
- [ ] Run full test suite: `pytest tests/test_formula/ -v`
- [ ] Run `ruff check src/bimodal_harness/formula/` and `mypy src/bimodal_harness/formula/`

**Timing**: 0.5 hours

**Depends on**: 2, 3

**Files to modify**:
- `tests/test_formula/test_integration.py` - cross-module integration tests
- `src/bimodal_harness/formula/__init__.py` - finalize public exports

**Verification**:
- `pytest tests/test_formula/ -v` all green
- `ruff check src/bimodal_harness/formula/` reports 0 issues
- `mypy src/bimodal_harness/formula/` reports 0 errors
- Full project test suite still passes: `pytest tests/ -v`

## Testing & Validation

- [ ] Unit tests for all 6 AST constructors (construction, equality, hashing)
- [ ] Round-trip tests: `from_json(to_json(f)) == f` for all constructor types
- [ ] Metric tests against hand-computed values matching Lean definitions
- [ ] Enumeration count tests for complexity 1-4 over 2-atom sets
- [ ] Random generation respects complexity budget (1000 samples)
- [ ] Each mutation operator produces valid, distinct formulas
- [ ] Integration: generated formulas pass `validate_formula_json`
- [ ] Integration: generated formulas render via `formula_json_to_pretty`
- [ ] Linting: ruff clean, mypy clean

## Artifacts & Outputs

- `src/bimodal_harness/formula/__init__.py` - Package init with public API
- `src/bimodal_harness/formula/ast.py` - AST types, serialization, metrics
- `src/bimodal_harness/formula/generator.py` - Enumerator and random generator
- `src/bimodal_harness/formula/mutator.py` - 10 mutation operators
- `tests/test_formula/__init__.py` - Test package init
- `tests/test_formula/test_ast.py` - AST and metrics tests
- `tests/test_formula/test_generator.py` - Generator tests
- `tests/test_formula/test_mutator.py` - Mutation operator tests
- `tests/test_formula/test_integration.py` - Cross-module integration tests

## Rollback/Contingency

The `formula/` package is entirely new with no modifications to existing code. Rollback is straightforward: remove `src/bimodal_harness/formula/` and `tests/test_formula/` directories. No existing module is modified, so reverting has zero impact on the rest of the codebase.
