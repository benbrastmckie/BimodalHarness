# Teammate A Findings: Primary Approach — Comprehensive Task List

**Task**: 1 — Implement AlphaZero proof search training harness
**Teammate**: A (Primary Angle)
**Date**: 2026-05-29
**Confidence**: HIGH

---

## Key Findings

### Source Document Analysis

Three primary sources inform this task decomposition:

1. **Task Decomposition Plan** (`01_task-decomposition.md`): Defines 6 phases for the BimodalLogic project, focused on Lean-side infrastructure. The plan targets the BimodalLogic repo but the training harness Python code should live in BimodalHarness.

2. **Team Research Report** (`02_team-research.md`): Reveals that the ModelChecker is semantically incompatible with the ProofChecker (7 divergences, 4 critical). Recommends a three-tier corrective signal strategy: (1) Lean-native countermodels, (2) standalone Z3 generator, (3) full ModelChecker update.

3. **Technical Memo** (`03-technical_memo.typ`): Establishes the Logos vision — dual verification architecture where ProofChecker provides positive RL signal (proof certificates) and ModelChecker provides corrective signal (countermodels). Stage 1 commercialization: sell verified synthetic training data to frontier labs.

### Architecture Split

The BimodalHarness repo should contain all Python-side ML infrastructure. The Lean-side work (formula enumeration, dataset generation, tableau traces) lives in BimodalLogic. The ModelChecker refactoring lives in `Logos/ModelChecker/code/src/model_checker/theory_lib/bimodal/`.

Key codebase facts:
- **ProofChecker (Lean 4 v4.27.0-rc1)**: 42 BX axiom constructors + 7 inference rules; `DecisionProcedure.lean` returns `DecisionResult` (valid proof | invalid countermodel | timeout); `SuccessPatterns.lean` implements shallow value function; `ProofSearch/Core.lean` has IDDFS + best-first search
- **ModelChecker (Python/Z3)**: Only has G/H/Box operators — missing Until/Since (22 of 42 axioms untestable); uses fixed integer times, binary task relation, single frame class
- **Existing countermodel extraction**: `CountermodelExtraction.lean` produces `SimpleCountermodel` (atom-level only, not full task-frame structure)

### Task Scope for BimodalHarness

The BimodalHarness repo needs:
1. **Project scaffolding** — Python package structure, dependencies, CI
2. **Data pipeline** — Lean-to-Python bridge, dataset extraction, format conversion
3. **Model training** — Value network, policy network, training loops
4. **Search infrastructure** — Best-first search, MCTS, AND/OR tree management
5. **Evaluation** — Benchmarks, metrics, comparison to baselines
6. **ModelChecker alignment** — Until/Since operators, frame classes, ternary task relation
7. **Integration** — Connecting all components into the dual verification training pipeline

---

## Recommended Task List

### Layer 0: Project Foundation

#### Task 1. Initialize Python project structure
- **Description**: Set up BimodalHarness as a Python package with pyproject.toml, src layout, pytest configuration, CI pipeline, and development dependencies (PyTorch, numpy, etc.).
- **Task Type**: python
- **Effort**: S
- **Dependencies**: None

#### Task 2. Define training data schema
- **Description**: Design the JSON/Parquet schema for training data: (formula, label, proof_trace_or_countermodel, difficulty_metrics, PatternKey_features). Must be extensible for the full Logos operator set, multiple frame classes, and rich countermodels.
- **Task Type**: python
- **Effort**: M
- **Dependencies**: None

### Layer 1: Lean Bridge & Data Extraction

#### Task 3. Validate Python-Lean bridge
- **Description**: Test LeanDojo-v2, lean-interact, and PyPantograph against the BimodalLogic project (Lean v4.27.0-rc1). Determine which bridge(s) can load the ProofChecker, send tactic steps, receive goal states, and handle the import graph. Produce latency benchmarks.
- **Task Type**: python
- **Effort**: L
- **Dependencies**: Task 1

#### Task 4. Build formula export pipeline from Lean
- **Description**: Create a Python script that invokes the Lean `decide` API (via bridge or compiled executable) on enumerated formulas and exports (formula, DecisionResult, proof_trace, countermodel) tuples in the training data schema. Requires coordination with BimodalLogic's FormulaEnumerator.
- **Task Type**: python
- **Effort**: L
- **Dependencies**: Task 2, Task 3

#### Task 5. Extract training data from existing proofs
- **Description**: Use LeanDojo tracing to extract (goal_state, tactic, result) pairs from the ~2,519 theorem/lemma declarations in BimodalLogic/Theories/Bimodal/. Produce a supervised dataset of human-written proof traces.
- **Task Type**: python
- **Effort**: M
- **Dependencies**: Task 3

#### Task 6. Implement PatternKey feature extractor in Python
- **Description**: Port the PatternKey feature extraction from SuccessPatterns.lean to Python. Extract modalDepth, temporalDepth, impCount, complexity, topOperator from formula ASTs for use as neural network input features.
- **Task Type**: python
- **Effort**: M
- **Dependencies**: Task 2

### Layer 2: Value Network

#### Task 7. Implement value network (proof-progress predictor)
- **Description**: Build a PyTorch MLP that takes PatternKey features and predicts DerivationTree.height (steps-to-completion). Start with shallow MLP (1.5M-10M params, CPU-trainable). Include training script with configurable hyperparameters.
- **Task Type**: python
- **Effort**: L
- **Dependencies**: Task 4, Task 6

#### Task 8. Build evaluation benchmark suite
- **Description**: Create a held-out benchmark of 500-1K formulas with ground-truth provability, difficulty tier (easy/medium/hard), and DerivationTree.height. Implement evaluation metrics: nodes visited, time-to-proof, success rate. Compare against SuccessPatterns.lean baseline.
- **Task Type**: python
- **Effort**: M
- **Dependencies**: Task 4

#### Task 9. Integrate value network with Lean proof search
- **Description**: Connect the trained value network to the Lean proof search via the Python-Lean bridge. The network provides an additive bonus to the modal_search heuristic scorer. Evaluate performance vs baseline on the benchmark.
- **Task Type**: python
- **Effort**: L
- **Dependencies**: Task 7, Task 8

### Layer 3: Policy Network & Expert Iteration

#### Task 10. Implement policy network (tactic predictor)
- **Description**: Build a neural network that predicts the next tactic (from 42 axiom constructors + 7 inference rules) given a proof goal state. Options: fine-tune small LM (DeepSeek-Coder-1.3B via LoRA), GNN over formula AST, or T5-small transformer. Start with SFT on proof trace dataset.
- **Task Type**: python
- **Effort**: XL
- **Dependencies**: Task 5, Task 7

#### Task 11. Implement expert iteration training loop
- **Description**: Build the expert iteration loop: (1) use current policy + value network to guide best-first search, (2) verify proofs with Lean, (3) add verified (state, tactic) pairs to training data, (4) retrain. Manage training data accumulation across iterations.
- **Task Type**: python
- **Effort**: XL
- **Dependencies**: Task 9, Task 10

#### Task 12. Implement best-first search with neural guidance
- **Description**: Build a Python-side best-first search that uses the policy network for action selection and value network for node evaluation. Handle AND/OR tree structure (proof goals that decompose into multiple subgoals). Include search budget management and rollout limiting.
- **Task Type**: python
- **Effort**: L
- **Dependencies**: Task 9, Task 10

### Layer 4: MCTS (Conditional on Layer 3 Success)

#### Task 13. Implement AND/OR MCTS with PUCT
- **Description**: Build AlphaZero-style Monte Carlo Tree Search adapted for theorem proving with AND/OR hypergraph backup (weakest-link principle). Use policy + value networks from expert iteration as initialization. Include PUCT exploration, virtual loss for parallelization.
- **Task Type**: python
- **Effort**: XL
- **Dependencies**: Task 11, Task 12

#### Task 14. Implement online training from MCTS search trees
- **Description**: Extract training data from MCTS search trees (visit counts → improved policy targets, value estimates → improved value targets). Implement online model updates during search, analogous to AlphaZero self-play.
- **Task Type**: python
- **Effort**: L
- **Dependencies**: Task 13

### Layer 5: ModelChecker Alignment (Parallel Track)

#### Task 15. Add Until and Since operators to ModelChecker bimodal theory
- **Description**: Implement Until U(φ,ψ) and Since S(φ,ψ) temporal operators in the ModelChecker's bimodal theory (operators.py, semantic/). This addresses the most critical semantic divergence — 22 of 42 BX axioms involve Until/Since. Include Z3 constraint encoding.
- **Task Type**: python
- **Effort**: L
- **Dependencies**: Task 1

#### Task 16. Add frame class support to ModelChecker bimodal theory
- **Description**: Add Base, Dense, and Discrete frame class parameters to the ModelChecker's bimodal theory. Currently only supports effectively-discrete (integer times). Implement strict temporal quantification and rational/real time support for dense frames.
- **Task Type**: python
- **Effort**: L
- **Dependencies**: Task 15

#### Task 17. Update task relation to ternary with duration
- **Description**: Upgrade the ModelChecker's binary task(w, u) relation to the ProofChecker's ternary task_rel w d u with duration parameter. Implement nullity_identity, forward_comp, and converse constraints. Update shift-closure from ±1 Skolem to arbitrary Δ.
- **Task Type**: python
- **Effort**: M
- **Dependencies**: Task 16

#### Task 18. Build conformance test suite
- **Description**: Create a cross-validation suite that runs both the ProofChecker's decide API and the ModelChecker on 1000+ formulas, verifying agreement on provability/invalidity. Flag any semantic divergences. This validates Tiers 2 and 3 of the corrective signal strategy.
- **Task Type**: python
- **Effort**: M
- **Dependencies**: Task 17, Task 4

### Layer 6: Dual Verification Pipeline

#### Task 19. Build standalone Z3 countermodel generator (Tier 2)
- **Description**: Implement a ~500 LOC Python/Z3 script that parses formula ASTs from Lean-exported JSON, constructs Z3 constraints matching the ProofChecker's semantics, and extracts full task-frame countermodels (world histories, time intervals, task relations). This is the Tier 2 corrective signal source.
- **Task Type**: python
- **Effort**: L
- **Dependencies**: Task 4, Task 18

#### Task 20. Implement countermodel-to-tensor encoding
- **Description**: Design and implement encoding of structured countermodels (world histories, task relations, truth valuations) as training tensors. No published prior art exists — this is novel engineering. Explore graph-based, sequence-based, and feature-vector approaches.
- **Task Type**: python
- **Effort**: L
- **Dependencies**: Task 19

#### Task 21. Integrate dual verification into training pipeline
- **Description**: Connect proof certificates (positive signal) and countermodels (corrective signal) into the training loop. Implement structured negative RL signal from countermodels, curriculum design based on countermodel complexity, and adversarial training with near-miss invalid formulas.
- **Task Type**: python
- **Effort**: XL
- **Dependencies**: Task 11, Task 20

### Layer 7: Production & Publication

#### Task 22. Build training data export pipeline for frontier labs
- **Description**: Create a production pipeline that generates verified synthetic training data at scale in formats consumable by frontier AI labs (HuggingFace datasets, JSONL, Parquet). Include quality metrics, provenance tracking, and dataset versioning. This is the Stage 1 commercialization deliverable.
- **Task Type**: python
- **Effort**: L
- **Dependencies**: Task 21

#### Task 23. Write evaluation and benchmarking report
- **Description**: Produce comprehensive evaluation comparing neural-guided proof search against baselines (SuccessPatterns.lean, symbolic-only, published results). Include ablation studies, failure analysis, and learning curve analysis. Target TABLEAUX/CADE/ICML publication.
- **Task Type**: general
- **Effort**: L
- **Dependencies**: Task 11, Task 13

---

## Dependency Graph

```
Layer 0 (Foundation):
  [1] Project Setup ─────────────┐
  [2] Data Schema ───────────┐   │
                             │   │
Layer 1 (Data):              │   │
  [3] Lean Bridge ──────────(1)──┘
  [4] Formula Export ───────(2,3)
  [5] Proof Traces ─────────(3)
  [6] PatternKey Extractor──(2)
                             │
Layer 2 (Value):             │
  [7] Value Network ────────(4,6)
  [8] Benchmark Suite ──────(4)
  [9] Value Integration ────(7,8)
                             │
Layer 3 (Policy):            │
  [10] Policy Network ──────(5,7)
  [11] Expert Iteration ────(9,10)
  [12] Neural Search ───────(9,10)
                             │
Layer 4 (MCTS):              │
  [13] AND/OR MCTS ─────────(11,12)
  [14] Online Training ─────(13)
                             │
Layer 5 (ModelChecker):      │  (parallel track)
  [15] Until/Since ─────────(1)
  [16] Frame Classes ───────(15)
  [17] Ternary Task Rel ────(16)
  [18] Conformance Tests ───(17,4)
                             │
Layer 6 (Dual Verification): │
  [19] Z3 Countermodels ────(4,18)
  [20] Countermodel Encoding(19)
  [21] Dual Training ───────(11,20)
                             │
Layer 7 (Production):        │
  [22] Data Export ──────────(21)
  [23] Evaluation Report ───(11,13)
```

**Critical path**: 1 → 3 → 4 → 7 → 9 → 10 → 11 → 21 → 22

**Parallel tracks**:
- Layer 5 (ModelChecker alignment) can proceed independently of Layers 2-4
- Task 5 (proof trace extraction) can proceed independently once bridge is validated
- Task 6 (PatternKey extractor) can proceed as soon as schema is defined
- Tasks 8 and 6 can run in parallel during Layer 2

---

## Confidence Assessment

| Section | Confidence | Notes |
|---------|------------|-------|
| Layer 0 (Foundation) | HIGH | Standard project setup |
| Layer 1 (Data) | HIGH | Well-understood from research; bridge validation is the key risk |
| Layer 2 (Value) | HIGH | MLP over PatternKey features is low-risk starting point |
| Layer 3 (Policy) | MEDIUM | Architecture choices still open; expert iteration is well-established but untested in this domain |
| Layer 4 (MCTS) | MEDIUM | Conditional on Layer 3 success; AND/OR adaptation is non-trivial |
| Layer 5 (ModelChecker) | HIGH | Semantic changes are well-specified; Z3 encoding is straightforward |
| Layer 6 (Dual Verification) | MEDIUM | Countermodel-to-tensor encoding is genuinely novel |
| Layer 7 (Production) | HIGH | Standard data engineering once pipeline works |

---

## Open Issues

1. **Lean version compatibility**: LeanDojo-v2 may not support Lean v4.27.0-rc1 — bridge validation (Task 3) is the critical risk gate
2. **Formula enumerator**: Lives in BimodalLogic repo, not BimodalHarness — need coordination on export format
3. **Compute requirements**: Layers 0-2 are CPU-only; Layer 3 needs 1x 24GB GPU; Layer 4 needs A100
4. **Publication timing**: TABLEAUX 2026 deadline may drive prioritization of evaluation tasks
5. **ModelChecker refactoring**: The bimodal code is being refactored in Logos/ModelChecker — tasks 15-17 should align with that refactoring
