# Teammate B Findings: Alternative Approaches and Reusable Infrastructure

**Task**: 1 — Implement AlphaZero proof search training harness
**Angle**: Alternative approaches, prior art, reusable code
**Date**: 2026-05-29
**Confidence**: HIGH

---

## Key Findings

### 1. BimodalHarness Is a New Repo — the Task Decomposition Must Be Re-scoped

The BimodalLogic plan (01_task-decomposition.md) defines 6 sub-tasks typed as `lean4` — formula enumerator, Python-Lean bridge, training data extraction, value network, policy network, and full MCTS. These were designed for the BimodalLogic repo where the Lean ProofChecker lives. BimodalHarness is a separate Python-focused repo that should contain **only the Python/ML training infrastructure**, not the Lean code itself.

This means the task decomposition needs adaptation:
- **Lean-side tasks** (formula enumerator, dataset generator) remain in BimodalLogic — they should be `lean4` tasks there, not Python tasks here
- **BimodalHarness tasks** cover: Python-Lean bridge validation, training data pipeline, value network, policy network, MCTS, and the corrective signal integration
- **A new cross-repo interface task** is needed to define the JSON/parquet data format bridging the two repos

### 2. The Technical Memo Adds a Critical Dimension: Corrective Signals via ModelChecker

The BimodalLogic task decomposition (01_task-decomposition.md) focuses exclusively on the proof-side (positive signal) pipeline. The team research report (02_team-research.md) reveals that the ModelChecker's bimodal logic is **semantically incompatible** with the ProofChecker, but identifies a three-tier corrective signal strategy:

1. **Tier 1**: Use Lean-native `decide`/`findCountermodel` for dual-signal training data (zero-cost, exists in BimodalLogic already)
2. **Tier 2**: Build standalone Z3 countermodel generator (~500 LOC) aligned to ProofChecker semantics — this naturally lives in BimodalHarness
3. **Tier 3**: Update the ModelChecker bimodal theory to match the ProofChecker

The technical memo explicitly describes the "dual verification architecture" as the core value proposition — proof certificates (positive RL signal) AND countermodels (corrective training signal). This means BimodalHarness **must** include corrective signal infrastructure, not just the proof-positive pipeline.

### 3. The ModelChecker Bimodal Code Is Actively Being Refactored

The ModelChecker at `/home/benjamin/Projects/Logos/ModelChecker/code/src/model_checker/theory_lib/bimodal/` has:
- `semantic.py` — BimodalSemantics with Z3-backed world histories, task relations, temporal evaluation
- `operators.py` — 10 operators (¬, ∧, ∨, →, ↔, ⊥, ⊤, □, ◇, ⏵, ⏴) — notably missing Until/Since
- `iterate.py` — BimodalModelIterator for generating multiple distinct countermodels
- `semantic/witness_constraints.py`, `witness_registry.py` — Phase 4 modal witness integration (recent work)
- Comprehensive test suite (unit, integration, e2e)

The 7 semantic divergences identified in the team research report mean the ModelChecker bimodal refactoring is a prerequisite for Tier 3 integration but **not** for Tier 1 or Tier 2. The harness should be designed to accept corrective signals from any of the three tiers via a uniform interface.

### 4. Existing Lean Infrastructure Is More Mature Than Expected

The BimodalLogic repo contains substantial infrastructure that the harness can consume:

| Component | Location | Relevance |
|-----------|----------|-----------|
| Formula AST | `Syntax/Formula.lean` | 6 constructors: atom, bot, imp, box, untl, snce |
| SubformulaClosure | `Syntax/SubformulaClosure/` | Bounded formula generation by depth |
| SuccessPatterns | `Automation/SuccessPatterns.lean` | `PatternKey` features: modalDepth, temporalDepth, impCount, complexity, topOperator — direct value network input |
| ProofSearch/Core | `Automation/ProofSearch/Core.lean` | IDDFS + BestFirst search with pattern learning — baseline to beat |
| Decision procedure | `Metalogic/Decidability/DecisionProcedure.lean` | `decide` function returning proof/countermodel/timeout |
| Countermodel extraction | `Metalogic/Decidability/CountermodelExtraction.lean` | `SimpleCountermodel` with trueAtoms/falseAtoms |
| Frame conditions | `FrameConditions/` | Base, Dense, Discrete — three curriculum levels |

The harness doesn't need to reimplement any of this — it needs to **consume** it via a Python-Lean bridge or exported data files.

---

## Alternative Architectures Considered

### Alternative A: Monorepo Approach (Everything in BimodalLogic)

Put all Python ML code in `BimodalLogic/scripts/training/`. Advantage: single repo, no cross-repo interface. Disadvantage: mixes Lean project concerns with Python ML concerns; difficult for ML-focused contributors; clutters the Lean build.

**Assessment**: Rejected. The BimodalHarness repo already exists as the designated separate home.

### Alternative B: Data-Only Interface (No Python-Lean Bridge)

Export all training data from Lean as static files (JSON/parquet). The harness never interacts with Lean at runtime — offline data generation only. This eliminates the Python-Lean bridge complexity entirely.

**Assessment**: Viable for Phases 0-2 (value network training). Insufficient for Phase 3+ (expert iteration requires interactive Lean verification). Recommend as **Phase 1 architecture** with bridge added later.

### Alternative C: ModelChecker-First Training Signal

Instead of the Lean ProofChecker, use the existing Python ModelChecker as the primary semantics engine. Z3 can check satisfiability/validity directly without Lean.

**Assessment**: Rejected. The 7 semantic divergences mean ModelChecker-produced labels would be incorrect for ~50%+ of formulas involving Until/Since. However, the ModelChecker's `iterate_example` infrastructure for generating diverse countermodels is valuable once semantics are aligned.

### Alternative D: Separate Training and Inference Repos

Split into three repos: BimodalLogic (Lean proofs), BimodalHarness (training pipeline), BimodalInference (serving/deployment). 

**Assessment**: Premature. Inference is a Phase 4+ concern. Keep training and inference together in BimodalHarness for now.

### Alternative E: LeanDojo-as-Framework vs Custom Pipeline

Use LeanDojo-v2 end-to-end (SFTTrainer, GRPOTrainer, DynamicDatabase) rather than building a custom training pipeline.

**Assessment**: Ideal if compatibility holds with Lean v4.27.0-rc1. The bridge validation task should test this first. If LeanDojo works, use it as framework; if not, lean-interact as bridge with custom PyTorch training loop.

---

## Reusable Existing Code/Infrastructure

### From BimodalLogic (Lean)
- Formula enumeration via SubformulaClosure module
- PatternKey feature extraction from SuccessPatterns.lean
- Decision procedure for bulk labeling (decide function)
- Countermodel extraction for corrective signals
- Existing proof search as baseline (ProofSearch/Core.lean)

### From ModelChecker (Python)
- `BimodalModelIterator.iterate_example` — model iteration pattern for diverse countermodel generation (once semantics aligned)
- `BimodalSemantics` Z3 constraint framework — template for standalone Z3 countermodel generator
- `WitnessRegistry` / `WitnessConstraintGenerator` — modal witness infrastructure
- Test suite patterns — example format (premises/conclusions/settings/expectation)

### From Broader Ecosystem
- **LeanDojo-v2**: Tactic-level proof data extraction, SFTTrainer, GRPOTrainer
- **lean-interact**: Lightweight REPL bridge (fallback if LeanDojo incompatible)
- **PyPantograph**: Rich tactic-state API (backup option)
- **HuggingFace datasets**: Standard format for training data storage

---

## Recommended Task Decomposition for BimodalHarness

Based on the alternative analysis, I recommend these tasks (Python-focused, in dependency order):

1. **Project setup and data schema definition** — pyproject.toml, directory structure, define the JSON/parquet schema for training data (formula, label, proof_trace_or_countermodel, PatternKey features, difficulty_metrics)
2. **Python-Lean bridge validation** — Test LeanDojo-v2, lean-interact, and PyPantograph against BimodalLogic; benchmark latency; document compatibility
3. **Static training data ingestion pipeline** — Import pre-exported datasets from Lean (formula enumerator output, decision results, countermodels); produce PyTorch-compatible datasets
4. **Tier 1 corrective signal integration** — Consume Lean-native countermodel data; encode SimpleCountermodel as training tensors; design uniform corrective signal interface
5. **Tier 2 standalone Z3 countermodel generator** — ~500 LOC Python/Z3 script aligned to ProofChecker semantics; richer countermodels than Lean-native
6. **Value network (proof-progress predictor)** — MLP over PatternKey features predicting DerivationTree.height; training script; evaluation against SuccessPatterns.lean baseline
7. **Policy network and supervised fine-tuning** — Tactic predictor trained on proof traces; action representation for 42 axioms + 7 rules
8. **Expert iteration loop** — Search-verify-retrain cycle using bridge; best-first search guided by policy + value
9. **ModelChecker semantic alignment** — Update operators.py to add Until/Since; fix temporal quantification, frame classes, ternary task relation (Tier 3 prerequisite)
10. **Full MCTS with AND/OR backup** — AlphaZero-style search with PUCT; weakest-link backup; online training

### Key Differences from BimodalLogic Task Decomposition
- Tasks 1, 3, 4, 5, 9 are **new** (not in original plan) — they address the BimodalHarness repo scope and dual verification architecture
- Task 2 maps to original Phase 2 (bridge validation)
- Tasks 6-8, 10 map to original Phases 4-6 but scoped for Python implementation in this repo
- Original Phase 1 (formula enumerator) stays in BimodalLogic as a Lean task — the harness consumes its output

---

## Evidence/Examples

- The ModelChecker's `BimodalSemantics.define_primitives()` shows binary `task` relation (line 153 of semantic.py) vs ProofChecker's ternary task relation with duration — confirming the incompatibility that makes Tier 3 non-trivial
- The `SuccessPatterns.lean` `PatternKey` structure already computes the exact features needed for the value network input (modalDepth, temporalDepth, impCount, complexity, topOperator) — this is ready to consume
- The `DecisionProcedure.lean` module's `decide` function returning `DecisionResult` with proof/countermodel/timeout is the Tier 1 corrective signal source
- The formula AST in `Formula.lean` has 6 constructors (atom, bot, imp, box, untl, snce) — all derived operators are definitional, so the action space for the policy network is well-defined

---

## Confidence Level

**HIGH** — The source documents are comprehensive and consistent. The key insight — that BimodalHarness needs corrective signal infrastructure beyond the original BimodalLogic task decomposition — is firmly supported by the technical memo's emphasis on "dual verification architecture" and the team research report's three-tier strategy. The ModelChecker bimodal code inspection confirms the semantic divergences and identifies reusable infrastructure.
