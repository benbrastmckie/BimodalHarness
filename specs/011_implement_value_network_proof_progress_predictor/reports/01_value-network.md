# Value Network Research Report

**Task**: 11 — Implement value network (proof-progress predictor)
**Date**: 2026-05-29
**Agent**: python-research-agent

---

## 1. Existing Infrastructure

### 1.1 PatternKey (input features)

`src/bimodal_harness/schema/records.py` defines:

```python
@dataclass(frozen=True, slots=True)
class PatternKey:
    modal_depth: int      # Max box-nesting depth
    temporal_depth: int   # Max until/since-nesting depth
    imp_count: int        # Total implication count
    complexity: int       # Total connective count + 1 (>= 1)
    top_operator: str     # One of 8 GoalCategory names
```

The 8 valid `top_operator` values (from `VALID_TOP_OPERATORS` in constants.py):
`Atom`, `Bottom`, `Implication`, `Box`, `AllPast`, `AllFuture`, `Until`, `Since`

### 1.2 Feature Extraction

`src/bimodal_harness/schema/features.py` implements `extract_pattern_key(formula_json) -> PatternKey` with full correspondence to Lean (Formula.lean and SuccessPatterns.lean). The function computes all 5 features from the raw formula JSON tree. This is the task 10 output and is ready to use.

### 1.3 TrainingRecord (supervision signal)

`ProofTrace.height` (int, >= 0) is the target label for regression. It lives at:
```python
record.proof_trace.height  # DerivationTree height for valid formulas
```
Only records with `label == "valid"` have a non-None `proof_trace`. Records with `label == "invalid"` or `"timeout"` must be excluded from height-regression training, or assigned a sentinel value.

### 1.4 BimodalDataset (task 7 output)

`src/bimodal_harness/data/dataset.py` wraps `list[TrainingRecord]` as a `torch.utils.data.Dataset`. Each `__getitem__` returns a raw `TrainingRecord`. The dataset provides:
- `labels` property (list of label strings)
- `difficulty_tiers` property
- `split_dataset()` for stratified train/val/test splits
- `CurriculumSampler` for epoch-gated difficulty progression

A custom `collate_fn` is needed to extract `PatternKey` tensors and `height` targets from raw records.

### 1.5 Model Stubs

`src/bimodal_harness/models/value.py` — contains only the module docstring and `from __future__ import annotations`. The file is ready to implement.

`src/bimodal_harness/models/policy.py` — identical stub state.

`src/bimodal_harness/training/loop.py` and `online.py` — also stubs. The training loop is task 16's scope; this task provides the model and a standalone training script.

### 1.6 PyTorch Version

Confirmed: `torch==2.11.0`, CPU only (no CUDA). This is fine for the 1.5M–10M param target.

---

## 2. Input Encoding

### 2.1 Numeric Features

Four non-negative integers with unbounded range in theory (but practically small for the bimodal logic formulas used in training data):
- `modal_depth` (typical range: 0–5)
- `temporal_depth` (typical range: 0–3)
- `imp_count` (typical range: 0–10)
- `complexity` (typical range: 1–30, always >= 1)

Recommended encoding: **log1p normalization** — `log(1 + x)` maps non-negative integers to a bounded positive range, is differentiable, and handles the heavy-tailed distributions typical of structural formula features. Alternatively, use running-statistics z-score normalization computed over the training set.

### 2.2 Categorical Feature

`top_operator` is one of 8 ordered categories. Recommended encoding: **one-hot** (8-dimensional), producing a sparse but exact representation. Learned embedding is overkill for 8 categories.

### 2.3 Total Input Dimension

```
4 numeric (log1p-normalized) + 8 one-hot = 12
```

Fixed input dimension `D_IN = 12`.

---

## 3. Network Architecture

### 3.1 Parameter Budget Analysis

With `D_IN = 12`, achieving 1.5M–10M parameters requires wide hidden layers:

| Config | Hidden sizes | Params | Notes |
|--------|-------------|--------|-------|
| small  | [256, 256, 128] | ~102K | Too small for target range |
| medium | [512, 512, 256] | ~401K | Below target |
| large  | [2048, 1024, 512, 256] | ~2.78M | Bottom of target range |
| xlarge | [4096, 2048, 1024] | ~10.54M | Top of target range |

**Recommended default**: `hidden_sizes = [2048, 1024, 512, 256]` (2.78M params). This sits comfortably within the target range and is CPU-trainable within minutes on small datasets.

**Note on the 1.5M–10M specification**: This range is appropriate for future formula-tree encoders (task 20, TreeLSTM or GNN inputs). For the current 12-feature input, the large/xlarge configs are necessary to hit the range. The configurable `hidden_sizes` parameter allows tuning.

### 3.2 Architecture Details

```python
class ValueNetwork(nn.Module):
    # Input: D_IN=12 encoded features
    # Hidden: configurable list of widths
    # Output: single scalar (height prediction)
    
    # Per-layer block: Linear -> LayerNorm -> GELU -> Dropout
    # Final layer: Linear -> Softplus (ensures non-negative output)
```

Activation: **GELU** (smoother gradients than ReLU, standard in modern MLPs).
Normalization: **LayerNorm** per hidden layer (better than BatchNorm for small batches and CPU training).
Output activation: **Softplus** — ensures non-negative predictions (`log(1 + exp(x))`), consistent with height >= 0.
Dropout: 0.1–0.2 for regularization.

### 3.3 Output Mode

**Regression** (predict raw height as a positive real number) is preferred over classification (difficulty buckets) because:
1. Height is an ordinal integer — regression preserves ordering and magnitude
2. The target distribution spans a continuous-like range
3. Simpler loss function (MSE or Huber)

Use **Huber loss** (`torch.nn.HuberLoss`) with `delta=1.0` as the primary loss — it is MSE near zero but L1 for large errors, making it robust to outlier heights in the training set.

---

## 4. Training Design

### 4.1 Collate Function

A custom `collate_fn` is needed to:
1. Filter out records where `label != "valid"` or `proof_trace is None`
2. Encode `PatternKey` into a tensor of shape `[B, 12]`
3. Stack heights into a target tensor of shape `[B, 1]`

```python
def value_collate_fn(records: list[TrainingRecord]) -> tuple[Tensor, Tensor]:
    valid = [r for r in records if r.label == "valid" and r.proof_trace is not None]
    features = torch.stack([encode_pattern_key(r.pattern_key) for r in valid])
    heights = torch.tensor([[r.proof_trace.height] for r in valid], dtype=torch.float32)
    return features, heights
```

### 4.2 Normalization

Log1p normalization for numerics should use **fixed constants** (not training-set statistics) since the formula features are interpretable and their scale is known. The `complexity` feature starts at 1, so `log1p(complexity - 1)` normalizes it to start at 0.

A `FeatureNormalizer` class can hold the normalization strategy and be serialized with the model checkpoint.

### 4.3 Training Loop

```
for epoch in range(max_epochs):
    sampler = CurriculumSampler(dataset, epoch=epoch, max_epochs=max_epochs)
    loader = DataLoader(dataset, sampler=sampler, collate_fn=value_collate_fn, batch_size=64)
    for features, heights in loader:
        optimizer.zero_grad()
        pred = model(features)
        loss = huber_loss(pred, heights)
        loss.backward()
        optimizer.step()
```

### 4.4 Hyperparameters (configurable)

| Parameter | Default | Notes |
|-----------|---------|-------|
| `hidden_sizes` | `[2048, 1024, 512, 256]` | 2.78M params |
| `dropout` | 0.1 | Applied after each hidden layer |
| `learning_rate` | 3e-4 | Adam, standard for MLPs |
| `batch_size` | 64 | CPU-friendly |
| `max_epochs` | 50 | With early stopping |
| `huber_delta` | 1.0 | Huber loss delta |
| `weight_decay` | 1e-4 | L2 regularization |
| `scheduler` | CosineAnnealingLR | T_max = max_epochs |
| `patience` | 7 | Early stopping patience |

### 4.5 Evaluation Metrics

- **MAE** (Mean Absolute Error on height): primary metric; lower is better
- **Spearman rank correlation** between predicted and actual height: measures monotonic ordering
- **Accuracy at ±1**: fraction of predictions within 1 step of true height
- **Baseline comparison**: dummy predictor using `SuccessData.avgDepth` from the pattern database

### 4.6 Checkpointing

Save:
```python
{
    "model_state_dict": model.state_dict(),
    "config": dataclasses.asdict(config),
    "normalizer": normalizer.to_dict(),
    "epoch": epoch,
    "best_val_mae": best_val_mae,
}
```

---

## 5. Lean SuccessPatterns Baseline

`SuccessPatterns.lean` implements a **hand-coded heuristic database**, not a learned predictor. The key heuristic for depth estimation is `suggestedDepth`:

```lean
def suggestedDepth (db : PatternDatabase) (φ : Formula) (defaultDepth : Nat := 20) : Nat :=
  match db.queryPatterns φ with
  | none => defaultDepth      -- No history: return 20
  | some data =>
      let avgDepth := data.avgDepth
      if avgDepth == 0 then defaultDepth
      else min (avgDepth * 2) defaultDepth  -- 2x average, capped at 20
```

The lookup uses `PatternKey` (same 5 features) as a hash key into `PatternDatabase`. This is an exact-match table — if the key has never been seen, it returns `defaultDepth = 20`. The `heuristicBonus` function gives strategy priority boosts (-2 to -10) based on strategy success rate thresholds (0.2, 0.5, 0.8).

**Weakness**: The exact-match table cannot generalize across unseen `(modal_depth, temporal_depth, impCount, complexity, topOperator)` combinations. The MLP value network will generalize continuously across the feature space.

**Baseline metric**: On the test set, a dummy predictor returning `min(avgDepth * 2, 20)` for seen keys and `20` for unseen keys establishes the floor. The value network should beat this on MAE.

---

## 6. Implementation Plan

### Files to Create

1. **`src/bimodal_harness/models/value.py`** — `ValueNetwork(nn.Module)`, `ValueNetworkConfig(dataclass)`, `encode_pattern_key()`, `FeatureNormalizer`

2. **`src/bimodal_harness/training/value_trainer.py`** — `ValueTrainer` class with `train()`, `evaluate()`, `save_checkpoint()`, `load_checkpoint()` methods; `value_collate_fn()`

3. **`scripts/train_value_network.py`** — CLI entry point using `argparse`; reads JSONL data, trains, saves checkpoint, prints metrics

4. **`tests/test_models/test_value.py`** — unit tests for encoding, forward pass shape, loss computation, save/load round-trip

### Files to Modify

- **`src/bimodal_harness/models/__init__.py`** — export `ValueNetwork`, `ValueNetworkConfig`

---

## 7. Key Design Decisions

1. **Regression over classification**: height is ordinal and continuous-like; regression with Softplus output preserves magnitude ordering.

2. **Huber loss over MSE**: robust to occasional very tall proof trees (outlier heights) which would dominate MSE gradients.

3. **GELU + LayerNorm over ReLU + BatchNorm**: GELU is smoother; LayerNorm works on CPU with small batch sizes without the instability of BatchNorm.

4. **Log1p normalization (fixed)**: avoids dataset-size-dependent normalization; `log1p` is monotonic and maps the bounded-but-skewed integer features to a well-behaved range.

5. **Softplus output activation**: guarantees non-negative predictions (height >= 0) without the hard zero-gradient of ReLU.

6. **`valid`-only training**: invalid formulas have no height target; timeout records have ambiguous height. Filter at collation time, not dataset creation time, to preserve the full dataset for the policy network.

7. **CurriculumSampler integration**: use the existing sampler from task 7; start with easy formulas (low height) and progressively include harder ones.

8. **Configurable hidden_sizes**: allows the `[2048, 1024, 512, 256]` default (2.78M) to be switched to `[4096, 2048, 1024]` (10.54M) without code changes.
