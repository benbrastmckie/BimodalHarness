# Research Report: Static Data Ingestion Pipeline

**Task**: 7 — Build static data ingestion pipeline
**Date**: 2026-05-29
**Agent**: python-research-agent

---

## 1. Existing Schema Infrastructure

Two schema systems coexist in the project, with a key mismatch that the ingestion pipeline must bridge:

### 1a. `bimodal_harness.data.schema` (data contract layer)

Located at `src/bimodal_harness/data/schema.py`. This is the **Lean-export-facing** schema, designed to parse JSONL produced by `BimodalLogic/DataExport.lean` directly. It uses snake_case field names matching the actual JSONL format from `data/samples/test_formulas.jsonl`:

```
formula: {tag, name/left/right/child/event/guard}
label: "VALID" | "INVALID" | "TIMEOUT"
metrics: {complexity, modal_depth, temporal_depth, imp_count, atom_count, decision_time_ms, difficulty_tier}
pattern_key: {modal_depth, temporal_depth, imp_count, complexity, top_operator}
proof_trace: {height, axioms_used, rules_applied: {imp_left, imp_right, ...}}
countermodel: {true_atoms, false_atoms, formula}
```

The `load_jsonl()` generator at the bottom of this file handles blank lines and comment lines, yields `LabeledFormula` objects lazily. The `data/__init__.py` exports this as the primary public API.

### 1b. `bimodal_harness.schema` (ML training layer)

Located at `src/bimodal_harness/schema/`. This is the **ML-facing** schema used by the training system. Key differences from the data layer:

- Uses `TrainingRecord` (not `LabeledFormula`) as the primary type
- `label` values are lowercase: `"valid"` / `"invalid"` (not `"VALID"` / `"INVALID"`)
- `DifficultyMetrics` expects `difficulty_tier` as string from `VALID_DIFFICULTY_TIERS = {"trivial", "easy", "medium", "hard", "very_hard"}` — not an integer (the JSONL has `difficulty_tier: 1..5`)
- `PatternKey.top_operator` expects PascalCase GoalCategory names (`"Atom"`, `"Box"`, `"Implication"`, etc.) — the JSONL has lowercase: `"atom"`, `"box"`, `"imp"`
- `TrainingRecord` adds `record_id` (UUID), `formula_pretty` (string), `schema_version`, `frame_class`, `source`, `logic_system`
- `DifficultyMetrics` adds `search_depth` (not in JSONL)
- `RuleProfile` fields differ: schema has `axiom_count`, `mp_count`, `necessitation_count`, etc.; JSONL has `imp_left`, `imp_right`, `box_left`, etc.

### Schema Mismatch Summary

| Field | JSONL (data layer) | ML Schema (training layer) |
|-------|-------------------|---------------------------|
| `label` | `"VALID"/"INVALID"/"TIMEOUT"` | `"valid"/"invalid"` (no TIMEOUT) |
| `difficulty_tier` | integer 1–5 | string: "trivial"/"easy"/... |
| `top_operator` | `"imp"/"box"/"atom"` | `"Implication"/"Box"/"Atom"` |
| `search_depth` | absent | required (int) |
| `record_id` | absent | required (UUID) |
| `formula_pretty` | absent | required (string) |
| `frame_class` | absent | required (one of Base/Dense/Discrete) |
| Rule profile keys | `imp_left`, `box_right`, etc. | `axiom_count`, `mp_count`, etc. |

The ingestion pipeline must perform **translation** between the two schemas in addition to loading.

---

## 2. JSONL Format (Confirmed from Samples)

The file `data/samples/test_formulas.jsonl` has 8 records covering all 6 formula tags and 3 label types. Key observations:

- Records are self-contained: no line continuations
- `proof_trace.rules_applied` uses tableau rule names (`imp_left`, `imp_right`, `box_left`, `box_right`, `untl_left`, `untl_right`, `snce_left`) — these are **different** from the ML schema's `RuleProfile`
- `countermodel.formula` is a string (e.g., `"p -> q"`) — different from `schema.SimpleCountermodel` which stores `formula_json` as a dict
- TIMEOUT records have neither `proof_trace` nor `countermodel`
- All records have `metrics` and `pattern_key`

---

## 3. PyTorch Dataset Design

### Pattern: `torch.utils.data.Dataset` from JSONL

For the BimodalHarness use case, the recommended approach is:

**Option A — In-memory Dataset** (preferred for datasets up to ~1M records):

```python
class BimodalDataset(torch.utils.data.Dataset):
    def __init__(self, records: list[TrainingRecord]):
        self._records = records
    def __len__(self): return len(self._records)
    def __getitem__(self, idx): return self._records[idx]  # or tensor encoding
```

Load once with `read_jsonl()`, store in memory. This is straightforward and the existing `bimodal_harness.schema.serialization.read_jsonl()` already handles this well. PyTorch DataLoader with `num_workers > 0` works correctly since the dataset is already in memory.

**Option B — Lazy JSONL loader** (for very large files):

Pre-index byte offsets at startup, then seek-and-read per `__getitem__`. Adds complexity; only beneficial when dataset is too large for RAM (typically >10M records for this domain). Not recommended for initial implementation.

**Option C — Parquet-backed Dataset** (best for repeated training runs):

Convert JSONL to Parquet once using `bimodal_harness.schema.parquet.records_to_parquet()`, then use PyArrow's memory-mapped Parquet for fast columnar access. The `parquet.py` module is already implemented and supports this. PyArrow Parquet supports random-access row groups.

### Recommended Initial Architecture

```
JSONL files (data/bimodal/*.jsonl)
    ↓  load_jsonl()  [data.schema]
LabeledFormula stream
    ↓  translate_record()  [new: data.ingestion]
TrainingRecord objects
    ↓  (optionally) records_to_parquet()  [schema.parquet]
Parquet cache
    ↓  BimodalDataset.__getitem__()
tensors  →  DataLoader  →  training loop
```

### DataLoader Configuration

For proof search training data:
- `batch_size=64` to `256` (formulas are variable-length; requires custom collate)
- `shuffle=True` during training, `False` for val/test
- `num_workers=4` (safe with in-memory dataset)
- `pin_memory=True` when using GPU
- Custom `collate_fn` required: formula ASTs cannot be naively stacked; use padding or per-sample encoding first

---

## 4. HuggingFace Datasets Integration

The `datasets` package (version `>=3.0.0`) is listed in `pyproject.toml` but **not currently installed** in the development environment (`ModuleNotFoundError` at import time). PyTorch 2.11.0 and PyArrow 23.0.0 are installed.

If HuggingFace datasets is added:
- `datasets.Dataset.from_list(records_as_dicts)` converts a list of dicts
- `datasets.Dataset.from_parquet(path)` reads directly from the Parquet files already produced by `parquet.py`
- Provides built-in caching, sharding, and streaming via `IterableDataset`
- `datasets.DatasetDict` wraps train/val/test splits cleanly

For BimodalHarness, `datasets.Dataset.from_parquet()` is the cleanest integration path since Parquet serialization is already implemented.

---

## 5. Train/Val/Test Split Strategy

### Difficulty-Stratified Split

The `difficulty_tier` field (1–5 in the JSONL, mapped to "trivial"/"easy"/"medium"/"hard"/"very_hard" in ML schema) enables curriculum-aware splits:

- Stratify on `(label, difficulty_tier)` to ensure proportional representation
- Recommended ratio: 80% train / 10% val / 10% test
- `sklearn.model_selection.train_test_split(stratify=...)` or manual binning

### Curriculum Ordering

For curriculum learning (easier examples first):
- Primary sort key: `difficulty_tier` (ascending)
- Secondary sort key: `metrics.complexity` (ascending)
- Tertiary: shuffle within same tier

The `complexity` and `difficulty_tier` fields in `PatternKey`/`DifficultyMetrics` are sufficient for curriculum ordering. A `CurriculumSampler` can wrap the dataset:

```python
class CurriculumSampler(torch.utils.data.Sampler):
    def __init__(self, dataset, epoch: int, max_epochs: int):
        # Linearly expand difficulty range from tier 1 to all tiers
        tier_cutoff = 1 + int(4 * epoch / max_epochs)
        self._indices = [i for i, r in enumerate(dataset) if r.difficulty_tier <= tier_cutoff]
```

---

## 6. Key Design Decisions for `data/ingestion.py`

The `data/ingestion.py` file is currently a stub (2 lines). It should implement:

### 6a. Schema Translation Function

```python
def labeled_formula_to_training_record(lf: LabeledFormula) -> TrainingRecord | None:
    """Translate a LabeledFormula (Lean export) to a TrainingRecord (ML schema).
    Returns None for TIMEOUT records (no label for ML use)."""
```

Translation rules:
- `label`: `"VALID"` → `"valid"`, `"INVALID"` → `"invalid"`, `"TIMEOUT"` → skip (return None)
- `difficulty_tier`: integer 1–5 → `{1:"trivial", 2:"easy", 3:"medium", 4:"hard", 5:"very_hard"}`
- `top_operator`: lowercase → PascalCase (`"imp"` → `"Implication"`, `"box"` → `"Box"`, `"atom"` → `"Atom"`, `"bot"` → `"Bottom"`, `"untl"` → `"Until"`, `"snce"` → `"Since"`)
- `formula_pretty`: generate via `schema.formula.formula_json_to_pretty(lf.formula.to_json())`
- `record_id`: generate with `TrainingRecord.make_id()`
- `search_depth`: not available from Lean export; default to `proof_trace.height` for VALID, `0` for INVALID
- `frame_class`: default to `"Base"` (Lean exports Base frame class)
- `proof_trace.rule_profile`: the tableau rule names in JSONL don't map to ML schema's `RuleProfile` — default all to 0
- `countermodel.formula_json`: JSONL has a string; convert to formula JSON dict via `lf.countermodel.formula` is a string, not a tree — use the `lf.formula.to_json()` instead

### 6b. Pipeline Entry Point

```python
def ingest_jsonl(path: Path, *, skip_timeout: bool = True) -> list[TrainingRecord]:
    """Load JSONL from path, translate records, filter TOUGHOUTs."""
```

### 6c. Directory Ingestion

```python
def ingest_directory(data_dir: Path, *, glob: str = "*.jsonl") -> list[TrainingRecord]:
    """Load and merge all JSONL files in a directory."""
```

---

## 7. Tensor Encoding Strategy

The ML schema stores `formula_json` as a dict, not a tensor. Encoding is deferred to a separate module (task 20 covers countermodel tensor encoding). For the ingestion pipeline, the output is `list[TrainingRecord]` — tensors are produced by an encoding layer that sits between the dataset and the DataLoader collate function.

The `PatternKey` fields (`modal_depth`, `temporal_depth`, `imp_count`, `complexity`) are directly usable as feature vectors: 4 integers that can be stacked into `torch.tensor([modal_depth, temporal_depth, imp_count, complexity])`.

---

## 8. Dependencies

All required dependencies are already in `pyproject.toml`:
- `torch>=2.12.0` — installed (2.11.0, slightly below pin but functional)
- `pyarrow>=?` — installed (23.0.0) via implicit dependency of `datasets`
- `datasets>=3.0.0` — listed but **not installed**; HF integration is optional for initial pipeline

No new dependencies are required for the core ingestion pipeline (JSONL loading + translation + Parquet caching). The `datasets` package should be installed if HF integration is desired.

---

## 9. Recommended Implementation Plan

### Phase 1: Translation layer in `data/ingestion.py`
1. Implement `labeled_formula_to_training_record()` with all field mappings
2. Implement `ingest_jsonl(path)` and `ingest_directory(data_dir)`
3. Handle TIMEOUT records (skip or collect separately)
4. Tests in `tests/test_data/` covering translation edge cases

### Phase 2: PyTorch Dataset in `data/dataset.py`
1. `BimodalDataset(Dataset)` — in-memory, wraps `list[TrainingRecord]`
2. `__getitem__` returns a dict of tensors or a structured sample
3. `split_dataset(records, ratios, stratify_by)` for train/val/test splits
4. `CurriculumSampler` for difficulty-ordered training

### Phase 3: Parquet cache integration
1. `ingest_and_cache(jsonl_dir, cache_path)` — load JSONL → translate → write Parquet
2. `load_cached(cache_path)` — read Parquet → `BimodalDataset`
3. Cache invalidation based on `data/VERSION` content hash

### Phase 4: HuggingFace integration (optional)
1. `to_hf_dataset(records)` — wrap Parquet in `datasets.Dataset`
2. Requires installing `datasets` package

---

## 10. Schema Inconsistency: `formula.py` vs `data/schema.py`

The `schema/formula.py` file defines `box` as requiring only `{"child"}`, but `data/schema.py` shows `box` requires both `child` and `event` (the bimodal box has an event formula). The `data/samples/test_formulas.jsonl` confirms the two-argument form: `{"tag": "box", "child": {...}, "event": {...}}`. The `schema/formula.py` validation function is **incorrect** for the actual JSONL format — it will reject valid box formulas from BimodalLogic. This is a pre-existing bug to note during implementation.

---

## Summary

The ingestion pipeline needs to:
1. Fill `data/ingestion.py` with a schema translation layer bridging `LabeledFormula` → `TrainingRecord`
2. Handle the label, difficulty_tier, and top_operator mismatches explicitly
3. Implement a `BimodalDataset` wrapping `list[TrainingRecord]`
4. Leverage existing Parquet infrastructure (`schema/parquet.py`) for caching
5. Fix the `schema/formula.py` box validation bug (missing `event` field check)
6. TIMEOUT records should be skipped for supervised training (no label) but could be retained for analysis
