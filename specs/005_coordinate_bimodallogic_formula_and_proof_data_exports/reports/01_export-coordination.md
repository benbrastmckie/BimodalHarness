# Research Report: Task #5

**Task**: 005 - Coordinate BimodalLogic formula and proof data exports
**Started**: 2026-05-29T00:00:00Z
**Completed**: 2026-05-29T00:30:00Z
**Effort**: ~1.5 hours
**Dependencies**: Task 3 (cross-repo integration architecture, completed)
**Sources/Inputs**: Codebase — BimodalLogic Lean sources, BimodalHarness Python schema modules, Makefile, data/README.md
**Artifacts**: `specs/005_coordinate_bimodallogic_formula_and_proof_data_exports/reports/01_export-coordination.md`
**Standards**: report-format.md, subagent-return.md

---

## Executive Summary

- BimodalLogic has a complete, working `lake exe dataset_generator` executable that writes JSONL; the pipeline from formula enumeration through labeling to file output is fully implemented.
- BimodalHarness has a mature schema layer (`schema/` package) whose field names, casing, and types do **not** match what the Lean executable actually emits; reconciliation is required before end-to-end integration can work.
- The sync workflow is already designed (rsync via `make sync-data`) and the data directory structure is in place; no new infrastructure needs to be invented, only the field-name mismatches must be fixed.

---

## Context & Scope

Task 3 (completed) chose artifact-only integration: BimodalLogic exports JSONL files; BimodalHarness reads them. Task 5 is the specification and gap-closing step before any training pipeline can consume real data. This report documents (a) exactly what the Lean executable emits, (b) exactly what the Python schema expects, and (c) every discrepancy between the two.

---

## Findings

### Codebase Patterns

#### What BimodalLogic Exports (`DatasetExport.lean`, `lake exe dataset_generator`)

The `dataset_generator` executable (registered in `lakefile.lean`, root `Bimodal.Automation.DatasetExport`) writes one JSON object per line. The canonical field set is:

```
{
  "id":             "bmlogic-00001",          // zero-padded 5-digit index
  "split":          "train"|"val"|"test",     // hash-based 80/10/10
  "formula_str":    "(□p → p)",              // Formula.prettyPrint
  "formula_ast":    { "tag": ..., ... },      // Formula.toJson (see below)
  "frame_class":    "Base",                  // always "Base" currently
  "label":          "valid"|"invalid"|"timeout",
  "proof_trace":    { ... } | null,          // present for label=="valid"
  "countermodel":   { ... } | null,          // present for label=="invalid"
  "pattern_key":    { ... },
  "metrics":        { ... },
  "augmentation":   null | { ... }           // set when --include-duals
}
```

**Formula AST** (`Formula.toJson` in `DataExport.lean`):
```
atom  -> {"tag": "atom", "name": "<base>"}
bot   -> {"tag": "bot"}
imp   -> {"tag": "imp", "left": <F>, "right": <F>}
box   -> {"tag": "box", "child": <F>}             // NOTE: single "child" field only
untl  -> {"tag": "untl", "event": <F>, "guard": <F>}
snce  -> {"tag": "snce", "event": <F>, "guard": <F>}
```

**PatternKey** (camelCase, from `PatternKey.toJson`):
```json
{"modalDepth": 1, "temporalDepth": 0, "impCount": 1, "complexity": 3, "topOperator": "Implication"}
```

**ProofTrace** (from `ProofTrace.toJson` in `DatasetGenerator.lean`):
```json
{"height": 2, "axioms_used": ["modal_t"], "rules_applied": ["modus_ponens"]}
```
Note: `rules_applied` is a **list of strings** (not a `RuleProfile` dict).

**SimpleCountermodel** (from `SimpleCountermodel.toJson`):
```json
{"trueAtoms": [{"base": "p", "fresh_index": null}], "falseAtoms": [...], "formula": <formula AST>}
```
Note: `trueAtoms`/`falseAtoms` are **lists of Atom objects** (with `base` and `fresh_index` keys), and `formula` is a **formula AST** (not a string).

**DifficultyMetrics** (from `DifficultyMetrics.toJson`):
```json
{"complexity": 3, "modalDepth": 1, "temporalDepth": 0, "impCount": 1, "atomCount": 2, "decisionTimeMs": 45, "difficultyTier": "easy"}
```
All keys are **camelCase**. `difficultyTier` is a **string** ("easy", "medium", "hard", "very_hard").

**Label values**: `"valid"`, `"invalid"`, `"timeout"` — all **lowercase**.

#### What BimodalHarness Expects

Two schema layers exist and diverge from each other and from the Lean export:

**`src/bimodal_harness/data/schema.py`** (`LabeledFormula`) — the simpler layer:
- Top-level fields: `formula`, `label`, `proof_trace`, `countermodel`, `metrics`, `pattern_key`
- No `id`, `split`, `formula_str`, `frame_class`, `augmentation` fields
- `Label` enum: `"VALID"`, `"INVALID"`, `"TIMEOUT"` — **uppercase**
- `PatternKey.from_json` reads `modal_depth`, `temporal_depth`, `imp_count`, `complexity`, `top_operator` — **snake_case**
- `SimpleCountermodel.from_json` reads `true_atoms` (a list of strings), `false_atoms`, `formula` (a string)
- `ProofTrace.from_dict` reads `rules_applied` as a `RuleProfile` dict (not a list of strings)
- `DifficultyMetrics.from_json` reads `decision_time_ms` as float, `difficulty_tier` as int (1–5)

**`src/bimodal_harness/schema/records.py`** (`TrainingRecord`) — the richer ML layer:
- Top-level fields: `record_id`, `formula_json`, `formula_pretty`, `label`, `pattern_key`, `difficulty_metrics`, `proof_trace`, `countermodel`, `schema_version`, `frame_class`, `source`, `logic_system`
- `PatternKey.from_dict` reads camelCase keys (`modalDepth`, `temporalDepth`, `impCount`, `topOperator`) — consistent with Lean
- `RuleProfile` has 7 named counts (`axiom`, `assumption`, `modus_ponens`, `necessitation`, `temporal_necessitation`, `temporal_duality`, `weakening`) — consistent with `DataExport.lean RuleProfile.toJson`
- `ProofTrace.from_dict` reads `rules` (a RuleProfile dict) and `axioms_used` (a list)
- `DifficultyMetrics` has `search_depth` field — **not emitted by Lean**
- Label values: `"valid"`, `"invalid"` only (no `"timeout"`)

**`data/samples/test_formulas.jsonl`** (actual fixture used by tests):
- Uses snake_case for PatternKey (`modal_depth`, `temporal_depth`)
- `difficulty_tier` is an integer (e.g., `1`)
- `rules_applied` in proof_trace is the `RuleProfile` dict form
- No `id`, `split`, `formula_str`, `frame_class` fields
- Labels are uppercase: `"VALID"`, `"INVALID"`

---

## Gap Analysis: Lean Export vs Python Expectation

| Field / Aspect | Lean `dataset_generator` emits | Python needs | Gap |
|---|---|---|---|
| Top-level record shape | `id`, `split`, `formula_str`, `formula_ast`, `frame_class`, `label`, `proof_trace`, `countermodel`, `pattern_key`, `metrics`, `augmentation` | `formula` (not `formula_ast`), `formula_pretty` (not `formula_str`), rest optional | **Key name mismatch**: `formula_ast` vs `formula`; `formula_str` vs `formula_pretty` |
| Label casing | `"valid"`, `"invalid"`, `"timeout"` (lowercase) | `schema.py` expects `"VALID"`, `"INVALID"`, `"TIMEOUT"`; `records.py` expects `"valid"`, `"invalid"` | **Casing conflict** between the two Python layers; Lean uses lowercase |
| PatternKey key style | camelCase (`modalDepth`, `temporalDepth`, `impCount`, `topOperator`) | `schema.py` uses snake_case; `records.py` uses camelCase | **`schema.py` diverges**; `records.py` matches Lean |
| `topOperator` values | Title-case strings from `GoalCategory.toJson`: `"Atom"`, `"Bottom"`, `"Implication"`, `"Box"`, `"AllPast"`, `"AllFuture"`, `"Until"`, `"Since"` | `VALID_TOP_OPERATORS` in `constants.py` has all 8 — matches | No gap |
| ProofTrace shape | `{"height": N, "axioms_used": [...], "rules_applied": [...strings...]}` | `records.py ProofTrace.from_dict` reads `rules` (dict) + `axioms_used`; Lean emits `rules_applied` (list of strings) | **Field name and type mismatch**: `rules_applied` (string list) vs `rules` (RuleProfile dict) |
| `RuleProfile` | Emitted separately by `DataExport.lean proofMetricsToJson` as `{"axiom": N, "assumption": N, ...}` — **not included** in `DatasetExport.lean datasetRecordToJson` | `records.py` RuleProfile has 7 named counts; `schema.py` RuleProfile has 7 different names (`imp_left`, etc.) | **`schema.py` RuleProfile is completely wrong** — field names do not match Lean |
| SimpleCountermodel atoms | `trueAtoms`: list of `{"base": "p", "fresh_index": null}` objects; `formula`: formula AST dict | `schema.py` expects `true_atoms` (string list) and `formula` (string); `records.py` reads `trueAtoms` correctly | **`schema.py` uses wrong key names and wrong formula type** |
| `DifficultyMetrics` key style | camelCase: `modalDepth`, `atomCount`, `decisionTimeMs`, `difficultyTier` (string) | `schema.py` uses snake_case; `records.py` uses snake_case | **Both Python layers diverge from Lean** |
| `difficulty_tier` type | String: `"easy"`, `"medium"`, `"hard"`, `"very_hard"` | `schema.py` expects int (1–5); `records.py` expects string from `VALID_DIFFICULTY_TIERS` | **`schema.py` uses int, Lean emits string** |
| `search_depth` | Not emitted by Lean | `records.py DifficultyMetrics` requires it | **Missing field**: must default to 0 |
| `record_id` | `id` field in Lean output (`"bmlogic-00001"`) | `records.py` uses `record_id` | **Key name mismatch** |
| `formula_pretty` | `formula_str` in Lean output | `records.py` uses `formula_pretty` | **Key name mismatch** |
| `timeout` label | Lean emits `"timeout"` | `records.py VALID_LABELS` only has `"valid"`, `"invalid"` | **Timeout records will fail validation**; must either be filtered or the set extended |
| `box` AST fields | `{"tag": "box", "child": <F>}` — one field | `schema.py FormulaNode.from_json` reads `child` AND `event`; requires `event` | **`schema.py` expects `event` field that Lean does not emit** |
| Split / augmentation | Lean emits `split`, `augmentation` | Neither Python layer reads these | Unused fields — no functional gap, but Python ignores them |

---

## Recommendations

### Priority 1: Create a canonical ingest adapter

The cleanest fix is a single Python function that maps a Lean `dataset_generator` JSONL line (as parsed by `json.loads`) to a `TrainingRecord` (the more complete type). This adapter lives in `src/bimodal_harness/data/ingestion.py` (currently a stub) and handles all field-name translations:

```python
def lean_export_to_training_record(data: dict) -> TrainingRecord:
    # id -> record_id
    # formula_ast -> formula_json
    # formula_str -> formula_pretty
    # label: already lowercase, but filter "timeout"
    # pattern_key: already camelCase — pass to PatternKey.from_dict
    # metrics: translate camelCase to snake_case; set search_depth=0
    # proof_trace.rules_applied (string list) -> synthesize RuleProfile from counts
    # countermodel.trueAtoms -> keep as-is; formula field is AST dict
    ...
```

### Priority 2: Retire or align `schema.py`

`src/bimodal_harness/data/schema.py` has a `LabeledFormula` type whose field mappings are wrong in multiple places (`schema.py` is the older, less accurate layer). Options:

a. Delete it — all callers should use `records.py TrainingRecord` + the ingest adapter.
b. Fix it in-place to match what `dataset_generator` emits.
c. Keep both and add a bridging `from_lean_export` classmethod.

Option (a) is recommended: the `schema/records.py` layer is more complete and has better Lean correspondence. The test fixtures in `data/samples/` use a format that matches neither layer perfectly, so they should be regenerated after a real `lake exe dataset_generator` run.

### Priority 3: Fix `ProofTrace` in `records.py`

The `DatasetExport.lean datasetRecordToJson` emits `proof_trace` as:
```json
{"height": N, "axioms_used": [...strings...], "rules_applied": [...strings...]}
```
But `records.py ProofTrace.from_dict` reads the key `rules` (a `RuleProfile` dict). Either:
- Change Lean to emit `rules` as a `RuleProfile` dict (the `DataExport.lean proofMetricsToJson` format already exists), OR
- Change `records.py` to accept `rules_applied` as a list of strings and build a synthetic `RuleProfile` by counting.

Lean-side change is cleaner: add `"rules": <ruleProfile>` to `DatasetExport.lean datasetRecordToJson`. This requires one additional line in `DatasetExport.lean` importing `walkDerivationTree` or passing through the `RuleProfile` from `labelFormula`. Given that `DatasetGenerator.lean` has `LabeledFormula` which currently stores a `ProofTrace` (not a raw `DerivationTree`), the rule counts are not directly available at export time — the Python-side interpretation of `rules_applied` as strings is the pragmatic path.

### Priority 4: Extend `VALID_LABELS` or filter timeouts

Lean emits `"timeout"` records. `records.py TrainingRecord.__post_init__` raises `ValueError` if `label not in {"valid", "invalid"}`. The ingest adapter should either:
- Filter timeout records (skip them) — appropriate if the training pipeline only wants decided formulas.
- Extend `VALID_LABELS` to `{"valid", "invalid", "timeout"}` and make `proof_trace`/`countermodel` optional for timeouts.

Filtering is appropriate for the ML training phase; keeping timeouts is appropriate for diagnostic/analysis purposes. The design decision should be explicit in the schema constants.

### Priority 5: Define the sync workflow explicitly

The Makefile `sync-data` target already works:
```bash
make sync-data BIMODAL_LOGIC_PATH=/home/benjamin/Projects/BimodalLogic
```
This rsyncs `*.jsonl` and `*.parquet` from `BimodalLogic/data/` to `BimodalHarness/data/bimodal/`. The workflow is:

```
1. In BimodalLogic:
   lake exe dataset_generator -- --max-complexity 5 --output data/bmlogic.jsonl
   lake exe dataset_generator -- --max-complexity 8 --mode hybrid --output data/bmlogic_large.jsonl

2. In BimodalHarness:
   make sync-data BIMODAL_LOGIC_PATH=../BimodalLogic
   make validate-data

3. After sync: update data/VERSION with the BimodalLogic git commit hash
```

This workflow is ready to use once the schema mismatches are resolved. No new tooling needed.

---

## Decisions

- The `records.py TrainingRecord` is the canonical Python data type; `schema.py LabeledFormula` is secondary and should be aligned or retired.
- Field name translation from Lean camelCase to Python snake_case happens in the ingest adapter, not in the Lean code (Python adapts, Lean stays idiomatic).
- `search_depth` defaults to `0` on ingest (Lean does not emit it; it is a future field for MCTS-based proof search depth tracking).
- `timeout` records should be filterable at ingest time; the flag or filter should be explicit.

---

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| `schema.py` and `records.py` coexist and diverge further as both are edited independently | Deprecate `schema.py` in the next implementation task; add a docstring warning to it now |
| Test fixtures in `data/samples/` use fields from neither layer accurately | Regenerate fixtures from a real `lake exe dataset_generator` run after schema is stabilized |
| `box` AST: `schema.py` requires an `event` field that Lean does not emit — silent parse failure | Only use `records.py` + `formula.py validate_formula_json` for box AST; `schema.py FormulaNode.from_json` for `box` should be fixed (remove `event` requirement) |
| Lean `difficultyTier` tier labels may not cover `"trivial"` (in `VALID_DIFFICULTY_TIERS`) | Lean uses `"easy"/"medium"/"hard"/"very_hard"` only; remove `"trivial"` from the valid set or add it to Lean's classifier |

---

## Context Extension Recommendations

- **Topic**: Cross-repo JSONL field mapping table
- **Gap**: No single reference document lists the exact JSON field names emitted by `lake exe dataset_generator` alongside the Python field names expected by `TrainingRecord.from_dict`. This forces developers to cross-reference 5+ files.
- **Recommendation**: Create `.context/data-contract.md` with the canonical field mapping table from this report's gap analysis section.

---

## Appendix

### Key Files Read

- `/home/benjamin/Projects/BimodalLogic/Theories/Bimodal/Automation/DataExport.lean` — JSON serialization primitives
- `/home/benjamin/Projects/BimodalLogic/Theories/Bimodal/Automation/DatasetGenerator.lean` — LabeledFormula, ProofTrace, DifficultyMetrics, labelFormula
- `/home/benjamin/Projects/BimodalLogic/Theories/Bimodal/Automation/DatasetExport.lean` — DatasetRecord, JSONL writer, CLI `main`
- `/home/benjamin/Projects/BimodalLogic/Theories/Bimodal/Automation/FormulaEnumerator.lean` — EnumConfig, enumerateUpToDepth, sampleFormulas
- `/home/benjamin/Projects/BimodalLogic/lakefile.lean` — lake exe targets: `dataset_generator`, `dataset_validator`
- `/home/benjamin/Projects/BimodalHarness/src/bimodal_harness/data/schema.py` — LabeledFormula (older schema layer)
- `/home/benjamin/Projects/BimodalHarness/src/bimodal_harness/schema/records.py` — TrainingRecord (canonical ML layer)
- `/home/benjamin/Projects/BimodalHarness/src/bimodal_harness/schema/constants.py` — VALID_LABELS, VALID_DIFFICULTY_TIERS, VALID_TOP_OPERATORS
- `/home/benjamin/Projects/BimodalHarness/src/bimodal_harness/schema/actions.py` — AXIOM_ACTIONS (42), RULE_ACTIONS (7)
- `/home/benjamin/Projects/BimodalHarness/src/bimodal_harness/schema/serialization.py` — read_jsonl, write_jsonl, jsonl_dict_to_record
- `/home/benjamin/Projects/BimodalHarness/src/bimodal_harness/data/ingestion.py` — stub (empty)
- `/home/benjamin/Projects/BimodalHarness/data/README.md` — sync workflow documentation
- `/home/benjamin/Projects/BimodalHarness/data/samples/test_formulas.jsonl` — existing test fixtures
- `/home/benjamin/Projects/BimodalHarness/Makefile` — sync-data, validate-data targets
