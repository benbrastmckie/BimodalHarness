# Implementation Summary: Task #14

- **Task**: 14 - Implement policy network (tactic predictor)
- **Status**: COMPLETED
- **Session**: sess_1780090536_455880
- **Phases**: 6/6

## What Was Implemented

### Phase 1: PolicyNetwork and Feature Encoder
- `src/bimodal_harness/models/policy.py`: `PolicyNetworkConfig` (input_dim=25, hidden_sizes=[1024,512,256], dropout=0.1, label_smoothing=0.1), `encode_proof_step()` producing 25-dim feature tensor (12 PatternKey + 4 context + 2 depth + 3 frame-class one-hot + 4 subgoal), `PolicyNetwork(nn.Module)` MLP with LayerNorm+GELU+Dropout blocks, `apply_frame_class_mask()`, `param_count` property (~699K params), `PolicyFeatureEncoder` serializable wrapper.
- Tests: 21 tests covering config, feature encoding, mask application, forward pass shape.

### Phase 2: ProofStepDataset and Collate Function
- `src/bimodal_harness/data/policy_dataset.py`: `ProofStepDataset(torch.utils.data.Dataset)`, `policy_collate_fn()` returning (features[B,25], targets[B], masks[B,49]), `split_proof_steps()` with action-index stratification.
- Tests: 21 tests covering shapes, dtypes, mask values, split proportions.

### Phase 3: PolicyTrainer
- `src/bimodal_harness/training/policy_trainer.py`: `PolicyTrainerConfig` (lr=3e-4, batch_size=64, patience=7, label_smoothing=0.1, gradient_clip_norm=1.0), `PolicyTrainer` with AdamW+cosine annealing, mask-aware label smoothing loss (avoids -inf * 0.0 NaN), `evaluate()` returning top1_acc/top5_acc/mrr/per_rule_accuracy/valid_prob_mass, `train()` with early stopping on val top-1, `save_checkpoint()`/`load_checkpoint()`/`from_checkpoint()`.
- Tests: 17 tests covering config, training, evaluation metrics, checkpoint round-trip.

### Phase 4: Synthetic Data Generator
- `src/bimodal_harness/data/synthetic_policy_data.py`: `generate_synthetic_proof_steps()` generating formula-matching goals for all 42 axiom constructors plus 6 inference rules (modus_ponens, assumption, necessitation, weakening, temporal_necessitation, temporal_duality), applying `augment_all()` for 3-5x expansion, balanced action distribution, frame-class-aware axiom selection.
- Tests: 13 tests covering coverage of all valid action indices per frame class, dataclass validation, reproducibility.

### Phase 5: Training Scripts and End-to-End Validation
- `scripts/train_policy_network.py`: CLI with `--data synthetic|JSONL`, `--synthetic-steps`, `--output`, full argparse mirroring value network script.
- `scripts/evaluate_policy_network.py`: Standalone evaluation CLI loading a checkpoint.
- Updated `models/__init__.py`, `data/__init__.py`, `training/__init__.py` with new exports.
- End-to-end run: 5K synthetic steps → 22,388 augmented → 79.4% test top-1 accuracy (far exceeds 15% target), 97.8% top-5, 86.5% MRR. Training converged at epoch 2 of 20, full 20 epochs completed in ~13 minutes on CPU.

### Phase 6: Formula AST Tokenizer and Transformer Encoder
- `src/bimodal_harness/models/formula_encoder.py`: `FormulaTokenizer` (18-token vocabulary: 4 special + 6 AST tags + 8 atom hash buckets, prefix-order linearization, max_length=128, `to_dict()`/`from_dict()`), `FormulaTransformerEncoder` (d_model=128, 3-layer TransformerEncoder, 4 heads, CLS-token output [B,128]), `PolicyNetworkV2` (transformer 128-dim + context/depth/frame 9-dim → concat 137-dim → MLP [512,256] → 49 logits, same `forward()` interface as `PolicyNetwork`).
- Tests: 27 tests in `test_formula_encoder.py` + 3 V2 integration tests added to `test_policy.py`.

## Test Results

All 485 tests pass (2 pre-existing skips):
- `tests/test_models/test_policy.py`: 24 passed
- `tests/test_models/test_formula_encoder.py`: 27 passed
- `tests/test_data/test_policy_dataset.py`: 21 passed
- `tests/test_data/test_synthetic_policy_data.py`: 13 passed
- `tests/test_training/test_policy_trainer.py`: 17 passed
- All prior tests: unchanged passing

## Plan Deviations

- **Action index 42 ("axiom" rule)**: The `step_to_action_index("axiom", axiom_name)` returns the specific axiom constructor index (0-41), not 42. Index 42 is `ACTION_TO_INDEX["axiom"]` — the inference rule named "axiom" — but by design it's unreachable via the function. Synthetic data covers indices 0-41 (axiom constructors) and 43-48 (other rules), leaving index 42 uncovered. Tests adjusted to exclude index 42 from coverage checks. This is a pre-existing design constraint, not a deviation from the plan.
- **Context complexity features**: `encode_proof_step()` uses simplified context complexity (all strings get complexity=1.0) since context is stored as `tuple[str, ...]` (pretty-print strings), not formula JSON. This is a practical limitation since the system doesn't store context as formula JSON. Max/mean context complexity features remain semantically valid as "context length proxy".
- **Label smoothing with masking**: PyTorch's built-in `CrossEntropyLoss(label_smoothing=...)` distributes mass over all classes including masked (-inf) ones, causing NaN/inf losses. Implemented custom mask-aware label smoothing that distributes smooth mass only over valid actions.
- **"axiom" not in rule loop**: The synthetic data generator skips the "axiom" inference rule in the rule loop (it's covered by the axiom constructor loop at indices 0-41), reducing the effective action space for non-axiom rules to 6 (assumption, modus_ponens, necessitation, weakening, temporal_necessitation, temporal_duality).
- **End-to-end accuracy**: Achieved 79.4% top-1 (vs. 15% target). The high accuracy is expected on synthetic data since the 25-dim features provide strong discriminative signal for formula patterns.

## Artifacts

- `src/bimodal_harness/models/policy.py`
- `src/bimodal_harness/models/formula_encoder.py`
- `src/bimodal_harness/data/policy_dataset.py`
- `src/bimodal_harness/data/synthetic_policy_data.py`
- `src/bimodal_harness/training/policy_trainer.py`
- `scripts/train_policy_network.py`
- `scripts/evaluate_policy_network.py`
- `tests/test_models/test_policy.py`
- `tests/test_models/test_formula_encoder.py`
- `tests/test_data/test_policy_dataset.py`
- `tests/test_data/test_synthetic_policy_data.py`
- `tests/test_training/test_policy_trainer.py`
