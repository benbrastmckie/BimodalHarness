# Implementation Summary: Static Data Ingestion Pipeline

- **Task**: 7 - Build static data ingestion pipeline
- **Status**: COMPLETED
- **Session**: sess_1780081000_c525c7
- **Date**: 2026-05-29

## What Was Built

A 5-phase implementation producing the full JSONL -> TrainingRecord -> PyTorch pipeline:

### Files Created

- `src/bimodal_harness/data/ingestion.py` - Translation layer + pipeline entry points + Parquet cache
- `src/bimodal_harness/data/dataset.py` - BimodalDataset, split_dataset, CurriculumSampler
- `src/bimodal_harness/data/__init__.py` - Updated public API (all new symbols exported)
- `tests/test_data/test_ingestion.py` - 55 translation + pipeline + cache tests
- `tests/test_data/test_dataset.py` - 29 dataset + sampler tests
- `tests/test_data/test_e2e_pipeline.py` - 6 end-to-end integration tests

### Files Modified

- `src/bimodal_harness/schema/formula.py` - Investigated box validation bug (see deviations)

## Test Results

- **Total tests**: 556 collected, 554 passed, 2 skipped, 0 failed
- **New tests added**: 90 (55 ingestion + 29 dataset + 6 e2e)
- **Zero regressions** in the prior 198-test baseline

## Key Translations Implemented

| Source (data.schema) | Target (schema.records) |
|----------------------|-------------------------|
| label "VALID" | label "valid" |
| label "INVALID" | label "invalid" |
| label "TIMEOUT" | None (skipped) |
| difficulty_tier 1-2 (int) | "easy" (string) |
| difficulty_tier 3 (int) | "medium" (string) |
| difficulty_tier 4 (int) | "hard" (string) |
| difficulty_tier 5 (int) | "very_hard" (string) |
| top_operator "atom" | "Atom" |
| top_operator "bot" | "Bottom" |
| top_operator "imp" | "Implication" |
| top_operator "box" | "Box" |
| top_operator "untl" | "Until" |
| top_operator "snce" | "Since" |
| countermodel.formula (str) | countermodel.formula_json (dict) |
| (absent) | record_id (UUID4) |
| (absent) | formula_pretty (derived) |
| (absent) | search_depth (from proof height or 0) |

## Plan Deviations

1. **Box validation "bug" was not a bug**: The plan identified `schema/formula.py` box validation as requiring only `{"child"}` while JSONL includes `{"child", "event"}` as a bug. Investigation revealed this is not a bug -- `validate_formula_json()` only requires the minimum required fields, and extra fields (like `event`) are silently ignored. A box formula with `{"tag": "box", "child": ..., "event": ...}` passes validation because `child` (the only required field) is present. The linter also reverted the change and added an explanatory comment. The box validation tests were updated to test the actual behavior.

2. **Difficulty tier mapping collapsed**: The plan mapped 5 tiers to 5 string values (1->trivial, 2->easy, 3->medium, 4->hard, 5->very_hard). However, `VALID_DIFFICULTY_TIERS` in `schema/constants.py` does not include "trivial". Both tiers 1 and 2 were mapped to "easy" instead. This was discovered at test time and corrected before any tests were committed to pass.

3. **Parquet cache implemented in Phase 2 (not Phase 4)**: The `ingest_and_cache()`, `load_cached()`, and `is_cache_fresh()` functions were co-located with other ingestion functions in `data/ingestion.py` rather than split between Phase 2 and Phase 4. This is a structural deviation that doesn't affect behavior; all cache functionality was present by the end of Phase 2 implementation.

4. **Phase 1 and 2 implemented together**: The translation function and pipeline entry points were implemented in a single pass of `data/ingestion.py`. The plan treated them as sequential phases but they are naturally co-located. Both were committed together.

5. **End-to-end tests in separate file**: The plan specified `tests/test_data/test_integration.py` for end-to-end tests. However, that file already existed with existing integration tests for the JSONL schema. The new end-to-end pipeline tests were placed in `tests/test_data/test_e2e_pipeline.py` to avoid conflicts with the existing test file.

6. **VALID_LABELS includes "timeout"**: The updated `schema/constants.py` includes `"timeout"` in `VALID_LABELS`, meaning TrainingRecord could store timeout records. The ingestion pipeline still skips TIMEOUT records by default (returning None from translation), which is the correct behavior for ML training.
