# Implementation Plan: Task #14

- **Task**: 14 - Implement policy network (tactic predictor)
- **Status**: [NOT STARTED]
- **Effort**: 8 hours
- **Dependencies**: Task 11 (value network, complete), Task 9 (data extraction, partial -- synthetic data used as bootstrap)
- **Research Inputs**: specs/014_implement_policy_network_tactic_predictor/reports/01_team-research.md
- **Artifacts**: plans/01_policy-network-plan.md (this file)
- **Standards**: plan-format.md, status-markers.md, artifact-management.md, tasks.md
- **Type**: python
- **Lean Intent**: false

## Overview

Build the policy network that predicts which of 49 proof actions (42 axiom constructors + 7 inference rules) to apply given a proof goal state. The implementation follows a two-tier approach: Phase 1 delivers an MLP baseline over handcrafted features (25-dim input from PatternKey + context/depth/frame-class features), CPU-trainable in minutes with ~699K parameters. Phase 2 adds a formula AST tokenizer and small transformer encoder (~1.3M params) that replaces handcrafted features with learned representations. The project is done when the MLP baseline trains on synthetic data, produces above-random predictions with frame-class masking, and the AST encoder is architecturally complete with a tokenizer and embedding pipeline.

### Research Integration

The team research report (4 teammates, high confidence) converges on:
- Two-tier architecture: MLP baseline (immediate, CPU) then transformer AST encoder (production quality)
- GPU NOT required for initial development; MLP trains in minutes on CPU
- Synthetic data bootstrap from formula structure rules (~5K-10K steps) unblocks development while Lean proof extraction (Task 9) remains deferred
- Existing infrastructure to reuse: `encode_pattern_key`, `FRAME_CLASS_MASKS`, `ProofStepRecord`, `load_proof_steps`, `ValueTrainer` pattern, `augment_all`
- Critic-identified gaps addressed: PatternKey acknowledged as limited baseline, focal loss for class imbalance, search-oriented metrics (MRR, top-5 recall)

### Prior Plan Reference

No prior plan.

### Roadmap Alignment

No ROADMAP.md found.

## Goals & Non-Goals

**Goals**:
- Implement `PolicyNetworkConfig` and `PolicyNetwork` MLP in `models/policy.py`
- Implement `encode_proof_step()` to produce 25-dim feature vectors from `ProofStepRecord`
- Create `ProofStepDataset` and `policy_collate_fn` for DataLoader integration
- Build `PolicyTrainer` with cross-entropy loss, frame-class masking, early stopping, and checkpoint save/load
- Generate synthetic proof step data from formula structure rules for bootstrap training
- Add search-oriented evaluation metrics: top-1, top-5, MRR, per-rule accuracy
- Create CLI training script mirroring `scripts/train_value_network.py`
- Implement formula AST tokenizer and small transformer encoder architecture

**Non-Goals**:
- Training on real Lean-extracted proof data (requires Task 9 completion)
- GPU optimization or distributed training
- LoRA fine-tuning of language models (Phase 3 in roadmap, not this task)
- Hierarchical action head (flat 49-way softmax with masking is sufficient for now)
- Integration with proof search (Task 15)
- Expert iteration / GRPO-style RL (Task 16)

## Risks & Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Synthetic data too simplistic for meaningful training signal | M | M | Cover all 49 actions, multiple formula structures per axiom; augment with temporal duals and context variations |
| PatternKey collisions (same features, different correct actions) | M | H | Acknowledged limitation; MLP is a baseline only. AST encoder in Phase 5 addresses this structurally |
| Action distribution heavily skewed (modus_ponens dominant) | M | H | Use class-weighted cross-entropy or focal loss; label smoothing epsilon=0.1 |
| Formula AST tokenizer vocabulary too small for novel formulas | L | L | Vocabulary designed with atom name hashing for open-ended coverage |
| Trainer divergence on small synthetic dataset | L | M | Early stopping, gradient clipping, learning rate warmup |

## Implementation Phases

**Dependency Analysis**:
| Wave | Phases | Blocked by |
|------|--------|------------|
| 1 | 1 | -- |
| 2 | 2, 3 | 1 |
| 3 | 4 | 2 |
| 4 | 5 | 3, 4 |
| 5 | 6 | 5 |

Phases within the same wave can execute in parallel.

---

### Phase 1: PolicyNetwork and Feature Encoder [COMPLETED]

**Goal**: Implement the core PolicyNetwork MLP architecture and the 25-dim proof step feature encoder in `models/policy.py`.

**Tasks**:
- [ ] Implement `PolicyNetworkConfig` dataclass with fields: `input_dim` (default 25), `num_actions` (default 49), `hidden_sizes` (default [1024, 512, 256]), `dropout` (default 0.1), `label_smoothing` (default 0.1), with `to_dict()`/`from_dict()` serialization
- [ ] Implement `encode_proof_step()` function producing a 25-dim feature tensor from a `ProofStepRecord`: 12-dim PatternKey (reuse `encode_pattern_key` on a synthesized PatternKey from `goal_json`), 4-dim context summary (log1p context length, has_context flag, max context complexity, mean context complexity), 2-dim depth features (log1p depth, log1p proof_height), 3-dim frame class one-hot (Base/Dense/Discrete), 4-dim subgoal summary (log1p subgoal count, has_subgoals flag, mean subgoal complexity, max subgoal depth)
- [ ] Implement `PolicyNetwork(nn.Module)` with: MLP hidden layers (Linear -> LayerNorm -> GELU -> Dropout), final Linear projection to `num_actions` logits, `apply_frame_class_mask(logits, mask)` method setting invalid actions to `-inf`, `forward(x)` returning raw logits, `param_count` property
- [ ] Implement `PolicyFeatureEncoder` class wrapping `encode_proof_step()` with `to_dict()`/`from_dict()` for checkpoint serialization (mirrors `FeatureNormalizer` pattern)
- [ ] Add unit tests in `tests/test_models/test_policy.py`: config creation, forward pass shape [B, 49], mask application zeros out correct actions, feature encoder output shape [25], param count ~699K

**Timing**: 2 hours

**Depends on**: none

**Files to modify**:
- `src/bimodal_harness/models/policy.py` - PolicyNetworkConfig, encode_proof_step, PolicyNetwork, PolicyFeatureEncoder
- `tests/test_models/test_policy.py` - Unit tests (new file)

**Verification**:
- `pytest tests/test_models/test_policy.py` passes
- `PolicyNetwork().param_count` is approximately 699K
- Forward pass with batch of 32 random inputs produces shape [32, 49]
- Frame-class mask correctly sets invalid action logits to `-inf`

---

### Phase 2: ProofStepDataset and Collate Function [COMPLETED]

**Goal**: Create the PyTorch Dataset and collate function for policy network training on `ProofStepRecord` data.

**Tasks**:
- [ ] Create `src/bimodal_harness/data/policy_dataset.py` with `ProofStepDataset(torch.utils.data.Dataset)` wrapping `list[ProofStepRecord]`, returning individual records via `__getitem__`
- [ ] Implement `policy_collate_fn(records: list[ProofStepRecord]) -> tuple[Tensor, Tensor, Tensor]` returning `(features [B, 25], targets [B], masks [B, 49])` where features come from `encode_proof_step`, targets are `action_index`, and masks are the frame-class boolean mask as float tensor
- [ ] Add `labels` property returning action indices, and `frame_classes` property returning frame class strings (for stratification)
- [ ] Implement `split_proof_steps(records, train_frac, val_frac, seed, stratify_by_action)` splitting `(ProofStepRecord, str)` tuples into train/val/test, stratified by action_index to preserve class balance
- [ ] Add unit tests in `tests/test_data/test_policy_dataset.py`: dataset length, collate output shapes, mask values match frame class, split proportions

**Timing**: 1.5 hours

**Depends on**: 1

**Files to modify**:
- `src/bimodal_harness/data/policy_dataset.py` - ProofStepDataset, policy_collate_fn, split_proof_steps (new file)
- `tests/test_data/test_policy_dataset.py` - Unit tests (new file)

**Verification**:
- `pytest tests/test_data/test_policy_dataset.py` passes
- Collate function produces correct tensor shapes and dtypes
- Frame-class masks from collate match `FRAME_CLASS_MASKS` values

---

### Phase 3: PolicyTrainer [COMPLETED]

**Goal**: Build the training orchestrator for the policy network, mirroring `ValueTrainer` structure but adapted for classification with frame-class masking.

**Tasks**:
- [ ] Create `src/bimodal_harness/training/policy_trainer.py` with `PolicyTrainerConfig` dataclass: `learning_rate` (3e-4), `batch_size` (64), `max_epochs` (50), `weight_decay` (1e-4), `patience` (7), `label_smoothing` (0.1), `focal_loss_gamma` (0.0, disabled by default), `seed` (42), `gradient_clip_norm` (1.0)
- [ ] Implement `PolicyTrainer` class with: `train_epoch()` computing masked cross-entropy loss (apply frame-class mask to logits before softmax, use `CrossEntropyLoss` with `label_smoothing`), AdamW optimizer, cosine annealing scheduler, gradient clipping
- [ ] Implement `evaluate()` method computing: top-1 accuracy, top-5 accuracy, mean reciprocal rank (MRR), per-rule accuracy breakdown, valid-action probability mass (fraction of softmax probability on valid actions)
- [ ] Implement `train()` method with full training loop: early stopping on validation top-1 accuracy, best model state restoration, return training history dict
- [ ] Implement `save_checkpoint()` and `load_checkpoint()` methods storing: model state dict, model config, trainer config, feature encoder state, epoch, best metrics
- [ ] Implement `from_checkpoint()` classmethod for resuming training
- [ ] Add unit tests in `tests/test_training/test_policy_trainer.py`: one epoch trains without error, evaluation returns expected keys, checkpoint round-trip preserves model weights

**Timing**: 2 hours

**Depends on**: 1

**Files to modify**:
- `src/bimodal_harness/training/policy_trainer.py` - PolicyTrainerConfig, PolicyTrainer (new file)
- `tests/test_training/test_policy_trainer.py` - Unit tests (new file)

**Verification**:
- `pytest tests/test_training/test_policy_trainer.py` passes
- Training one epoch on small synthetic data produces decreasing loss
- Checkpoint save/load round-trip: loaded model produces identical logits on same input
- Evaluation metrics dict contains keys: top1_acc, top5_acc, mrr, per_rule_accuracy, valid_prob_mass

---

### Phase 4: Synthetic Data Generator [COMPLETED]

**Goal**: Build a synthetic proof step data generator that creates labeled `ProofStepRecord` objects from formula structure rules, covering all 49 actions.

**Tasks**:
- [ ] Create `src/bimodal_harness/data/synthetic_policy_data.py` with `generate_synthetic_proof_steps(n_steps, seed, frame_class)` function
- [ ] Implement formula generators for each of the 6 AST node types (atom, bot, imp, box, untl, snce) at varying complexity levels (depth 1-4)
- [ ] For each of the 42 axiom constructors, generate goal formulas matching the axiom schema pattern (e.g., `prop_k` goal is `imp(imp(phi, imp(psi, chi)), imp(imp(phi, psi), imp(phi, chi)))`)
- [ ] For each of the 7 inference rules, generate appropriate (context, goal) pairs: `modus_ponens` with imp-headed goals, `necessitation` with empty context and box-headed goals, `assumption` with goal present in context, `axiom` with goals matching axiom patterns, `weakening` with non-empty context, `temporal_necessitation` with temporal goals, `temporal_duality` with Until/Since goals
- [ ] Generate `ProofStepRecord` objects with correct `action_index` via `step_to_action_index()`, appropriate `frame_class` respecting axiom validity, realistic `depth` and `proof_height` values
- [ ] Implement action distribution balancing: ensure each of the 49 actions gets at least `n_steps / 98` examples (2x floor), with remaining budget distributed proportionally
- [ ] Apply existing augmentation pipeline (`augment_all`) to expand synthetic data 3-5x
- [ ] Add unit tests: all 49 action indices covered, generated records pass `ProofStepRecord` validation, frame-class consistency (discrete axioms only on Discrete frame class)

**Timing**: 1.5 hours

**Depends on**: 2

**Files to modify**:
- `src/bimodal_harness/data/synthetic_policy_data.py` - Synthetic data generator (new file)
- `tests/test_data/test_synthetic_policy_data.py` - Unit tests (new file)

**Verification**:
- `pytest tests/test_data/test_synthetic_policy_data.py` passes
- `generate_synthetic_proof_steps(5000)` produces records covering all 49 action indices
- After `augment_all`, dataset size is 3-5x the input size
- All generated `ProofStepRecord` objects pass dataclass validation

---

### Phase 5: Training Script and End-to-End Validation [COMPLETED]

**Goal**: Create the CLI training script and run an end-to-end training cycle on synthetic data to validate the full pipeline.

**Tasks**:
- [ ] Create `scripts/train_policy_network.py` with argparse CLI mirroring `scripts/train_value_network.py`: `--data` (JSONL path or "synthetic" for generated data), `--output` (checkpoint path), `--synthetic-steps` (default 5000), `--max-epochs`, `--batch-size`, `--hidden-sizes`, `--dropout`, `--label-smoothing`, `--learning-rate`
- [ ] Implement training pipeline: load/generate data, split into train/val/test, create PolicyNetwork and PolicyTrainer, run training loop, save best checkpoint, print evaluation metrics
- [ ] Run end-to-end training on 5K synthetic steps: verify above-random accuracy (>1/49 = 2.04% baseline for uniform random, target >15% top-1 on synthetic data)
- [ ] Add `scripts/evaluate_policy_network.py` for standalone evaluation on a JSONL test set: loads checkpoint, runs evaluation, prints top-1/top-5/MRR/per-rule breakdown
- [ ] Register new modules in package `__init__.py` files: update `models/__init__.py`, `data/__init__.py`, `training/__init__.py` with public exports

**Timing**: 1.5 hours

**Depends on**: 3, 4

**Files to modify**:
- `scripts/train_policy_network.py` - CLI training script (new file)
- `scripts/evaluate_policy_network.py` - CLI evaluation script (new file)
- `src/bimodal_harness/models/__init__.py` - Export PolicyNetwork, PolicyNetworkConfig
- `src/bimodal_harness/data/__init__.py` - Export ProofStepDataset, policy_collate_fn
- `src/bimodal_harness/training/__init__.py` - Export PolicyTrainer, PolicyTrainerConfig

**Verification**:
- `python scripts/train_policy_network.py --data synthetic --synthetic-steps 5000 --max-epochs 20 --output /tmp/test_policy.pt` completes without error
- Training produces checkpoint file at specified output path
- Top-1 accuracy on synthetic test set exceeds 15%
- `python scripts/evaluate_policy_network.py --checkpoint /tmp/test_policy.pt --data synthetic` prints valid metrics

---

### Phase 6: Formula AST Tokenizer and Transformer Encoder [COMPLETED]

**Goal**: Implement the formula AST tokenizer and small transformer encoder as the Tier 2 architecture upgrade, replacing handcrafted 25-dim features with learned formula embeddings.

**Tasks**:
- [ ] Create `src/bimodal_harness/models/formula_encoder.py` with `FormulaTokenizer` class: vocabulary of ~20 tokens (6 AST tags: atom, bot, imp, box, untl, snce; special tokens: PAD, UNK, BOS, EOS; atom name hashing into 8 buckets), `tokenize(goal_json) -> list[int]` using prefix-order linearization, `max_length` truncation (default 128)
- [ ] Implement `FormulaTransformerEncoder(nn.Module)`: token embedding (d_model=128), learned positional encoding (max_len=128), 3-layer TransformerEncoder with 4 attention heads, output CLS-token embedding of dim 128, `forward(token_ids, padding_mask) -> [B, 128]`
- [ ] Implement `PolicyNetworkV2(nn.Module)` that combines: `FormulaTransformerEncoder` for goal representation (128-dim), context/depth/frame features (9-dim: 4-dim context + 2-dim depth + 3-dim frame class one-hot), concatenated 137-dim input to MLP head [512, 256] -> 49-dim logits with frame-class mask
- [ ] Add `FormulaTokenizer.to_dict()`/`from_dict()` for vocabulary serialization in checkpoints
- [ ] Ensure `PolicyNetworkV2` exposes the same `forward()` -> `[B, 49]` interface as `PolicyNetwork` so downstream code (PolicyTrainer, training scripts) works with either model
- [ ] Add unit tests: tokenizer covers all 6 AST tags, round-trip on sample formulas, transformer forward pass shape, V2 forward pass produces [B, 49], param count ~1.3M

**Timing**: 1.5 hours

**Depends on**: 5

**Files to modify**:
- `src/bimodal_harness/models/formula_encoder.py` - FormulaTokenizer, FormulaTransformerEncoder (new file)
- `src/bimodal_harness/models/policy.py` - PolicyNetworkV2 class
- `tests/test_models/test_formula_encoder.py` - Unit tests (new file)
- `tests/test_models/test_policy.py` - Add V2 forward pass tests

**Verification**:
- `pytest tests/test_models/test_formula_encoder.py` passes
- Tokenizer correctly linearizes `{"tag": "imp", "left": {"tag": "atom", "name": "p"}, "right": {"tag": "atom", "name": "q"}}` to expected token sequence
- `PolicyNetworkV2` forward pass on batch of 32 produces shape [32, 49]
- `PolicyNetworkV2().param_count` is approximately 1.3M
- `PolicyTrainer` works with `PolicyNetworkV2` without code changes

## Testing & Validation

- [ ] `pytest tests/test_models/test_policy.py` -- PolicyNetwork and PolicyNetworkV2 unit tests
- [ ] `pytest tests/test_data/test_policy_dataset.py` -- Dataset and collate tests
- [ ] `pytest tests/test_training/test_policy_trainer.py` -- Trainer tests
- [ ] `pytest tests/test_data/test_synthetic_policy_data.py` -- Synthetic data generator tests
- [ ] `pytest tests/test_models/test_formula_encoder.py` -- AST tokenizer and transformer tests
- [ ] End-to-end: `python scripts/train_policy_network.py --data synthetic --synthetic-steps 5000 --max-epochs 20` achieves >15% top-1 accuracy
- [ ] Frame-class masking: verify invalid actions receive 0 probability for all three frame classes
- [ ] All 49 action indices are represented in synthetic data and training
- [ ] Checkpoint save/load round-trip preserves model predictions exactly

## Artifacts & Outputs

- `src/bimodal_harness/models/policy.py` - PolicyNetworkConfig, PolicyNetwork, PolicyNetworkV2, encode_proof_step, PolicyFeatureEncoder
- `src/bimodal_harness/models/formula_encoder.py` - FormulaTokenizer, FormulaTransformerEncoder
- `src/bimodal_harness/data/policy_dataset.py` - ProofStepDataset, policy_collate_fn, split_proof_steps
- `src/bimodal_harness/data/synthetic_policy_data.py` - generate_synthetic_proof_steps
- `src/bimodal_harness/training/policy_trainer.py` - PolicyTrainerConfig, PolicyTrainer
- `scripts/train_policy_network.py` - CLI training script
- `scripts/evaluate_policy_network.py` - CLI evaluation script
- `tests/test_models/test_policy.py` - PolicyNetwork unit tests
- `tests/test_models/test_formula_encoder.py` - Formula encoder unit tests
- `tests/test_data/test_policy_dataset.py` - Dataset unit tests
- `tests/test_data/test_synthetic_policy_data.py` - Synthetic data unit tests
- `tests/test_training/test_policy_trainer.py` - Trainer unit tests

## Rollback/Contingency

All new code is in new files (`policy.py` expansion, `policy_dataset.py`, `synthetic_policy_data.py`, `policy_trainer.py`, `formula_encoder.py`, scripts). The only existing file modified is `models/policy.py` which currently contains only an import line. Rollback consists of reverting `models/policy.py` to its stub state and removing the new files. No existing functionality is changed or at risk.

If synthetic data proves insufficient for meaningful training:
- Fall back to overfitting on 10 existing test fixtures to validate the training pipeline mechanically
- Defer accuracy targets until real proof step data is available from Task 9
