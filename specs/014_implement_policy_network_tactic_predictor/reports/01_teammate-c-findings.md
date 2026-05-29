# Critic Findings: Task 14 — Implement Policy Network (Tactic Predictor)

**Teammate**: C (Critic)
**Date**: 2026-05-29
**Focus**: Gaps, blind spots, and unvalidated assumptions

---

## Gaps Identified

### GAP 1: Training Data Does Not Exist (Critical)

The **entire supervised training pipeline is blocked**. Task 9 completed only Phases 2, 4, and 5 (Python schema/ingestion/augmentation). The Lean-side phases (1: ProofStep extraction, 3: lake exe proof_extractor) are deferred. The only data available is a **10-record synthetic test fixture** (`tests/fixtures/proof_steps_fixture.jsonl`), hand-written for unit testing — not for training.

This means:
- No real proof step distribution data exists to inform architecture choices
- No training data exists to train the policy network
- No validation data exists to evaluate whether the network learns anything meaningful
- The ~2,554 theorem/lemma declarations in BimodalLogic remain unextracted

**Impact**: The policy network can be *architecturally implemented* (code structure, forward pass, loss function) but cannot be *trained or evaluated* without completing Task 9 Phases 1 and 3. This is only a partial blocker — the network code can be written, but the task description's "Start with SFT on proof trace dataset" cannot proceed.

### GAP 2: No Policy-Specific Collate Function or Dataset Class

The existing training infrastructure (`value_trainer.py`, `dataset.py`) is entirely value-network-specific:
- `value_collate_fn` filters to `label == "valid"` TrainingRecords and encodes PatternKey features
- `BimodalDataset` wraps `TrainingRecord` objects, not `ProofStepRecord` objects
- `CurriculumSampler` stratifies by difficulty tier, which doesn't exist for proof steps

Task 14 needs a **completely separate** data loading pipeline:
- A `ProofStepDataset` wrapping `list[ProofStepRecord]`
- A `policy_collate_fn` that encodes goal_json ASTs into tensors and produces action_index targets
- A sampler that handles the augmented data (temporal duals, context variations)

This is not mentioned in the task description.

### GAP 3: No AST-to-Tensor Encoding Pipeline

The ProofStepRecord stores `goal_json` as a nested dict (Formula.toJson format). The policy network needs this as a tensor. **No encoding exists.** The value network uses PatternKey (12-dim summary), but PatternKey discards almost all structural information from the formula AST.

Encoding options (each is a non-trivial engineering task):
1. **Tree-LSTM / GNN** over the recursive AST — requires building a tree-batching mechanism
2. **Serialized string tokenization** (e.g., polish/prefix notation) — requires a tokenizer and embedding layer
3. **Flat feature vector** from PatternKey — loses structural information critical for predicting the correct tactic

The task description mentions "GNN over formula AST" as an option, but provides no encoding infrastructure.

### GAP 4: Missing Context Encoding

`ProofStepRecord.context` is a `tuple[str, ...]` of formula pretty-print strings. The policy network needs to reason about *what hypotheses are available*. The context is critical for predicting:
- `assumption` (action_index 43): only valid when the goal is in the context
- `weakening` (action_index 48): adds unused hypotheses
- `modus_ponens` (action_index 44): requires checking if matching implications exist in context

No context encoding mechanism exists or is planned.

---

## Assumptions Questioned

### ASSUMPTION 1: PatternKey Is Sufficient for Policy Prediction (FALSE)

The value network works with PatternKey (12 features) because it predicts a *scalar* (derivation tree height) — a coarse measure that correlates with formula complexity. For policy prediction (49-class classification), PatternKey is **provably insufficient**:

**Proof by counterexample**: Consider two formulas with identical PatternKey but requiring different first proof steps:
- `□p → p` has PatternKey(modal_depth=1, temporal_depth=0, imp_count=1, complexity=4, top_operator=Implication) → correct first step: `axiom modal_t` (action 4)
- `□p → □□p` has PatternKey(modal_depth=2, temporal_depth=0, imp_count=1, complexity=4*, top_operator=Implication) → correct first step: `axiom modal_4` (action 5)

While complexity differs here (4 vs 5), many collisions exist at higher complexity values. The top_operator alone doesn't distinguish between different axiom schemas with the same top-level connective.

**The policy network MUST use the full formula AST**, not PatternKey summaries. This is a fundamental architectural requirement that the task description underspecifies.

### ASSUMPTION 2: 49-Class Uniform Classification Is Appropriate (QUESTIONABLE)

The 10-record fixture shows already-skewed distribution: axiom (4), modus_ponens (2), assumption (2), necessitation (1), weakening (1). In real proofs, the distribution will be far more extreme:
- `modus_ponens` is the primary workhorse rule (every non-leaf step in a Hilbert-style proof uses it)
- `axiom` is the only rule that selects from 42 sub-actions
- `assumption`, `necessitation`, `temporal_necessitation`, `temporal_duality`, `weakening` are structurally determined by the goal/context

**The action space is really two-level**: first choose a rule (7 classes), then if rule=axiom, choose which axiom (42 sub-classes). A hierarchical policy head would be more appropriate than a flat 49-way softmax.

### ASSUMPTION 3: GPU Is Required (PARTIALLY FALSE)

The task is marked "Requires GPU for training — de-prioritized until GPU available." This is overstated:

- **MLP-based policy network**: If using PatternKey features (which we've argued is insufficient but might serve as a baseline), an MLP similar to the value network would be ~2-10M params, CPU-trainable in minutes
- **Small transformer/GNN**: A T5-small (60M params) fine-tune with LoRA might need GPU, but a custom small transformer over formula tokens (~1-5M params) would be CPU-trainable
- **Development and testing**: Architecture, data pipeline, loss function, evaluation metrics — all CPU work

GPU is needed for *production-scale training* on large datasets, not for initial development.

### ASSUMPTION 4: The Three Proposed Architectures Are All Viable (QUESTIONABLE)

The task description proposes: "fine-tuned small LM (LoRA), GNN over formula AST, T5-small."

- **T5-small**: 60M params, pretrained on English text, not formula syntax. The vocabulary mismatch is severe — T5's tokenizer would fragment formula strings unpredictably. Fine-tuning overhead is high for questionable benefit.
- **GNN over formula AST**: Strong match for the recursive tree structure, but requires custom batching, message-passing over heterogeneous node types (6 formula constructors), and is poorly supported by standard libraries for this specific tree shape.
- **LoRA fine-tune of small LM**: Similar vocabulary mismatch issue as T5. Better to train a small model from scratch on formula tokens.

A simpler **custom encoder** should be considered: linearize the formula AST to a token sequence (e.g., `imp atom_p imp atom_q atom_p` for `p → (q → p)`), embed with a small learned vocabulary (~20 tokens), and process with 2-4 transformer layers. This avoids the vocabulary mismatch entirely and keeps the model small enough for CPU training.

---

## Missing Questions

### Q1: What Is the Expected Accuracy Ceiling?

No analysis exists of the theoretical accuracy ceiling for this classification task. In a Hilbert-style proof system:
- The correct next step is **deterministic** given the full proof tree, but highly ambiguous given only the current goal
- Many goals admit multiple valid proof continuations (e.g., both `prop_k` and `prop_s` can start proofs of certain implications)
- The "correct" action is the one from the specific DerivationTree extracted, but alternative proofs exist

**Expected behavior**: Top-1 accuracy might be 30-50% even with a perfect model, but top-5 accuracy (critical for search guidance) could be 80%+. No one has quantified this.

### Q2: How Does Policy Accuracy Map to Proof Search Performance?

Task 15 (best-first search) will use the policy network to prioritize which action to try next. But:
- A policy with 40% top-1 accuracy but good top-5 coverage might work well for search
- A policy with 60% top-1 accuracy but terrible calibration (overconfident on wrong actions) could be worse
- Beam width, value network integration, and search budget all interact

**The evaluation metrics for Task 14 should be search-oriented**, not just classification accuracy. Metrics like "mean reciprocal rank of correct action" and "probability mass on valid actions" matter more than raw top-1 accuracy.

### Q3: What About Applicability Constraints?

Not all 49 actions are *applicable* at every proof state. For example:
- `necessitation` requires an empty context (it's a theorem-level rule)
- `assumption` requires the goal to be in the context
- `temporal_duality` requires an empty context
- Frame-class masks exclude 2-5 axioms depending on the frame class

The policy network should learn to output near-zero probability for inapplicable actions. **But there's no applicability checker** in the Python codebase to verify this during training or evaluation. The frame-class masks (`FRAME_CLASS_MASKS`) handle axiom frame validity but not the structural constraints (empty context for necessitation, goal-in-context for assumption).

### Q4: What's the Relationship to the ModelChecker?

The task description mentions looking at `/home/benjamin/Projects/Logos/ModelChecker/code/src/model_checker/theory_lib/bimodal/` for training signals. This module is a **semantic model checker** using Z3, completely different from the syntactic proof system:
- It evaluates formula truth in finite models (Z3 constraint solving)
- It doesn't produce proof steps or derivation trees
- Its training signal is countermodels for invalid formulas, not proof tactics

The ModelChecker could provide **negative training signal** (which formulas are unprovable and why), but this is a Task 19/20/21 concern, not Task 14. The mention in the research focus may be a confusion.

---

## Risk Assessment

| Risk | Severity | Likelihood | Mitigation |
|------|----------|------------|------------|
| No training data (Task 9 Phases 1,3 deferred) | **Critical** | **Certain** | Build network architecture now, generate synthetic data for testing, complete Lean extraction separately |
| PatternKey insufficient for policy prediction | **High** | **Certain** | Implement AST encoding from the start; PatternKey-MLP only as a baseline |
| Class imbalance in action distribution | **Medium** | **Very Likely** | Use focal loss or class-weighted cross-entropy; evaluate with per-class metrics |
| Architecture choice paralysis (3 options) | **Medium** | **Likely** | Start with custom small encoder (linearized AST + small transformer); it's the simplest viable option |
| GPU dependency blocks development | **Low** | **Unlikely** | MLP and small custom models are CPU-trainable; only T5/large models need GPU |
| Action applicability not enforced | **Medium** | **Certain** | Implement applicability masks before training, not after |

---

## Confidence Level

**High confidence** on:
- Training data gap is a real and certain blocker for training (though not for implementation)
- PatternKey is insufficient for policy prediction (provable by structural argument)
- The existing training infrastructure is value-network-specific and cannot be reused for policy training without significant new code

**Medium confidence** on:
- Hierarchical policy head being better than flat softmax (standard practice but unvalidated here)
- Custom small encoder being preferable to LM fine-tuning (domain-specific reasoning)
- GPU not being needed for initial development (depends on chosen architecture)

**Low confidence** on:
- Expected accuracy ceiling estimates (no empirical data)
- How much training data is needed (depends heavily on architecture and action distribution)
- Whether the ModelChecker bimodal module provides useful training signals for policy (likely not directly)
