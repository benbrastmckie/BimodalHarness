# Implementation Summary: Task #5

**Completed**: 2026-05-29
**Duration**: ~2 hours

## Overview

Resolved 12 field-level mismatches between BimodalLogic's Lean `dataset_generator`
JSONL output and BimodalHarness's Python schema layers. The implementation aligned
`schema/constants.py`, `schema/records.py`, and `schema/formula.py` with the actual
Lean export format, added a canonical ingest adapter (`data/ingestion.py` Layer 2),
created a Lean-format test fixture, wrote 61 new tests, and documented the full
field mapping in `.context/data-contract.md`.

## What Changed

- `src/bimodal_harness/schema/constants.py` -- Added `"timeout"` to `VALID_LABELS`; removed `"trivial"` from `VALID_DIFFICULTY_TIERS` (Lean never emits it)
- `src/bimodal_harness/schema/records.py` -- Updated `ProofTrace.from_dict` to accept both `rules` dict and `rules_applied` string list; updated `DifficultyMetrics.from_dict` to accept camelCase Lean keys (`atomCount`, `modalDepth`, `decisionTimeMs`, `difficultyTier`) with snake_case fallback
- `src/bimodal_harness/schema/formula.py` -- Fixed `box` validation: requires only `child` (not `child` + `event`); `event` was a mismatch from the deprecated `data.schema` S4-modal interpretation
- `src/bimodal_harness/data/ingestion.py` -- Added Layer 2: `lean_export_to_training_record()`, `load_lean_jsonl()`, `filter_timeout_records()`; updated module docstring
- `src/bimodal_harness/data/schema.py` -- Added module-level `DeprecationWarning` with migration guide
- `src/bimodal_harness/data/__init__.py` -- Added deprecation notice to docstring; removed missing `dataset` module import
- `data/samples/test_lean_export.jsonl` -- Created: 8 Lean-format JSONL records with all 6 formula tags, 3 labels, correct camelCase/Atom-object format
- `tests/test_data/test_lean_ingestion.py` -- Created: 61 tests for `lean_export_to_training_record`, `load_lean_jsonl`, `filter_timeout_records`
- `tests/test_schema/test_records.py` -- Updated: removed `"trivial"` from valid tier list; changed invalid label test to use unrecognized string
- `tests/test_schema/test_serialization.py` -- Updated: changed `"trivial"` tier to `"easy"`
- `tests/test_schema/test_validation.py` -- Updated: changed `"trivial"` tier to `"easy"` in both fixture helpers
- `tests/test_schema/test_parquet.py` -- Updated: changed `"trivial"` tier to `"easy"`
- `.context/data-contract.md` -- Created: complete field-mapping reference for cross-repo development
- `.context/index.json` -- Created: context index with entry for data-contract

## Decisions

- Kept `"timeout"` as a valid label in `VALID_LABELS` rather than filtering it before validation -- Lean emits it and callers can filter via `skip_timeout=True` or `filter_timeout_records()`
- Created a NEW Lean-format fixture (`test_lean_export.jsonl`) rather than regenerating the existing `test_formulas.jsonl` -- the existing file is used by `test_integration.py` via the legacy `data.schema.load_jsonl` path which uses uppercase labels and integer tiers; changing it would require updating `test_integration.py` to use the new ingest adapter
- Mapped integer difficulty tier 1 (formerly "trivial") to "easy" in `DIFFICULTY_TIER_MAP` since "trivial" is not a valid Lean-export tier
- Fixed `formula.py` box validation as part of Phase 1 even though it wasn't in the plan's Phase 1 file list -- the pre-existing `test_validation.py` tests verified this was correct

## Plan Deviations

- **Task 1.extra** (altered): Also fixed `schema/formula.py` box validation (not listed in Phase 1 files) -- `_REQUIRED_FIELDS["box"]` required both `child` and `event`; changed to `child` only per Lean format
- **Task 3.update-tests** (deferred): `test_data/test_schema.py` and `test_data/test_integration.py` still import from the deprecated `data.schema` -- they test the legacy path which still works; migration would require a separate task
- **Task 4.regenerate-fixture** (altered): Created new `test_lean_export.jsonl` instead of regenerating `test_formulas.jsonl` -- avoids breaking legacy tests

## Verification

- Build: N/A (pure Python)
- Tests: 615 passed, 2 skipped, 18 deselected (pre-existing formula.mutator module error), 1 deprecation warning
- Files verified: All new/modified files exist and are non-empty
- Manual verification: `lean_export_to_training_record` handles all 12 mismatch points correctly as verified by 61 new tests

## Notes

- The 18 deselected tests (`tests/test_formula/test_ast.py`) have a pre-existing import error (`ModuleNotFoundError: No module named 'bimodal_harness.formula.mutator'`) that predates this task -- this is task 8's concern (Python formula generator)
- The deprecation warning from `ingestion.py` importing `data.schema` is intentional and expected -- `labeled_formula_to_training_record` still needs the legacy types to bridge the two schema layers
- Future cleanup: `test_integration.py` and `test_schema.py` should be updated to use `load_lean_jsonl` + `lean_export_to_training_record` and `test_lean_export.jsonl` as the primary fixture
