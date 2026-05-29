# Research Report: Extract Supervised Training Data from Existing Proofs

**Task**: 9 — Extract supervised training data from existing proofs
**Date**: 2026-05-29
**Status**: Research complete

---

## Executive Summary

The existing dataset generator (`lake exe dataset_generator`) already produces labeled
formula records with proof traces, but these traces are **summary statistics only**
(height, axioms_used, rules_applied) rather than step-by-step `(goal_state, action,
result_state)` sequences suitable for policy network training. Critically, all 888
valid records in the current deep dataset (53,979 total) have `height=0` — single-axiom
proofs via `ex_falso`, `prop_s`, or `modal_t`. The required multi-step training data must
be extracted from a different source: the **existing `DerivationTree` definitions** in
`Theories/Bimodal/Theorems/` plus re-running the search procedure with step-logging.

The recommended approach is **Option B: Step-sequence extraction from the existing
DerivationTree proof corpus** using a new `extractStepSequence` Lean function, compiled
into a new `lake exe` executable. This is fully compatible with the existing Python
ingestion pipeline and requires no external tools.

---

## 1. Existing Infrastructure Audit

### 1.1 LeanBridge (`src/bimodal_harness/lean/bridge.py`)

The `LeanBridge` class wraps `lean-interact` and provides:
- `run_command(cmd)` — REPL round-trip for arbitrary Lean commands
- `apply_tactic(proof_state, tactic)` — tactic stepping via `ProofStep`
- `run_subprocess(args)` — `lake exe` subprocess with timeout

**Status**: `lean-interact` is **not installed** in the current environment. The bridge
is functional but requires installation before REPL-path operations can be used.

### 1.2 Data Ingestion (`src/bimodal_harness/data/ingestion.py`)

Two adapters are implemented:
- `labeled_formula_to_training_record(lf)` — bridges the deprecated `data.schema` format
- `lean_export_to_training_record(data)` — direct adapter for `lake exe dataset_generator` JSONL

Both accept the `proof_trace` field as either:
- `{"rules": {...}}` — Python-internal RuleProfile dict
- `{"rules_applied": [...]}` — Lean export list of rule names

The ingestion pipeline is **ready to accept richer proof traces** once they are emitted.

### 1.3 TrainingRecord / ProofTrace (`src/bimodal_harness/schema/records.py`)

```python
@dataclass(frozen=True, slots=True)
class ProofTrace:
    height: int                   # Derivation tree depth
    rule_profile: RuleProfile     # Count of each rule type
    axioms_used: tuple[str, ...]  # Axiom constructor names used
```

The current `ProofTrace` schema captures **aggregate statistics** of a proof. It does NOT
capture the sequential `(goal_state, action, next_goal_states)` structure needed for
supervised policy training. This schema will need extension for task 9.

### 1.4 Existing Dataset Status

**`bmlogic-deep.jsonl`** (53,979 records, `max-complexity=7`, random sampling):
- 888 valid (1.6%), 51,730 invalid (95.8%), 1,361 timeout (2.5%)
- All 888 valid records have `proof_trace.height = 0`
- Axiom distribution: `ex_falso` (818), `prop_s` (53), `modal_t` (13), `modal_4` (4)

**`bmlogic-medium.jsonl`** (5,136 records, `max-complexity=5`):
- 1,284 valid (25.0%), all at height 0
- Same trivial single-axiom pattern

**Root cause**: The formula enumerator generates random/exhaustive formulas.
These are almost always invalid, and the valid ones are trivially valid
(a propositional tautology embedding). Multi-step proofs (`modus_ponens` chains,
`necessitation`) are rare in randomly-sampled formulas.

---

## 2. Lean Proof Structure Analysis

### 2.1 DerivationTree (Object-Level Proof System)

```lean
inductive DerivationTree (fc : FrameClass) : Context → Formula → Type where
  | axiom     (Γ : Context) (φ : Formula) (h : Axiom φ) (h_fc : h.minFrameClass ≤ fc)
  | assumption (Γ : Context) (φ : Formula) (h : φ ∈ Γ)
  | modus_ponens (Γ : Context) (φ ψ : Formula)
                 (d1 : DerivationTree fc Γ (φ.imp ψ)) (d2 : DerivationTree fc Γ φ)
  | necessitation (φ : Formula) (d : DerivationTree fc [] φ)
  | temporal_necessitation (φ : Formula) (d : DerivationTree fc [] φ)
  | temporal_duality (φ : Formula) (d : DerivationTree fc [] φ)
  | weakening (Γ Δ : Context) (φ : Formula) (d : DerivationTree fc Γ φ) (h : Γ ⊆ Δ)
```

Each constructor maps to one of the 7 inference rules in the 49-action space.
The `height` function computes tree depth (0 for leaves, `max+1` for binary nodes).

### 2.2 ProofTrace (DatasetGenerator.lean)

```lean
structure ProofTrace where
  height : Nat
  axioms_used : List String     -- unique axiom names used
  rules_applied : List String   -- unique rule names used (deduplicated)
```

`extractProofTrace` is a recursive tree walk that **deduplicates** axioms and rules
across the whole tree. This is useful for dataset metadata but loses step ordering
and spatial structure.

### 2.3 Existing Theorem Corpus

The `Theories/Bimodal/Theorems/` directory contains **108 `def`/`theorem`/`lemma`
declarations** that directly produce `DerivationTree` values:

| File | Topic | Key Proof Patterns |
|------|-------|--------------------|
| `Combinators.lean` | SKK, BK, KI combinators | multi-step MP chains |
| `GeneralizedNecessitation.lean` | □(φ→ψ)→(□φ→□ψ) | necessitation + MP |
| `ModalS4.lean` | S4 nested modalities | box_mono, MP chains |
| `ModalS5.lean` | S5 diamond/box | S5 + temporal + MP |
| `TemporalDerived.lean` | G/H derived forms | temporal_necessitation |
| `Propositional/{Core,Connectives,Reasoning}.lean` | Basic logic | MP, weakening chains |
| `Perpetuity/{Helpers,Principles,Bridge}.lean` | Temporal perpetuity | Complex 5+ step proofs |

These definitions are `DerivationTree` values themselves (term-mode). They can be
**walked at compile time** by a Lean extractor to yield step sequences.

Additionally, the `Metalogic/` directory contains ~2,400 theorems, but these are
**meta-level Lean propositions** (soundness, completeness, MCS properties) that use
Lean's own tactic engine (`simp`, `intro`, `apply`, `exact`), not the DerivationTree
constructors. These are **not actionable** for the DerivationTree policy network.

---

## 3. Extraction Strategies Assessment

### Option A: lean-interact REPL Stepping

**Approach**: Use `LeanBridge.apply_tactic()` to step through proofs interactively.

**Viability**: Low for this task.
- `lean-interact` is not installed.
- The REPL exposes **Lean tactic goals**, not `DerivationTree` subgoals.
- The 49-action space corresponds to `DerivationTree` constructors, not Lean tactics.
- REPL is best for formula labeling and MCTS rollouts (Tasks 13/15/16), not batch extraction.

### Option B: Step-sequence extraction from DerivationTree corpus (RECOMMENDED)

**Approach**: Write a new Lean function `extractStepSequence` that recursively walks
a `DerivationTree` and emits an ordered list of `ProofStep` records:

```lean
structure ProofStep where
  context : Context                -- assumptions available at this node
  goal : Formula                   -- formula to be proved
  rule : String                    -- "axiom"|"assumption"|"modus_ponens"|...
  axiom_name : Option String       -- axiom constructor name (for axiom rule)
  subgoals : List (Context × Formula)  -- child nodes

def extractStepSequence {fc Γ φ} (d : DerivationTree fc Γ φ) : List ProofStep
```

This is compiled into a new `lake exe proof_extractor` executable that:
1. Constructs the known theorem `DerivationTree` objects from `Theorems/`
2. Calls `extractStepSequence` on each
3. Serializes to JSONL

**Viability**: High.
- `DerivationTree` is a `Type` (not `Prop`), so it supports pattern matching
- The same tree-walk pattern is already used in `walkDerivationTree` and `extractProofTrace`
- No new external dependencies required
- Compatible with existing Python ingestion pipeline

**Expected yield from Theorems/**:
- ~108 theorem definitions, average ~5-15 proof steps = ~540-1,620 step triples
- Richer axiom distribution: `mp`, `nec`, `temp_nec`, `weakening` all represented

### Option C: Re-run decision procedure with step logging

**Approach**: Modify `DatasetGenerator.lean` to log each search node expansion as a
step record, not just the final tree.

**Viability**: Medium.
- Requires modifying `Core.lean`'s IDDFS/BestFirst to emit step trace
- Must handle failed search paths (non-proof nodes)
- Would yield many more steps but from the same trivial formula distribution
- Expert policy data = only the search paths that lead to proofs

**Expected yield**: ~5K formulas × avg 3 steps = ~15K step triples. But still
dominated by `ex_falso` single-axiom patterns unless formula generation is improved.

### Option D: LeanDojo tracing

**Approach**: Use LeanDojo's `.olean`-based proof tracing.

**Viability**: Low for this project.
- LeanDojo is not installed.
- LeanDojo is designed for Mathlib-style tactic proofs, not custom `DerivationTree` types.
- Would require significant infrastructure (Docker, trace server) with no guaranteed payoff.
- The BimodalLogic proof system is not Lean-standard — theorems are `def`s producing
  `DerivationTree` values, not `theorem` declarations with tactic proofs.

---

## 4. Data Format for Policy Network Training

### 4.1 Proposed ProofStep Record Schema

```json
{
  "step_id": "bmlogic-step-00001",
  "theorem_name": "Bimodal.Theorems.Combinators.imp_trans",
  "context": ["(A → B)", "(B → C)"],
  "goal": "(A → C)",
  "rule": "modus_ponens",
  "axiom_name": null,
  "action_index": 44,
  "subgoal_0": {"context": [...], "goal": "((A → B) → (A → C))"},
  "subgoal_1": {"context": [...], "goal": "(A → B)"},
  "proof_closed": false,
  "depth": 2
}
```

**Action index**: Maps `rule` + `axiom_name` to the 49-action space from `schema/actions.py`:
- Rules: indices 42-48 (`axiom`=42, `assumption`=43, ..., `weakening`=48)
- Axioms: indices 0-41 (when `rule == "axiom"`, the specific axiom name determines the index)

### 4.2 Goal State Representation

Goal states are `(Context, Formula)` pairs. Three representation options:

| Representation | Description | Pros | Cons |
|----------------|-------------|------|------|
| Raw pretty-print | `"(A → B) ⊢ (A → C)"` | Human-readable | No structure |
| Formula AST JSON | `{"tag": "imp", "left": ..., "right": ...}` | Structured | Large |
| Feature vector | PatternKey fields (5 integers) | Compact | Low information |

**Recommendation**: Use formula AST JSON for the goal and pretty-print strings for
context formulas. The PatternKey is already computed in the existing pipeline.

### 4.3 Matching to 49-Action Space

The policy network outputs a distribution over 49 actions. Each ProofStep provides
the **label** (which action was chosen at this node). The action index is:

```python
from bimodal_harness.schema.actions import ACTION_TO_INDEX, AXIOM_ACTIONS

def step_to_action_index(rule: str, axiom_name: str | None) -> int:
    if rule == "axiom" and axiom_name is not None:
        return ACTION_TO_INDEX[axiom_name]  # indices 0-41
    else:
        return ACTION_TO_INDEX[rule]  # indices 42-48 for rule names
```

### 4.4 Frame Class Masking

Each training step must include the frame class mask (which of the 49 actions are
valid). For Base-class proofs (all existing theorems), `BASE_MASK` applies:
37 axioms + 7 rules = 44 valid actions out of 49.

---

## 5. Scale Considerations

### 5.1 Current Data Volume

| Source | Records | Step Triples (est.) | Notes |
|--------|---------|---------------------|-------|
| `bmlogic-deep.jsonl` (valid only) | 888 | 888 | All height=0 |
| `Theorems/` DerivationTree defs | ~108 | ~540-1,620 | Multi-step |
| **Total currently extractable** | | **~1,500-2,500** | |

This is **insufficient** for supervised pretraining alone. Standard supervised
imitation learning for theorem provers requires 10K-100K examples.

### 5.2 Augmentation Strategies

1. **Higher-complexity formula generation**: Run `dataset_generator` with
   `--max-complexity 10 --max-modal-depth 3` to generate formulas requiring
   multi-step proofs. Expected: 5-20x more valid records with `height > 0`.

2. **Temporal dual augmentation**: Already supported via `--include-duals`.
   Doubles dataset size at no extra proof cost.

3. **Context variation**: For each theorem `⊢ φ`, generate variants `[ψ] ⊢ φ`
   via the `weakening` rule. Adds one step per variant but multiplies examples.

4. **Proof search step logging**: Instrument the IDDFS/BestFirst search to record
   all **explored** nodes (not just successful paths). Provides failure examples
   for contrastive training.

5. **Theorem decomposition**: Theorems like `imp_trans` decompose into sub-lemmas,
   each providing additional training data.

### 5.3 Reachability from Formula Enumeration

With `--max-complexity 10` (formulas up to complexity 10), the search produces
proofs with `modus_ponens` chains of height 3-7. Expected:
- ~2% valid rate × 10K formulas = 200 valid records
- Average height ~3 = ~600 step triples
- Still insufficient alone; combine with Theorems/ extraction

---

## 6. Implementation Plan for Task 9

### Phase 1: Lean extractor (1-2 days)

Add to `Theories/Bimodal/Automation/DataExport.lean`:

```lean
structure ProofStep where
  context : List String     -- pretty-printed context formulas
  goal : String             -- JSON AST of goal formula
  rule : String
  axiom_name : Option String
  subgoals : List (List String × String)

def extractStepSequence {fc Γ φ} (d : DerivationTree fc Γ φ) : List ProofStep
```

Add a new `lean_exe proof_extractor` in `lakefile.lean` that:
- Imports `Bimodal.Theorems`
- Enumerates the known theorem `DerivationTree` values
- Calls `extractStepSequence` on each
- Streams JSONL to stdout

### Phase 2: Python ingestion (1 day)

Add to `src/bimodal_harness/data/ingestion.py`:
- `load_proof_steps(path)` — loads step JSONL
- `ProofStepRecord` dataclass (mirrors Lean `ProofStep`)
- `step_to_action_index(rule, axiom_name)` — maps to 49-action index

### Phase 3: Dataset expansion (1 day)

Run `lake exe dataset_generator` with higher complexity and step-logging enabled:
```bash
lake exe dataset_generator -- \
  --max-complexity 8 \
  --max-modal-depth 3 \
  --max-temporal-depth 2 \
  --max-formulas 50000 \
  --output data/supervised.jsonl
```

Verify height distribution is no longer all-zero.

---

## 7. Key Risks and Mitigations

| Risk | Severity | Mitigation |
|------|----------|------------|
| Theorem extractor yields insufficient diversity | High | Combine with higher-complexity formula generation |
| `extractStepSequence` is complex to implement correctly | Medium | Start with `walkDerivationTree` pattern, which is already tested |
| Metalogic theorems (Soundness/Completeness) are not extractable | Low | These use Lean tactics, not DerivationTree — correctly excluded |
| Step sequences have different depth distributions | Medium | Curriculum learning: start with shallow proofs |
| lean-interact not installed | Low | Use subprocess path (`lake exe`) for all extraction |
| Single-axiom bias persists in augmented data | Medium | Weight training examples by tree height |

---

## 8. Answers to Research Questions

**Q1: What patterns exist in the codebase?**
The existing `ProofTrace` captures summary statistics only. The `extractProofTrace`
function in `DatasetGenerator.lean` and `walkDerivationTree` in `DataExport.lean`
provide the structural pattern to follow for step extraction.

**Q2: Which extraction approach works best?**
`lake exe`-based batch extraction of `DerivationTree` step sequences from the
Theorems/ corpus. This requires a new Lean extractor but no new dependencies.

**Q3: How to represent goal states?**
`(context_formulas_as_pretty_strings, goal_as_formula_ast_json)` pair.
The formula AST JSON format is already implemented in `Formula.toJson`.

**Q4: How to encode actions matching the 49-action space?**
Map `(rule, axiom_name)` to the `ACTION_TO_INDEX` dict from `schema/actions.py`.
Rules use indices 42-48; axioms use their specific index 0-41.

**Q5: Is 2,519 theorems × 5-10 steps enough?**
The 2,519 total theorems include ~2,400 metalogic theorems (not extractable via
DerivationTree). Only ~108 are DerivationTree definitions in `Theorems/`.
This yields ~500-1,600 step triples — insufficient alone. Must combine with:
- Higher-complexity formula generation (50K formulas → ~500 valid at height > 0)
- Temporal dual augmentation (2x)
- Context variation via weakening (3-5x)
Target: 10K-20K step triples for pretraining.

---

## File Paths Referenced

- `/home/benjamin/Projects/BimodalHarness/src/bimodal_harness/lean/bridge.py`
- `/home/benjamin/Projects/BimodalHarness/src/bimodal_harness/data/ingestion.py`
- `/home/benjamin/Projects/BimodalHarness/src/bimodal_harness/schema/records.py`
- `/home/benjamin/Projects/BimodalHarness/src/bimodal_harness/schema/actions.py`
- `/home/benjamin/Projects/BimodalLogic/Theories/Bimodal/Automation/DataExport.lean`
- `/home/benjamin/Projects/BimodalLogic/Theories/Bimodal/Automation/DatasetGenerator.lean`
- `/home/benjamin/Projects/BimodalLogic/Theories/Bimodal/Automation/DatasetExport.lean`
- `/home/benjamin/Projects/BimodalLogic/Theories/Bimodal/ProofSystem/Derivation.lean`
- `/home/benjamin/Projects/BimodalLogic/Theories/Bimodal/Theorems/Combinators.lean`
- `/home/benjamin/Projects/BimodalLogic/data/bmlogic-deep.jsonl` (53,979 records)
