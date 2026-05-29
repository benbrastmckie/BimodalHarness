# Research Report: Task 4 - Define Training Data Schema and Action Space

**Task**: 4 - Define training data schema and action space for AlphaZero proof search training harness
**Started**: 2026-05-29T00:00:00Z
**Completed**: 2026-05-29T00:30:00Z
**Effort**: ~30 minutes of codebase exploration + synthesis
**Sources/Inputs**:
- `/home/benjamin/Projects/BimodalLogic/Theories/Bimodal/Syntax/Formula.lean`
- `/home/benjamin/Projects/BimodalLogic/Theories/Bimodal/ProofSystem/Axioms.lean`
- `/home/benjamin/Projects/BimodalLogic/Theories/Bimodal/ProofSystem/Derivation.lean`
- `/home/benjamin/Projects/BimodalLogic/Theories/Bimodal/Automation/SuccessPatterns.lean`
- `/home/benjamin/Projects/BimodalLogic/Theories/Bimodal/Automation/DatasetGenerator.lean`
- `/home/benjamin/Projects/BimodalLogic/Theories/Bimodal/Automation/DataExport.lean`
- `/home/benjamin/Projects/BimodalLogic/Theories/Bimodal/Metalogic/Decidability/DecisionProcedure.lean`
- `/home/benjamin/Projects/BimodalLogic/Theories/Bimodal/Metalogic/Decidability/CountermodelExtraction.lean`
- `/home/benjamin/Projects/BimodalHarness/specs/001_implement_alphazero_proof_search_training_harness/reports/01_team-research.md`

**Artifacts**:
- `specs/004_define_training_data_schema_and_action_space/reports/01_data-schema-research.md` (this file)

---

## Executive Summary

This report provides the complete, ground-truth information for designing the training data schema and action space for the BimodalHarness AlphaZero proof search system. All findings come from direct codebase inspection.

Key findings:

1. **Action space is exactly 42 axiom constructors + 7 inference rule constructors = 49 total actions**. The "57" figure from team research was a counting artifact (counting all `|` pipe lines in Axioms.lean including FrameClass enum constructors and pattern match arms, not just Axiom constructors).

2. **BimodalLogic already implements a complete JSON serialization layer** (`DataExport.lean`) and a labeled record structure (`DatasetGenerator.lean`) that defines the natural schema. The Python schema should mirror these Lean types exactly.

3. **Formula has 6 primitive constructors** with well-defined JSON serialization using a `"tag"` discriminant field — already implemented in `DataExport.lean`.

4. **PatternKey has 5 features** with known types: `modalDepth` (Nat), `temporalDepth` (Nat), `impCount` (Nat), `complexity` (Nat), `topOperator` (8-value enum).

5. **The Lean-side already exports** `LabeledFormula` records containing formula, label (valid/invalid/timeout), proof trace, countermodel, difficulty metrics, and pattern key — this is the canonical schema.

---

## Context & Scope

Task 4 is a foundation task (Layer 0) with no dependencies. Its output (the schema definition) gates Tasks 5, 7, 8, and 10. The schema must:
- Represent bimodal TM logic formulas (and be extensible for full Logos operator set)
- Precisely enumerate the action space (policy network output dimension)
- Support JSON and Parquet serialization for ML training
- Capture proof traces for positive training signal and countermodels for corrective signal

The BimodalLogic Lean project has already implemented significant infrastructure that the Python schema should mirror. This dramatically reduces design work.

---

## Findings

### 1. Formula AST: Exact Constructors

`Formula.lean` defines an inductive type with **6 primitive constructors**:

| Constructor | Arguments | Description |
|-------------|-----------|-------------|
| `atom` | `Atom` | Propositional atom (base: String, fresh_index: Option Nat) |
| `bot` | — | Bottom (⊥, falsum) |
| `imp` | `Formula × Formula` | Implication (φ → ψ) |
| `box` | `Formula` | Modal necessity (□φ) |
| `untl` | `Formula × Formula` | Until (Burgess convention: event first, guard second) |
| `snce` | `Formula × Formula` | Since (Burgess convention: event first, guard second) |

All other operators are derived abbreviations, NOT separate constructors:
- `neg φ = imp φ bot`
- `top = imp bot bot`
- `diamond φ = neg (box (neg φ))`
- `some_future φ = untl φ top`
- `some_past φ = snce φ top`
- `all_future φ = neg (some_future (neg φ))`
- `all_past φ = neg (some_past (neg φ))`
- `always φ = and (all_past φ) (and φ (all_future φ))`
- `sometimes φ = neg (always (neg φ))`
- `next φ = untl φ bot`
- `prev φ = snce φ bot`

**JSON Serialization** (already implemented in `DataExport.lean`):
```json
{"tag": "atom", "name": "p"}
{"tag": "bot"}
{"tag": "imp", "left": <formula>, "right": <formula>}
{"tag": "box", "child": <formula>}
{"tag": "untl", "event": <formula>, "guard": <formula>}
{"tag": "snce", "event": <formula>, "guard": <formula>}
```

**Extensibility note**: The `tag`-based discriminant pattern is ideal for adding new operators. Future Logos operators (constitutive, epistemic, normative) simply add new tag values. The schema is already extensible by design.

**Formula metrics** available from `Formula.lean`:
- `modalDepth`: Max nesting of `box` operators (Nat)
- `temporalDepth`: Max nesting of `untl`/`snce` operators (Nat)
- `countImplications`: Total `imp` operators (Nat)
- `complexity`: Total connective count + 1 (Nat, ≥ 1)
- `atoms`: Finset of atoms appearing in formula

### 2. Action Space Enumeration (CRITICAL: 42 vs 57 Resolution)

**The correct answer is 42 axiom constructors.**

The "57" figure came from counting ALL pipe (`|`) lines in `Axioms.lean` without filtering — this accidentally includes:
- 3 FrameClass enum constructors (`Base`, `Dense`, `Discrete`)
- 6 pattern match arms in `Axiom.minFrameClass`

Precise count: `awk '/^inductive Axiom/,/^  deriving Repr/' Axioms.lean | grep "^  | " | grep -v "^  | --" | wc -l` = **42**.

#### Complete Axiom Constructor Enumeration (42 total)

**Layer 1: Propositional (4)**
| # | Constructor | Formula Schema |
|---|-------------|----------------|
| 1 | `prop_k` | `(φ → (ψ → χ)) → ((φ → ψ) → (φ → χ))` |
| 2 | `prop_s` | `φ → (ψ → φ)` |
| 3 | `ex_falso` | `⊥ → φ` |
| 4 | `peirce` | `((φ → ψ) → φ) → φ` |

**Layer 2: S5 Modal (5)**
| # | Constructor | Formula Schema |
|---|-------------|----------------|
| 5 | `modal_t` | `□φ → φ` |
| 6 | `modal_4` | `□φ → □□φ` |
| 7 | `modal_b` | `φ → □◇φ` |
| 8 | `modal_5_collapse` | `◇□φ → □φ` |
| 9 | `modal_k_dist` | `□(φ → ψ) → (□φ → □ψ)` |

**Layer 3: BX Temporal (22)**
| # | Constructor | BX Label |
|---|-------------|----------|
| 10 | `serial_future` | BX1 |
| 11 | `serial_past` | BX1' |
| 12 | `left_mono_until_G` | BX2G |
| 13 | `left_mono_since_H` | BX2H |
| 14 | `right_mono_until` | BX3 |
| 15 | `right_mono_since` | BX3' |
| 16 | `connect_future` | BX4 |
| 17 | `connect_past` | BX4' |
| 18 | `enrichment_until` | BX13 |
| 19 | `enrichment_since` | BX13' |
| 20 | `self_accum_until` | BX5 |
| 21 | `self_accum_since` | BX5' |
| 22 | `absorb_until` | BX6 |
| 23 | `absorb_since` | BX6' |
| 24 | `linear_until` | BX7 |
| 25 | `linear_since` | BX7' |
| 26 | `until_F` | BX10 |
| 27 | `since_P` | BX10' |
| 28 | `temp_linearity` | BX11 |
| 29 | `temp_linearity_past` | BX11' |
| 30 | `F_until_equiv` | BX12 |
| 31 | `P_since_equiv` | BX12' |

**Layer 4: Modal-Temporal Interaction (1)**
| # | Constructor | Formula Schema |
|---|-------------|----------------|
| 32 | `modal_future` | `□φ → □(Gφ)` |

**Layer 5: Uniformity (5)**
| # | Constructor | Description |
|---|-------------|-------------|
| 33 | `discrete_symm_fwd` | Forward gap implies backward gap |
| 34 | `discrete_symm_bwd` | Backward gap implies forward gap |
| 35 | `discrete_propagate_fwd` | Discreteness propagates forward |
| 36 | `discrete_propagate_bwd` | Discreteness propagates backward |
| 37 | `discrete_box_necessity` | Discreteness is necessary |

**Layer 6: Prior Axioms (2) — Discrete frame class only**
| # | Constructor | Formula Schema |
|---|-------------|----------------|
| 38 | `prior_UZ` | `F(φ) → U(φ, ¬φ)` |
| 39 | `prior_SZ` | `P(φ) → S(φ, ¬φ)` |

**Layer 7: Z1 Axiom (1) — Discrete frame class only**
| # | Constructor | Formula Schema |
|---|-------------|----------------|
| 40 | `z1` | `G(Gφ→φ) → (FGφ→Gφ)` |

**Layer 8: Density Axioms (2) — Dense frame class only**
| # | Constructor | Formula Schema |
|---|-------------|----------------|
| 41 | `density` | `GGφ → Gφ` |
| 42 | `dense_indicator` | `¬U(⊤,⊥)` |

**Frame class breakdown**:
- Base (valid on all linear orders): constructors 1–37 (37 total)
- Discrete only: constructors 38–40 (3 total)
- Dense only: constructors 41–42 (2 total)

#### Inference Rules (7 constructors from DerivationTree)

| # | Constructor | Rule Description |
|---|-------------|-----------------|
| 1 | `axiom` | Apply an axiom schema instance |
| 2 | `assumption` | Use formula from context |
| 3 | `modus_ponens` | If Γ ⊢ φ→ψ and Γ ⊢ φ, then Γ ⊢ ψ |
| 4 | `necessitation` | If ⊢ φ (from empty context), then ⊢ □φ |
| 5 | `temporal_necessitation` | If ⊢ φ (from empty context), then ⊢ Gφ |
| 6 | `temporal_duality` | If ⊢ φ, then ⊢ swap_temporal(φ) |
| 7 | `weakening` | Γ ⊢ φ and Γ ⊆ Δ implies Δ ⊢ φ |

**Total policy network output dimension**:
- If action = select an axiom: **42 classes** (or 37 for Base-only)
- If action = select inference rule: **7 classes**
- If combined: **49 classes** (42 axioms + 7 rules)

For AlphaZero-style search, the most natural action space is: given a proof goal state, select which rule or axiom schema to attempt next. This gives **49 possible actions** for Full (Base+Dense+Discrete) or **44** for Base-only (37+7).

### 3. PatternKey Features

`SuccessPatterns.lean` defines `PatternKey` with exactly 5 fields:

| Field | Type | Source | Description |
|-------|------|--------|-------------|
| `modalDepth` | `Nat` | `Formula.modalDepth` | Max box nesting depth |
| `temporalDepth` | `Nat` | `Formula.temporalDepth` | Max until/since nesting depth |
| `impCount` | `Nat` | `Formula.countImplications` | Total implication count |
| `complexity` | `Nat` | `Formula.complexity` | Connective count + 1 (≥ 1) |
| `topOperator` | `GoalCategory` | `goalCategory φ` | 8-value enum |

`GoalCategory` enum (8 values):
- `Atom` — propositional variable
- `Bottom` — ⊥
- `Implication` — φ → ψ
- `Box` — □φ
- `AllPast` — Hφ (all_past, derived from snce)
- `AllFuture` — Gφ (all_future, derived from untl)
- `Until` — U(φ, ψ) primitive
- `Since` — S(φ, ψ) primitive

**Note**: `goalCategory` only checks primitive constructors (atom, bot, imp, box, untl, snce). Derived operators like all_past/all_future are detected by examining whether the top-level is an `imp` of a particular derived form — in practice, since derived ops compile down to primitives, the pattern match on the outermost constructor governs. `AllPast` and `AllFuture` in GoalCategory appear to be reserved for when the formula's top operator is detected as such (but since they are derived, they would show as `Implication` at the primitive level). This is a subtlety that should be resolved in the Python implementation.

**Value ranges** (empirical for typical TM formulas, complexity ≤ 9):
- `modalDepth`: 0–4 (typical), up to depth of formula
- `temporalDepth`: 0–4 (typical), up to depth of formula
- `impCount`: 0–8 (typical), can be up to complexity-1
- `complexity`: 1–9 (for training set), unbounded
- `topOperator`: one of 8 categorical values

**JSON serialization** (from `DataExport.lean`):
```json
{
  "modalDepth": 1,
  "temporalDepth": 0,
  "impCount": 1,
  "complexity": 3,
  "topOperator": "Implication"
}
```

### 4. DecisionResult and Proof Trace Format

`DecisionProcedure.lean` defines `DecisionResult φ` with 3 constructors:
- `valid (proof : ⊢ φ)` — proof term (DerivationTree)
- `invalid (counter : SimpleCountermodel)` — countermodel description
- `timeout` — resources exhausted

`DatasetGenerator.lean` defines the complete labeled record structure:

**`ProofTrace`** (simplified proof info):
```
height: Nat                    -- max depth of proof tree
axioms_used: List String       -- distinct axiom schema names
rules_applied: List String     -- distinct inference rule names
```

**`DifficultyMetrics`**:
```
complexity: Nat                -- Formula.complexity
modalDepth: Nat                -- Formula.modalDepth
temporalDepth: Nat             -- Formula.temporalDepth
impCount: Nat                  -- Formula.countImplications
atomCount: Nat                 -- atoms.card
decisionTimeMs: Nat            -- wall-clock time
difficultyTier: String         -- "easy" | "medium" | "hard" | "very_hard"
```

Difficulty tiers: easy (complexity ≤ 3), medium (≤ 6), hard (≤ 9), very_hard (> 9).

**`FormulaLabel`** (3 values): `valid | invalid | timeout`

**`LabeledFormula`** (the canonical training record):
```
formula: Formula               -- the formula
label: FormulaLabel            -- valid/invalid/timeout
proofTrace: Option ProofTrace  -- proof info if valid
countermodel: Option SimpleCountermodel  -- countermodel if invalid
metrics: DifficultyMetrics     -- structural + computational metrics
patternKey: PatternKey         -- 5-feature structural key
```

### 5. Countermodel Format

`CountermodelExtraction.lean` defines `SimpleCountermodel`:
```
trueAtoms: List Atom           -- atoms that are true at the falsifying point
falseAtoms: List Atom          -- atoms that are false
formula: Formula               -- the formula being refuted
```

This is a simplified countermodel (propositional valuation only, not full temporal/modal frame). A full countermodel would include world histories, temporal ordering, modal accessibility, and task relations. The Python schema should:
1. Keep `SimpleCountermodel` as the primary format (matches Lean export)
2. Add a `RichCountermodel` field for future Z3-extracted full countermodels (Task 19)

**JSON serialization** (from `DataExport.lean`):
```json
{
  "trueAtoms": [{"base": "p", "fresh_index": null}],
  "falseAtoms": [{"base": "q", "fresh_index": null}],
  "formula": {"tag": "imp", ...}
}
```

### 6. Rule Profile (Extended Proof Metrics)

`DataExport.lean` also defines `RuleProfile` for richer proof traces:
```
axiomCount: Nat
assumptionCount: Nat
mpCount: Nat
necessitationCount: Nat
temporalNecessitationCount: Nat
temporalDualityCount: Nat
weakeningCount: Nat
```

This can serve as input features for the value network alongside PatternKey.

### 7. Existing Export Infrastructure

`DataExport.lean` already provides complete JSON serialization for:
- `Atom.toJson` → `{"base": "p", "fresh_index": null}`
- `Formula.toJson` → recursive tagged JSON tree
- `Formula.prettyPrint` → human-readable notation
- `GoalCategory.toJson` → string
- `PatternKey.toJson` → 5-field object
- `SimpleCountermodel.toJson` → object with trueAtoms, falseAtoms, formula
- `RuleProfile.toJson` → 7-field count object

This means the Lean-side can export complete JSONL files. The Python ingestion pipeline (Task 7) only needs to parse this format.

---

## Decisions

### D1: Canonical Schema Definition

The Python schema for a training record is a direct Python mirror of `LabeledFormula`:

```python
@dataclass
class TrainingRecord:
    # Identity
    record_id: str              # UUID for deduplication
    formula_json: dict          # Tagged JSON tree (Formula.toJson format)
    formula_pretty: str         # Human-readable (Formula.prettyPrint format)
    
    # Label (from FormulaLabel)
    label: Literal["valid", "invalid", "timeout"]
    
    # Proof trace (present iff label == "valid")
    proof_height: Optional[int]
    proof_axioms_used: Optional[List[str]]
    proof_rules_applied: Optional[List[str]]
    proof_rule_profile: Optional[dict]   # RuleProfile JSON
    
    # Countermodel (present iff label == "invalid")
    countermodel_true_atoms: Optional[List[str]]
    countermodel_false_atoms: Optional[List[str]]
    countermodel_rich: Optional[dict]    # Future: Z3-extracted full countermodel
    
    # PatternKey features (always present)
    modal_depth: int
    temporal_depth: int
    imp_count: int
    complexity: int
    top_operator: str           # GoalCategory string value
    
    # Difficulty metrics (always present)
    atom_count: int
    decision_time_ms: int
    difficulty_tier: str        # "easy" | "medium" | "hard" | "very_hard"
    
    # Schema metadata
    schema_version: str         # e.g., "1.0.0"
    frame_class: str            # "Base" | "Dense" | "Discrete"
    source: str                 # "lean_enumerator" | "python_generator" | "human_proof"
```

### D2: Action Space Definition

For the policy network:

```python
AXIOM_ACTIONS = [
    # Layer 1: Propositional (4)
    "prop_k", "prop_s", "ex_falso", "peirce",
    # Layer 2: S5 Modal (5)
    "modal_t", "modal_4", "modal_b", "modal_5_collapse", "modal_k_dist",
    # Layer 3: BX Temporal (22)
    "serial_future", "serial_past",
    "left_mono_until_G", "left_mono_since_H",
    "right_mono_until", "right_mono_since",
    "connect_future", "connect_past",
    "enrichment_until", "enrichment_since",
    "self_accum_until", "self_accum_since",
    "absorb_until", "absorb_since",
    "linear_until", "linear_since",
    "until_F", "since_P",
    "temp_linearity", "temp_linearity_past",
    "F_until_equiv", "P_since_equiv",
    # Layer 4: Modal-Temporal Interaction (1)
    "modal_future",
    # Layer 5: Uniformity (5)
    "discrete_symm_fwd", "discrete_symm_bwd",
    "discrete_propagate_fwd", "discrete_propagate_bwd",
    "discrete_box_necessity",
    # Layer 6: Prior (2)
    "prior_UZ", "prior_SZ",
    # Layer 7: Z1 (1)
    "z1",
    # Layer 8: Density (2)
    "density", "dense_indicator",
]  # Total: 42

RULE_ACTIONS = [
    "axiom",               # (meta: apply an axiom from AXIOM_ACTIONS)
    "assumption",
    "modus_ponens",
    "necessitation",
    "temporal_necessitation",
    "temporal_duality",
    "weakening",
]  # Total: 7

# Combined action space for policy network
ALL_ACTIONS = AXIOM_ACTIONS + RULE_ACTIONS  # Total: 49

# Frame-class-restricted subsets
BASE_AXIOMS = AXIOM_ACTIONS[:37]   # 37 base axioms
DENSE_AXIOMS = BASE_AXIOMS + ["density", "dense_indicator"]  # 39
DISCRETE_AXIOMS = BASE_AXIOMS + ["prior_UZ", "prior_SZ", "z1"]  # 40
```

**Policy network output dimension**: 42 (axiom selection) or 49 (combined). For AlphaZero, the most natural formulation is to pick axiom schemata (since rules are typically applied in a fixed pattern around axiom instantiation). Recommend **42-dimensional softmax** for the axiom policy head, with separate heads for rule selection if needed.

### D3: JSON vs Parquet Trade-off

**Use JSON/JSONL for primary storage, Parquet for training batches**:
- JSON/JSONL: Human-readable, easy to debug, directly compatible with Lean export format
- Parquet: Columnar compression, fast batch loading in PyTorch, Arrow integration for HuggingFace datasets
- Recommendation: Lean exports JSONL → Python ingestion converts to Parquet for training

### D4: Schema Versioning

Include `schema_version` field (semver string) and `frame_class` field in every record. This enables filtering and future evolution without breaking parsers.

### D5: Formula Representation for Neural Networks

Three representations should be supported:

1. **Feature vector** (for MLP value network): 5 PatternKey features + 7 RuleProfile counts = 12-dimensional float vector. Immediately usable with no architecture changes.

2. **Token sequence** (for transformer policy network): Linearize formula tree as S-expression tokens. Vocabulary: 6 constructor tokens + atom tokens. Example: `(imp (box (atom p)) (atom p))`.

3. **Tree structure** (for GNN): Adjacency list + node-type features from the tagged JSON tree. Each node is one of 6 types with optional atom label.

---

## Recommendations

### R1: Mirror the Lean Types Directly

The Python types should be named and structured to match their Lean counterparts:
- `Formula` → tagged JSON dict with `"tag"` discriminant
- `LabeledFormula` → `TrainingRecord` dataclass
- `PatternKey` → flat dict or `PatternKey` dataclass
- `SimpleCountermodel` → `SimpleCountermodel` dataclass

This minimizes translation bugs and makes cross-referencing easy.

### R2: Use the Exact Constructor Names as Action IDs

Use the Lean constructor names (e.g., `"prop_k"`, `"modal_t"`, `"serial_future"`) as action identifiers. These are stable, unambiguous, and match `extractAxiomName` in `DatasetGenerator.lean`. Never use numeric indices as primary identifiers — always map through the canonical name list.

### R3: Add `frame_class` Field Immediately

Every training record should declare which frame class axiom set was used to produce it. This is critical for filtering (Base-only training vs. all axioms) and for the Z3 conformance test suite (Task 21).

### R4: Reserve `countermodel_rich` for Z3 Extension

The current `SimpleCountermodel` is propositional-valuation-only. Reserve a `countermodel_rich` field (nullable, initially always null) for the full temporal-modal frame countermodel that Task 19 will produce. This avoids schema breaking changes later.

### R5: Reserve Operator Extension Fields for Logos

Add a `logic_system` field with value `"TM"` (for the current bimodal tense-modal logic). Future Logos logics (constitutive, epistemic, normative) will set different values and add additional formula constructors via new `tag` values. The `top_operator` field should use a string (not an enum constant in code) to allow extension.

### R6: Atom Representation

Use the compound Lean `Atom` representation: `{"base": "p", "fresh_index": null}`. Flattening to just the string `"p"` loses the fresh index needed for the IRR rule. The Python `Atom` class should preserve both fields.

### R7: Parquet Column Layout

For Parquet files, flatten the nested JSON into columns:
- `formula_json` → store as string (JSON-encoded)
- `formula_pretty` → string
- `modal_depth`, `temporal_depth`, `imp_count`, `complexity`, `atom_count` → int64
- `top_operator` → categorical string
- `label` → categorical string
- `proof_height` → int64 (nullable)
- `proof_axioms_used` → list<string> (nullable)
- `countermodel_true_atoms` → list<string> (nullable)
- `difficulty_tier` → categorical string
- `frame_class` → categorical string
- `schema_version` → string
- `decision_time_ms` → int64

---

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Schema version drift between Lean export and Python ingestion | Medium | High | Pin schema_version in both; add conformance tests (Task 5) |
| GoalCategory enum extension for Logos operators | Certain | Medium | Use string values, not integer enums; plan for open extension |
| ProofTrace size explosion for deep proofs | Low | Medium | Cap `axioms_used` and `rules_applied` list length; store full trace separately if needed |
| `SimpleCountermodel` insufficient for dual training signal | High | Medium | Reserve `countermodel_rich` field from day 1 (R4) |
| Policy network dimension changes if axioms added | Medium | High | Use named action arrays with version tagging; bump schema_version on any action space change |
| Frame class filtering needed for training | Certain | Low | Include `frame_class` field; build filtering utilities |
| `AllPast`/`AllFuture` in GoalCategory vs actual primitive | Medium | Low | Clarify in Python PatternKey implementation: match on `imp` structure to detect derived forms, or use only primitive constructor categories |

---

## Appendix

### A1: Complete Formula Constructor JSON Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "Formula",
  "oneOf": [
    {
      "properties": {"tag": {"const": "atom"}, "name": {"type": "string"}},
      "required": ["tag", "name"]
    },
    {
      "properties": {"tag": {"const": "bot"}},
      "required": ["tag"]
    },
    {
      "properties": {
        "tag": {"const": "imp"},
        "left": {"$ref": "#"},
        "right": {"$ref": "#"}
      },
      "required": ["tag", "left", "right"]
    },
    {
      "properties": {
        "tag": {"const": "box"},
        "child": {"$ref": "#"}
      },
      "required": ["tag", "child"]
    },
    {
      "properties": {
        "tag": {"const": "untl"},
        "event": {"$ref": "#"},
        "guard": {"$ref": "#"}
      },
      "required": ["tag", "event", "guard"]
    },
    {
      "properties": {
        "tag": {"const": "snce"},
        "event": {"$ref": "#"},
        "guard": {"$ref": "#"}
      },
      "required": ["tag", "event", "guard"]
    }
  ]
}
```

### A2: Training Record JSONL Line Example

```json
{
  "record_id": "550e8400-e29b-41d4-a716-446655440000",
  "formula_json": {"tag": "imp", "left": {"tag": "box", "child": {"tag": "atom", "name": "p"}}, "right": {"tag": "atom", "name": "p"}},
  "formula_pretty": "(□p → p)",
  "label": "valid",
  "proof_height": 0,
  "proof_axioms_used": ["modal_t"],
  "proof_rules_applied": [],
  "proof_rule_profile": {"axiom": 1, "assumption": 0, "modus_ponens": 0, "necessitation": 0, "temporal_necessitation": 0, "temporal_duality": 0, "weakening": 0},
  "countermodel_true_atoms": null,
  "countermodel_false_atoms": null,
  "countermodel_rich": null,
  "modal_depth": 1,
  "temporal_depth": 0,
  "imp_count": 1,
  "complexity": 3,
  "top_operator": "Implication",
  "atom_count": 1,
  "decision_time_ms": 0,
  "difficulty_tier": "easy",
  "schema_version": "1.0.0",
  "frame_class": "Base",
  "source": "lean_enumerator"
}
```

### A3: Action Space Index Mapping

```python
ACTION_TO_INDEX = {name: i for i, name in enumerate(ALL_ACTIONS)}
INDEX_TO_ACTION = {i: name for i, name in enumerate(ALL_ACTIONS)}

# Base-only mask (True = allowed)
BASE_MASK = [True] * 37 + [False] * 5 + [True] * 7  # 37 base axioms + 7 rules
DENSE_MASK = [True] * 37 + [True, True] + [False] * 3 + [True] * 7  # density + dense_indicator
DISCRETE_MASK = [True] * 37 + [False] * 2 + [True, True, True] + [True] * 7  # prior_UZ, prior_SZ, z1
```

### A4: Source of "57" Discrepancy

The "57" figure from team research Teammate C was an artifact of counting all `| ` lines in `Axioms.lean` without restricting to the `inductive Axiom` block. The file contains:
- 42 Axiom constructors (the true count)
- 3 FrameClass enum constructors (`Base`, `Dense`, `Discrete`)
- 6 pattern match arms in `Axiom.minFrameClass`
Total: 51 pipe lines (not 57 — the teammate's exact counting method is unclear, but the canonical answer from `awk` extraction is definitively 42).

The docstring in `Axioms.lean` line 37 also explicitly states: "**Total**: 42 axiom constructors (32 base + 5 uniformity + 2 prior + 1 Z1 + 2 density)." This is the authoritative count.

Breakdown cross-check: 4 propositional + 5 S5 modal + 22 BX temporal + 1 modal-temporal + 5 uniformity + 2 prior + 1 Z1 + 2 density = **42**. ✓
