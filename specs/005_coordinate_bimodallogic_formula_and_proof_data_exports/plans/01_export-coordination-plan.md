# Implementation Plan: Task #5

- **Task**: 5 - Coordinate BimodalLogic formula and proof data exports
- **Status**: [IMPLEMENTING]
- **Effort**: 5 hours
- **Dependencies**: Task 3 (completed), Task 4 (completed)
- **Research Inputs**: specs/005_coordinate_bimodallogic_formula_and_proof_data_exports/reports/01_export-coordination.md
- **Artifacts**: plans/01_export-coordination-plan.md (this file)
- **Standards**: plan-format.md, status-markers.md, artifact-management.md, tasks.md
- **Type**: general
- **Lean Intent**: false

## Overview

This plan resolves the 12 field-level mismatches between BimodalLogic's Lean JSONL export and BimodalHarness's Python schema layers. The core problem is that two Python schema modules (`data/schema.py` and `schema/records.py`) diverge from each other and from what the Lean `dataset_generator` actually emits. The approach is: (1) align `records.py` and `constants.py` to accept Lean-exported data directly, (2) build a canonical ingest adapter in `data/ingestion.py` that translates Lean JSONL fields to `TrainingRecord`, (3) deprecate `data/schema.py` and redirect its callers, (4) regenerate test fixtures, and (5) create a data-contract reference document.

### Research Integration

Research report `01_export-coordination.md` identified 12 specific field-level mismatches between the Lean `dataset_generator` output and the Python schema expectations. Key findings integrated into this plan:

- `records.py ProofTrace.from_dict` reads key `rules` (dict), but Lean emits `rules_applied` (string list) -- the pragmatic fix is to accept both forms on the Python side.
- `records.py DifficultyMetrics` uses snake_case keys but Lean emits camelCase (`modalDepth`, `atomCount`, `decisionTimeMs`, `difficultyTier`); the ingest adapter must translate.
- `data/schema.py` has fundamentally wrong field names for `RuleProfile` (uses `imp_left`, `box_left` etc. instead of `axiom`, `modus_ponens` etc.) and requires an `event` field on `box` AST nodes that Lean does not emit.
- `VALID_LABELS` excludes `"timeout"` which Lean emits; must be extended or timeouts filtered.
- `VALID_DIFFICULTY_TIERS` includes `"trivial"` which Lean never emits; should be pruned.
- `search_depth` field in `DifficultyMetrics` has no Lean counterpart; must default to 0.
- Test fixtures in `data/samples/test_formulas.jsonl` use a hybrid format matching neither layer accurately.

### Prior Plan Reference

No prior plan.

### Roadmap Alignment

No ROADMAP.md found.

## Goals & Non-Goals

**Goals**:
- Resolve all 12 field-level mismatches so that Lean-exported JSONL can be loaded end-to-end into `TrainingRecord` objects
- Build a canonical ingest adapter (`data/ingestion.py`) that maps Lean JSONL to `TrainingRecord`
- Extend `constants.py` to accept `"timeout"` label and remove `"trivial"` difficulty tier
- Deprecate `data/schema.py` with clear deprecation notice and redirect callers to `schema/records.py`
- Regenerate test fixtures to match the actual Lean export format
- Create a data-contract reference document for cross-repo field mappings

**Non-Goals**:
- Modifying the Lean-side `DatasetExport.lean` code (Python adapts, Lean stays idiomatic)
- Building the full sync pipeline (already working via `make sync-data`)
- Implementing Parquet export (separate concern, handled by existing `schema/parquet.py`)
- Porting formula generation to Python (Task 8)

## Risks & Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Deprecating `data/schema.py` breaks downstream callers in tests and `data/__init__.py` | H | H | Phase 3 explicitly updates all 3 import sites; run full test suite to verify |
| `ProofTrace` format change: Lean emits `rules_applied` as string list, `records.py` expects `rules` as RuleProfile dict | M | H | Ingest adapter builds synthetic RuleProfile by counting string occurrences; `ProofTrace.from_dict` also accepts `rules_applied` key |
| `DifficultyMetrics` camelCase translation misses edge cases | M | M | Write explicit unit tests for camelCase-to-snake_case mapping in ingest adapter |
| Test fixtures currently use hybrid format; regenerating them may break existing passing tests | M | H | Update tests atomically with fixtures; verify all tests pass in Phase 4 |
| `box` AST node has `child`-only in Lean but `child`+`event` in `schema.py` | L | H | Only affects `schema.py` which is being deprecated; `schema/formula.py` handles `box` correctly with `child` only |

## Implementation Phases

**Dependency Analysis**:
| Wave | Phases | Blocked by |
|------|--------|------------|
| 1 | 1 | -- |
| 2 | 2, 3 | 1 |
| 3 | 4 | 2, 3 |
| 4 | 5 | 4 |

Phases within the same wave can execute in parallel.

---

### Phase 1: Align constants.py and records.py with Lean export format [COMPLETED]

**Goal**: Fix the `constants.py` valid sets and `records.py` deserialization methods so they can accept the exact field names and values that Lean's `dataset_generator` emits.

**Tasks**:
- [x] Extend `VALID_LABELS` in `constants.py` to include `"timeout"` *(completed)*
- [x] Remove `"trivial"` from `VALID_DIFFICULTY_TIERS` in `constants.py` *(completed)*
- [x] Update `ProofTrace.from_dict` in `records.py` to accept both `"rules"` key (RuleProfile dict) and `"rules_applied"` key (list of strings) *(completed)*
- [x] Update `DifficultyMetrics.from_dict` in `records.py` to accept camelCase keys from Lean *(completed)*
- [x] Verify `PatternKey.from_dict` already handles camelCase correctly (confirmed) *(completed)*
- [x] Verify `SimpleCountermodel.from_dict` already handles `trueAtoms`/`falseAtoms` with Atom objects (confirmed) *(completed)*

**Timing**: 1.5 hours

**Depends on**: none

**Files to modify**:
- `src/bimodal_harness/schema/constants.py` -- extend VALID_LABELS, prune VALID_DIFFICULTY_TIERS
- `src/bimodal_harness/schema/records.py` -- update ProofTrace.from_dict, DifficultyMetrics.from_dict

**Verification**:
- Existing tests in `tests/test_schema/test_records.py` still pass
- Can manually construct a `TrainingRecord` from a dict matching the Lean export shape

---

### Phase 2: Build canonical ingest adapter in data/ingestion.py [NOT STARTED]

**Goal**: Implement `lean_export_to_training_record()` that maps a raw Lean JSONL dict to a `TrainingRecord`, handling all field-name translations identified in the research report.

**Tasks**:
- [ ] Implement `lean_export_to_training_record(data: dict) -> TrainingRecord` in `src/bimodal_harness/data/ingestion.py` that performs:
  - `id` -> `record_id` (or generate UUID if absent)
  - `formula_ast` -> `formula_json`
  - `formula_str` -> `formula_pretty`
  - `label`: pass through lowercase (already matches `VALID_LABELS`)
  - `pattern_key`: pass camelCase dict to `PatternKey.from_dict`
  - `metrics`: translate camelCase keys to `DifficultyMetrics.from_dict` (using updated from Phase 1)
  - `proof_trace`: pass to `ProofTrace.from_dict` (handles both formats from Phase 1)
  - `countermodel`: pass to `SimpleCountermodel.from_dict`
  - `frame_class`: pass through (defaults to `"Base"`)
  - Set `search_depth=0`, `source="lean_export"`, `logic_system="TM_BX"`
- [ ] Implement `load_lean_jsonl(path: Path, *, skip_timeout: bool = True) -> list[TrainingRecord]` that reads a Lean-exported JSONL file, applies `lean_export_to_training_record` per line, optionally filtering timeout records
- [ ] Implement `filter_timeout_records(records: list[TrainingRecord]) -> list[TrainingRecord]` utility for filtering `"timeout"` label records after ingest
- [ ] Add type annotations and docstrings following existing codebase style

**Timing**: 1 hour

**Depends on**: 1

**Files to modify**:
- `src/bimodal_harness/data/ingestion.py` -- implement all three functions

**Verification**:
- Unit test: construct a sample Lean-format dict, pass to `lean_export_to_training_record`, verify all fields map correctly
- Unit test: load a sample Lean-format JSONL file, verify records parse without error
- Unit test: verify timeout filtering works correctly

---

### Phase 3: Deprecate data/schema.py and redirect callers [NOT STARTED]

**Goal**: Mark `data/schema.py` as deprecated with clear warnings and update all existing callers to use `schema/records.py` types instead.

**Tasks**:
- [ ] Add a module-level deprecation docstring and `warnings.warn` in `data/schema.py` indicating callers should use `bimodal_harness.schema.records` instead
- [ ] Update `src/bimodal_harness/data/__init__.py` to re-export from `schema.records` and `schema.constants` instead of `data.schema`; add deprecation shims for `LabeledFormula`, `FormulaNode`, etc. that emit `DeprecationWarning`
- [ ] Update `tests/test_data/test_schema.py` to import from `bimodal_harness.schema.records` (or adapt tests to use the ingest adapter)
- [ ] Update `tests/test_data/test_integration.py` to import from `bimodal_harness.schema.records` and use the ingest adapter
- [ ] Remove `load_jsonl` usage from `data/schema.py` in favor of `data/ingestion.py load_lean_jsonl` or `schema/serialization.py read_jsonl`

**Timing**: 1 hour

**Depends on**: 1

**Files to modify**:
- `src/bimodal_harness/data/schema.py` -- add deprecation warning
- `src/bimodal_harness/data/__init__.py` -- redirect exports
- `tests/test_data/test_schema.py` -- update imports
- `tests/test_data/test_integration.py` -- update imports

**Verification**:
- `import bimodal_harness.data.schema` triggers `DeprecationWarning`
- All existing test files import successfully from the new paths
- `pytest tests/test_data/` passes

---

### Phase 4: Regenerate test fixtures and write adapter tests [NOT STARTED]

**Goal**: Update `data/samples/test_formulas.jsonl` to match the actual Lean export format and write comprehensive tests for the ingest adapter and updated deserialization methods.

**Tasks**:
- [ ] Regenerate `data/samples/test_formulas.jsonl` to use the exact Lean `dataset_generator` field names and format:
  - Add `id`, `split`, `formula_str`, `formula_ast` (rename from `formula`), `frame_class`, `augmentation` fields
  - Use lowercase labels (`"valid"`, `"invalid"`, `"timeout"`)
  - Use camelCase for `pattern_key` and `metrics` fields
  - Use `"rules_applied"` as string list in `proof_trace` (not RuleProfile dict)
  - Use Atom objects (`{"base": "p", "fresh_index": null}`) in countermodel `trueAtoms`/`falseAtoms`
  - Use string `difficulty_tier` values (`"easy"`, `"medium"`, `"hard"`)
- [ ] Create `tests/test_data/test_ingestion.py` with tests:
  - Test `lean_export_to_training_record` with valid, invalid, and timeout records
  - Test field-name translation for all 12 mismatch points
  - Test `load_lean_jsonl` with the regenerated fixture file
  - Test `skip_timeout` flag filters correctly
  - Test edge cases: missing optional fields, empty proof traces
- [ ] Update `tests/test_data/test_schema.py` and `tests/test_data/test_integration.py` to work with regenerated fixtures (using the ingest adapter for Lean-format fixtures, or using `schema/serialization.py` for Python-format fixtures)
- [ ] Update `tests/test_schema/test_serialization.py` to verify `jsonl_dict_to_record` handles the updated `DifficultyMetrics` and `ProofTrace` from Phase 1
- [ ] Run full test suite: `pytest`

**Timing**: 1.5 hours

**Depends on**: 2, 3

**Files to modify**:
- `data/samples/test_formulas.jsonl` -- regenerate in Lean export format
- `tests/test_data/test_ingestion.py` -- new test file
- `tests/test_data/test_schema.py` -- update for new fixtures
- `tests/test_data/test_integration.py` -- update for new fixtures
- `tests/test_schema/test_serialization.py` -- add camelCase mapping tests

**Verification**:
- `pytest tests/test_data/` passes with zero failures
- `pytest tests/test_schema/` passes with zero failures
- `pytest` (full suite) passes
- Coverage of ingest adapter is >= 90% for lines touched

---

### Phase 5: Create data-contract reference document [NOT STARTED]

**Goal**: Write a canonical field-mapping reference document that developers can consult when working across the Lean/Python boundary.

**Tasks**:
- [ ] Create `.context/data-contract.md` containing:
  - Complete field-mapping table: Lean `dataset_generator` field name -> Python `TrainingRecord` field name
  - Type mapping table: Lean JSON types -> Python types
  - Label value mapping (lowercase passthrough)
  - PatternKey camelCase-to-snake_case mapping
  - DifficultyMetrics camelCase-to-snake_case mapping
  - ProofTrace format variants (string list vs RuleProfile dict)
  - SimpleCountermodel Atom object format
  - Sync workflow documentation (existing `make sync-data` usage)
  - Schema version compatibility notes
- [ ] Add entry to `.context/index.json` (if it exists) for the new data-contract document

**Timing**: 0.5 hours (documentation only)

**Depends on**: 4

**Files to modify**:
- `.context/data-contract.md` -- new file
- `.context/index.json` -- add entry (if file exists)

**Verification**:
- Document is readable and complete
- All 12 mismatches from the research report are addressed in the mapping table
- Sync workflow is documented with exact commands

## Testing & Validation

- [ ] `pytest tests/test_schema/` passes (records, serialization, validation, actions, parquet)
- [ ] `pytest tests/test_data/` passes (schema, integration, ingestion)
- [ ] `pytest` full suite passes with zero regressions
- [ ] `ruff check src/bimodal_harness/` reports no new linting errors
- [ ] `mypy src/bimodal_harness/` reports no new type errors
- [ ] Manual verification: construct a dict matching Lean `dataset_generator` output, call `lean_export_to_training_record()`, confirm all fields populated correctly

## Artifacts & Outputs

- `specs/005_coordinate_bimodallogic_formula_and_proof_data_exports/plans/01_export-coordination-plan.md` (this file)
- `src/bimodal_harness/data/ingestion.py` -- canonical ingest adapter
- `src/bimodal_harness/schema/constants.py` -- extended VALID_LABELS and pruned VALID_DIFFICULTY_TIERS
- `src/bimodal_harness/schema/records.py` -- updated ProofTrace.from_dict, DifficultyMetrics.from_dict
- `src/bimodal_harness/data/schema.py` -- deprecated with warnings
- `data/samples/test_formulas.jsonl` -- regenerated in Lean export format
- `tests/test_data/test_ingestion.py` -- new test file
- `.context/data-contract.md` -- cross-repo field mapping reference

## Rollback/Contingency

If schema changes break downstream consumers:
1. Revert `constants.py` changes (VALID_LABELS, VALID_DIFFICULTY_TIERS) to restore original validation behavior
2. Revert `records.py` changes to ProofTrace.from_dict and DifficultyMetrics.from_dict
3. Restore original `data/samples/test_formulas.jsonl` from git history
4. The ingest adapter (`data/ingestion.py`) can be deleted without affecting existing code since it is a new addition
5. `data/schema.py` deprecation warnings can be removed to restore the original module

All changes are confined to BimodalHarness Python code; no Lean-side modifications are made, so BimodalLogic is unaffected by any rollback.
