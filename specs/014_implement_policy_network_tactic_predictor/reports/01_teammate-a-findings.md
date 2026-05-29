# Teammate A Findings: Primary Implementation Approach for Policy Network

**Task**: 14 — Implement policy network (tactic predictor)
**Angle**: Architecture selection, input encoding, training procedure, and integration
**Date**: 2026-05-29
**Confidence**: High

---

## Key Findings

### 1. The Domain Strongly Constrains Architecture Choice

The policy network's job is narrow and well-defined: given a `ProofStepRecord` (goal formula AST + context formulas + frame class), predict which of 49 actions (42 axioms + 7 rules) was taken. Key constraints:

- **Small, fixed action space**: Only 49 actions. Frame-class masking further narrows to 44-47 valid actions per step.
- **Structured tree input**: Formulas are binary trees with exactly 6 node types (`atom`, `bot`, `imp`, `box`, `untl`, `snce`). Maximum practical depth is ~15-20 based on BimodalLogic theorems.
- **Small dataset initially**: Only synthetic fixtures exist; real proof traces from ~2,519 theorems are pending (Lean extraction phases 1 and 3 from Task 9). Estimated total proof steps: 5,000-50,000.
- **Must work on CPU first**: The task notes "GPU REQUIRED" but the initial architecture should train on CPU for prototyping, with GPU scaling later.

### 2. Architecture Comparison

| Architecture | Pros | Cons | GPU Need | Param Count |
|---|---|---|---|---|
| **TreeLSTM over AST** | Directly encodes tree structure; proven on formula tasks (Evans et al. 2018) | Custom batching; moderate complexity | Low (CPU-ok) | ~500K-2M |
| **Transformer on linearized formula** | Standard batching; attention captures long-range deps | Loses tree structure; needs tokenizer | Medium | ~5M-30M |
| **Fine-tuned T5-small/GPT-2 with LoRA** | Pretrained language understanding; LoRA reduces params | Massive overkill for 6-tag grammar; heavy setup | High (GPU required) | 60M+ (LoRA: ~1M trainable) |
| **GNN (message-passing) over AST** | Natural tree encoding; permutation-aware | Requires explicit graph construction each batch | Low (CPU-ok) | ~200K-1M |
| **MLP over PatternKey + structural features** | Simplest; mirrors ValueNetwork; fast CPU training | Loses all sub-formula structure; weak for MP chains | Minimal | ~2M |

### 3. Recommended Architecture: Two-Tier Approach

**Tier 1 (Immediate — CPU-trainable, no GPU):** MLP policy head over extended PatternKey features. This mirrors the existing ValueNetwork pattern and can be built, tested, and trained TODAY with zero GPU and the existing synthetic data.

**Tier 2 (GPU-ready — when data and hardware available):** TreeLSTM or GNN encoder over formula AST + MLP policy head. This replaces the feature encoder while keeping the same output head and training infrastructure.

This two-tier approach matches the project's staged dependency structure: Task 14 is blocked until GPU is available, but the MLP baseline provides immediate utility for the expert iteration loop (Task 16).

### 4. Input Representation Design

**Tier 1 (MLP) Input Encoding — 25 dimensions:**

From `ProofStepRecord`:
- **Goal PatternKey features** (12 dims): Reuse existing `encode_pattern_key()` — 4 log1p numerics + 8 one-hot top_operator. Already implemented in `models/value.py`.
- **Context features** (4 dims): `len(context)`, max/mean/sum complexity of context formulas (computed via `extract_pattern_key` on each context formula string parsed to JSON).
- **Depth features** (2 dims): `log1p(depth)`, `log1p(proof_height)`.
- **Frame class** (3 dims): One-hot encoding of frame_class (Base/Dense/Discrete).
- **Subgoal features** (4 dims): `len(subgoals)`, mean complexity of subgoal formulas, max modal depth of subgoals, max temporal depth of subgoals. (For leaf nodes, all zeros.)

Total: 12 + 4 + 2 + 3 + 4 = **25 input dimensions**.

**Tier 2 (TreeLSTM) Input Encoding:**

- Each AST node gets an embedding: 6-dim tag one-hot + optional atom name embedding (learned vocabulary for atom names, or hash-based).
- Bottom-up TreeLSTM (Tai et al. 2015) produces a fixed-size vector per node; root vector is the "formula embedding" (~128 or 256 dims).
- Context formulas: each encoded independently via TreeLSTM, then attention-pooled or mean-pooled.
- Concatenate: [goal_embedding, context_pool, depth_features, frame_class_onehot] → MLP policy head.

### 5. Output Head Design

Identical for both tiers:

```python
# logits: [B, 49] raw scores from final Linear layer
# mask: [B, 49] boolean tensor from FRAME_CLASS_MASKS[frame_class]
masked_logits = logits.masked_fill(~mask, float('-inf'))
action_probs = F.softmax(masked_logits, dim=-1)
```

The masking infrastructure already exists in `schema/actions.py` via `FRAME_CLASS_MASKS` and `get_mask_for_frame_class()`. The policy network just needs to convert the boolean list to a tensor and apply it before softmax.

### 6. Training Procedure

**Loss function**: Cross-entropy with optional label smoothing (ε=0.1). Label smoothing helps because proof steps often have multiple valid continuations (e.g., both `prop_k` and `prop_s` can start many proofs).

```python
loss = F.cross_entropy(masked_logits, target_action_index, label_smoothing=0.1)
```

**Optimizer**: AdamW with lr=3e-4, weight_decay=1e-4 (matching ValueTrainer pattern).

**Curriculum**: The existing `CurriculumSampler` gates by difficulty tier. For policy training, adapt by proof_height tiers: train on short proofs first (height 0-2), then medium (3-5), then all.

**Metrics**:
- Top-1 accuracy (did we predict the exact action?)
- Top-5 accuracy (is the correct action in top 5?)
- Per-rule-type accuracy breakdown (axiom actions vs. inference rules)
- Cross-entropy loss

### 7. Integration with Existing Code

**What to reuse directly:**
- `encode_pattern_key()` and `FeatureNormalizer` from `models/value.py` — for the 12-dim PatternKey encoding
- `FRAME_CLASS_MASKS`, `get_mask_for_frame_class()`, `ACTION_TO_INDEX` from `schema/actions.py`
- `ProofStepRecord` and `ProofStepRecord.from_dict()` from `schema/records.py`
- `load_proof_steps()` from `data/ingestion.py` — for loading JSONL data
- `TrainerConfig` pattern from `training/value_trainer.py` — adapt for policy training
- `split_dataset` pattern from `data/augmentation.py` (proof step version)

**What needs new code:**
- `PolicyNetworkConfig` dataclass (in `models/policy.py`)
- `PolicyNetwork` nn.Module (in `models/policy.py`)
- `encode_proof_step()` function — converts ProofStepRecord to input tensor
- `ProofStepDataset` — torch Dataset wrapping list[ProofStepRecord]
- `policy_collate_fn` — batches ProofStepRecords into (features, action_indices, masks) tensors
- `PolicyTrainer` — orchestrates training with metrics, checkpointing, early stopping

**Parallel structure with ValueNetwork:**

| Component | ValueNetwork (exists) | PolicyNetwork (new) |
|---|---|---|
| Config | `ValueNetworkConfig` | `PolicyNetworkConfig` |
| Encoder | `encode_pattern_key` (12-dim) | `encode_proof_step` (25-dim) |
| Model | MLP → [B,1] Softplus | MLP → [B,49] + mask |
| Dataset | `BimodalDataset` over `TrainingRecord` | `ProofStepDataset` over `ProofStepRecord` |
| Collate | `value_collate_fn` | `policy_collate_fn` |
| Trainer | `ValueTrainer` | `PolicyTrainer` |
| Loss | HuberLoss (regression) | CrossEntropy (classification) |
| Metrics | MAE, Spearman, acc@1 | Top-1, Top-5, per-class acc |

### 8. Parameter Count Estimates

**Tier 1 MLP** (input_dim=25, hidden_sizes=[1024, 512, 256], output_dim=49):
- Layer 1: 25×1024 + 1024 = 26,624
- Layer 2: 1024×512 + 512 = 524,800
- Layer 3: 512×256 + 256 = 131,328
- Output: 256×49 + 49 = 12,593
- LayerNorm params: ~3,584
- **Total: ~699K parameters** — easily CPU-trainable

**Tier 2 TreeLSTM + MLP** (embedding_dim=128, hidden_dim=256):
- Node embeddings: 6×128 = 768 (+ atom vocab)
- TreeLSTM cell: ~4×(128+256)×256 = ~394K
- MLP head: ~200K
- **Total: ~600K-1M parameters** — still CPU-trainable, GPU for speed

### 9. Training Signal Analysis

**Available now:**
- 10 synthetic proof steps in `tests/fixtures/proof_steps_fixture.jsonl` — only for testing
- 8 sample training records in `data/samples/test_lean_export.jsonl` — formula-level, not step-level

**Expected from Task 9 completion (Lean phases 1, 3):**
- ~2,519 theorems in BimodalLogic, each with 1-20+ proof steps
- Estimated: **5,000-25,000 raw proof steps**
- After temporal dual augmentation: ~1.5x = **7,500-37,500 steps**
- After context variation augmentation: additional 3x for empty-context steps

**From ModelChecker bimodal module** (/home/benjamin/Projects/Logos/ModelChecker/code/src/model_checker/theory_lib/bimodal/):
- Provides semantic evaluation (countermodel generation) — primarily useful for Task 19 (Z3 countermodel generator), not directly for policy training
- The `operators.py` and `semantic.py` validate the operator semantics the proof system reasons about, useful for understanding the domain but not as direct training signal

**From BimodalLogic automation** (/home/benjamin/Projects/BimodalLogic/Theories/Bimodal/Automation/):
- `ProofStepExtractor.lean`: Walks DerivationTree to emit ProofStep records — THE primary training signal source
- `SuccessPatterns.lean`: PatternKey features, GoalCategory — already ported to Python
- `DatasetGenerator.lean`: Enumerates formulas and runs proof search — generates additional (formula, proof) pairs
- `ProofSearch/Core.lean`: IDDFS + BestFirst search with heuristic weights — the search process that produces proof traces

### 10. Data Scarcity Mitigation Strategies

With only ~5K-25K proof steps initially:

1. **Augmentation** (already built): Temporal duals and context variations from Task 9
2. **Self-play from search**: Run `ProofSearch` on generated formulas, extract successful proof traces (requires Lean bridge from Task 6)
3. **Multi-task learning**: Train policy head and value head jointly on shared encoder (for Tier 2)
4. **Weight initialization**: Initialize MLP hidden layers with Xavier uniform (standard for small datasets)
5. **Heavy regularization**: Dropout 0.2-0.3, weight decay 1e-3, label smoothing 0.1

---

## Recommended Approach

**Phase 1: MLP Baseline (CPU, immediate)**

1. Implement `PolicyNetworkConfig` and `PolicyNetwork` in `models/policy.py`
2. Implement `encode_proof_step()` producing 25-dim feature vector
3. Implement `ProofStepDataset` and `policy_collate_fn`
4. Implement `PolicyTrainer` following `ValueTrainer` patterns
5. Train and evaluate on synthetic fixture data (10 steps) for correctness
6. Ready for real data when Task 9 Lean phases complete

**Phase 2: TreeLSTM Encoder (GPU, when available)**

1. Implement `TreeLSTMCell` and `FormulaEncoder` modules
2. Replace `encode_proof_step()` with tree-based encoding
3. Retrain on full dataset with GPU
4. Compare accuracy against MLP baseline

**Phase 3: Joint Training (GPU, for Task 16)**

1. Share encoder between policy and value networks
2. Multi-task loss: λ_policy * CE_loss + λ_value * Huber_loss
3. Feed into expert iteration loop

---

## Evidence / Examples

**Proof step structure** (from fixture):
```json
{
  "step_id": "mp_example/0",
  "goal_json": {"tag": "atom", "name": "q"},
  "goal_pretty": "q",
  "rule": "modus_ponens",
  "axiom_name": null,
  "action_index": 44,
  "context": [],
  "subgoals": [{"tag": "imp", ...}, {"tag": "atom", "name": "p"}],
  "depth": 0,
  "frame_class": "Base",
  "proof_height": 2
}
```

This maps to: goal = atom("q"), action = modus_ponens (index 44), producing 2 subgoals. The policy network must learn that modus_ponens on an atom goal is a valid choice when the antecedent can be found.

**Comparable systems** (supporting TreeLSTM for formulas):
- GPT-f (Polu & Sutskever, 2020): Used transformer on serialized Lean goals — but had millions of training examples
- TacticToe (Gauthier et al., 2018): Used feature vectors (like our PatternKey) — effective with small data
- HTPS (Lample et al., 2022): Encoder-decoder transformer — but on much larger action spaces

For ~10K-50K steps with 49 actions, an MLP baseline is the right starting point — matching TacticToe's approach with our richer PatternKey features.

---

## Confidence Level

**High** — The MLP-first approach is well-supported by:
1. The existing ValueNetwork proves the pattern works in this codebase
2. The 49-action space is small enough that a classifier over structural features is viable
3. The two-tier upgrade path to TreeLSTM is well-defined and doesn't require rewriting infrastructure
4. All integration points are clearly identified with existing code to reuse
