# Research Report: Task #3

**Task**: 3 - Design cross-repo integration architecture
**Started**: 2026-05-29T00:00:00Z
**Completed**: 2026-05-29T00:30:00Z
**Effort**: S (estimated 2-4 hours, actual ~1 hour)
**Dependencies**: None
**Sources/Inputs**:
- `/home/benjamin/Projects/BimodalLogic/` — direct codebase inspection
- `/home/benjamin/Projects/BimodalLogic/lakefile.lean` — dependency declarations
- `/home/benjamin/Projects/BimodalLogic/lean-toolchain` — version pinning
- `/home/benjamin/Projects/BimodalLogic/Theories/Bimodal/Automation/DataExport.lean` — JSON serialization
- `/home/benjamin/Projects/BimodalLogic/Theories/Bimodal/Automation/DatasetGenerator.lean` — labeling pipeline
- `/home/benjamin/Projects/BimodalLogic/Theories/Bimodal/Automation/FormulaEnumerator.lean` — formula generation
- `/home/benjamin/Projects/BimodalLogic/Theories/Bimodal/Metalogic/Decidability/DecisionProcedure.lean` — decision types
- `/home/benjamin/Projects/BimodalLogic/Theories/Bimodal/Metalogic/Decidability/CountermodelExtraction.lean` — countermodel types
- `/home/benjamin/Projects/BimodalLogic/specs/203_formula_enumerator_dataset_export/plans/01_formula-enum-dataset.md` — prior implementation plan
- `/home/benjamin/Projects/Logos/ModelChecker/code/src/model_checker/theory_lib/bimodal/` — Python/Z3 bimodal implementation
- `/home/benjamin/Projects/Logos/ModelChecker/code/pyproject.toml` — ModelChecker Python config
- `specs/001_implement_alphazero_proof_search_training_harness/reports/01_team-research.md` — prior team research
- `specs/002_initialize_python_project_structure/.return-meta.json` — Python project setup findings
- `specs/TODO.md` — full task list for dependency mapping
**Artifacts**:
- `specs/003_design_cross_repo_integration_architecture/reports/01_cross-repo-design.md` (this file)

---

## Executive Summary

- **Recommended architecture**: Artifact-only integration. BimodalLogic exports JSONL/Parquet data files; BimodalHarness reads them as static files with no live repo link. No git submodule, no Python package dependency.
- **Export infrastructure already exists**: BimodalLogic has `DataExport.lean`, `DatasetGenerator.lean`, and `FormulaEnumerator.lean` fully implemented with JSON serialization for Formula, PatternKey, SimpleCountermodel, RuleProfile, and LabeledFormula types. A compiled Lake executable target (`lake exe dataset_generator`) is planned in BimodalLogic task 203.
- **ModelChecker role**: The Z3/Python bimodal countermodel checker (in `Logos/ModelChecker`) can serve as a Tier 2 corrective signal source, parsing formula ASTs from Lean-exported JSON and producing richer countermodels than the Lean tableau method. It is a separate dependency (installed as a pip package) rather than a git submodule.
- **Version pinning**: BimodalLogic uses `leanprover/lean4:v4.27.0-rc1` + Mathlib `v4.27.0-rc1`. BimodalHarness is Python-only and has no Lean toolchain dependency. Version compatibility for bridge tools (LeanDojo-v2, lean-interact v0.11) is a separate risk gate addressed by Task 6.

---

## Context & Scope

BimodalHarness is an AlphaZero-style proof search ML training harness. It trains neural networks to guide proof search in TM bimodal logic. The project depends on two external repositories:

1. **BimodalLogic** (`/home/benjamin/Projects/BimodalLogic/`) — Lean 4 formalization of TM bimodal logic. Contains the syntax, proof system, decision procedure, and automation modules that generate training data.

2. **ModelChecker** (`/home/benjamin/Projects/Logos/ModelChecker/`) — Python/Z3 countermodel checker for bimodal logic. Provides the `BimodalSemantics`, `BimodalProposition`, `BimodalStructure` classes. Published as the `model-checker` pip package.

BimodalHarness itself is currently an empty Python project. The question is how to structure the relationships between these three codebases.

The scope of this research is: decide the coupling mechanism, define the data boundary, document version compatibility, and specify the data exchange format.

---

## Findings

### Codebase Patterns

#### BimodalLogic: Export Infrastructure Already Implemented

BimodalLogic has a complete data export stack already built:

**`Theories/Bimodal/Automation/DataExport.lean`** — JSON serialization:
- `Formula.toJson` — recursive JSON for the 6 constructors: `atom`, `bot`, `imp`, `box`, `untl`, `snce`
- `PatternKey.toJson` — 5-field feature vector: `modalDepth`, `temporalDepth`, `impCount`, `complexity`, `topOperator`
- `SimpleCountermodel.toJson` — countermodel with `trueAtoms`, `falseAtoms`, `formula`
- `RuleProfile.toJson` — 7 rule application counts from derivation tree walks
- `proofMetricsToJson` — combined `height + rules` as JSON object

**`Theories/Bimodal/Automation/DatasetGenerator.lean`** — labeled records:
- `LabeledFormula` struct: `formula`, `label` (valid/invalid/timeout), `proofTrace?`, `countermodel?`, `metrics` (DifficultyMetrics), `patternKey`
- `labelFormula : Formula -> IO LabeledFormula` — runs `decideAuto`, extracts proof traces and countermodels
- `labelBatch` — processes lists with progress reporting

**`Theories/Bimodal/Automation/FormulaEnumerator.lean`** — formula generation:
- `EnumParams` struct with `maxComplexity`, `maxModalDepth`, `maxTemporalDepth`, `atoms`, `maxFormulas`, `samplingMode`
- Exhaustive enumeration at complexity <= 7 (~60K formulas)
- Grammar-based random sampling above complexity 7

**`Theories/Bimodal/Metalogic/Decidability/DecisionProcedure.lean`** — decision output:
- `DecisionResult φ`: inductive type with `.valid proof`, `.invalid countermodel`, `.timeout`
- `decide φ searchDepth tableauFuel` — main decision function
- `decideBatch : List Formula -> BatchDecisionResult` — batch processing

The BimodalLogic task 203 plan explicitly calls for a `lake exe dataset_generator` compiled executable that streams JSONL to stdout. The boundary is precisely stated: "the JSONL file — everything upstream is pure Lean in this repo."

#### Formula JSON Schema (Defined in DataExport.lean)

```json
{
  "tag": "imp",
  "left": {"tag": "box", "child": {"tag": "atom", "name": "p"}},
  "right": {"tag": "untl",
            "event": {"tag": "atom", "name": "q"},
            "guard": {"tag": "atom", "name": "r"}}
}
```

Primitive tags: `"atom"`, `"bot"`, `"imp"`, `"box"`, `"untl"`, `"snce"`

#### ModelChecker: Python Package Structure

ModelChecker is published as `model-checker` on PyPI, version `1.2.12`. It requires:
- Python >= 3.8
- z3-solver >= 4.8.0
- networkx >= 2.0

The bimodal theory lives at `model_checker.theory_lib.bimodal` and exposes:
- `BimodalSemantics(settings)` — configures semantic framework (N world-states, M time points)
- `BimodalProposition(formula, model)` — evaluates formulas
- `BimodalStructure(semantics)` — manages world histories
- `bimodal_operators` — operator definitions

The `BimodalSemantics.DEFAULT_EXAMPLE_SETTINGS` uses `N: 2` (world states), `M: 2` (time points), with Z3 BitVec encoding. This is a different approach than the Lean tableau countermodel — it produces a full semantic model (world arrays, time intervals, task relations) rather than just atom truth assignments.

#### BimodalHarness: Currently Empty

BimodalHarness (`/home/benjamin/Projects/BimodalHarness/`) contains only:
- `README.md` (1 line, empty)
- `specs/` directory with full task management infrastructure

The Python project structure has not yet been initialized (Task 2 is in RESEARCHING status). The prior research for Task 2 recommends: hatchling build backend, `src/bimodal_harness` layout, PyTorch 2.12, z3-solver 4.16, lean-interact 0.11, with dependency groups (core/dev/gpu/lean).

#### Version Compatibility Matrix

| Component | Version | Notes |
|-----------|---------|-------|
| BimodalLogic Lean | `v4.27.0-rc1` | Locked in `lean-toolchain` |
| BimodalLogic Mathlib | `v4.27.0-rc1` | Locked in `lakefile.lean` |
| ModelChecker Python | `>= 3.8` | Published as pip package `model-checker==1.2.12` |
| ModelChecker Z3 | `>= 4.8.0` | Core dependency |
| lean-interact | `0.11` | REPL bridge candidate (Task 6 validates) |
| LeanDojo-v2 | unknown | May not support Lean v4.27.0-rc1 (Task 6 risk gate) |
| PyPantograph | unknown | Alternative bridge candidate |

### External Resources

The task list (TODO.md) reveals the intended data flow architecture:

- **Task 5** (Coordinate BimodalLogic exports): "Define what BimodalLogic needs to export (formulas, DecisionResults, proof traces, countermodels). Specify JSON/Parquet export format matching training data schema. Set up data sync pipeline between repos."
- **Task 7** (Static data ingestion): "Create pipeline to import pre-exported datasets from Lean (formula enumerator output, DecisionResult, countermodels). Produce PyTorch-compatible datasets."
- **Task 19** (Z3 countermodel generator): "Implement Python/Z3 module parsing formula ASTs from Lean-exported JSON, constructing Z3 constraints matching ProofChecker semantics."

This confirms the artifact-only architecture: Lean produces JSONL/Parquet, Python reads it, no live repo coupling.

---

## Decisions

### Decision 1: Artifact-Only Integration (ADOPTED)

**Chosen approach**: BimodalLogic exports data files (JSONL/Parquet); BimodalHarness reads them as static training data. No git submodule, no shared runtime dependency.

**Reasoning**:
- BimodalLogic is a Lean 4 project; BimodalHarness is Python-only. There is no runtime interop without a bridge tool (lean-interact, LeanDojo) which is a separate dependency layer.
- The export infrastructure already exists in BimodalLogic (`DataExport.lean`, `DatasetGenerator.lean`, `FormulaEnumerator.lean`).
- Git submodules add CI/CD complexity (nested `lake build` calls on top of Python CI) for no benefit if the interface is purely file-based.
- Artifact coupling provides clean version snapshots: a specific dataset version corresponds to a specific BimodalLogic commit, and the Harness can pin a dataset version without tracking the Lean source.
- This pattern is standard in ML: the data preprocessing stage runs offline; training reads static files.

**Rejected alternatives**:
- **Git submodule**: Would require the Python CI to have Lean toolchain installed and run `lake build`. No benefit since we only need exported files, not Lean source at runtime.
- **Path-based config**: Fragile (machine-specific), breaks CI, requires both repos checked out. Only viable during development; not suitable as the primary coupling mechanism.
- **Python package (BimodalLogic)**: Lean does not publish Python packages. This would require a separate packaging step beyond JSONL export.

### Decision 2: ModelChecker as pip Dependency (ADOPTED)

**Chosen approach**: ModelChecker is consumed as a pip package (`model-checker`) in BimodalHarness, not as a git submodule or path reference.

**Reasoning**:
- ModelChecker is already published on PyPI (`model-checker==1.2.12`).
- The bimodal theory module (`model_checker.theory_lib.bimodal`) provides the `BimodalSemantics`, `BimodalStructure`, `BimodalProposition` classes needed for Tier 2 countermodel generation (Task 19).
- Version pinning is straightforward: `model-checker==1.2.12` in `pyproject.toml`.
- No live checkout or path manipulation needed.

**Note**: Task 19 says "Implement Python/Z3 module parsing formula ASTs from Lean-exported JSON, constructing Z3 constraints matching ProofChecker semantics." This module may largely reuse or wrap the existing ModelChecker bimodal semantics code rather than reimplementing from scratch.

### Decision 3: JSONL as Primary Export Format (ADOPTED)

**Chosen approach**: BimodalLogic exports JSONL (newline-delimited JSON) as the primary format. Parquet is a secondary option for large datasets.

**Reasoning**:
- JSONL is streamable (each line is one record), human-readable, debuggable, and supported natively by HuggingFace `datasets`.
- BimodalLogic's `DataExport.lean` already produces JSON strings via string concatenation (no external library).
- The BimodalLogic task 203 plan explicitly targets JSONL streaming from a compiled executable.
- For datasets exceeding ~1GB, Parquet provides 5-10x compression and columnar query speed; Task 22 (training data export pipeline) specifically mentions Parquet for production export.
- The transition from JSONL to Parquet is handled in Python (pandas/pyarrow), not in Lean.

### Decision 4: Lean v4.27.0-rc1 is a BimodalLogic-Only Concern (ADOPTED)

**Chosen approach**: BimodalHarness has no Lean toolchain dependency for its core training pipeline. Lean version compatibility is relevant only if a live bridge (lean-interact, LeanDojo) is used for online proof search (Tasks 6, 9, 13).

**Reasoning**:
- The static data pipeline (Tasks 7-12) operates entirely on exported JSONL files with no Lean at runtime.
- The live bridge (needed for Tasks 9, 13, 16, 17) is gated on Task 6 (bridge validation), which will determine which tool (lean-interact 0.11, LeanDojo-v2, PyPantograph) is compatible with Lean v4.27.0-rc1.
- BimodalHarness CI/CD does not need to invoke `lake build`.

---

## Recommendations

### Recommended Architecture

```
BimodalLogic (Lean 4 repo)
  Theories/Bimodal/Automation/
    FormulaEnumerator.lean      <- generate formulas
    DatasetGenerator.lean       <- label with decide()
    DataExport.lean             <- serialize to JSON
  [lake exe dataset_generator]  <- compiled binary
  [output: data/]
    formulas_complexity5.jsonl
    formulas_complexity7.jsonl
    benchmark_500.jsonl
        |
        | (file copy / git release / rsync)
        v
BimodalHarness (Python repo)
  data/
    bimodal_formulas_v0.1.jsonl  <- static snapshot
    benchmark_v0.1.jsonl
  src/bimodal_harness/
    data/
      loader.py                  <- reads JSONL into PyTorch datasets
      schema.py                  <- dataclass definitions matching JSON schema
    models/
      value_net.py
      policy_net.py
    search/
      mcts.py
    verification/
      z3_countermodel.py         <- wraps ModelChecker bimodal theory

ModelChecker (separate pip package: model-checker==1.2.12)
  model_checker.theory_lib.bimodal
    BimodalSemantics, BimodalStructure, BimodalProposition
```

### Data Sync Pattern

During development (pre-CI): use a `Makefile` or `justfile` target in BimodalHarness:

```makefile
sync-data:
    rsync -av /home/benjamin/Projects/BimodalLogic/data/ ./data/bimodal/
```

For reproducible CI: pin dataset version via a GitHub release artifact or a `data/VERSION` file specifying the BimodalLogic commit SHA that generated it.

### JSON Schema for LabeledFormula Records

Based on `DataExport.lean` and `DatasetGenerator.lean`:

```json
{
  "formula": {
    "tag": "imp",
    "left": {"tag": "box", "child": {"tag": "atom", "name": "p"}},
    "right": {"tag": "atom", "name": "q"}
  },
  "label": "valid",
  "proof_trace": {
    "height": 3,
    "axioms_used": ["modal_t", "prop_k"],
    "rules_applied": ["modus_ponens", "necessitation"]
  },
  "countermodel": null,
  "metrics": {
    "complexity": 4,
    "modal_depth": 1,
    "temporal_depth": 0,
    "imp_count": 1,
    "atom_count": 2,
    "decision_time_ms": 12,
    "difficulty_tier": "easy"
  },
  "pattern_key": {
    "modalDepth": 1,
    "temporalDepth": 0,
    "impCount": 1,
    "complexity": 4,
    "topOperator": "Implication"
  }
}
```

For invalid formulas, `"countermodel"` contains:
```json
{
  "trueAtoms": [{"base": "p", "fresh_index": null}],
  "falseAtoms": [{"base": "q", "fresh_index": null}],
  "formula": {...}
}
```

### Python Schema Module

`src/bimodal_harness/data/schema.py` should define dataclasses matching this schema for type-safe loading. The `label` field should be an `Enum` with values `VALID`, `INVALID`, `TIMEOUT`. The `formula` field should be a recursive `FormulaNode` dataclass matching the JSON tag structure.

### Integration Points by Task

| Task | Coupling Required | Notes |
|------|-------------------|-------|
| Task 4 (schema) | None | Defines schema that matches Lean JSON |
| Task 5 (export coordination) | Coordinate with BimodalLogic task 203 | Specify JSONL format jointly |
| Task 7 (static ingestion) | File-based | Read JSONL, produce PyTorch Dataset |
| Task 8 (Python formula gen) | None | Python reimplements formula grammar |
| Task 9 (proof trace extraction) | Live bridge (lean-interact or LeanDojo) | Gated on Task 6 |
| Task 10 (PatternKey extractor) | Schema only | Port PatternKey formula from Lean |
| Task 11 (value network) | None | PyTorch, uses PatternKey features |
| Task 12 (benchmark) | File-based | Load benchmark JSONL |
| Task 13 (value net + search) | Live bridge | Gated on Task 6 |
| Task 19 (Z3 countermodel) | pip: model-checker | Parse Lean-exported formula JSON |

---

## Risks & Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| BimodalLogic task 203 not yet complete (no compiled exporter) | H | M | Task 5 coordinates export; data can be bootstrapped manually via `#eval` in Lean for small datasets |
| Lean-exported JSONL schema diverges from Python schema (Task 4) | M | M | Task 4 and Task 5 must be coordinated; Python schema.py is the canonical consumer contract |
| LeanDojo-v2 incompatible with Lean v4.27.0-rc1 | H | M | Task 6 is the explicit risk gate; lean-interact 0.11 is the fallback for Tasks 9, 13 |
| ModelChecker version skew (`model-checker` API changes) | M | L | Pin to `model-checker==1.2.12` in pyproject.toml; test in CI |
| SimpleCountermodel in Lean (atom-level only) insufficient for Tier 2 signal | M | M | Task 19 uses ModelChecker Z3 semantics for richer countermodels; Lean countermodel is Tier 1 approximation |
| Data files not version-controlled (JSONL excluded from git) | M | M | Use git LFS or GitHub Releases for dataset versioning; track `data/VERSION` in git |
| Large JSONL files (complexity 7: ~60K records) slow I/O at training time | L | L | Convert to Parquet via pandas/pyarrow in Task 22; or use HuggingFace datasets with memory-mapping |

---

## Appendix

### Repository Inventory

| Repo | Language | Version | Location |
|------|----------|---------|----------|
| BimodalLogic | Lean 4 | v4.27.0-rc1 | `/home/benjamin/Projects/BimodalLogic/` |
| ModelChecker | Python/Z3 | 1.2.12 | `/home/benjamin/Projects/Logos/ModelChecker/` |
| BimodalHarness | Python | (not initialized) | `/home/benjamin/Projects/BimodalHarness/` |

### Key BimodalLogic Files

| File | Purpose |
|------|---------|
| `lean-toolchain` | `leanprover/lean4:v4.27.0-rc1` |
| `lakefile.lean` | Mathlib `v4.27.0-rc1`, plausible@main; no Python targets |
| `Theories/Bimodal/Automation/DataExport.lean` | JSON serializers for Formula, PatternKey, SimpleCountermodel, RuleProfile |
| `Theories/Bimodal/Automation/DatasetGenerator.lean` | `LabeledFormula`, `labelFormula`, `labelBatch` |
| `Theories/Bimodal/Automation/FormulaEnumerator.lean` | `EnumParams`, exhaustive + random enumeration |
| `Theories/Bimodal/Metalogic/Decidability/DecisionProcedure.lean` | `DecisionResult`, `decide`, `decideBatch` |
| `Theories/Bimodal/Metalogic/Decidability/CountermodelExtraction.lean` | `SimpleCountermodel` (atom-level) |

### Operator Reference (Formula Tag to Symbol)

| JSON tag | Lean constructor | Symbol |
|----------|-----------------|--------|
| `"atom"` | `Formula.atom` | `p` |
| `"bot"` | `Formula.bot` | `⊥` |
| `"imp"` | `Formula.imp` | `→` |
| `"box"` | `Formula.box` | `□` |
| `"untl"` | `Formula.untl` | `U(φ,ψ)` |
| `"snce"` | `Formula.snce` | `S(φ,ψ)` |

### Boundary Summary

```
BimodalLogic owns:
  - Formula inductive type
  - Decision procedure (tableau + proof search)
  - ProofTrace extraction
  - SimpleCountermodel extraction
  - JSONL serialization and export executable
  - Benchmark curation (held-out 500-1K formulas)

BimodalHarness owns:
  - Python FormulaNode dataclass (mirrors Lean Formula)
  - PyTorch Dataset wrapper (reads JSONL)
  - PatternKey feature extractor (Python port)
  - Value/policy neural networks
  - MCTS search implementation
  - Z3 countermodel generator (Task 19, uses ModelChecker)
  - Training loop and experiment tracking

ModelChecker owns:
  - Full Z3 bimodal semantics (BimodalSemantics, BimodalStructure)
  - Rich countermodel extraction (world histories, task relations)
  - Published as pip package
```
