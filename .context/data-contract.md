# Data Contract: BimodalLogic -> BimodalHarness Field Mapping

**Version**: 1.0 (task 5, 2026-05-29)
**Status**: Active

This document is the canonical reference for the field-level mapping between
BimodalLogic's Lean `dataset_generator` JSONL output and BimodalHarness's
Python `schema.records.TrainingRecord`.

## Overview

BimodalLogic exports training data via `lake exe dataset_generator` to JSONL
files. BimodalHarness reads these files using `data.ingestion.load_lean_jsonl`
or `data.ingestion.lean_export_to_training_record`. This document specifies
exactly how each Lean field maps to a Python field.

---

## Top-Level Field Mapping

| Lean JSONL field   | Python `TrainingRecord` field | Notes |
|--------------------|-------------------------------|-------|
| `id`               | `record_id`                   | Auto-generated UUID if absent |
| `formula_ast`      | `formula_json`                | Formula AST as JSON dict |
| `formula_str`      | `formula_pretty`              | Human-readable formula string |
| `label`            | `label`                       | Passthrough (already lowercase) |
| `pattern_key`      | `pattern_key`                 | Via `PatternKey.from_dict` (camelCase) |
| `metrics`          | `difficulty_metrics`          | Via `DifficultyMetrics.from_dict` (camelCase) |
| `proof_trace`      | `proof_trace`                 | Via `ProofTrace.from_dict` |
| `countermodel`     | `countermodel`                | Via `SimpleCountermodel.from_dict` |
| `frame_class`      | `frame_class`                 | Passthrough; defaults to `"Base"` |
| `split`            | *(not stored)*                | Train/val/test split; ignored on ingest |
| `augmentation`     | *(not stored)*                | Augmentation data; ignored on ingest |
| *(absent)*         | `record_id`                   | Auto-generated UUID4 |
| *(absent)*         | `source`                      | Always `"lean_export"` |
| *(absent)*         | `logic_system`                | Always `"TM_BX"` |
| *(absent)*         | `schema_version`              | Set from `constants.SCHEMA_VERSION` |

---

## Label Values

| Lean label    | Python label  | Meaning |
|---------------|---------------|---------|
| `"valid"`     | `"valid"`     | Formula is a theorem |
| `"invalid"`   | `"invalid"`   | Formula has a countermodel |
| `"timeout"`   | `"timeout"`   | Proof search exceeded time limit |

All labels are **lowercase** on both sides. `VALID_LABELS` in
`schema.constants` includes all three values.

**Note**: The legacy `data.schema.Label` enum uses uppercase values
(`"VALID"`, `"INVALID"`, `"TIMEOUT"`) -- this is a known mismatch in the
deprecated schema layer.

---

## PatternKey Field Mapping (camelCase)

| Lean JSON key   | Python field       | Type  | Notes |
|-----------------|--------------------|-------|-------|
| `modalDepth`    | `modal_depth`      | `int` | Modal nesting depth |
| `temporalDepth` | `temporal_depth`   | `int` | Temporal nesting depth |
| `impCount`      | `imp_count`        | `int` | Implication count |
| `complexity`    | `complexity`       | `int` | Total connective count + 1 |
| `topOperator`   | `top_operator`     | `str` | GoalCategory name (PascalCase) |

### Valid `topOperator` / `top_operator` Values

| Lean `topOperator` | Python `top_operator` |
|--------------------|-----------------------|
| `"Atom"`           | `"Atom"`              |
| `"Bottom"`         | `"Bottom"`            |
| `"Implication"`    | `"Implication"`       |
| `"Box"`            | `"Box"`               |
| `"AllPast"`        | `"AllPast"`           |
| `"AllFuture"`      | `"AllFuture"`         |
| `"Until"`          | `"Until"`             |
| `"Since"`          | `"Since"`             |

---

## DifficultyMetrics Field Mapping (camelCase)

| Lean JSON key     | Python field         | Type  | Notes |
|-------------------|----------------------|-------|-------|
| `atomCount`       | `atom_count`         | `int` | Distinct atom count |
| `modalDepth`      | `modal_depth`        | `int` | Modal depth |
| `temporalDepth`   | `temporal_depth`     | `int` | Temporal depth |
| `decisionTimeMs`  | `decision_time_ms`   | `int` | Wall-clock time (ms) |
| `difficultyTier`  | `difficulty_tier`    | `str` | Difficulty category string |
| *(absent)*        | `search_depth`       | `int` | Defaults to `0` (no Lean counterpart) |
| *(absent)*        | `complexity`         | `int` | From `PatternKey.complexity` |

### Valid `difficultyTier` / `difficulty_tier` Values

| Value        | Meaning |
|--------------|---------|
| `"easy"`     | Simple formula, fast proof |
| `"medium"`   | Moderate complexity |
| `"hard"`     | Complex or slow |
| `"very_hard"`| Very complex or very slow |

**Note**: `"trivial"` is NOT a valid value -- Lean never emits it.
The legacy `data.schema` used integer tiers (1-5); `DIFFICULTY_TIER_MAP`
in `data.ingestion` converts these to strings (1,2 -> `"easy"`, 3 -> `"medium"`,
4 -> `"hard"`, 5 -> `"very_hard"`).

---

## ProofTrace Format Variants

Lean exports `proof_trace` in two possible formats (both are accepted by
`ProofTrace.from_dict` after Phase 1 changes):

### Lean export format (string list)
```json
{
  "height": 2,
  "axioms_used": ["modal_t", "prop_k"],
  "rules_applied": ["axiom", "modus_ponens", "axiom"]
}
```
The `rules_applied` field is a **list of rule-name strings**. The adapter
builds a synthetic `RuleProfile` by counting occurrences.

### Python round-trip format (RuleProfile dict)
```json
{
  "height": 2,
  "axioms_used": ["modal_t", "prop_k"],
  "rules": {
    "axiom": 2,
    "modus_ponens": 1,
    ...
  }
}
```
The `rules` field is a **RuleProfile dict** with integer counts.

### RuleProfile Key Mapping

| `rules_applied` string | `RuleProfile` field       |
|------------------------|---------------------------|
| `"axiom"`              | `axiom_count`             |
| `"assumption"`         | `assumption_count`        |
| `"modus_ponens"`       | `mp_count`                |
| `"necessitation"`      | `necessitation_count`     |
| `"temporal_necessitation"` | `temporal_necessitation_count` |
| `"temporal_duality"`   | `temporal_duality_count`  |
| `"weakening"`          | `weakening_count`         |

---

## SimpleCountermodel Format

### Lean export format (Atom objects)
```json
{
  "trueAtoms": [{"base": "p", "fresh_index": null}],
  "falseAtoms": [{"base": "q", "fresh_index": null}],
  "formula": {"tag": "atom", "name": "p"}
}
```

- `trueAtoms` / `falseAtoms`: lists of Atom JSON objects with `base` (string) and `fresh_index` (int or null)
- `formula`: the refuted formula as a **formula AST dict** (not a string)

### Python storage
```python
SimpleCountermodel(
    true_atoms=("p",),      # tuple of base names
    false_atoms=("q",),     # tuple of base names
    formula_json={...},     # formula AST dict
)
```

The `base` field of each Atom object is extracted as the atom name.

---

## Formula AST Mapping

| Lean `Formula.toJson`                    | Python JSON dict |
|------------------------------------------|-----------------|
| `atom n`                                 | `{"tag": "atom", "name": "n"}` |
| `bot`                                    | `{"tag": "bot"}` |
| `imp l r`                                | `{"tag": "imp", "left": L, "right": R}` |
| `box f`                                  | `{"tag": "box", "child": F}` |
| `untl e g`                               | `{"tag": "untl", "event": E, "guard": G}` |
| `snce e g`                               | `{"tag": "snce", "event": E, "guard": G}` |

**Critical note**: `box` uses **only** `child` -- the `event` field found in
the deprecated `data.schema.FormulaNode` does NOT appear in Lean's output.

---

## Frame Classes

| Lean `FrameClass` constructor | Python `frame_class` string |
|-------------------------------|----------------------------|
| `Base`                        | `"Base"`                   |
| `Dense`                       | `"Dense"`                  |
| `Discrete`                    | `"Discrete"`               |

Currently the `dataset_generator` always emits `"Base"`.

---

## Python API Summary

### Reading Lean JSONL directly

```python
from bimodal_harness.data.ingestion import load_lean_jsonl, filter_timeout_records
from pathlib import Path

records = load_lean_jsonl(Path("data/export.jsonl"))  # skips timeout by default
non_timeout = filter_timeout_records(records)  # explicit post-ingest filter
```

### Single record translation

```python
from bimodal_harness.data.ingestion import lean_export_to_training_record

data = {
    "id": "bmlogic-00001",
    "formula_ast": {"tag": "atom", "name": "p"},
    "formula_str": "p",
    "label": "invalid",
    "frame_class": "Base",
    "proof_trace": None,
    "countermodel": {
        "trueAtoms": [],
        "falseAtoms": [{"base": "p", "fresh_index": None}],
        "formula": {"tag": "atom", "name": "p"},
    },
    "pattern_key": {"modalDepth": 0, "temporalDepth": 0, "impCount": 0,
                    "complexity": 1, "topOperator": "Atom"},
    "metrics": {"atomCount": 1, "modalDepth": 0, "temporalDepth": 0,
                "decisionTimeMs": 5, "difficultyTier": "easy"},
}
record = lean_export_to_training_record(data)
```

### Using the make sync-data workflow

```bash
# In BimodalLogic repository:
lake exe dataset_generator --output data/export.jsonl

# In BimodalHarness repository:
make sync-data   # rsync from BimodalLogic data/ to BimodalHarness data/

# Load in Python:
from bimodal_harness.data.ingestion import load_lean_jsonl
records = load_lean_jsonl(Path("data/train.jsonl"))
```

---

## Schema Version Compatibility

- `SCHEMA_VERSION = "1.0.0"` in `schema.constants`
- The Lean `dataset_generator` does not embed a schema version in its output
- BimodalHarness adds `schema_version` during ingest

When the Lean export format changes, update:
1. `schema.constants` (`VALID_LABELS`, `VALID_DIFFICULTY_TIERS`, etc.)
2. `schema.records` (`from_dict` methods)
3. `data.ingestion` (`lean_export_to_training_record`)
4. This document

---

## Known Mismatches in Deprecated `data.schema`

The `data.schema` module (deprecated) has the following mismatches vs Lean:

| Field                | `data.schema` value          | Lean actual value              |
|----------------------|------------------------------|--------------------------------|
| `Label` enum values  | `"VALID"`, `"INVALID"`, `"TIMEOUT"` | `"valid"`, `"invalid"`, `"timeout"` |
| `PatternKey` keys    | snake_case                   | camelCase                     |
| `DifficultyMetrics.difficulty_tier` | `int` (1-5) | `str` ("easy", etc.)   |
| `RuleProfile` fields | `imp_left`, `box_right`, etc. | `axiom`, `modus_ponens`, etc. |
| `box` AST node       | `child` + `event` required   | `child` only                  |
| `SimpleCountermodel.formula` | `str` | formula AST dict              |

Use `data.ingestion.labeled_formula_to_training_record` to bridge from the
deprecated schema to `schema.records.TrainingRecord`.
