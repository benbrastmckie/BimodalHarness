# Implementation Plan: Extract Supervised Training Data from Existing Proofs

- **Task**: 9 - Extract supervised training data from existing proofs
- **Status**: [NOT STARTED]
- **Effort**: 10 hours
- **Dependencies**: None (builds on existing infrastructure in BimodalLogic and BimodalHarness)
- **Research Inputs**: specs/009_extract_supervised_training_data_from_existing_proofs/reports/01_proof-extraction.md
- **Artifacts**: plans/01_proof-extraction-plan.md (this file)
- **Standards**: plan-format.md, status-markers.md, artifact-management.md, tasks.md
- **Type**: python
- **Lean Intent**: true

## Overview

Extract step-level supervised training data from the BimodalLogic proof corpus for policy network pretraining. The research report establishes that only ~108 theorem definitions in `Theories/Bimodal/Theorems/` produce actionable `DerivationTree` values (not the ~2,519 metalogic theorems originally estimated). The existing `ProofTrace` captures only summary statistics (height, axioms_used, rules_applied), not the sequential `(goal_state, action, result_state)` triples needed for imitation learning. This plan implements Option B from the research: a new `extractStepSequence` Lean function compiled into a `lake exe proof_extractor` executable, paired with Python-side schema extensions, ingestion, and augmentation to reach 10-20K step triples.

### Research Integration

Key findings from report `01_proof-extraction.md`:
- All 888 valid records in `bmlogic-deep.jsonl` have `height=0` (trivial single-axiom proofs)
- Only ~108 `DerivationTree` definitions in `Theorems/` are extractable; ~2,400 metalogic theorems use Lean tactics
- The existing `walkDerivationTree` and `extractProofTrace` patterns provide the structural template for step extraction
- `Formula.toJson` and `Formula.prettyPrint` already exist for serialization
- The 49-action space mapping (`ACTION_TO_INDEX` in `schema/actions.py`) is well-defined
- Target: 10-20K step triples via extraction + augmentation (temporal duals, context variation, higher-complexity generation)

### Prior Plan Reference

No prior plan.

### Roadmap Alignment

No ROADMAP.md found.

## Goals & Non-Goals

**Goals**:
- Implement `ProofStep` structure and `extractStepSequence` function in Lean
- Create `lake exe proof_extractor` executable that walks all 108 theorem DerivationTrees
- Extend Python `ProofStepRecord` schema to capture step-level data with 49-action index
- Build Python ingestion pipeline for proof step JSONL
- Produce initial supervised dataset of ~500-1,600 raw step triples from Theorems/
- Implement augmentation strategies to reach 10-20K step triples

**Non-Goals**:
- Modifying the decision procedure search logic (Option C from research)
- Installing or integrating LeanDojo (Option D)
- Training the policy network (separate downstream task)
- Extracting steps from metalogic theorems (these use Lean tactics, not DerivationTree constructors)
- Installing lean-interact (not needed for batch extraction)

## Risks & Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| `extractStepSequence` complex to implement due to dependent types | H | M | Follow `walkDerivationTree` pattern which already handles the same inductive; start simple (no subgoal serialization), iterate |
| Theorem corpus yields fewer steps than estimated (~108 theorems x ~5 steps) | M | M | Combine with higher-complexity formula generation and augmentation strategies |
| Lean compilation time for proof_extractor is long | M | L | The `Theorems/` imports are already compiled; incremental build should be manageable |
| Action index mapping mismatches between Lean constructor names and Python ACTION_TO_INDEX | H | L | Validate mapping with explicit test cases; use canonical names from `actions.py` |
| Augmented data is too homogeneous (dominated by weakening/context variants) | M | M | Weight training examples by tree height; curriculum learning starting with shallow proofs |
| `by`-tactic proofs in Combinators.lean produce opaque terms that cannot be walked | M | L | `DerivationTree` is a `Type` (not `Prop`), so Lean preserves the term; `by`-mode produces the same constructor applications as term-mode |

## Implementation Phases

**Dependency Analysis**:
| Wave | Phases | Blocked by |
|------|--------|------------|
| 1 | 1, 2 | -- |
| 2 | 3 | 1 |
| 3 | 4 | 2, 3 |
| 4 | 5 | 4 |

Phases within the same wave can execute in parallel.

---

### Phase 1: Lean ProofStep Structure and extractStepSequence [NOT STARTED]

**Goal**: Implement the core Lean data structure and extraction function that recursively walks a `DerivationTree` to produce an ordered list of proof steps with context, goal, rule, and subgoal information.

**Tasks**:
- [ ] Define `ProofStep` structure in `Theories/Bimodal/Automation/DataExport.lean` with fields: `context` (List String), `goal` (String, formula JSON), `goalPretty` (String, human-readable), `rule` (String), `axiomName` (Option String), `subgoals` (List (List String x String)), `depth` (Nat)
- [ ] Implement `extractStepSequence` function that pattern-matches on `DerivationTree` constructors (axiom, assumption, modus_ponens, necessitation, temporal_necessitation, temporal_duality, weakening), emitting one `ProofStep` per node in pre-order traversal
- [ ] Implement `ProofStep.toJson` serialization using the existing `escapeJsonString` and `listToJsonArray` helpers
- [ ] Map each `DerivationTree` constructor to its canonical rule name matching `RULE_ACTIONS` in `actions.py` (axiom -> "axiom", assumption -> "assumption", modus_ponens -> "modus_ponens", etc.)
- [ ] For the `axiom` constructor, extract the axiom schema name (e.g., "prop_k", "modal_t") using a match on the `Axiom` inductive type
- [ ] Serialize context formulas using `Formula.prettyPrint` and goal formula using both `Formula.toJson` and `Formula.prettyPrint`
- [ ] Add unit tests: apply `extractStepSequence` to a simple hand-built `DerivationTree` and verify the output step count and rule names

**Timing**: 3 hours

**Depends on**: none

**Files to modify**:
- `BimodalLogic/Theories/Bimodal/Automation/DataExport.lean` - Add ProofStep structure, extractStepSequence, ProofStep.toJson
- `BimodalLogic/Tests/` (optional) - Unit test for extractStepSequence

**Verification**:
- `lake build Bimodal` compiles without errors
- A simple test `DerivationTree` (e.g., modus_ponens with two axiom leaves) produces 3 `ProofStep` records with correct rule names

---

### Phase 2: Python ProofStepRecord Schema and Action Mapping [COMPLETED]

**Goal**: Extend the Python schema to represent step-level proof data and provide the mapping from (rule, axiom_name) pairs to the 49-action index.

**Tasks**:
- [ ] Define `ProofStepRecord` frozen dataclass in `src/bimodal_harness/schema/records.py` with fields: `step_id` (str), `theorem_name` (str), `context` (tuple[str, ...]), `goal_json` (dict), `goal_pretty` (str), `rule` (str), `axiom_name` (str | None), `action_index` (int), `subgoals` (tuple[dict, ...]), `depth` (int), `frame_class` (str), `proof_height` (int)
- [ ] Implement `step_to_action_index(rule: str, axiom_name: str | None) -> int` function in `src/bimodal_harness/schema/actions.py` that maps rule="axiom" + axiom_name to indices 0-41, and rule names to indices 42-48
- [ ] Add `to_dict()` and `from_dict()` class methods on `ProofStepRecord` for JSON round-tripping
- [ ] Write pytest tests: verify `step_to_action_index` returns correct indices for all 42 axiom names and all 7 rule names; verify `ProofStepRecord.from_dict(record.to_dict()) == record` round-trip

**Timing**: 1.5 hours

**Depends on**: none

**Files to modify**:
- `BimodalHarness/src/bimodal_harness/schema/records.py` - Add ProofStepRecord dataclass
- `BimodalHarness/src/bimodal_harness/schema/actions.py` - Add step_to_action_index function
- `BimodalHarness/tests/` - pytest tests for ProofStepRecord and step_to_action_index

**Verification**:
- `pytest tests/test_proof_step_record.py` passes
- `step_to_action_index("axiom", "prop_k")` returns 0; `step_to_action_index("modus_ponens", None)` returns 44
- Round-trip serialization preserves all fields

---

### Phase 3: Lean proof_extractor Executable [NOT STARTED]

**Goal**: Create a `lake exe proof_extractor` executable that imports all theorem modules, enumerates known `DerivationTree` definitions, extracts step sequences, and writes JSONL to stdout.

**Tasks**:
- [ ] Create `Theories/Bimodal/Automation/ProofExtractor.lean` as the executable entry point
- [ ] Import all `Theorems/` modules (Combinators, GeneralizedNecessitation, ModalS4, ModalS5, TemporalDerived, Propositional/Core, Propositional/Connectives, Propositional/Reasoning, Perpetuity/Helpers, Perpetuity/Principles, Perpetuity/Bridge, Perpetuity)
- [ ] Create a registry of (theorem_name: String, extraction: IO (List ProofStep)) entries that covers all ~108 theorem definitions; each entry calls `extractStepSequence` on the corresponding `DerivationTree` value
- [ ] Implement `main : IO Unit` that iterates through the registry, extracts steps, assigns sequential step_ids, and writes one JSONL line per step to stdout
- [ ] Each JSONL line includes: step_id, theorem_name, context, goal (JSON AST), goal_pretty, rule, axiom_name, action_index (computed in Lean using a lookup table), subgoals, depth, frame_class ("Base"), proof_height
- [ ] Register `proof_extractor` in `lakefile.lean` as a new `lean_exe` target
- [ ] Run `lake exe proof_extractor > data/proof-steps.jsonl` and verify output

**Timing**: 2.5 hours

**Depends on**: 1

**Files to modify**:
- `BimodalLogic/Theories/Bimodal/Automation/ProofExtractor.lean` - New file: executable entry point
- `BimodalLogic/lakefile.lean` - Add `lean_exe proof_extractor` target
- `BimodalLogic/data/proof-steps.jsonl` - Generated output (not committed; gitignored)

**Verification**:
- `lake build proof_extractor` succeeds
- `lake exe proof_extractor | head -5` outputs valid JSONL with expected fields
- `lake exe proof_extractor | wc -l` produces ~500-1,600 lines (matching estimated step count)
- Each line has valid `rule` and `action_index` fields

---

### Phase 4: Python Ingestion Pipeline for Proof Steps [NOT STARTED]

**Goal**: Build the Python pipeline to load proof step JSONL, validate action indices, and produce the supervised training dataset.

**Tasks**:
- [ ] Add `load_proof_steps(path: Path) -> list[ProofStepRecord]` function in `src/bimodal_harness/data/ingestion.py` that reads JSONL, calls `ProofStepRecord.from_dict`, and validates each record
- [ ] Validate action_index consistency: assert `step_to_action_index(record.rule, record.axiom_name) == record.action_index` for every record
- [ ] Add `frame_class_mask` field computation: attach the appropriate boolean mask from `FRAME_CLASS_MASKS` to each step record for training
- [ ] Implement dataset statistics reporter: print theorem count, total steps, step depth distribution, rule distribution, axiom distribution
- [ ] Write integration test: load `data/proof-steps.jsonl` (or a fixture), verify record count, verify action indices are in [0, 48], verify all rules are valid
- [ ] Create `scripts/extract_and_ingest.py` CLI script that runs `lake exe proof_extractor` via subprocess and then ingests the output

**Timing**: 1.5 hours

**Depends on**: 2, 3

**Files to modify**:
- `BimodalHarness/src/bimodal_harness/data/ingestion.py` - Add load_proof_steps function
- `BimodalHarness/scripts/extract_and_ingest.py` - New CLI script
- `BimodalHarness/tests/` - Integration test for proof step ingestion

**Verification**:
- `python scripts/extract_and_ingest.py` runs end-to-end without errors
- Statistics output shows >500 total steps with non-trivial rule distribution
- `pytest tests/test_proof_step_ingestion.py` passes
- All action indices validated against `step_to_action_index`

---

### Phase 5: Data Augmentation and Final Dataset Assembly [NOT STARTED]

**Goal**: Apply augmentation strategies to expand the raw ~500-1,600 step triples to 10-20K and assemble the final supervised dataset.

**Tasks**:
- [ ] Implement temporal dual augmentation: for each theorem step involving a future temporal operator, generate the corresponding past-dual step (swap U<->S, F<->P, G<->H) and vice versa; add `augmentation_source` field to track provenance
- [ ] Implement context variation augmentation: for each theorem `[] |- phi`, generate variants `[psi] |- phi` via the weakening rule, producing one additional step per context formula added; limit to 3-5 context formulas per theorem to control dataset size
- [ ] Run `lake exe dataset_generator` with `--max-complexity 8 --max-modal-depth 3` on a batch of 50K formulas to generate higher-complexity valid records; extract step sequences from any records with `height > 0`
- [ ] Combine all sources (theorem extraction, augmented variants, higher-complexity generation) into `data/supervised-combined.jsonl`
- [ ] Compute and report final dataset statistics: total steps, height distribution, rule/axiom distribution, augmentation source breakdown
- [ ] Verify no duplicate step_ids; verify action_index coverage (how many of the 49 actions are represented)
- [ ] Write dataset split utility: train/val/test split (80/10/10) stratified by proof height

**Timing**: 1.5 hours

**Depends on**: 4

**Files to modify**:
- `BimodalHarness/src/bimodal_harness/data/augmentation.py` - New file: augmentation strategies
- `BimodalHarness/scripts/assemble_supervised_dataset.py` - New CLI script for final assembly
- `BimodalHarness/data/supervised-combined.jsonl` - Final combined dataset (gitignored)

**Verification**:
- Final dataset contains >= 5,000 step triples (stretch goal: 10-20K)
- Height distribution is non-trivial: at least 30% of steps have depth > 0
- Rule distribution includes modus_ponens, necessitation, and axiom (not just single-axiom trivial proofs)
- Train/val/test splits are created and non-overlapping
- Statistics report printed to console

---

## Testing & Validation

- [ ] `lake build Bimodal` compiles with new DataExport additions (Phase 1)
- [ ] `lake build proof_extractor` compiles and runs (Phase 3)
- [ ] `pytest tests/test_proof_step_record.py` - Schema round-trip and action mapping (Phase 2)
- [ ] `pytest tests/test_proof_step_ingestion.py` - Ingestion pipeline (Phase 4)
- [ ] End-to-end: `lake exe proof_extractor | python -c "import sys, json; [json.loads(l) for l in sys.stdin]"` validates all output is valid JSON
- [ ] Action index coverage: count distinct action indices in final dataset
- [ ] Height distribution: verify non-trivial proof depth representation

## Artifacts & Outputs

- `BimodalLogic/Theories/Bimodal/Automation/DataExport.lean` - Extended with ProofStep and extractStepSequence
- `BimodalLogic/Theories/Bimodal/Automation/ProofExtractor.lean` - New executable entry point
- `BimodalLogic/lakefile.lean` - Updated with proof_extractor target
- `BimodalHarness/src/bimodal_harness/schema/records.py` - Extended with ProofStepRecord
- `BimodalHarness/src/bimodal_harness/schema/actions.py` - Extended with step_to_action_index
- `BimodalHarness/src/bimodal_harness/data/ingestion.py` - Extended with load_proof_steps
- `BimodalHarness/src/bimodal_harness/data/augmentation.py` - New augmentation module
- `BimodalHarness/scripts/extract_and_ingest.py` - Extraction CLI
- `BimodalHarness/scripts/assemble_supervised_dataset.py` - Assembly CLI
- `BimodalLogic/data/proof-steps.jsonl` - Raw extracted step data
- `BimodalHarness/data/supervised-combined.jsonl` - Final augmented dataset

## Rollback/Contingency

- **Lean compilation failure**: The new code is additive to `DataExport.lean`; revert additions without affecting existing functionality. `proof_extractor` is a separate `lean_exe` target.
- **Insufficient theorem yield**: If fewer than 300 steps are extracted from Theorems/, prioritize higher-complexity formula generation (Phase 5 augmentation) and consider adding new hand-written theorems to the corpus.
- **Action index mismatch**: The canonical mapping lives in `actions.py`; if Lean-side names diverge, fix the Lean `axiomNameStr` mapping function rather than changing the Python side.
- **Full rollback**: Remove new files (`ProofExtractor.lean`, `augmentation.py`, scripts) and revert additions to `DataExport.lean`, `records.py`, `actions.py`, `ingestion.py`. No existing functionality is modified destructively.
