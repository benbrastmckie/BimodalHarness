# Implementation Plan: Static Data Ingestion Pipeline

- **Task**: 7 - Build static data ingestion pipeline
- **Status**: [NOT STARTED]
- **Effort**: 6 hours
- **Dependencies**: Task 4 (training data schema)
- **Research Inputs**: specs/007_build_static_data_ingestion_pipeline/reports/01_data-ingestion.md
- **Artifacts**: plans/01_data-ingestion-plan.md (this file)
- **Standards**: plan-format.md, status-markers.md, artifact-management.md, tasks.md
- **Type**: python
- **Lean Intent**: false

## Overview

Build the data ingestion pipeline that bridges the Lean-export schema (`data.schema.LabeledFormula`) to the ML-training schema (`schema.records.TrainingRecord`), producing PyTorch-compatible datasets. The core challenge is translating between two co-existing schema systems with mismatched field names, value encodings, and structural differences (labels, difficulty tiers, top operators, rule profiles, countermodel format). The pipeline loads JSONL files exported by BimodalLogic, translates each record, optionally caches to Parquet, and wraps the result in a `BimodalDataset` with stratified splitting and curriculum sampling.

### Research Integration

The research report (01_data-ingestion.md) identified:
- **Dual-schema conflict**: 7 field-level mismatches between `data.schema` and `schema.records` requiring explicit translation (label casing, difficulty_tier int-to-string, top_operator lowercase-to-PascalCase, absent fields like search_depth/record_id/formula_pretty, rule profile key divergence, countermodel format)
- **Box formula validation bug**: `schema/formula.py` defines box as requiring only `{"child"}` but the JSONL format includes `{"child", "event"}` -- validation rejects valid box formulas
- **Architecture recommendation**: JSONL -> LabeledFormula -> translate -> TrainingRecord -> BimodalDataset -> DataLoader, with optional Parquet caching via existing `schema.parquet` infrastructure
- **CurriculumSampler design**: Epoch-dependent difficulty gating using `difficulty_tier` for curriculum learning
- **HuggingFace integration**: `datasets` package listed but not installed; defer to optional final phase

### Prior Plan Reference

No prior plan.

### Roadmap Alignment

No ROADMAP.md found.

## Goals & Non-Goals

**Goals**:
- Implement `labeled_formula_to_training_record()` translation function with all field mappings
- Implement `ingest_jsonl()` and `ingest_directory()` pipeline entry points in `data/ingestion.py`
- Fix the `schema/formula.py` box validation bug (missing `event` field)
- Create `BimodalDataset(torch.utils.data.Dataset)` wrapping `list[TrainingRecord]`
- Implement stratified `split_dataset()` for train/val/test partitioning
- Implement `CurriculumSampler` for difficulty-ordered training
- Integrate Parquet caching for repeated training runs
- Achieve comprehensive test coverage for translation edge cases

**Non-Goals**:
- Tensor encoding of formula ASTs (deferred to task 20)
- Custom `collate_fn` for DataLoader batching (separate concern for model training)
- HuggingFace datasets integration (optional future work; `datasets` package not installed)
- Online/streaming ingestion from a running Lean process
- Lazy/memory-mapped JSONL loading (in-memory is sufficient for expected dataset size)

## Risks & Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Rule profile keys do not map between schemas | M | H | Default ML-schema RuleProfile to all zeros; document gap for future reconciliation |
| TIMEOUT records cause downstream errors | M | M | Filter at translation layer; collect separately for analysis |
| Difficulty tier mapping is incomplete for future tiers | L | L | Use lookup dict with explicit KeyError for unknown values |
| Box validation fix breaks existing tests | M | M | Run full test suite after fix; the fix adds a required field, not removes one |
| Parquet cache invalidation is unreliable | M | L | Use content hash of source JSONL files as cache key |
| Large datasets exceed memory | M | L | In-memory approach is safe for up to ~1M records; document lazy loading escape hatch |

## Implementation Phases

**Dependency Analysis**:
| Wave | Phases | Blocked by |
|------|--------|------------|
| 1 | 1 | -- |
| 2 | 2 | 1 |
| 3 | 3 | 2 |
| 4 | 4 | 2 |
| 5 | 5 | 3, 4 |

Phases within the same wave can execute in parallel.

---

### Phase 1: Fix Box Validation Bug and Schema Translation Layer [NOT STARTED]

**Goal**: Fix the `schema/formula.py` box validation bug and implement the core `labeled_formula_to_training_record()` translation function in `data/ingestion.py`.

**Tasks**:
- [ ] Fix `_REQUIRED_FIELDS` in `schema/formula.py`: change box from `frozenset({"child"})` to `frozenset({"child", "event"})` to match the actual bimodal JSONL format
- [ ] Update `validate_formula_json()` box branch to recursively validate both `child` and `event`
- [ ] Add unit tests for box formula validation with event field
- [ ] Define translation constants in `data/ingestion.py`: `DIFFICULTY_TIER_MAP` (int->str), `TOP_OPERATOR_MAP` (lowercase->PascalCase)
- [ ] Implement `labeled_formula_to_training_record(lf: LabeledFormula) -> TrainingRecord | None` covering all 7 field translations identified in research
- [ ] Handle TIMEOUT records (return None)
- [ ] Handle missing fields: generate `record_id` via `TrainingRecord.make_id()`, derive `formula_pretty` via `formula_json_to_pretty()`, default `search_depth` from `proof_trace.height` or 0, default `frame_class` to `"Base"`, default RuleProfile to all zeros
- [ ] Write unit tests for translation function covering: VALID record, INVALID record, TIMEOUT skip, all 6 top_operator mappings, all 5 difficulty_tier mappings, edge cases (missing optional fields)

**Timing**: 2 hours

**Depends on**: none

**Files to modify**:
- `src/bimodal_harness/schema/formula.py` - Fix box required fields and validation
- `src/bimodal_harness/data/ingestion.py` - Implement translation function and constants
- `tests/test_data/test_ingestion.py` - New: translation unit tests
- `tests/test_data/test_schema.py` - Add box validation tests with event field

**Verification**:
- All existing tests still pass after formula.py fix
- `pytest tests/test_data/test_ingestion.py` passes with coverage of all label types and field mappings
- Translation of `data/samples/test_formulas.jsonl` records produces valid TrainingRecord objects

---

### Phase 2: Pipeline Entry Points and Directory Ingestion [NOT STARTED]

**Goal**: Implement `ingest_jsonl()`, `ingest_directory()`, and update the `data/__init__.py` public API to expose ingestion functions.

**Tasks**:
- [ ] Implement `ingest_jsonl(path: Path, *, skip_timeout: bool = True) -> list[TrainingRecord]` using `load_jsonl()` + `labeled_formula_to_training_record()`
- [ ] Implement `ingest_directory(data_dir: Path, *, glob: str = "*.jsonl") -> list[TrainingRecord]` to load and merge all JSONL files in a directory
- [ ] Add logging: record count, skip count (TIMEOUT), file count for directory ingestion
- [ ] Update `data/__init__.py` to export `ingest_jsonl`, `ingest_directory`, `labeled_formula_to_training_record`
- [ ] Write integration tests: ingest the sample file `data/samples/test_formulas.jsonl`, verify record count (should be 5 after filtering 1 TIMEOUT and 2 edge cases), verify field values on specific records
- [ ] Write tests for `ingest_directory()` with a temp directory containing multiple JSONL files
- [ ] Write test for empty file and file with only TIMEOUT records

**Timing**: 1.5 hours

**Depends on**: 1

**Files to modify**:
- `src/bimodal_harness/data/ingestion.py` - Add pipeline entry points
- `src/bimodal_harness/data/__init__.py` - Export new functions
- `tests/test_data/test_ingestion.py` - Add integration tests

**Verification**:
- `ingest_jsonl("data/samples/test_formulas.jsonl")` returns a list of TrainingRecord objects with correct field translations
- `pytest tests/test_data/` passes with no failures
- `ruff check src/bimodal_harness/data/` passes cleanly

---

### Phase 3: BimodalDataset and Data Splitting [NOT STARTED]

**Goal**: Create `BimodalDataset(torch.utils.data.Dataset)` and `split_dataset()` for train/val/test partitioning with difficulty stratification.

**Tasks**:
- [ ] Create `src/bimodal_harness/data/dataset.py` with `BimodalDataset` class wrapping `list[TrainingRecord]`
- [ ] Implement `__len__`, `__getitem__` returning the TrainingRecord (tensor encoding deferred to task 20)
- [ ] Add `labels` property returning list of label strings for stratification
- [ ] Add `difficulty_tiers` property returning list of difficulty tier strings
- [ ] Implement `split_dataset(records, train_ratio=0.8, val_ratio=0.1, test_ratio=0.1, stratify=True, seed=42) -> tuple[BimodalDataset, BimodalDataset, BimodalDataset]` using stratified sampling on `(label, difficulty_tier)`
- [ ] Handle edge cases: single-class datasets, too-few records for stratification (fall back to random split)
- [ ] Update `data/__init__.py` to export `BimodalDataset` and `split_dataset`
- [ ] Write unit tests for dataset indexing, length, stratified split proportions, seed reproducibility

**Timing**: 1.5 hours

**Depends on**: 2

**Files to modify**:
- `src/bimodal_harness/data/dataset.py` - New: BimodalDataset and split_dataset
- `src/bimodal_harness/data/__init__.py` - Export dataset classes
- `tests/test_data/test_dataset.py` - New: dataset and splitting tests

**Verification**:
- `BimodalDataset` is compatible with `torch.utils.data.DataLoader`
- Stratified split preserves label and difficulty proportions within tolerance
- `pytest tests/test_data/test_dataset.py` passes

---

### Phase 4: CurriculumSampler and Parquet Cache Integration [NOT STARTED]

**Goal**: Implement `CurriculumSampler` for epoch-gated difficulty progression and integrate Parquet caching for repeated training runs.

**Tasks**:
- [ ] Implement `CurriculumSampler(torch.utils.data.Sampler)` in `data/dataset.py` with epoch-dependent tier cutoff: `tier_cutoff = 1 + int(4 * epoch / max_epochs)`
- [ ] CurriculumSampler accepts `dataset: BimodalDataset`, `epoch: int`, `max_epochs: int`, optional `shuffle: bool`
- [ ] Implement `__iter__` yielding indices for records with `difficulty_tier <= tier_cutoff`, with optional shuffle
- [ ] Implement `__len__` returning the count of eligible indices
- [ ] Implement `ingest_and_cache(jsonl_dir: Path, cache_path: Path) -> list[TrainingRecord]` in `data/ingestion.py`: load JSONL, translate, write Parquet via `records_to_parquet()`, return records
- [ ] Implement `load_cached(cache_path: Path) -> list[TrainingRecord]` using `parquet_to_records()`
- [ ] Add cache freshness check: compare modification times of JSONL source files against cache file
- [ ] Update `data/__init__.py` to export `CurriculumSampler`, `ingest_and_cache`, `load_cached`
- [ ] Write tests for CurriculumSampler: verify tier gating at different epochs, verify all records included at final epoch, verify shuffle seed reproducibility
- [ ] Write tests for Parquet cache round-trip: ingest -> cache -> load -> verify field equality

**Timing**: 1.5 hours

**Depends on**: 2

**Files to modify**:
- `src/bimodal_harness/data/dataset.py` - Add CurriculumSampler
- `src/bimodal_harness/data/ingestion.py` - Add cache functions
- `src/bimodal_harness/data/__init__.py` - Export new symbols
- `tests/test_data/test_dataset.py` - Add sampler tests
- `tests/test_data/test_ingestion.py` - Add cache round-trip tests

**Verification**:
- CurriculumSampler produces correct subsets at epoch boundaries
- Parquet cache round-trip preserves all TrainingRecord fields exactly
- `pytest tests/test_data/` passes with all new tests

---

### Phase 5: End-to-End Integration and Type Checking [NOT STARTED]

**Goal**: Run the full pipeline end-to-end on sample data, verify type checking, and ensure all tests pass across the codebase.

**Tasks**:
- [ ] Write end-to-end integration test: `ingest_jsonl(sample_path)` -> `split_dataset()` -> `BimodalDataset` -> `DataLoader(batch_size=2)` -> iterate one batch
- [ ] Write end-to-end test with Parquet cache: `ingest_and_cache()` -> `load_cached()` -> `BimodalDataset` -> verify
- [ ] Run `mypy src/bimodal_harness/data/` and fix any type errors
- [ ] Run `ruff check src/bimodal_harness/data/` and fix any lint issues
- [ ] Run full test suite `pytest` and verify no regressions
- [ ] Verify `data/ingestion.py` docstrings are complete and accurate
- [ ] Verify `data/dataset.py` docstrings are complete and accurate

**Timing**: 1 hour

**Depends on**: 3, 4

**Files to modify**:
- `tests/test_data/test_integration.py` - Add end-to-end pipeline tests
- `src/bimodal_harness/data/ingestion.py` - Fix any type/lint issues
- `src/bimodal_harness/data/dataset.py` - Fix any type/lint issues

**Verification**:
- `pytest` passes with zero failures across entire test suite
- `mypy src/bimodal_harness/data/` reports no errors
- `ruff check src/bimodal_harness/data/` reports no issues
- End-to-end pipeline produces a working DataLoader from sample JSONL

## Testing & Validation

- [ ] Translation function handles all 3 label types (VALID, INVALID, TIMEOUT)
- [ ] All 6 top_operator values map correctly (atom, bot, imp, box, untl, snce -> PascalCase)
- [ ] All 5 difficulty tiers map correctly (1-5 -> trivial/easy/medium/hard/very_hard)
- [ ] Box formula validation accepts `{"tag": "box", "child": ..., "event": ...}` format
- [ ] TIMEOUT records are skipped (return None from translation)
- [ ] `ingest_jsonl()` on `data/samples/test_formulas.jsonl` produces correct record count
- [ ] `BimodalDataset` is compatible with `torch.utils.data.DataLoader`
- [ ] Stratified split preserves label/tier proportions
- [ ] CurriculumSampler gates correctly at epoch boundaries
- [ ] Parquet cache round-trip preserves all fields
- [ ] `mypy` and `ruff` pass clean on all modified files
- [ ] No regressions in existing test suite

## Artifacts & Outputs

- `specs/007_build_static_data_ingestion_pipeline/plans/01_data-ingestion-plan.md` (this file)
- `src/bimodal_harness/data/ingestion.py` - Translation layer and pipeline entry points
- `src/bimodal_harness/data/dataset.py` - BimodalDataset, split_dataset, CurriculumSampler
- `src/bimodal_harness/schema/formula.py` - Box validation fix
- `src/bimodal_harness/data/__init__.py` - Updated public API
- `tests/test_data/test_ingestion.py` - Translation and pipeline tests
- `tests/test_data/test_dataset.py` - Dataset and sampler tests
- `tests/test_data/test_integration.py` - End-to-end pipeline tests

## Rollback/Contingency

- The box validation fix in `schema/formula.py` is a single-line change to `_REQUIRED_FIELDS` and a small branch update; revert by restoring the original frozenset
- All new code is in new files (`data/dataset.py`) or the existing stub (`data/ingestion.py`); rollback by reverting those files
- If rule profile translation proves more complex than expected (future Lean exports include different keys), the all-zeros default is safe for initial training -- it means rule counts are not used as features until a proper mapping is established
- If `datasets` package is needed sooner than expected, install it and add `to_hf_dataset()` as a separate utility function
