# Implementation Summary: Extract Supervised Training Data from Existing Proofs (Partial)

- **Task**: 9 - Extract supervised training data from existing proofs
- **Status**: [PARTIAL] - Phases 2, 4, and 5 complete; Phases 1 and 3 deferred (Lean build environment required)
- **Session**: sess_1780087581_50964e
- **Date**: 2026-05-29
- **Phases Completed**: 3 of 5 (all Python-actionable phases)

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
- Phase 5: 85/85 tests passing (`tests/test_data/test_augmentation.py`)
- Total new tests: 172

## Phase 5: Data Augmentation and Final Dataset Assembly

### `src/bimodal_harness/data/augmentation.py`

**`temporal_dual_augmentation(records) -> list[tuple[ProofStepRecord, str]]`**:
- Generates temporal dual steps for records whose goal_json contains `untl` or `snce` nodes
- Swaps `untl` <-> `snce` recursively throughout goal_json and subgoals via `_swap_temporal()`
- Swaps axiom names using `_TEMPORAL_AXIOM_DUALS` (26-entry map of BX temporal axiom future/past pairs)
- Handles both `"child"` (canonical DataExport format) and `"arg"` (legacy fixture format) field names for box nodes
- Recomputes `action_index` for the swapped axiom; falls back to original if dual not in action space
- Each dual gets step_id `"<orig_step_id>__dual"` and source `"temporal_dual:<orig_step_id>"`

**`context_variation_augmentation(records, max_context_additions=3) -> list[tuple[ProofStepRecord, str]]`**:
- Generates context variants for steps with empty context (empty `[]` sequent)
- For each source step, creates k variants (k=1..max_context_additions), each with k formulas from `_CONTEXT_STRINGS` bank added to context
- Each variant uses `rule="weakening"`, `axiom_name=None`, `action_index=48`, `subgoals=(original_goal,)`
- Step IDs: `"<orig_step_id>__ctx{k}"`; sources: `"context_variation:<orig_step_id>:{k}ctx"`

**`augment_all(records, max_context_additions=3, include_originals=True)`**:
- Combines originals + temporal duals + context variations in a single list
- Provenance strings: `"original"`, `"temporal_dual:<id>"`, `"context_variation:<id>:Nctx"`

**`augmented_statistics(augmented_records) -> dict`**:
- Returns: total_steps, unique_step_ids, duplicate_step_ids, action_index_coverage, augmentation_source_counts, proof_height_distribution, rule_distribution

**`split_dataset(records, train_frac=0.8, val_frac=0.1, seed=42, stratify_by_height=True)`**:
- Stratified train/val/test split using proof_height strata
- Within each stratum, records are shuffled using seed for reproducibility
- Returns (train, val, test) lists of (ProofStepRecord, source) tuples

### `scripts/assemble_supervised_dataset.py`

CLI with `--input JSONL` (required) and `--output-dir` (default: data/supervised/). Writes combined.jsonl and train/val/test.jsonl splits with `augmentation_source` field appended to each JSONL line. Supports `--dry-run` mode for stats-only inspection.

## Files Created or Modified

| File | Action |
|------|--------|
| `src/bimodal_harness/schema/actions.py` | Added `step_to_action_index` (Phase 2) |
| `src/bimodal_harness/schema/records.py` | Added `ProofStepRecord` dataclass (Phase 2) |
| `src/bimodal_harness/data/ingestion.py` | Added `load_proof_steps`, `get_frame_class_mask`, `proof_step_statistics`, `print_proof_step_statistics` (Phase 4) |
| `src/bimodal_harness/data/augmentation.py` | New file: augmentation strategies (Phase 5) |
| `scripts/extract_and_ingest.py` | New CLI script (Phase 4) |
| `scripts/assemble_supervised_dataset.py` | New CLI script (Phase 5) |
| `tests/test_schema/test_proof_step_record.py` | New test file: 44 tests (Phase 2) |
| `tests/test_data/test_proof_step_ingestion.py` | New test file: 43 tests (Phase 4) |
| `tests/test_data/test_augmentation.py` | New test file: 85 tests (Phase 5) |
| `tests/fixtures/proof_steps_fixture.jsonl` | New test fixture: 10 synthetic steps (Phase 4) |

## Plan Deviations

- **`frame_class_mask` as function vs field**: The plan described attaching `frame_class_mask` to each step record. Implemented as `get_frame_class_mask(record)` function instead, since the mask is always derivable from `frame_class` at zero cost.
- **`augmentation_source` as parallel string vs dataclass field**: Since `ProofStepRecord` is frozen, `augmentation_source` is tracked as a parallel string in `list[tuple[ProofStepRecord, str]]` and written to JSONL by the CLI. The existing dataclass schema is not extended.
- **Box node field name handling**: The fixture uses `"arg"` key for box nodes while the canonical DataExport schema specifies `"child"`. The augmentation module handles both transparently.
- **Higher-complexity dataset_generator item deferred**: The `lake exe dataset_generator` batch generation step depends on Lean phases 1 and 3 being complete.
- **Phases 1 and 3 deferred**: Lean-side phases require BimodalLogic Lean build environment.

## Next Steps (Deferred)

- **Phase 1**: Implement `ProofStep` structure and `extractStepSequence` in `BimodalLogic/Theories/Bimodal/Automation/DataExport.lean`
- **Phase 3**: Create `lake exe proof_extractor` executable in `BimodalLogic/`
- After Phases 1 and 3: Run `python scripts/assemble_supervised_dataset.py --input data/proof-steps.jsonl --output-dir data/supervised/` to produce the final augmented dataset
