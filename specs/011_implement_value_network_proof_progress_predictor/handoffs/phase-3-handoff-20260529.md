# Phase 3 Handoff: CLI Training Script

**Task**: 11 - Implement value network (proof-progress predictor)
**Phase**: 3 of 4
**Status**: COMPLETED
**Timestamp**: 2026-05-29

## What Was Done

Created `scripts/train_value_network.py` with full argparse CLI:

Arguments: --data (required), --output, --hidden-sizes (comma-separated), --dropout, --lr, --batch-size, --max-epochs, --patience, --huber-delta, --weight-decay, --seed, --no-curriculum, --train-ratio, --val-ratio

Features:
- Loads JSONL via `read_jsonl()` from schema.serialization
- Calls `split_dataset()` with configurable train/val ratios
- Builds ValueNetworkConfig and ValueTrainer from CLI args
- Calls `trainer.train()` with per-epoch progress table
- Saves best checkpoint to specified output path
- Evaluates on test split and prints summary metrics

## Verification Results

- `--help` works correctly, prints all options with defaults
- Smoke test: 50 synthetic records, 5 epochs, completes in 0.2s
- Checkpoint saved at specified path
- Test set evaluation prints MAE, Spearman, Accuracy@1

## Next Phase

Phase 4: Unit Tests (`tests/test_models/test_value.py`, `tests/test_training/test_value_trainer.py`)
