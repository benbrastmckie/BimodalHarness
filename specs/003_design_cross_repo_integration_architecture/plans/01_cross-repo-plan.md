# Implementation Plan: Task #3

- **Task**: 3 - Design cross-repo integration architecture
- **Status**: [NOT STARTED]
- **Effort**: 4 hours
- **Dependencies**: Task 2 (Python project structure) -- recommended but not blocking
- **Research Inputs**: specs/003_design_cross_repo_integration_architecture/reports/01_cross-repo-design.md
- **Artifacts**: plans/01_cross-repo-plan.md (this file)
- **Standards**: plan-format.md, status-markers.md, artifact-management.md, tasks.md
- **Type**: general
- **Lean Intent**: false

## Overview

Define and implement the integration architecture between BimodalLogic (Lean 4), ModelChecker (Python/Z3), and BimodalHarness (Python). The research report recommends artifact-only integration: BimodalLogic exports JSONL data files, BimodalHarness reads them as static training data, and ModelChecker is consumed as a pip dependency. This plan creates the concrete data contract (Python schema module matching the Lean JSON export format), sets up the data directory structure with sync tooling, documents the architecture and version compatibility matrix, and validates the integration with sample data.

### Research Integration

Key findings from the research report (01_cross-repo-design.md):
- BimodalLogic already has complete export infrastructure: `DataExport.lean`, `DatasetGenerator.lean`, `FormulaEnumerator.lean` with JSON serialization for Formula, PatternKey, SimpleCountermodel, RuleProfile, and LabeledFormula types.
- Artifact-only coupling is the recommended architecture. No git submodule, no live Lean dependency for core training pipeline.
- ModelChecker (`model-checker==1.2.12`) provides Z3-based bimodal semantics as a pip package for Tier 2 countermodel generation.
- JSONL is the primary export format (streamable, human-readable, HuggingFace datasets compatible). Parquet is a secondary option for large datasets.
- Lean v4.27.0-rc1 is a BimodalLogic-only concern; BimodalHarness has no Lean toolchain dependency.
- The JSON schema for LabeledFormula records is fully specified in the research report, including formula tags (`atom`, `bot`, `imp`, `box`, `untl`, `snce`), proof traces, countermodels, metrics, and pattern keys.

### Prior Plan Reference

No prior plan.

### Roadmap Alignment

No ROADMAP.md found.

## Goals & Non-Goals

**Goals**:
- Define the Python data contract (dataclasses/Pydantic models) that mirrors the Lean JSON export schema for Formula, LabeledFormula, PatternKey, SimpleCountermodel, and RuleProfile
- Set up the `data/` directory structure with version tracking (`data/VERSION`) and sync tooling (Makefile target)
- Configure `model-checker==1.2.12` as a pip dependency with version pin
- Document the architecture boundary, data flow, and version compatibility matrix
- Validate the integration by round-tripping sample JSONL data through the Python schema

**Non-Goals**:
- Implementing the full PyTorch Dataset wrapper (that is Task 7)
- Building the live Lean bridge (lean-interact/LeanDojo -- that is Task 6)
- Creating the Z3 countermodel generator module (that is Task 19)
- Implementing the BimodalLogic export executable (that is BimodalLogic Task 203)
- Setting up CI/CD pipeline for data sync (premature until data pipeline is proven)

## Risks & Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Task 2 (Python project structure) not yet complete -- no `pyproject.toml` or `src/` layout | H | M | Phase 1 creates standalone schema module; if project structure exists, place in `src/bimodal_harness/data/`; otherwise create at root and move later |
| Lean JSON export schema diverges from Python schema after initial definition | M | M | Pin schema version in `data/VERSION`; include schema validation tests that load real Lean-exported samples |
| ModelChecker API changes break integration | M | L | Pin exact version `model-checker==1.2.12`; document the specific classes used (BimodalSemantics, BimodalStructure, BimodalProposition) |
| No real Lean-exported JSONL available yet (BimodalLogic Task 203 incomplete) | M | H | Create synthetic sample JSONL matching the documented schema for validation; mark as test fixture |
| Formula tag set expands in future BimodalLogic versions | L | L | Schema uses explicit enum; new tags raise validation errors, prompting schema update |

## Implementation Phases

**Dependency Analysis**:
| Wave | Phases | Blocked by |
|------|--------|------------|
| 1 | 1, 2 | -- |
| 2 | 3, 4 | 1, 2 |

Phases within the same wave can execute in parallel.

---

### Phase 1: Define Python Data Contract [NOT STARTED]

**Goal**: Create the Python schema module with dataclasses/types that exactly mirror the Lean JSON export format, enabling type-safe loading of JSONL records.

**Tasks**:
- [ ] Create `src/bimodal_harness/data/schema.py` (or `schema.py` at project root if Task 2 not done)
- [ ] Define `FormulaTag` enum: `ATOM`, `BOT`, `IMP`, `BOX`, `UNTL`, `SNCE`
- [ ] Define recursive `FormulaNode` dataclass with `tag`, `name?`, `child?`, `left?`, `right?`, `event?`, `guard?` fields matching the Lean JSON schema
- [ ] Define `Label` enum: `VALID`, `INVALID`, `TIMEOUT`
- [ ] Define `PatternKey` dataclass: `modal_depth`, `temporal_depth`, `imp_count`, `complexity`, `top_operator`
- [ ] Define `SimpleCountermodel` dataclass: `true_atoms`, `false_atoms`, `formula`
- [ ] Define `RuleProfile` dataclass with 7 rule-application count fields
- [ ] Define `ProofTrace` dataclass: `height`, `axioms_used`, `rules_applied`
- [ ] Define `DifficultyMetrics` dataclass: `complexity`, `modal_depth`, `temporal_depth`, `imp_count`, `atom_count`, `decision_time_ms`, `difficulty_tier`
- [ ] Define `LabeledFormula` dataclass: `formula`, `label`, `proof_trace?`, `countermodel?`, `metrics`, `pattern_key`
- [ ] Implement `FormulaNode.from_json(data: dict)` class method for recursive deserialization
- [ ] Implement `LabeledFormula.from_json(data: dict)` class method for full record deserialization
- [ ] Create `tests/test_schema.py` with round-trip serialization/deserialization tests

**Timing**: 1.5 hours

**Depends on**: none

**Files to modify**:
- `src/bimodal_harness/data/__init__.py` - Create package (or root-level if Task 2 not done)
- `src/bimodal_harness/data/schema.py` - Core schema definitions
- `tests/test_schema.py` - Schema validation tests

**Verification**:
- All dataclasses instantiate without error
- `FormulaNode.from_json()` correctly parses the documented JSON examples from the research report
- `LabeledFormula.from_json()` handles both valid (with proof_trace) and invalid (with countermodel) records
- Round-trip: `from_json(to_json(x)) == x` for all types

---

### Phase 2: Configure Integration Infrastructure [NOT STARTED]

**Goal**: Set up the data directory structure, data sync tooling, ModelChecker dependency pin, and version tracking for reproducible integration.

**Tasks**:
- [ ] Create `data/` directory with `.gitkeep` and `data/README.md` explaining the directory purpose and data flow
- [ ] Create `data/VERSION` file documenting schema version and source BimodalLogic commit convention
- [ ] Create `data/samples/` directory for test fixtures
- [ ] Create synthetic sample JSONL file `data/samples/test_formulas.jsonl` with 5-10 records covering all formula tags, valid/invalid/timeout labels, proof traces, and countermodels
- [ ] Add `Makefile` (or `justfile`) with `sync-data` target: `rsync -av /home/benjamin/Projects/BimodalLogic/data/ ./data/bimodal/`
- [ ] Add `validate-data` target that runs schema validation against `data/` JSONL files
- [ ] Add `model-checker==1.2.12` to project dependencies (in `pyproject.toml` if available, otherwise document in `requirements.txt`)
- [ ] Add `data/*.jsonl` and `data/bimodal/` to `.gitignore` (keep `data/samples/` tracked)

**Timing**: 1 hour

**Depends on**: none

**Files to modify**:
- `data/.gitkeep` - Create directory marker
- `data/README.md` - Data directory documentation
- `data/VERSION` - Schema version tracking
- `data/samples/test_formulas.jsonl` - Synthetic test fixtures
- `Makefile` - Data sync and validation targets
- `.gitignore` - Exclude large data files, keep samples
- `pyproject.toml` or `requirements.txt` - ModelChecker dependency pin

**Verification**:
- `make sync-data` runs without error (even if BimodalLogic data/ is empty)
- `make validate-data` runs schema checks against sample JSONL
- `data/samples/test_formulas.jsonl` is valid JSONL parseable by Python `json` module
- `.gitignore` excludes `data/*.jsonl` but not `data/samples/`

---

### Phase 3: Document Architecture and Version Compatibility [NOT STARTED]

**Goal**: Create a comprehensive architecture document that defines the integration boundary, data flow, version compatibility matrix, and integration points for downstream tasks.

**Tasks**:
- [ ] Create `docs/architecture/cross-repo-integration.md` (or `specs/003_design_cross_repo_integration_architecture/ARCHITECTURE.md`)
- [ ] Document the three-repo architecture diagram (BimodalLogic -> JSONL -> BimodalHarness, ModelChecker -> pip -> BimodalHarness)
- [ ] Document the data boundary: what BimodalLogic owns vs. what BimodalHarness owns (from research report Boundary Summary)
- [ ] Document the JSONL schema contract with examples for each record type
- [ ] Document version compatibility matrix: Lean v4.27.0-rc1, ModelChecker 1.2.12, Python >= 3.8, z3-solver >= 4.8.0
- [ ] Document integration points by downstream task (Tasks 4, 5, 7, 8, 9, 10, 19) with coupling type
- [ ] Document the data sync workflow: development (rsync/Makefile) and production (GitHub Releases / git LFS)
- [ ] Document the formula operator reference (JSON tag to Lean constructor to symbol mapping)

**Timing**: 1 hour

**Depends on**: 1, 2

**Files to modify**:
- `docs/architecture/cross-repo-integration.md` - Architecture documentation

**Verification**:
- Document includes all six formula tags with examples
- Version compatibility matrix matches research report
- Integration points table covers Tasks 4, 5, 7, 8, 9, 10, 19
- Data flow diagram is clear and matches implemented directory structure

---

### Phase 4: Validate Integration End-to-End [NOT STARTED]

**Goal**: Verify the complete integration path works by loading sample JSONL through the Python schema, confirming ModelChecker imports, and running all tests.

**Tasks**:
- [ ] Create `tests/test_integration.py` with end-to-end JSONL loading test: read `data/samples/test_formulas.jsonl`, parse each line through `LabeledFormula.from_json()`, verify all fields populated
- [ ] Add test that imports `model_checker.theory_lib.bimodal` and verifies `BimodalSemantics` class is accessible (skip if package not installed)
- [ ] Add test that validates `data/VERSION` file format
- [ ] Run full test suite (`pytest tests/`) and verify all pass
- [ ] Run `make validate-data` and verify output
- [ ] Verify `.gitignore` correctly excludes data files: `git status` should not show `data/*.jsonl` as untracked (only `data/samples/` tracked)

**Timing**: 0.5 hours

**Depends on**: 1, 2

**Files to modify**:
- `tests/test_integration.py` - End-to-end integration tests

**Verification**:
- `pytest tests/` passes with zero failures
- `make validate-data` succeeds on sample data
- `git status` does not show large data files as untracked
- ModelChecker import test passes (or is cleanly skipped if package not installed)

## Testing & Validation

- [ ] All schema dataclasses instantiate and serialize/deserialize correctly
- [ ] `FormulaNode.from_json()` handles all 6 formula tags (atom, bot, imp, box, untl, snce)
- [ ] `LabeledFormula.from_json()` handles valid, invalid, and timeout records
- [ ] Sample JSONL in `data/samples/` matches the documented schema exactly
- [ ] `make sync-data` executes without error
- [ ] `make validate-data` passes on sample data
- [ ] ModelChecker `model-checker==1.2.12` is listed in project dependencies
- [ ] Architecture document covers all integration points and version constraints
- [ ] `pytest tests/` passes with zero failures

## Artifacts & Outputs

- `src/bimodal_harness/data/schema.py` - Python data contract (FormulaNode, LabeledFormula, PatternKey, etc.)
- `data/samples/test_formulas.jsonl` - Synthetic sample data for testing
- `data/VERSION` - Schema version and source tracking
- `data/README.md` - Data directory documentation
- `Makefile` - Data sync and validation targets
- `docs/architecture/cross-repo-integration.md` - Architecture documentation
- `tests/test_schema.py` - Schema unit tests
- `tests/test_integration.py` - End-to-end integration tests

## Rollback/Contingency

All changes are additive (new files only). Rollback is straightforward:
- Delete created files and directories (`data/`, `docs/architecture/`, schema module, tests)
- Remove ModelChecker dependency from `pyproject.toml`/`requirements.txt`
- Revert `.gitignore` additions

If Task 2 (Python project structure) is not yet complete when implementation begins:
- Create schema module at project root (`schema.py`) instead of `src/bimodal_harness/data/`
- Move to correct location when Task 2 completes
- All imports use relative paths to minimize refactoring
