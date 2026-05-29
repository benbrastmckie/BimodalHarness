# Implementation Summary: Extract Supervised Training Data from Existing Proofs (Partial)

- **Task**: 9 - Extract supervised training data from existing proofs
- **Status**: [PARTIAL] - Phases 2 and 4 complete; Phases 1, 3, 5 deferred (Lean build environment required)
- **Session**: sess_1780086457_029818
- **Date**: 2026-05-29
- **Phases Completed**: 2 of 5 (Python-only phases)

## What Was Implemented

### Phase 2: Python ProofStepRecord Schema and Action Mapping

Added two new items to the schema package:

**`step_to_action_index(rule, axiom_name)` in `src/bimodal_harness/schema/actions.py`**:
- Maps `(rule="axiom", axiom_name=<name>)` to the axiom's index in 0-41
- Maps `(rule=<non_axiom_rule>, axiom_name=None)` to the rule's index in 42-48
- Validates that `axiom_name is None` iff `rule != "axiom"`, raising `ValueError` otherwise
- Raises `KeyError` for unknown action names

Key correctness: `step_to_action_index("axiom", "prop_k") == 0` and `step_to_action_index("modus_ponens", None) == 44`.

**`ProofStepRecord` dataclass in `src/bimodal_harness/schema/records.py`**:
- Frozen, slotted dataclass following the existing `frozen=True, slots=True` pattern
- 12 fields: step_id, theorem_name, context (tuple[str,...]), goal_json (dict), goal_pretty (str), rule (str), axiom_name (str|None), action_index (int), subgoals (tuple[dict,...]), depth (int), frame_class (str), proof_height (int)
- `__post_init__` validates: action_index in [0,48], frame_class in VALID_FRAME_CLASSES, non-negative depth and proof_height
- `to_dict()`: converts tuples to lists for JSON serialization
- `from_dict()`: coerces lists back to tuples; handles missing optional fields with defaults
- 44 tests, all passing

### Phase 4: Python Ingestion Pipeline for Proof Steps

Extended `src/bimodal_harness/data/ingestion.py` with:

**`load_proof_steps(path, *, validate_action_index=True) -> list[ProofStepRecord]`**:
- Reads JSONL line by line, deserializes each via `ProofStepRecord.from_dict`
- Skips blank lines and comment lines (`#`-prefixed)
- By default, cross-checks `record.action_index` against `step_to_action_index(record.rule, record.axiom_name)` and raises `ValueError` on mismatch

**`get_frame_class_mask(record) -> list[bool]`**:
- Returns the 49-element boolean mask from `FRAME_CLASS_MASKS` for `record.frame_class`
- Enables per-step masking of invalid actions during policy network training

**`proof_step_statistics(records) -> dict`** and **`print_proof_step_statistics(records)`**:
- Computes total steps, distinct theorem count, depth min/max/mean, rule/axiom distributions, action index coverage
- Handles empty lists gracefully
- 43 tests, all passing

**`scripts/extract_and_ingest.py`** CLI:
- `--input` mode: ingest existing JSONL
- `--extract` mode: run `lake exe proof_extractor` then ingest (requires Lean build)
- `--stats`, `--dry-run`, `--no-validate` flags

## Test Results

- Phase 2: 44/44 tests passing (`tests/test_schema/test_proof_step_record.py`)
- Phase 4: 43/43 tests passing (`tests/test_data/test_proof_step_ingestion.py`)
- Total new tests: 87

## Files Created or Modified

| File | Action |
|------|--------|
| `src/bimodal_harness/schema/actions.py` | Added `step_to_action_index` |
| `src/bimodal_harness/schema/records.py` | Added `ProofStepRecord` dataclass |
| `src/bimodal_harness/data/ingestion.py` | Added `load_proof_steps`, `get_frame_class_mask`, `proof_step_statistics`, `print_proof_step_statistics` |
| `scripts/extract_and_ingest.py` | New CLI script |
| `tests/test_schema/test_proof_step_record.py` | New test file (44 tests) |
| `tests/test_data/test_proof_step_ingestion.py` | New test file (43 tests) |
| `tests/fixtures/proof_steps_fixture.jsonl` | New test fixture (10 synthetic steps) |

## Plan Deviations

- **`frame_class_mask` as function vs field**: The plan described attaching `frame_class_mask` to each step record. Implemented as `get_frame_class_mask(record)` function instead, since the mask is always derivable from `frame_class` at zero cost and adding it as a field would introduce redundancy in the serialized format and require it in `from_dict`.
- **Phases 1, 3, 5 deferred**: Lean-side phases (ProofStep structure, proof_extractor executable, augmentation) require the BimodalLogic Lean build environment. The Python pipeline is fully implemented and tested using a synthetic JSONL fixture.

## Next Steps (Deferred)

- **Phase 1**: Implement `ProofStep` structure and `extractStepSequence` in `BimodalLogic/Theories/Bimodal/Automation/DataExport.lean`
- **Phase 3**: Create `lake exe proof_extractor` executable in `BimodalLogic/`
- **Phase 5**: Data augmentation module (`src/bimodal_harness/data/augmentation.py`) and `scripts/assemble_supervised_dataset.py` CLI
