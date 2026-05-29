# Phase 2 Handoff: Training Infrastructure

**Task**: 11 - Implement value network (proof-progress predictor)
**Phase**: 2 of 4
**Status**: COMPLETED
**Timestamp**: 2026-05-29

## What Was Done

Created `src/bimodal_harness/training/value_trainer.py` with:

- `value_collate_fn(list[TrainingRecord]) -> (Tensor[N,12], Tensor[N,1])`: filters to label=="valid" + non-None proof_trace, encodes features via FeatureNormalizer, returns empty tensors of correct shape for all-invalid batches
- `TrainerConfig` dataclass: learning_rate=3e-4, batch_size=64, max_epochs=50, huber_delta=1.0, weight_decay=1e-4, patience=7, use_curriculum=True, seed=42; with `to_dict`/`from_dict`
- `ValueTrainer.__init__`: sets up Adam optimizer, HuberLoss, CosineAnnealingLR scheduler
- `ValueTrainer.train_epoch(epoch) -> float`: one epoch with optional CurriculumSampler; returns mean Huber loss (0.0 for empty epochs)
- `ValueTrainer.evaluate(dataset) -> dict`: computes mae, spearman, accuracy_at_1; handles constant-input spearman edge case (returns 0.0)
- `ValueTrainer.train() -> dict`: full loop with early stopping, restores best weights
- `ValueTrainer.save_checkpoint(path)` / `load_checkpoint(path)`: saves model_state_dict, config, trainer_config, normalizer, epoch, best_val_mae
- `ValueTrainer.from_checkpoint(path, train_ds, val_ds)`: class method for full restore

Updated `src/bimodal_harness/training/__init__.py` to export ValueTrainer, TrainerConfig, value_collate_fn.

## Verification Results

- collate_fn filters 20 valid + 5 invalid -> [20,12] features, [20,1] targets
- Empty batch (all invalid) -> ([0,12], [0,1]) tensors
- `train_epoch(0)` on synthetic data completes without error
- `evaluate()` returns correct keys: mae, spearman, accuracy_at_1
- Checkpoint round-trip: outputs match when model.eval() before both measurement and reload

## Notes

- Checkpoint outputs match only when model is in eval mode (dropout off). This is correct behavior; tests must call model.eval() before comparing predictions.

## Next Phase

Phase 3: CLI Training Script (`scripts/train_value_network.py`) and Phase 4: Unit Tests
