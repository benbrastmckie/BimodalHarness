# Phase 5 Handoff: Data Augmentation and Final Dataset Assembly

**Task**: 9 — Extract supervised training data from existing proofs
**Phase**: 5 — Data Augmentation and Final Dataset Assembly
**Status**: COMPLETED
**Date**: 2026-05-29
**Session**: sess_1780087581_50964e

## What Was Done

Implemented `src/bimodal_harness/data/augmentation.py` with:

- `temporal_dual_augmentation(records)`: Swaps `untl` <-> `snce` tags in goal formulas and subgoals; swaps axiom names using `_TEMPORAL_AXIOM_DUALS` map (26 BX temporal axiom pairs). Handles both `"child"` and `"arg"` field names for box nodes (fixture uses `"arg"`, canonical schema uses `"child"`). Recomputes `action_index` for the dual axiom.

- `context_variation_augmentation(records, max_context_additions=3)`: For steps with empty context, generates k variants (k=1..max_context_additions) with k propositional formulas added from `_CONTEXT_STRINGS` bank. Each variant uses the `weakening` rule (action_index=48) and subgoal set to the original goal formula.

- `augment_all(records, ...)`: Combines originals + temporal duals + context variations into a single list with provenance strings.

- `augmented_statistics(augmented_records)`: Returns total_steps, unique_step_ids, duplicate_step_ids, action_index_coverage, augmentation_source_counts, proof_height_distribution, rule_distribution.

- `split_dataset(records, train_frac=0.8, val_frac=0.1, seed=42, stratify_by_height=True)`: Stratified 80/10/10 train/val/test split by proof height with reproducible shuffling.

Created `scripts/assemble_supervised_dataset.py` CLI with:
- `--input JSONL_PATH` (required), `--output-dir DIR` (default: data/supervised/)
- `--max-context-additions N`, `--no-temporal-dual`, `--no-context-variation`
- `--no-split`, `--train-frac F`, `--val-frac F`, `--seed N`
- `--dry-run` to compute stats without writing files

Created `tests/test_data/test_augmentation.py` with 85 tests covering all functions.

## Deviations from Plan

- `Run lake exe dataset_generator` item skipped — this depends on Lean phases 1 and 3 which are NOT STARTED.
- `augmentation_source` is tracked as a parallel list of strings paired with records (not a new field on the frozen `ProofStepRecord` dataclass). Added to output JSONL by the CLI script.
- Box node uses both `"child"` and `"arg"` key variants (found in fixture), handled transparently.

## Test Results

All 1017 tests pass (85 new augmentation tests + 932 pre-existing).

## State After Phase

| Phase | Status |
|-------|--------|
| 1 (Lean ProofStep) | NOT STARTED |
| 2 (Python Schema) | COMPLETED |
| 3 (Lean proof_extractor) | NOT STARTED |
| 4 (Python Ingestion) | COMPLETED |
| 5 (Augmentation) | COMPLETED |

Blocking dependency: Phases 1 and 3 require Lean 4 implementation — not actionable by Python agent.
