# Phase 1 Handoff: Core Model and Feature Encoding

**Task**: 11 - Implement value network (proof-progress predictor)
**Phase**: 1 of 4
**Status**: COMPLETED
**Timestamp**: 2026-05-29

## What Was Done

Implemented `src/bimodal_harness/models/value.py` with full content:

- `TOP_OPERATOR_INDEX`: stable alphabetically-sorted mapping of 8 VALID_TOP_OPERATORS to indices 0-7
- `ValueNetworkConfig` dataclass with input_dim=12, hidden_sizes=[2048,1024,512,256], dropout=0.1, output_activation="softplus"; includes `to_dict`/`from_dict`
- `encode_pattern_key(PatternKey) -> Tensor[12]`: log1p of 4 numeric features + 8-dim one-hot for top_operator
- `FeatureNormalizer`: wraps encode_pattern_key with `encode()`, `to_dict()`, `from_dict()` for checkpoint serialization
- `ValueNetwork(nn.Module)`: Sequential of [Linear, LayerNorm, GELU, Dropout] blocks + final Linear(last_hidden,1) + Softplus; `param_count` property

Updated `src/bimodal_harness/models/__init__.py` to export all public symbols.

## Verification Results

- `param_count`: 2,788,865 (~2.78M, matches design target)
- `forward([32,12])` -> shape [32,1], all values non-negative (Softplus guarantee)
- `encode_pattern_key` produces correct 12-dim tensor with log1p numerics and one-hot at correct index
- `FeatureNormalizer` round-trips through `to_dict()`/`from_dict()`

## Next Phase

Phase 2: Training Infrastructure (`value_trainer.py`)
- `value_collate_fn` filtering valid records with non-None proof_trace
- `TrainerConfig`, `ValueTrainer` with train/evaluate/checkpoint methods
