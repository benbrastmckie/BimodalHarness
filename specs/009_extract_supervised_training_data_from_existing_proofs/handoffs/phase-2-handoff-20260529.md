# Phase 2 Handoff: Python ProofStepRecord Schema and Action Mapping

**Date**: 2026-05-29
**Phase**: 2 of 5
**Status**: COMPLETED
**Session**: sess_1780086457_029818

## What Was Done

Implemented the Python-side schema types and action mapping function for proof step data:

1. **`step_to_action_index`** added to `src/bimodal_harness/schema/actions.py`:
   - Maps `(rule="axiom", axiom_name=<name>)` -> index in 0-41 (AXIOM_ACTIONS space)
   - Maps `(rule=<non_axiom_rule>, axiom_name=None)` -> index in 42-48 (RULE_ACTIONS space)
   - Raises `ValueError` for invalid (rule, axiom_name) combinations
   - Raises `KeyError` for unknown action names

2. **`ProofStepRecord`** frozen dataclass added to `src/bimodal_harness/schema/records.py`:
   - 12 fields: step_id, theorem_name, context, goal_json, goal_pretty, rule, axiom_name, action_index, subgoals, depth, frame_class, proof_height
   - `__post_init__` validates action_index in [0,48], frame_class against VALID_FRAME_CLASSES, non-negative depth and proof_height
   - `to_dict()` converts tuples to lists for JSON compatibility
   - `from_dict()` coerces lists back to tuples for immutability
   - Follows existing `frozen=True, slots=True` pattern

3. **Tests** in `tests/test_schema/test_proof_step_record.py`:
   - 44 tests, all passing
   - Tests step_to_action_index for all 42 axioms and all 7 rules
   - Tests construction, validation, and round-trip serialization

## Files Modified

- `src/bimodal_harness/schema/actions.py` - Added `step_to_action_index` function
- `src/bimodal_harness/schema/records.py` - Added `ProofStepRecord` dataclass
- `tests/test_schema/test_proof_step_record.py` - New test file (44 tests)

## Plan Deviations

None. All checklist items completed as specified.

## Handoff Notes for Phase 4

Phase 4 (Python Ingestion Pipeline) depends on Phase 2 (this) and Phase 3 (Lean proof_extractor). Since Phase 3 requires a Lean build environment, Phase 4 will use a JSONL fixture for testing instead of actual Lean output. The `load_proof_steps` function signature and validation logic are ready to implement.
