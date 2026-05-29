---
next_project_number: 24
---

# TODO

## Tasks

### 23. Set up experiment tracking and write evaluation report
- **Effort**: L
- **Status**: [NOT STARTED]
- **Task Type**: python
- **Dependencies**: Task 16, Task 17

**Description**: Configure experiment tracking (W&B or MLflow), model versioning, dataset versioning. Produce comprehensive evaluation comparing neural-guided search against baselines. Include ablation studies and learning curves. Target TABLEAUX/CADE publication. NOTE: Requires GPU (depends on Tasks 16 and 17).

---

### 22. Build training data export pipeline
- **Effort**: L
- **Status**: [NOT STARTED]
- **Task Type**: python
- **Dependencies**: Task 21

**Description**: Create production pipeline generating verified synthetic training data at scale in formats for frontier AI labs (HuggingFace datasets, JSONL, Parquet). Include quality metrics, provenance tracking, dataset versioning. Stage 1 commercialization deliverable.

---

### 21. Integrate dual verification into training pipeline
- **Effort**: XL
- **Status**: [NOT STARTED]
- **Task Type**: python
- **Dependencies**: Task 16, Task 20

**Description**: Connect proof certificates (positive signal) and countermodels (corrective signal) into training loop. Implement structured negative RL signal, curriculum design based on countermodel complexity, adversarial training with near-miss invalid formulas. NOTE: Requires GPU (depends on Task 16).

---

### 20. Implement countermodel-to-tensor encoding
- **Effort**: L
- **Status**: [NOT STARTED]
- **Task Type**: python
- **Dependencies**: Task 19

**Description**: Design encoding of structured countermodels (world histories, task relations, truth valuations) as training tensors. No published prior art — novel engineering. Explore graph-based, sequence-based, and feature-vector approaches.

---

### 19. Build standalone Z3 countermodel generator (Tier 2)
- **Effort**: L
- **Status**: [NOT STARTED]
- **Task Type**: python
- **Dependencies**: Task 7

**Description**: Implement Python/Z3 module parsing formula ASTs from Lean-exported JSON, constructing Z3 constraints matching ProofChecker semantics (strict temporal quantification, Until/Since, ternary task relation, three frame classes), extracting full task-frame countermodels. Tier 2 corrective signal source.

---

### 18. Implement online training from MCTS search trees
- **Effort**: L
- **Status**: [NOT STARTED]
- **Task Type**: python
- **Dependencies**: Task 17

**Description**: Extract training data from MCTS search trees (visit counts → improved policy targets, value estimates → improved value targets). Implement online model updates during search. NOTE: Requires GPU — de-prioritized until GPU available.

---

### 17. Implement AND/OR MCTS with PUCT
- **Effort**: XL
- **Status**: [NOT STARTED]
- **Task Type**: python
- **Dependencies**: Task 15, Task 16

**Description**: Build AlphaZero-style MCTS adapted for theorem proving with AND/OR hypergraph backup (weakest-link principle). Use policy + value networks from expert iteration. Include PUCT exploration, virtual loss. NOTE: Requires GPU — conditional on Layer 3 completion.

---

### 16. Implement expert iteration training loop
- **Effort**: XL
- **Status**: [NOT STARTED]
- **Task Type**: python
- **Dependencies**: Task 13, Task 14

**Description**: Build expert iteration loop: use current policy + value to guide search, verify proofs with Lean, add verified (state, tactic) pairs to training data, retrain. Manage training data accumulation. NOTE: Requires GPU — de-prioritized until GPU available.

---

### 15. Implement best-first search with neural guidance
- **Effort**: L
- **Status**: [NOT STARTED]
- **Task Type**: python
- **Dependencies**: Task 13, Task 14

**Description**: Build Python-side best-first search using policy network for action selection, value network for node evaluation. Handle AND/OR tree structure. Include search budget management. NOTE: Requires GPU — de-prioritized until GPU available.

---

### 14. Implement policy network (tactic predictor)
- **Effort**: XL
- **Status**: [NOT STARTED]
- **Task Type**: python
- **Dependencies**: Task 9, Task 11

**Description**: Build neural network predicting next tactic from axiom constructors + inference rules given proof goal state. Evaluate architectures: fine-tuned small LM (LoRA), GNN over formula AST, T5-small. Start with SFT on proof trace dataset. NOTE: Requires GPU for training — de-prioritized until GPU available.

---

### 13. Integrate value network with Lean proof search
- **Effort**: L
- **Status**: [NOT STARTED]
- **Task Type**: python
- **Dependencies**: Task 6, Task 11, Task 12

**Description**: Connect trained value network to Lean proof search via bridge. Network provides additive bonus to modal_search heuristic scorer. Evaluate performance vs baseline on benchmark. Requires runtime bridge.

---

### 12. Build evaluation benchmark suite
- **Effort**: M
- **Status**: [NOT STARTED]
- **Task Type**: python
- **Dependencies**: Task 7

**Description**: Create held-out benchmark of 500-1K formulas with ground-truth provability, difficulty tier, DerivationTree.height. Implement metrics: nodes visited, time-to-proof, success rate. Compare against SuccessPatterns.lean baseline. Design as publishable open benchmark.

---

### 11. Implement value network (proof-progress predictor)
- **Effort**: L
- **Status**: [NOT STARTED]
- **Task Type**: python
- **Dependencies**: Task 7, Task 10

**Description**: Build PyTorch MLP taking PatternKey features, predicting DerivationTree.height. Start with shallow MLP (1.5M-10M params, CPU-trainable). Include configurable hyperparameters and training script.

---

### 10. Implement PatternKey feature extractor in Python
- **Effort**: M
- **Status**: [PLANNED]
- **Task Type**: python
- **Dependencies**: Task 4
- **Research**: [010_implement_patternkey_feature_extractor_in_python/reports/01_patternkey-extractor.md]
- **Plan**: [010_implement_patternkey_feature_extractor_in_python/plans/01_patternkey-plan.md]

**Description**: Port PatternKey feature extraction from SuccessPatterns.lean to Python. Extract modalDepth, temporalDepth, impCount, complexity, topOperator from formula ASTs. Primary neural network input features.

---

### 9. Extract supervised training data from existing proofs
- **Effort**: M
- **Status**: [NOT STARTED]
- **Task Type**: python
- **Dependencies**: Task 6

**Description**: Use LeanDojo tracing (or bridge) to extract (goal_state, tactic, result) pairs from ~2,519 theorem/lemma declarations in BimodalLogic. Produce supervised dataset of human-written proof traces.

---

### 8. Implement Python-side formula generator
- **Effort**: M
- **Status**: [PLANNED]
- **Task Type**: python
- **Dependencies**: Task 4
- **Research**: [008_implement_python_side_formula_generator/reports/01_formula-generator.md]
- **Plan**: [008_implement_python_side_formula_generator/plans/01_formula-generator-plan.md]

**Description**: Build Python formula generator using operator grammar (6 constructors: atom, bot, imp, box, untl, snce). Generate formulas by depth/complexity for rapid prototyping. Include near-miss mutation generator for contrastive pairs.

---

### 7. Build static data ingestion pipeline
- **Effort**: M
- **Status**: [PLANNED]
- **Task Type**: python
- **Dependencies**: Task 4
- **Research**: [007_build_static_data_ingestion_pipeline/reports/01_data-ingestion.md]
- **Plan**: [007_build_static_data_ingestion_pipeline/plans/01_data-ingestion-plan.md]

**Description**: Create pipeline to import pre-exported datasets from Lean (formula enumerator output, DecisionResult, countermodels). Produce PyTorch-compatible datasets in training data schema.

---

### 6. Validate Python-Lean bridge options
- **Effort**: L
- **Status**: [PLANNED]
- **Task Type**: python
- **Dependencies**: Task 2
- **Research**: [006_validate_python_lean_bridge_options/reports/01_bridge-validation.md]
- **Plan**: [006_validate_python_lean_bridge_options/plans/01_bridge-validation-plan.md]

**Description**: Test LeanDojo-v2, lean-interact, PyPantograph against BimodalLogic (Lean v4.27.0-rc1). Determine which can load ProofChecker, send tactic steps, receive goal states. Produce latency benchmarks. Critical risk gate.

---

### 5. Coordinate BimodalLogic formula and proof data exports
- **Effort**: M
- **Status**: [PLANNED]
- **Task Type**: general
- **Dependencies**: Task 3, Task 4
- **Research**: [005_coordinate_bimodallogic_formula_and_proof_data_exports/reports/01_export-coordination.md]
- **Plan**: [005_coordinate_bimodallogic_formula_and_proof_data_exports/plans/01_export-coordination-plan.md]

**Description**: Define what BimodalLogic needs to export (formulas, DecisionResults, proof traces, countermodels). Specify JSON/Parquet export format matching training data schema. Set up data sync pipeline between repos. Coordinate with BimodalLogic task 201.

---

### 4. Define training data schema and action space
- **Effort**: M
- **Status**: [COMPLETED]
- **Task Type**: python
- **Dependencies**: none
- **Research**: [004_define_training_data_schema_and_action_space/reports/01_data-schema-research.md]
- **Plan**: [004_define_training_data_schema_and_action_space/plans/01_data-schema-plan.md]
- **Summary**: [004_define_training_data_schema_and_action_space/summaries/01_schema-implementation-summary.md]

**Description**: Design JSON/Parquet schema for (formula, label, proof_trace_or_countermodel, PatternKey_features, difficulty_metrics). Precisely enumerate action space (resolve 42 vs 57 axiom constructor count). Schema must be extensible for full Logos operator set.

---

### 3. Design cross-repo integration architecture
- **Effort**: S
- **Status**: [COMPLETED]
- **Task Type**: general
- **Dependencies**: none
- **Research**: [003_design_cross_repo_integration_architecture/reports/01_cross-repo-design.md]
- **Plan**: [003_design_cross_repo_integration_architecture/plans/01_cross-repo-plan.md]
- **Summary**: [003_design_cross_repo_integration_architecture/summaries/01_cross-repo-summary.md]

**Description**: Decide how BimodalHarness references BimodalLogic (git submodule, path config, exported artifacts). Define boundary: BimodalHarness is Python-only, consumes Lean-exported data. Document version compatibility (Lean v4.27.0-rc1).

---

### 2. Initialize Python project structure
- **Effort**: S
- **Status**: [COMPLETED]
- **Task Type**: python
- **Dependencies**: none
- **Research**: [002_initialize_python_project_structure/reports/01_python-project-setup.md]
- **Plan**: [002_initialize_python_project_structure/plans/01_python-project-plan.md]
- **Summary**: [002_initialize_python_project_structure/summaries/01_project-setup-summary.md]

**Description**: Set up pyproject.toml, src/ layout, pytest, CI pipeline, dev dependencies (PyTorch, numpy, Z3). Configure ruff linting, mypy type checking.

---

### 1. Implement AlphaZero proof search training harness
- **Effort**: XL
- **Status**: [EXPANDED]
- **Task Type**: python
- **Subtasks**: 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23

- **Research**: [specs/001_implement_alphazero_proof_search_training_harness/reports/01_team-research.md]
- **Plan**: [001_implement_alphazero_proof_search_training_harness/plans/01_task-creation-plan.md]
- **Summary**: [001_implement_alphazero_proof_search_training_harness/summaries/01_task-creation-summary.md]

**Description**: Implement AlphaZero proof search training harness, drawing on task decomposition plan and team research from BimodalLogic project (specs/201_alphazero_proof_search_harness/plans/01_task-decomposition.md, specs/201_alphazero_proof_search_harness/reports/02_team-research.md) and following technical memo specifications (Logos/Vision/shared/strategy/01-overview/03-technical_memo.typ)
