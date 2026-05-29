# Implementation Plan: Define Training Data Schema and Action Space

- **Task**: 4 - Define training data schema and action space
- **Status**: [IMPLEMENTING]
- **Effort**: 4 hours
- **Dependencies**: None (Layer 0 foundation task)
- **Research Inputs**: specs/004_define_training_data_schema_and_action_space/reports/01_data-schema-research.md
- **Artifacts**: plans/01_data-schema-plan.md (this file)
- **Standards**: plan-format.md, status-markers.md, artifact-management.md, tasks.md
- **Type**: python
- **Lean Intent**: false

## Overview

Implement the Python training data schema and action space for the BimodalHarness AlphaZero proof search system. The research report confirmed 42 axiom constructors + 7 inference rules = 49 total actions, and identified that BimodalLogic already exports `LabeledFormula` records with complete JSON serialization via `DataExport.lean`. This plan mirrors those Lean types as Python dataclasses with Pydantic validation, defines the canonical action space arrays, and provides JSONL/Parquet serialization utilities. The schema gates downstream Tasks 5, 7, 8, and 10.

### Research Integration

Key findings from `reports/01_data-schema-research.md` integrated into this plan:

- **D1 (Canonical Schema)**: `TrainingRecord` dataclass mirrors Lean `LabeledFormula` exactly. Formula uses tagged JSON tree with `"tag"` discriminant matching `DataExport.lean` format.
- **D2 (Action Space)**: 42 axiom constructors organized in 8 layers + 7 inference rules = 49 total actions. Frame-class-restricted subsets (Base=37, Dense=39, Discrete=40) with boolean masks.
- **D3 (JSON vs Parquet)**: JSONL for primary storage (Lean-compatible), Parquet for training batches (columnar, fast PyTorch loading).
- **D4 (Versioning)**: `schema_version` semver field and `frame_class` field on every record.
- **D5 (NN Representations)**: Three formula representations (feature vector, token sequence, tree structure) planned for future phases.
- **R1-R7**: Mirror Lean types directly, use constructor names as action IDs, include `frame_class` field, reserve `countermodel_rich` for Z3 extension, use compound Atom representation.

### Prior Plan Reference

No prior plan.

### Roadmap Alignment

No ROADMAP.md found.

## Goals & Non-Goals

**Goals**:
- Define Python dataclasses/Pydantic models for the complete training record schema matching Lean `LabeledFormula`
- Enumerate the 42-axiom + 7-rule action space with canonical ordering, frame-class masks, and index mappings
- Implement JSONL serialization/deserialization matching `DataExport.lean` output format
- Implement Parquet serialization for efficient ML training batch loading
- Include schema version metadata and extensibility hooks for future Logos operators
- Provide validation functions ensuring schema conformance (label-conditional fields, value ranges)

**Non-Goals**:
- Neural network architecture or tensor encoding (Tasks 11, 14, 20)
- Actual data generation or ingestion pipeline (Tasks 7, 8)
- Python-Lean bridge integration (Task 6)
- Z3 countermodel generation (Task 19)
- PatternKey feature extraction from formula ASTs (Task 10)

## Risks & Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Schema drift between Lean export and Python ingestion | H | M | Pin `schema_version` in both; add round-trip conformance tests against sample Lean JSONL output |
| GoalCategory enum extension for future Logos operators | M | Certain | Use string values (not integer enums) for `top_operator`; validate against known set but allow unknown |
| AllPast/AllFuture GoalCategory ambiguity at primitive level | L | M | Document the subtlety; implement pattern detection on derived forms in Task 10 |
| Parquet nested-type limitations for formula_json | M | L | Store formula_json as JSON string column in Parquet; parse on read |
| Action space dimension change when axioms added | H | M | Version-tag action arrays; provide `action_space_version` alongside `schema_version` |
| Python project structure not yet initialized (Task 2) | M | H | Use standalone module paths; structure for easy integration when pyproject.toml exists |

## Implementation Phases

**Dependency Analysis**:
| Wave | Phases | Blocked by |
|------|--------|------------|
| 1 | 1 | -- |
| 2 | 2, 3 | 1 |
| 3 | 4 | 2, 3 |

Phases within the same wave can execute in parallel.

### Phase 1: Core Schema Definitions [COMPLETED]

**Goal**: Define the Python dataclass/Pydantic models for Formula, TrainingRecord, PatternKey, SimpleCountermodel, ProofTrace, DifficultyMetrics, and the action space constants.

**Tasks**:
- [ ] Create `src/bimodal_harness/schema/` package with `__init__.py`
- [ ] Implement `src/bimodal_harness/schema/formula.py`: Formula JSON type aliases, Atom dataclass (base + fresh_index), formula validation functions (valid tag values, required fields per tag)
- [ ] Implement `src/bimodal_harness/schema/actions.py`: `AXIOM_ACTIONS` list (42 items, layered ordering from research D2), `RULE_ACTIONS` list (7 items), `ALL_ACTIONS` combined list (49 items), `ACTION_TO_INDEX` / `INDEX_TO_ACTION` mappings, frame-class masks (`BASE_MASK`, `DENSE_MASK`, `DISCRETE_MASK`), `FrameClass` string enum
- [ ] Implement `src/bimodal_harness/schema/records.py`: `PatternKey` dataclass (5 fields), `ProofTrace` dataclass (height, axioms_used, rules_applied), `RuleProfile` dataclass (7 count fields), `SimpleCountermodel` dataclass (true_atoms, false_atoms, formula), `DifficultyMetrics` dataclass (7 fields including difficulty_tier), `TrainingRecord` dataclass (all fields from research D1 including record_id, label, schema_version, frame_class, source, logic_system)
- [ ] Implement `src/bimodal_harness/schema/constants.py`: `SCHEMA_VERSION = "1.0.0"`, `VALID_LABELS`, `VALID_DIFFICULTY_TIERS`, `VALID_TOP_OPERATORS` (8 GoalCategory values), `VALID_FRAME_CLASSES`, `VALID_FORMULA_TAGS` (6 tags), `VALID_SOURCES`

**Timing**: 1.5 hours

**Depends on**: none

**Files to modify**:
- `src/bimodal_harness/schema/__init__.py` - Package init with public API exports
- `src/bimodal_harness/schema/formula.py` - Formula types and validation
- `src/bimodal_harness/schema/actions.py` - Action space enumeration
- `src/bimodal_harness/schema/records.py` - Training record dataclasses
- `src/bimodal_harness/schema/constants.py` - Schema constants and version

**Verification**:
- All modules import without error
- `len(AXIOM_ACTIONS) == 42` and `len(ALL_ACTIONS) == 49`
- `TrainingRecord` can be instantiated with all required fields
- Action index mappings are bijective (no duplicates, no gaps)

---

### Phase 2: Validation and Serialization [COMPLETED]

**Goal**: Implement validation functions ensuring schema conformance and JSONL serialization matching Lean DataExport.lean format.

**Tasks**:
- [ ] Implement `src/bimodal_harness/schema/validation.py`: `validate_formula_json(data: dict) -> bool` (checks tag field, required children per tag, recursive validation), `validate_training_record(record: TrainingRecord) -> list[str]` (label-conditional checks: proof_trace present iff label==valid, countermodel present iff label==invalid; value range checks for PatternKey; frame_class validity; action names in proof_axioms_used are all in AXIOM_ACTIONS)
- [ ] Implement `src/bimodal_harness/schema/serialization.py`: `record_to_jsonl_dict(record: TrainingRecord) -> dict` (flatten to JSON-serializable dict matching Lean export format), `jsonl_dict_to_record(data: dict) -> TrainingRecord` (parse from Lean-exported JSONL line), `write_jsonl(records: list[TrainingRecord], path: Path)`, `read_jsonl(path: Path) -> list[TrainingRecord]`
- [ ] Add `from_lean_export(data: dict) -> TrainingRecord` class method that handles field name mapping (camelCase Lean fields to snake_case Python fields)

**Timing**: 1 hour

**Depends on**: 1

**Files to modify**:
- `src/bimodal_harness/schema/validation.py` - Validation functions
- `src/bimodal_harness/schema/serialization.py` - JSONL read/write

**Verification**:
- Validation rejects records with label=="valid" but no proof_trace
- Validation rejects records with unknown formula tags
- Round-trip: `jsonl_dict_to_record(record_to_jsonl_dict(record)) == record`
- Sample JSONL line from research appendix A2 parses correctly

---

### Phase 3: Parquet Serialization [COMPLETED]

**Goal**: Implement Parquet read/write with flattened columnar layout for efficient ML training.

**Tasks**:
- [ ] Implement `src/bimodal_harness/schema/parquet.py`: `records_to_parquet(records: list[TrainingRecord], path: Path)` using PyArrow (flatten formula_json to string column, expand PatternKey to individual int columns, handle nullable fields for proof_trace and countermodel), `parquet_to_records(path: Path) -> list[TrainingRecord]`, define PyArrow schema constant matching research R7 column layout
- [ ] Implement column-type mapping: `formula_json` -> string (JSON-encoded), `formula_pretty` -> string, `modal_depth/temporal_depth/imp_count/complexity/atom_count` -> int64, `top_operator/label/difficulty_tier/frame_class` -> dictionary(string), `proof_height` -> int64 (nullable), `proof_axioms_used/countermodel_true_atoms/countermodel_false_atoms` -> list<string> (nullable), `decision_time_ms` -> int64, `schema_version/source/logic_system` -> string
- [ ] Add metadata to Parquet file footer: schema_version, creation_date, record_count, frame_class_distribution

**Timing**: 1 hour

**Depends on**: 1

**Files to modify**:
- `src/bimodal_harness/schema/parquet.py` - Parquet serialization with PyArrow

**Verification**:
- Round-trip: write records to Parquet, read back, compare equality
- Parquet file metadata contains schema_version
- Nullable columns handle None values for proof_trace fields when label != "valid"
- File size is smaller than equivalent JSONL for 100+ records

---

### Phase 4: Tests and Documentation [COMPLETED]

**Goal**: Comprehensive test suite validating all schema components and a docstring-level API reference.

**Tasks**:
- [ ] Create `tests/test_schema/test_actions.py`: test action counts (42 axioms, 7 rules, 49 total), test index mapping bijectivity, test frame-class masks (BASE_MASK has exactly 37+7=44 True values, DENSE_MASK has 39+7=46, DISCRETE_MASK has 40+7=47), test action names match Lean constructor names
- [ ] Create `tests/test_schema/test_records.py`: test TrainingRecord instantiation with valid data, test optional field handling (None for proof_trace when invalid), test PatternKey value ranges
- [ ] Create `tests/test_schema/test_validation.py`: test formula validation (valid tags, missing fields, unknown tags), test record validation (label-conditional checks, out-of-range values), test edge cases (empty atom lists, zero complexity rejected since complexity >= 1)
- [ ] Create `tests/test_schema/test_serialization.py`: test JSONL round-trip, test Lean export format parsing (camelCase to snake_case), test sample JSONL from research appendix A2
- [ ] Create `tests/test_schema/test_parquet.py`: test Parquet round-trip, test nullable column handling, test metadata in file footer
- [ ] Add module-level docstrings to all schema modules explaining purpose, Lean type correspondence, and usage examples

**Timing**: 1 hour

**Depends on**: 2, 3

**Files to modify**:
- `tests/test_schema/__init__.py` - Test package init
- `tests/test_schema/test_actions.py` - Action space tests
- `tests/test_schema/test_records.py` - Record dataclass tests
- `tests/test_schema/test_validation.py` - Validation tests
- `tests/test_schema/test_serialization.py` - JSONL serialization tests
- `tests/test_schema/test_parquet.py` - Parquet serialization tests

**Verification**:
- All tests pass with `pytest tests/test_schema/`
- No test failures on edge cases (empty lists, None optionals, boundary values)
- Coverage of schema package exceeds 90%

## Testing & Validation

- [ ] `len(AXIOM_ACTIONS) == 42` and axiom names match Lean `Axiom` constructor names exactly
- [ ] `len(ALL_ACTIONS) == 49` with no duplicate entries
- [ ] Frame-class masks correctly restrict action space (Base=44, Dense=46, Discrete=47 total with rules)
- [ ] TrainingRecord round-trips through JSONL without data loss
- [ ] TrainingRecord round-trips through Parquet without data loss
- [ ] Validation rejects structurally invalid records (wrong label-conditional fields, unknown tags)
- [ ] Sample JSONL line from research appendix A2 parses into valid TrainingRecord
- [ ] Schema version field is consistently "1.0.0" across all serialization formats
- [ ] `pytest tests/test_schema/ -v` passes with zero failures

## Artifacts & Outputs

- `src/bimodal_harness/schema/__init__.py` - Public API for schema package
- `src/bimodal_harness/schema/formula.py` - Formula types matching DataExport.lean
- `src/bimodal_harness/schema/actions.py` - 49-action space with frame-class masks
- `src/bimodal_harness/schema/records.py` - TrainingRecord and component dataclasses
- `src/bimodal_harness/schema/constants.py` - Schema version and validation constants
- `src/bimodal_harness/schema/validation.py` - Record and formula validation
- `src/bimodal_harness/schema/serialization.py` - JSONL read/write
- `src/bimodal_harness/schema/parquet.py` - Parquet read/write with PyArrow
- `tests/test_schema/` - Comprehensive test suite (5 test modules)

## Rollback/Contingency

All changes are new file additions in `src/bimodal_harness/schema/` and `tests/test_schema/`. Rollback is straightforward: delete these directories. No existing files are modified. If PyArrow is unavailable (Task 2 not yet completed), Phase 3 can be deferred -- Phases 1 and 2 (core schema + JSONL) are independently useful and unblock downstream Tasks 7, 8, and 10.
