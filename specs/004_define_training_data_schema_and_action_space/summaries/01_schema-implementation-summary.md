# Implementation Summary: Training Data Schema and Action Space

- **Task**: 4 — Define training data schema and action space
- **Status**: COMPLETED
- **Session**: sess_1780078869_8696d2
- **Date**: 2026-05-29

## Overview

Implemented the Python training data schema and action space for the
BimodalHarness AlphaZero proof search system.  All 4 phases completed;
145 tests pass.

## What Was Built

### Action Space (`src/bimodal_harness/schema/actions.py`)

- `AXIOM_ACTIONS`: 42 canonical axiom constructor names matching Lean
  `Bimodal.ProofSystem.Axioms.Axiom` exactly, organized in 8 layers
- `RULE_ACTIONS`: 7 inference rule names matching
  `Bimodal.ProofSystem.Derivation.DerivationTree` constructors
- `ALL_ACTIONS`: 49 total (policy network output dimension)
- `ACTION_TO_INDEX` / `INDEX_TO_ACTION`: bijective mappings (indices 0-48)
- Frame-class boolean masks: `BASE_MASK` (44 True), `DENSE_MASK` (46 True),
  `DISCRETE_MASK` (47 True)
- `FrameClass` StrEnum with values "Base", "Dense", "Discrete"

Axiom layer summary:
| Layer | Count | Constructors |
|-------|-------|--------------|
| 1 Propositional | 4 | prop_k, prop_s, ex_falso, peirce |
| 2 S5 Modal | 5 | modal_t, modal_4, modal_b, modal_5_collapse, modal_k_dist |
| 3 BX Temporal | 22 | serial_future/past + 9 pairs |
| 4 Interaction | 1 | modal_future |
| 5 Uniformity | 5 | discrete_symm_fwd/bwd, discrete_propagate_fwd/bwd, discrete_box_necessity |
| 6 Prior | 2 | prior_UZ, prior_SZ (Discrete only) |
| 7 Z1 | 1 | z1 (Discrete only) |
| 8 Density | 2 | density, dense_indicator (Dense only) |

### Schema Modules (`src/bimodal_harness/schema/`)

| Module | Purpose |
|--------|---------|
| `constants.py` | SCHEMA_VERSION="1.0.0", valid value sets |
| `formula.py` | FormulaJson type alias, AtomRepr, validate_formula_json(), formula_json_to_pretty() |
| `records.py` | PatternKey, RuleProfile, ProofTrace, SimpleCountermodel, DifficultyMetrics, TrainingRecord |
| `validation.py` | validate_training_record() with label-conditional checks |
| `serialization.py` | write_jsonl(), read_jsonl(), record_to_jsonl_dict(), jsonl_dict_to_record() |
| `parquet.py` | records_to_parquet(), parquet_to_records(), PARQUET_SCHEMA (21 columns), read_parquet_metadata() |
| `__init__.py` | Public API re-exports |

### Test Suite (`tests/test_schema/`)

| File | Tests | Coverage |
|------|-------|----------|
| `test_actions.py` | 37 | Action counts, bijectivity, masks, Lean name matching |
| `test_records.py` | 40 | Dataclass validation, edge cases, serialization |
| `test_validation.py` | 28 | Formula validation, record validation, label-conditional |
| `test_serialization.py` | 25 | JSONL round-trips, camelCase/snake_case, edge cases |
| `test_parquet.py` | 15 | Parquet round-trips, nullable columns, metadata, size |

**Total: 145 tests, all passing.**

## Lean Correspondences

| Python | Lean |
|--------|------|
| `TrainingRecord` | Conceptual mirror of LabeledFormula (DataExport.lean) |
| `PatternKey` | `PatternKey` struct (SuccessPatterns.lean) |
| `RuleProfile` | `RuleProfile` struct (DataExport.lean) |
| `SimpleCountermodel` | `SimpleCountermodel` (CountermodelExtraction.lean) |
| Formula JSON tags | `Formula.toJson` output (DataExport.lean) |
| GoalCategory names | `GoalCategory` constructors (SuccessPatterns.lean) |
| Axiom constructor names | `Axiom` constructors (Axioms.lean) |
| FrameClass values | `FrameClass` constructors (Axioms.lean) |

## Plan Deviations

- None (implementation followed plan).

All plan tasks completed as specified.  Phases 2 and 3 were developed concurrently
(both depend on Phase 1), matching the wave-2 parallelism noted in the plan.
