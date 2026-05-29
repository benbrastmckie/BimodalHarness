# Teammate C Findings: Critic Analysis

**Task**: 1 — Implement AlphaZero proof search training harness
**Angle**: Critic — Gaps, blind spots, unvalidated assumptions
**Date**: 2026-05-29
**Confidence Level**: HIGH

---

## Key Findings

### 1. The Task Decomposition Was Written for BimodalLogic, Not BimodalHarness

The task decomposition plan (01_task-decomposition.md) was written in the context of the BimodalLogic repository, targeting Lean 4 files inside `Theories/Bimodal/`. The BimodalHarness repo is an empty repository with only a README and specs directory. The decomposition assumes deliverables like `Theories/Bimodal/Automation/FormulaEnumerator.lean` — but BimodalHarness has no Lean project, no lakefile, no Theories directory.

**Critical question**: Is BimodalHarness a **Python-only** repo that talks to BimodalLogic remotely (via a bridge), or does it include its own Lean code? The task decomposition conflates work that belongs in BimodalLogic (Lean modules) with work that belongs in BimodalHarness (Python ML pipeline). Task creation must clearly separate:
- **Lean-side tasks** (formula enumeration, data export) → belong in BimodalLogic or need explicit cross-repo coordination
- **Python-side tasks** (model training, bridge integration, MCTS) → belong in BimodalHarness
- **Interface tasks** (data format specification, bridge validation) → bridge both repos

### 2. The ModelChecker Semantic Incompatibility Is Partially Resolved but Not Fully Addressed

The Round 2 team research correctly identifies 7 semantic divergences between ProofChecker and ModelChecker. The three-tier corrective signal strategy is sound. However:

- **The Tier 1 path (Lean-native `findCountermodel`) has a hidden dependency**: Exporting decision results from Lean to Python requires a serialization pipeline that does not exist yet. The decomposition mentions JSON export but no task explicitly covers building the Lean-to-Python data export pipeline.
- **The Tier 2 path (standalone Z3 ~500 LOC) is underestimated**: Building Z3 constraints that match the ProofChecker's exact semantics (strict temporal quantification, Until/Since, three frame classes, ternary task relation with duration, nullity, compositionality, converse) is significantly more than 500 LOC. The ModelChecker's `operators.py` is 1048 lines and only covers the simpler fragment (no Until/Since, one frame class, binary task relation).
- **No task covers the conformance test suite**: The research recommends a cross-validation suite of 1000+ formulas to verify agreement between signal sources and ProofChecker. This is not in the decomposition.

### 3. Missing Foundation Tasks for BimodalHarness Repository

The BimodalHarness repo has zero infrastructure. Before any ML work can begin, several foundation tasks are missing from the decomposition:

1. **Project scaffolding**: Python project setup (pyproject.toml/setup.py, directory structure, CI, linting, testing infrastructure)
2. **Dependency management**: PyTorch, LeanDojo, Z3, HuggingFace datasets — version pinning and compatibility matrix
3. **Data format specification**: Formal schema for (formula, label, proof_trace, countermodel, difficulty_metrics) tuples that serves as the contract between Lean-side data generation and Python-side consumption
4. **Lean interop design**: How does BimodalHarness reference BimodalLogic? Git submodule? Path reference? Package dependency? This must be decided before any bridge work.

### 4. Axiom Count Discrepancy

The task decomposition and Round 1 research state "42 axiom constructors + 7 inference rules." Code inspection shows:
- **57 axiom constructor lines** in Axioms.lean (including frame class variants: Base, Dense, Discrete constructors, plus `minFrameClass` definitions)
- **7 derivation rules** in Derivation.lean (axiom, assumption, modus_ponens, necessitation, temporal_necessitation, temporal_duality, weakening)

The 42 vs 57 discrepancy may be because some of those 57 lines are the `minFrameClass` definitions, not separate axiom constructors. But this needs precise validation — the action space size directly affects neural network architecture (output dimension).

### 5. The Technical Memo's Vision Exceeds the Training Harness Scope

The technical memo describes a full Logos system with:
- Abduction-deduction-induction reasoning cycle
- Personal assistants with semantic model construction
- Domain partnerships (medical, legal, financial)
- Scalable oversight architecture
- Three commercialization stages

The training harness (task 201) only covers **one component** of Stage 1 (selling verified training data). Tasks for the broader Logos vision — including the ModelChecker semantic alignment needed for the "dual verification architecture" described in the memo — are not covered in the decomposition. This is appropriate scoping if intentional, but should be explicitly acknowledged: the decomposition covers ~15% of the technical memo's vision.

### 6. The Python ModelChecker Bimodal Refactoring Is Incomplete

The bimodal theory in `/home/benjamin/Projects/Logos/ModelChecker/code/src/model_checker/theory_lib/bimodal/` has:
- `operators.py` (1048 lines) — extensional, modal, temporal operators but **no Until/Since**
- `semantic/witness_registry.py` — witness predicate tracking
- `semantic/witness_constraints.py` — constraint generation
- `iterate.py`, `examples.py` — basic iteration and examples

This confirms the Round 2 research finding: the ModelChecker cannot currently serve as a corrective signal source for formulas involving Until/Since (22 of the ~42 axiom constructors). The Tier 3 path (updating ModelChecker) is a substantial undertaking that should be a separate task with its own research cycle.

### 7. Dependencies Are Understated in the Decomposition

The dependency graph shows Phase 1 as having no dependencies, but this ignores:
- The formula enumerator (Phase 1) assumes `SubformulaClosure/` and `Decidability/` modules are stable and correct — any bugs discovered during implementation would block progress
- Phase 2 (Python-Lean bridge) depends on the specific Lean toolchain version (v4.27.0-rc1) being supported by bridge libraries — this is an **external dependency** that could fail validation
- Phase 4 (value network) integration point assumes `modal_search` in `ProofSearch/Strategies.lean` has a pluggable scorer architecture — code inspection shows it uses a simple `heuristic` field on `SearchNode`, so integration may require refactoring the search infrastructure

---

## Gaps Identified (Missing Tasks)

1. **Project scaffolding for BimodalHarness** — Python project setup, CI, linting, testing
2. **Cross-repo integration design** — How BimodalHarness references/depends on BimodalLogic
3. **Data format specification** — Formal schema contract between Lean data generation and Python consumption
4. **Lean-to-Python export pipeline** — Serialization of `DecisionResult`, `DerivationTree`, `PatternKey` to JSON
5. **Conformance test suite** — Validate agreement between countermodel sources and ProofChecker
6. **ModelChecker semantic alignment** — Update bimodal operators to add Until/Since, ternary task relation, frame classes (prerequisite for dual verification architecture)
7. **Precise action space enumeration** — Resolve 42 vs actual count, document which axioms parameterize over formulas vs fixed
8. **Hardware/compute procurement plan** — Phase 2+ requires GPU; where does this run? Cloud? Local? What budget?
9. **Evaluation infrastructure** — Beyond the held-out benchmark: how do we measure "the value network beats SuccessPatterns.lean"? Need a standardized evaluation harness.
10. **Documentation and reproducibility** — Experiment tracking (W&B/MLflow), model versioning, dataset versioning

---

## Assumptions to Validate

| Assumption | Source | Risk if Wrong |
|------------|--------|---------------|
| LeanDojo-v2 supports Lean v4.27.0-rc1 | Research report | Bridge is unusable; need to wait or use alternative |
| 10K-50K labeled formulas achievable | Research estimate | Insufficient training data; may need different generation strategy |
| `DerivationTree.height` is a good value label | Research report | Network optimizes for wrong target; may need log-height or classification |
| CPU-only training viable for Phase 1-2 | Research report | Need GPU sooner than planned; budget impact |
| BimodalHarness is the right repo for this work | Implicit assumption | May need to work directly in BimodalLogic for Lean-side tasks |
| `SubformulaClosure/` provides bounded generation | Research report | May need new enumeration infrastructure |
| The heuristic field in SearchNode is extensible | Code structure | May require ProofSearch refactoring before neural integration |

---

## Questions That Should Be Asked

1. **Which repo owns which tasks?** Are Lean-side tasks (formula enumeration, data export, ProofSearch integration) done in BimodalLogic with results consumed by BimodalHarness? Or does BimodalHarness contain its own Lean code?

2. **What is the minimum viable product?** The decomposition targets a full AlphaZero pipeline. What is the simplest thing that demonstrates value? A value network that beats SuccessPatterns.lean on the benchmark would be sufficient for a paper submission — everything after that is incremental.

3. **Is the ModelChecker alignment a prerequisite or nice-to-have?** The technical memo's "dual verification architecture" requires it. The training pipeline doesn't (Tier 1/2 suffice). Which goal are we optimizing for?

4. **What publication deadline drives the timeline?** TABLEAUX 2026 submission deadline would constrain which phases must complete first.

5. **How will this repo be tested?** No CI infrastructure exists. For an ML project, testing means both unit tests (data pipeline correctness) and integration tests (end-to-end training loop on small data).

6. **Should the formula enumerator live in Lean or Python?** The decomposition assumes Lean, but a Python enumerator that constructs formulas syntactically and calls the Lean decider via bridge might be faster to develop and more flexible.

---

## Summary Assessment

The task decomposition plan is **well-structured but incomplete for the BimodalHarness context**. It was designed for BimodalLogic and needs adaptation:
- Add foundation tasks (scaffolding, cross-repo design, data format spec)
- Separate Lean-side vs Python-side work clearly
- Add missing infrastructure tasks (export pipeline, conformance tests, evaluation harness)
- Acknowledge that the decomposition covers the training pipeline portion of the technical memo's vision, not the full Logos system

The phased approach with feasibility gates is sound. The main blind spot is the gap between "we have research findings" and "we have a working codebase" — the infrastructure tasks needed to bridge that gap are systematically missing.
