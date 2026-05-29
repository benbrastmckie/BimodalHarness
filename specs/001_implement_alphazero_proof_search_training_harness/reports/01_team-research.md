# Research Report: Task #1

**Task**: Implement AlphaZero proof search training harness
**Date**: 2026-05-29
**Mode**: Team Research (4 teammates)

## Summary

Four research teammates investigated the BimodalHarness training harness from complementary angles: primary task decomposition (A), alternative approaches and reusable infrastructure (B), critical gaps and blind spots (C), and strategic alignment with the Logos ecosystem (D). All teammates converged on several key conclusions:

1. **BimodalHarness is Python-only** — Lean-side tasks (formula enumeration, dataset generation) remain in BimodalLogic; this repo covers the ML training pipeline
2. **The original BimodalLogic task decomposition needs adaptation** — it was written for a Lean repo and must be re-scoped for a Python training harness
3. **Corrective signal infrastructure is essential** — the technical memo's "dual verification architecture" requires countermodel integration, not just proof-positive training
4. **Foundation tasks are missing** — project scaffolding, cross-repo interface design, data format specification, and evaluation infrastructure are absent from the original plan
5. **BimodalHarness is strategically central** — it IS the Stage 1 revenue pipeline (verified synthetic training data), not a side project

## Key Findings

### Primary Approach (from Teammate A)

Teammate A produced a comprehensive 23-task decomposition across 8 layers, derived from reading all three source documents and inspecting the BimodalLogic and ModelChecker codebases. Key structural insights:

- The ProofChecker (Lean 4 v4.27.0-rc1) has 42 BX axiom constructors + 7 inference rules, with `DecisionProcedure.lean` returning proof/countermodel/timeout results
- `SuccessPatterns.lean` already computes PatternKey features (modalDepth, temporalDepth, impCount, complexity, topOperator) — these are the neural network input features
- The ModelChecker has only G/H/Box operators — missing Until/Since (22 of 42 axioms untestable)
- Critical path: Project setup → Lean bridge → Formula export → Value network → Value integration → Policy network → Expert iteration → Dual training → Data export
- ModelChecker alignment (Until/Since, frame classes, ternary task relation) is a parallel track

### Alternative Approaches (from Teammate B)

Teammate B evaluated 5 alternative architectures and identified substantial reusable infrastructure:

- **Data-Only Interface** (no runtime Lean bridge): Viable for Phases 0-2, recommended as Phase 1 architecture with bridge added later for expert iteration
- **LeanDojo-as-Framework**: Ideal if compatible with Lean v4.27.0-rc1; bridge validation is the critical risk gate
- **Reusable from BimodalLogic**: SubformulaClosure, SuccessPatterns/PatternKey, DecisionProcedure, CountermodelExtraction, ProofSearch/Core
- **Reusable from ModelChecker**: BimodalModelIterator pattern, Z3 constraint framework, WitnessRegistry, test suite patterns
- 10-task alternative decomposition emphasizing corrective signal tasks absent from the original plan

### Gaps and Shortcomings (from Critic)

Teammate C identified 10 missing foundation/infrastructure tasks and 7 unvalidated assumptions:

- **~10 missing tasks**: Project scaffolding, cross-repo integration design, data format spec, Lean-to-Python export pipeline, conformance tests, evaluation harness, action space validation, compute plan, experiment tracking
- **Axiom count discrepancy**: 57 constructor lines in Axioms.lean vs stated "42" — needs precise enumeration as it affects neural network output dimension
- **Tier 2 Z3 scope underestimated**: ModelChecker's operators.py is 1,048 lines for a simpler fragment; standalone Z3 aligned to ProofChecker semantics is significantly more than ~500 LOC
- **Repo boundary confusion**: Original decomposition conflates Lean-side work (BimodalLogic) with Python-side work (BimodalHarness)
- **Technical memo scope**: The decomposition covers ~15% of the memo's vision, which is appropriate but should be explicit

### Strategic Horizons (from Horizons)

Teammate D assessed strategic alignment and proposed creative alternatives:

- **Production infrastructure, not experiment**: BimodalHarness should be designed for team scaling (pre-seed roadmap expects CTO + ML team)
- **Python-first formula generation**: Generate formulas in Python using operator grammar, validate with Lean — removes formula enumerator as Lean dependency
- **Near-miss mutations**: Generate contrastive training pairs from existing ~2,519 theorems by flipping operators/weakening premises
- **Semantic gap as feature**: ModelChecker/ProofChecker divergences are natural hard negatives for training
- **Benchmark as marketing asset**: No prior benchmark exists for neural theorem proving in modal logic
- **Compute constraint**: Pre-CTO work must stay in CPU-only regime; architecture decisions must accommodate this

## Synthesis

### Conflicts Resolved

| Conflict | Resolution | Reasoning |
|----------|------------|-----------|
| Task count (23 vs 10) | **25 tasks** — merged with missing infrastructure tasks | A's 23-task decomposition is comprehensive but Critic identified 10+ gaps; B's 10-task alternative is too compressed. Merged into 25 tasks that cover all angles. |
| Axiom count (42 vs 57) | **Include validation task** — enumerate precisely before neural architecture decisions | Affects output dimension of policy network; must be resolved early. Added as part of data schema task. |
| Z3 Tier 2 scope (~500 LOC vs "significantly more") | **L effort, not M** — acknowledge complexity of matching ProofChecker semantics exactly | Critic's evidence (ModelChecker operators.py = 1,048 LOC for simpler fragment) is compelling. Upgraded effort estimate. |
| Formula generation ownership (Lean vs Python) | **Both** — Lean enumerator for systematic coverage, Python generator for rapid prototyping | Horizons' Python-first suggestion is valuable for early prototyping; doesn't replace systematic Lean enumeration for production. Include both paths. |
| Data-only vs bridge-first | **Data-only first, bridge for expert iteration** — phased approach reduces risk | B's recommendation aligns with feasibility gates from original plan. Value network training doesn't need runtime bridge. |

### Gaps Identified

All four teammates identified the same meta-gap: **the original decomposition was designed for BimodalLogic (Lean) and needs adaptation for BimodalHarness (Python)**. Specific gaps now addressed in the synthesized task list:

1. Project scaffolding and CI (all teammates)
2. Cross-repo integration design (C, D)
3. Data format specification (all teammates)
4. Conformance test suite (A, C)
5. Evaluation infrastructure (A, C)
6. Experiment tracking (C)
7. Python-side formula generation (D)
8. Near-miss mutation training data (D)

### Recommendations

**Synthesized Task List for BimodalHarness** (25 tasks across 8 layers):

---

#### Layer 0: Project Foundation (3 tasks)

**Task 2. Initialize Python project structure**
- Set up pyproject.toml, src/ layout, pytest, CI pipeline, dependencies (PyTorch, numpy, Z3). Configure ruff for linting, mypy for type checking. Establish development workflow.
- Type: python | Effort: S | Dependencies: none

**Task 3. Design cross-repo integration architecture**
- Decide how BimodalHarness references BimodalLogic (git submodule, path config, exported artifacts). Define the boundary: BimodalHarness is Python-only, consumes Lean-exported data and optionally calls Lean via bridge. Document version compatibility requirements (Lean v4.27.0-rc1).
- Type: general | Effort: S | Dependencies: none

**Task 4. Define training data schema and action space**
- Design JSON/Parquet schema for (formula, label, proof_trace_or_countermodel, PatternKey_features, difficulty_metrics). Precisely enumerate the action space (resolve 42 vs 57 axiom constructor count). Schema must be extensible for full Logos operator set, multiple frame classes, and rich countermodels.
- Type: python | Effort: M | Dependencies: none

---

#### Layer 1: Data Pipeline (5 tasks)

**Task 5. Validate Python-Lean bridge options**
- Test LeanDojo-v2, lean-interact, and PyPantograph against BimodalLogic (Lean v4.27.0-rc1). Determine which can load the ProofChecker, send tactic steps, receive goal states, handle the import graph. Produce latency benchmarks. This is the critical risk gate.
- Type: python | Effort: L | Dependencies: Task 2

**Task 6. Build static data ingestion pipeline**
- Create pipeline to import pre-exported datasets from Lean (formula enumerator output, DecisionResult, countermodels). Produce PyTorch-compatible datasets in the training data schema. This is the data-only interface (no runtime bridge needed).
- Type: python | Effort: M | Dependencies: Task 4

**Task 7. Implement Python-side formula generator**
- Build a Python formula generator using the operator grammar (6 constructors: atom, bot, imp, box, untl, snce). Generate formulas by depth/complexity for rapid prototyping without Lean dependency. Include near-miss mutation generator for contrastive pairs from existing theorems.
- Type: python | Effort: M | Dependencies: Task 4

**Task 8. Extract supervised training data from existing proofs**
- Use LeanDojo tracing (or bridge) to extract (goal_state, tactic, result) pairs from ~2,519 theorem/lemma declarations in BimodalLogic. Produce supervised dataset of human-written proof traces.
- Type: python | Effort: M | Dependencies: Task 5

**Task 9. Implement PatternKey feature extractor in Python**
- Port PatternKey feature extraction from SuccessPatterns.lean to Python. Extract modalDepth, temporalDepth, impCount, complexity, topOperator from formula ASTs. These are the primary neural network input features.
- Type: python | Effort: M | Dependencies: Task 4

---

#### Layer 2: Value Network (3 tasks)

**Task 10. Implement value network (proof-progress predictor)**
- Build PyTorch MLP taking PatternKey features, predicting DerivationTree.height (steps-to-completion). Start with shallow MLP (1.5M-10M params, CPU-trainable). Include configurable hyperparameters and training script.
- Type: python | Effort: L | Dependencies: Task 6, Task 9

**Task 11. Build evaluation benchmark suite**
- Create held-out benchmark of 500-1K formulas with ground-truth provability, difficulty tier, and DerivationTree.height. Implement metrics: nodes visited, time-to-proof, success rate. Compare against SuccessPatterns.lean baseline. Design as publishable open benchmark for neural theorem proving in modal logic.
- Type: python | Effort: M | Dependencies: Task 6

**Task 12. Integrate value network with Lean proof search**
- Connect trained value network to Lean proof search via bridge. Network provides additive bonus to modal_search heuristic scorer. Evaluate performance vs baseline on benchmark. Requires runtime bridge (not data-only).
- Type: python | Effort: L | Dependencies: Task 5, Task 10, Task 11

---

#### Layer 3: Policy Network & Expert Iteration (3 tasks)

**Task 13. Implement policy network (tactic predictor)**
- Build neural network predicting next tactic (from axiom constructors + inference rules) given proof goal state. Evaluate architectures: fine-tuned small LM (LoRA), GNN over formula AST, or T5-small transformer. Start with SFT on proof trace dataset.
- Type: python | Effort: XL | Dependencies: Task 8, Task 10

**Task 14. Implement best-first search with neural guidance**
- Build Python-side best-first search using policy network for action selection, value network for node evaluation. Handle AND/OR tree structure (proof goals decomposing into subgoals). Include search budget management and rollout limiting.
- Type: python | Effort: L | Dependencies: Task 12, Task 13

**Task 15. Implement expert iteration training loop**
- Build the expert iteration loop: use current policy + value to guide search, verify proofs with Lean, add verified (state, tactic) pairs to training data, retrain. Manage training data accumulation across iterations.
- Type: python | Effort: XL | Dependencies: Task 12, Task 13

---

#### Layer 4: MCTS — Conditional on Layer 3 (2 tasks)

**Task 16. Implement AND/OR MCTS with PUCT**
- Build AlphaZero-style MCTS adapted for theorem proving with AND/OR hypergraph backup (weakest-link principle). Use policy + value networks from expert iteration. Include PUCT exploration, virtual loss for parallelization.
- Type: python | Effort: XL | Dependencies: Task 14, Task 15

**Task 17. Implement online training from MCTS search trees**
- Extract training data from MCTS search trees (visit counts → improved policy targets, value estimates → improved value targets). Implement online model updates during search, analogous to AlphaZero self-play.
- Type: python | Effort: L | Dependencies: Task 16

---

#### Layer 5: ModelChecker Alignment — Parallel Track (4 tasks)

> **Note**: These tasks modify ModelChecker code in `Logos/ModelChecker/`, not BimodalHarness. They are included because the dual verification architecture depends on them. They can be tracked here or in the ModelChecker project — clarify with user.

**Task 18. Add Until and Since operators to ModelChecker bimodal theory**
- Implement Until U(φ,ψ) and Since S(φ,ψ) in ModelChecker's bimodal theory (operators.py, semantic/). Addresses most critical semantic divergence — 22 of 42 BX axioms involve Until/Since. Include Z3 constraint encoding.
- Type: python | Effort: L | Dependencies: Task 2

**Task 19. Add frame class support to ModelChecker bimodal theory**
- Add Base, Dense, Discrete frame class parameters. Currently only supports effectively-discrete (integer times). Implement strict temporal quantification and rational/real time support for dense frames.
- Type: python | Effort: L | Dependencies: Task 18

**Task 20. Update ModelChecker task relation to ternary with duration**
- Upgrade binary task(w,u) to ternary task_rel w d u with duration parameter. Implement nullity_identity, forward_comp, converse constraints. Update shift-closure from ±1 Skolem to arbitrary Δ.
- Type: python | Effort: M | Dependencies: Task 19

**Task 21. Build cross-system conformance test suite**
- Create validation suite running both ProofChecker's decide API and ModelChecker on 1000+ formulas, verifying agreement on provability/invalidity. Flag semantic divergences. Validates Tiers 2 and 3 of corrective signal strategy.
- Type: python | Effort: M | Dependencies: Task 6, Task 20

---

#### Layer 6: Dual Verification Pipeline (3 tasks)

**Task 22. Build standalone Z3 countermodel generator (Tier 2)**
- Implement Python/Z3 module that parses formula ASTs from Lean-exported JSON, constructs Z3 constraints matching ProofChecker semantics exactly (strict temporal quantification, Until/Since, ternary task relation, three frame classes), and extracts full task-frame countermodels. This is the Tier 2 corrective signal source.
- Type: python | Effort: L | Dependencies: Task 6, Task 21

**Task 23. Implement countermodel-to-tensor encoding**
- Design encoding of structured countermodels (world histories, task relations, truth valuations) as training tensors. No published prior art — novel engineering. Explore graph-based, sequence-based, and feature-vector approaches.
- Type: python | Effort: L | Dependencies: Task 22

**Task 24. Integrate dual verification into training pipeline**
- Connect proof certificates (positive signal) and countermodels (corrective signal) into training loop. Implement structured negative RL signal from countermodels, curriculum design based on countermodel complexity, adversarial training with near-miss invalid formulas.
- Type: python | Effort: XL | Dependencies: Task 15, Task 23

---

#### Layer 7: Production & Evaluation (2 tasks)

**Task 25. Build training data export pipeline**
- Create production pipeline generating verified synthetic training data at scale in formats for frontier AI labs (HuggingFace datasets, JSONL, Parquet). Include quality metrics, provenance tracking, dataset versioning. Stage 1 commercialization deliverable.
- Type: python | Effort: L | Dependencies: Task 24

**Task 26. Set up experiment tracking and write evaluation report**
- Configure experiment tracking (W&B or MLflow), model versioning, dataset versioning. Produce comprehensive evaluation comparing neural-guided search against baselines (SuccessPatterns.lean, symbolic-only). Include ablation studies and learning curves. Target TABLEAUX/CADE publication.
- Type: python | Effort: L | Dependencies: Task 15, Task 16

---

### Dependency Graph

```
Layer 0 (Foundation):
  [2] Project Setup
  [3] Cross-Repo Design
  [4] Data Schema + Action Space

Layer 1 (Data Pipeline):
  [5]  Lean Bridge Validation ──────── (2)
  [6]  Static Data Ingestion ────────── (4)
  [7]  Python Formula Generator ──────── (4)
  [8]  Proof Trace Extraction ────────── (5)
  [9]  PatternKey Extractor ──────────── (4)

Layer 2 (Value Network):
  [10] Value Network ─────────────────── (6, 9)
  [11] Benchmark Suite ───────────────── (6)
  [12] Value-Lean Integration ────────── (5, 10, 11)

Layer 3 (Policy + ExIt):
  [13] Policy Network ───────────────── (8, 10)
  [14] Neural Best-First Search ─────── (12, 13)
  [15] Expert Iteration Loop ────────── (12, 13)

Layer 4 (MCTS):
  [16] AND/OR MCTS ──────────────────── (14, 15)
  [17] Online Training ──────────────── (16)

Layer 5 (ModelChecker — parallel):
  [18] Until/Since Operators ────────── (2)
  [19] Frame Classes ────────────────── (18)
  [20] Ternary Task Relation ────────── (19)
  [21] Conformance Tests ────────────── (6, 20)

Layer 6 (Dual Verification):
  [22] Z3 Countermodel Gen ──────────── (6, 21)
  [23] Countermodel Encoding ────────── (22)
  [24] Dual Training Integration ────── (15, 23)

Layer 7 (Production):
  [25] Data Export Pipeline ─────────── (24)
  [26] Experiment Tracking + Report ─── (15, 16)
```

**Critical path**: 2 → 5 → 12 → 13 → 15 → 24 → 25

**Parallel tracks**:
- Layer 5 (ModelChecker alignment) proceeds independently of Layers 2-4
- Tasks 6, 7, 9 can run in parallel once schema (Task 4) is defined
- Task 11 (benchmark) is independent once data ingestion works
- Tasks 3, 4 can run in parallel with Task 2

### Open Questions for User

1. **ModelChecker tasks (18-21)**: Should these be tracked in BimodalHarness or in the Logos/ModelChecker project? They modify ModelChecker code, not BimodalHarness code.
2. **Lean-side coordination**: Should BimodalHarness have tasks for coordinating with BimodalLogic (e.g., requesting formula enumerator output), or is that managed separately?
3. **Priority**: Is the immediate goal a value-network-beats-baseline paper (Layers 0-2), or the full dual verification pipeline (all layers)?
4. **Compute**: Layers 0-2 are CPU-only. Layer 3+ needs GPU. Is GPU available now, or should the task ordering account for a pre-GPU constraint?

## Teammate Contributions

| Teammate | Angle | Status | Confidence |
|----------|-------|--------|------------|
| A | Primary task decomposition | completed | high |
| B | Alternative approaches & reuse | completed | high |
| C | Critic — gaps & blind spots | completed | high |
| D | Strategic horizons | completed | high |

## References

- BimodalLogic task decomposition: `/home/benjamin/Projects/BimodalLogic/specs/201_alphazero_proof_search_harness/plans/01_task-decomposition.md`
- BimodalLogic team research: `/home/benjamin/Projects/BimodalLogic/specs/201_alphazero_proof_search_harness/reports/02_team-research.md`
- Technical memo: `/home/benjamin/Projects/Logos/Vision/shared/strategy/01-overview/03-technical_memo.typ`
- ModelChecker bimodal: `/home/benjamin/Projects/Logos/ModelChecker/code/src/model_checker/theory_lib/bimodal/`
- BimodalLogic ProofChecker: `/home/benjamin/Projects/BimodalLogic/Theories/Bimodal/`
