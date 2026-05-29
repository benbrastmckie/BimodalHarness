# Implementation Plan: Task #11

- **Task**: 11 - Implement value network (proof-progress predictor)
- **Status**: [COMPLETED]
- **Effort**: 5 hours
- **Dependencies**: Task 7 (BimodalDataset), Task 10 (PatternKey feature extraction)
- **Research Inputs**: specs/011_implement_value_network_proof_progress_predictor/reports/01_value-network.md
- **Artifacts**: plans/01_value-network-plan.md (this file)
- **Standards**: plan-format.md, status-markers.md, artifact-management.md, tasks.md
- **Type**: python
- **Lean Intent**: false

## Overview

Build a PyTorch MLP value network that takes 12-dimensional PatternKey features (4 log1p-normalized numeric features + 8 one-hot GoalCategory encoding) and predicts derivation tree height via regression. The model targets approximately 2.78M parameters using a configurable `[2048, 1024, 512, 256]` hidden-layer architecture with GELU activation, LayerNorm, and Softplus output. A standalone training script with configurable hyperparameters, Huber loss, early stopping, and checkpoint save/load will be provided alongside comprehensive unit tests.

### Research Integration

The research report (01_value-network.md) identified the following key findings integrated into this plan:

- **Input encoding**: 12-dim input (4 numeric log1p-normalized + 8 one-hot `top_operator`). Fixed normalization via `log1p()` avoids dataset-dependent statistics.
- **Architecture**: `Linear -> LayerNorm -> GELU -> Dropout` per hidden block, Softplus output for non-negative predictions. Default hidden sizes `[2048, 1024, 512, 256]` yield 2.78M params.
- **Loss function**: Huber loss (delta=1.0), robust to outlier proof tree heights.
- **Training integration**: Custom `collate_fn` filters to `label == "valid"` records; existing `CurriculumSampler` provides difficulty progression.
- **Existing infrastructure**: `PatternKey` extractor in `schema/features.py`, `BimodalDataset` in `data/dataset.py`, stub file at `models/value.py`.

### Prior Plan Reference

No prior plan.

### Roadmap Alignment

No ROADMAP.md found.

## Goals & Non-Goals

**Goals**:
- Implement `ValueNetwork(nn.Module)` with configurable hidden layer sizes, dropout, and activation
- Implement `ValueNetworkConfig` dataclass with all tunable hyperparameters
- Implement `encode_pattern_key()` for tensor encoding (log1p numerics + one-hot categorical)
- Implement `FeatureNormalizer` class for serializable normalization logic
- Implement `ValueTrainer` class with train/evaluate/checkpoint methods
- Implement `value_collate_fn()` for DataLoader integration
- Create standalone CLI training script with argparse
- Export public API from `models/__init__.py`
- Achieve full test coverage for encoding, forward pass shapes, loss computation, and checkpoint round-trip

**Non-Goals**:
- Full AlphaZero training loop integration (task 16 scope)
- Tree-structured formula encoder (task 20 scope)
- Policy network implementation (separate task)
- GPU/CUDA optimization (CPU-only per specification)
- Hyperparameter search or automated tuning

## Risks & Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Over-parameterized for 12-dim input | M | M | Configurable hidden_sizes; default 2.78M is validated by research; smaller configs available |
| Huber loss delta sensitivity | L | L | delta=1.0 is standard default; configurable in ValueNetworkConfig |
| Empty batches from valid-only filtering in collate_fn | H | L | Return empty tensors with proper shape; DataLoader handles gracefully |
| CurriculumSampler epoch parameter coupling | M | L | ValueTrainer passes epoch through; document the interface contract |
| Checkpoint format breaking on config changes | M | L | Include config dict in checkpoint; version the checkpoint format |

## Implementation Phases

**Dependency Analysis**:
| Wave | Phases | Blocked by |
|------|--------|------------|
| 1 | 1 | -- |
| 2 | 2 | 1 |
| 3 | 3 | 2 |
| 4 | 4 | 2 |

Phases within the same wave can execute in parallel.

---

### Phase 1: Core Model and Feature Encoding [COMPLETED]

**Goal**: Implement the ValueNetwork module, ValueNetworkConfig, encode_pattern_key, and FeatureNormalizer in `models/value.py`. Update `models/__init__.py` exports.

**Tasks**:
- [ ] Define `ValueNetworkConfig` dataclass with fields: `input_dim` (default 12), `hidden_sizes` (default `[2048, 1024, 512, 256]`), `dropout` (default 0.1), `output_activation` (default "softplus")
- [ ] Implement `encode_pattern_key(pattern_key: PatternKey) -> torch.Tensor` that applies log1p to 4 numeric features and one-hot encodes `top_operator` across 8 categories, returning shape `[12]`
- [ ] Define ordered mapping `TOP_OPERATOR_INDEX: dict[str, int]` mapping VALID_TOP_OPERATORS to indices 0-7
- [ ] Implement `FeatureNormalizer` class with `encode(pattern_key) -> Tensor`, `to_dict() -> dict`, `from_dict(dict) -> FeatureNormalizer` for checkpoint serialization
- [ ] Implement `ValueNetwork(nn.Module)` with `__init__(config: ValueNetworkConfig)` building `nn.Sequential` of `[Linear, LayerNorm, GELU, Dropout]` blocks per hidden size, final `Linear(last_hidden, 1)` followed by `nn.Softplus()`
- [ ] Implement `ValueNetwork.forward(x: Tensor) -> Tensor` with input shape `[B, 12]`, output shape `[B, 1]`
- [ ] Add `ValueNetwork.param_count() -> int` property for parameter counting
- [ ] Update `src/bimodal_harness/models/__init__.py` to export `ValueNetwork`, `ValueNetworkConfig`, `encode_pattern_key`, `FeatureNormalizer`

**Timing**: 1.5 hours

**Depends on**: none

**Files to modify**:
- `src/bimodal_harness/models/value.py` - Full implementation (new content)
- `src/bimodal_harness/models/__init__.py` - Add exports

**Verification**:
- `ValueNetwork` instantiates with default config
- `param_count` returns approximately 2.78M for default config
- `forward()` accepts `[B, 12]` input and returns `[B, 1]` non-negative output
- `encode_pattern_key` produces correct 12-dim tensor for known PatternKey values
- `FeatureNormalizer` round-trips through `to_dict()`/`from_dict()`

---

### Phase 2: Training Infrastructure [COMPLETED]

**Goal**: Implement `ValueTrainer` and `value_collate_fn` in a new `training/value_trainer.py` module, providing train/evaluate/checkpoint functionality.

**Tasks**:
- [ ] Create `src/bimodal_harness/training/value_trainer.py`
- [ ] Implement `value_collate_fn(records: list[TrainingRecord]) -> tuple[Tensor, Tensor]` that filters to `label == "valid"` with non-None `proof_trace`, encodes PatternKey features, stacks heights as targets, handles empty batch edge case
- [ ] Define `TrainerConfig` dataclass with fields: `learning_rate` (3e-4), `batch_size` (64), `max_epochs` (50), `huber_delta` (1.0), `weight_decay` (1e-4), `patience` (7), `use_curriculum` (True)
- [ ] Implement `ValueTrainer.__init__(model, config, train_dataset, val_dataset)` setting up Adam optimizer, HuberLoss, CosineAnnealingLR scheduler
- [ ] Implement `ValueTrainer.train_epoch(epoch) -> float` running one training epoch, returning mean loss; integrate CurriculumSampler when `use_curriculum` is True
- [ ] Implement `ValueTrainer.evaluate(dataset) -> dict[str, float]` computing MAE, Spearman correlation, and accuracy-at-plus-minus-1 on a dataset
- [ ] Implement `ValueTrainer.train() -> dict` running the full training loop with early stopping on validation MAE, returning best metrics
- [ ] Implement `ValueTrainer.save_checkpoint(path)` and `ValueTrainer.load_checkpoint(path)` saving/loading model state, config, normalizer, epoch, and best_val_mae
- [ ] Update `src/bimodal_harness/training/__init__.py` to export `ValueTrainer`, `TrainerConfig`, `value_collate_fn`

**Timing**: 2 hours

**Depends on**: 1

**Files to modify**:
- `src/bimodal_harness/training/value_trainer.py` - New file, full implementation
- `src/bimodal_harness/training/__init__.py` - Add exports

**Verification**:
- `value_collate_fn` correctly filters invalid records and produces `[B, 12]` features and `[B, 1]` targets
- `value_collate_fn` returns empty tensors with correct shape for all-invalid batches
- `ValueTrainer.train_epoch()` runs without error on a small synthetic dataset
- `ValueTrainer.evaluate()` returns dict with `mae`, `spearman`, and `accuracy_at_1` keys
- Checkpoint save/load round-trips successfully, model produces identical outputs before and after

---

### Phase 3: CLI Training Script [COMPLETED]

**Goal**: Create a standalone CLI entry point that loads JSONL data, trains the value network, saves a checkpoint, and prints evaluation metrics.

**Tasks**:
- [ ] Create `scripts/train_value_network.py` with argparse CLI
- [ ] Add arguments: `--data` (JSONL path), `--output` (checkpoint path), `--hidden-sizes` (comma-separated ints), `--dropout`, `--lr`, `--batch-size`, `--max-epochs`, `--patience`, `--huber-delta`, `--weight-decay`, `--seed`, `--no-curriculum`
- [ ] Implement data loading: read JSONL, deserialize to `TrainingRecord` list, call `split_dataset()`
- [ ] Instantiate `ValueNetworkConfig`, `ValueNetwork`, `ValueTrainer` from CLI args
- [ ] Run training, print epoch-by-epoch loss and validation metrics
- [ ] Save final checkpoint with best model weights
- [ ] Print summary table with test-set MAE, Spearman, accuracy-at-1

**Timing**: 1 hour

**Depends on**: 2

**Files to modify**:
- `scripts/train_value_network.py` - New file, CLI entry point

**Verification**:
- Script runs with `--help` and prints usage
- Script loads a small JSONL file and completes training without error
- Checkpoint file is written to the specified output path
- Summary metrics are printed to stdout

---

### Phase 4: Unit Tests [COMPLETED]

**Goal**: Comprehensive test coverage for the value network, feature encoding, collate function, and trainer.

**Tasks**:
- [ ] Create `tests/test_models/test_value.py`
- [ ] Test `encode_pattern_key` produces correct 12-dim tensor for an Atom formula (all zeros except one-hot)
- [ ] Test `encode_pattern_key` applies log1p correctly to numeric features
- [ ] Test `ValueNetwork` forward pass shape: `[B, 12]` input -> `[B, 1]` output
- [ ] Test `ValueNetwork` output is always non-negative (Softplus guarantee)
- [ ] Test `ValueNetwork` param_count matches expected value for default config
- [ ] Test `ValueNetwork` with custom hidden_sizes produces correct param count
- [ ] Test `FeatureNormalizer` to_dict/from_dict round-trip
- [ ] Create `tests/test_training/test_value_trainer.py`
- [ ] Test `value_collate_fn` filters out invalid-label records
- [ ] Test `value_collate_fn` handles all-invalid batch (empty tensors)
- [ ] Test `ValueTrainer.train_epoch` runs on synthetic data
- [ ] Test `ValueTrainer.evaluate` returns correct metric keys
- [ ] Test checkpoint save/load round-trip with model weight equality check
- [ ] Test that loaded model produces identical forward pass outputs

**Timing**: 1.5 hours

**Depends on**: 2

**Files to modify**:
- `tests/test_models/test_value.py` - New file
- `tests/test_training/test_value_trainer.py` - New file

**Verification**:
- All tests pass with `pytest tests/test_models/test_value.py tests/test_training/test_value_trainer.py -v`
- No test takes longer than 10 seconds (CPU-trainable constraint)

## Testing & Validation

- [ ] `pytest tests/test_models/test_value.py -v` passes all model unit tests
- [ ] `pytest tests/test_training/test_value_trainer.py -v` passes all trainer unit tests
- [ ] `python scripts/train_value_network.py --help` prints usage without error
- [ ] Smoke test: instantiate `ValueNetwork(ValueNetworkConfig())` and verify `param_count` is approximately 2.78M
- [ ] Forward pass test: random `[32, 12]` input through default model produces `[32, 1]` non-negative output
- [ ] Collate test: `value_collate_fn` with mixed valid/invalid records produces correctly filtered batch
- [ ] Checkpoint round-trip: save and reload model, verify output equality on same input
- [ ] Type check: `mypy src/bimodal_harness/models/value.py src/bimodal_harness/training/value_trainer.py` passes

## Artifacts & Outputs

- `src/bimodal_harness/models/value.py` - ValueNetwork, ValueNetworkConfig, encode_pattern_key, FeatureNormalizer
- `src/bimodal_harness/models/__init__.py` - Updated exports
- `src/bimodal_harness/training/value_trainer.py` - ValueTrainer, TrainerConfig, value_collate_fn
- `src/bimodal_harness/training/__init__.py` - Updated exports
- `scripts/train_value_network.py` - CLI training entry point
- `tests/test_models/test_value.py` - Model unit tests
- `tests/test_training/test_value_trainer.py` - Trainer unit tests

## Rollback/Contingency

All changes are additive (new files or minimal export additions to `__init__.py` files). Rollback is straightforward:
- Remove newly created files: `value.py` content, `value_trainer.py`, `train_value_network.py`, test files
- Revert `__init__.py` export additions
- No existing code is modified in a breaking way; the existing `models/value.py` stub is replaced, not patched
