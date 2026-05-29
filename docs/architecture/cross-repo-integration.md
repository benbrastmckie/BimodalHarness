# Cross-Repository Integration Architecture

**Document version**: 1  
**Last updated**: 2026-05-29  
**Schema version**: 1 (see `data/VERSION`)

## Overview

BimodalHarness integrates with two external repositories:

1. **BimodalLogic** (Lean 4) — generates labeled formula datasets via tableau proof search
2. **ModelChecker** (Python/Z3 pip package) — provides bimodal semantics verification

The integration is **artifact-only**: BimodalHarness never directly calls Lean tooling at runtime. BimodalLogic exports JSONL files; BimodalHarness reads them as static training data.

## Architecture Diagram

```
BimodalLogic (Lean 4, Lean v4.27.0-rc1)
  ├── FormulaEnumerator.lean    — generates formula ASTs up to complexity bound
  ├── DataExport.lean           — JSON serialization for all types
  └── DatasetGenerator.lean     — entrypoint: lake exe dataset_generator
              |
              | JSONL export (one LabeledFormula per line)
              v
  BimodalLogic/data/*.jsonl
              |
              | make sync-data (rsync)
              v
  BimodalHarness/data/bimodal/*.jsonl   [NOT tracked in git]
              |
              | bimodal_harness.data.load_jsonl()
              v
  Python training pipeline
              ^
              |
  ModelChecker (pip: model-checker==1.2.12)
  ├── BimodalSemantics            — Z3-based formula evaluator
  ├── BimodalStructure            — Kripke structure constructor
  └── BimodalProposition          — formula-to-Z3-constraint compiler
```

## Architectural Boundary

### What BimodalLogic Owns

- Formula generation logic and enumeration bounds
- Tableau proof search algorithm and rule set
- JSONL serialization format and schema evolution
- `lake exe dataset_generator` build target and CLI
- Lean version and Mathlib version pinning
- Ground truth labels: VALID, INVALID, TIMEOUT

### What BimodalHarness Owns

- Python deserialization of exported JSONL (`schema.py`)
- PyTorch Dataset wrapper and DataLoader configuration (Task 7)
- Neural network architecture (MCTS policy/value networks, Tasks 8-10)
- Training loop, loss functions, curriculum scheduling
- Z3 countermodel generation for INVALID candidates (Task 19, via ModelChecker)
- Evaluation metrics and benchmarking
- Version pinning for all Python dependencies

### Shared Contract

The JSONL schema (defined below) is the integration contract. When BimodalLogic
changes its export format, the `SCHEMA_VERSION` in `data/VERSION` must be bumped,
and `src/bimodal_harness/data/schema.py` must be updated to match.

## JSONL Schema Contract

### LabeledFormula Record

Each line in a JSONL export is one JSON object:

```json
{
  "formula": <FormulaNode>,
  "label": "VALID" | "INVALID" | "TIMEOUT",
  "proof_trace": <ProofTrace> | null,
  "countermodel": <SimpleCountermodel> | null,
  "metrics": <DifficultyMetrics>,
  "pattern_key": <PatternKey>
}
```

**Field invariants**:
- `proof_trace` is non-null if and only if `label == "VALID"`
- `countermodel` is non-null if and only if `label == "INVALID"`
- `metrics` and `pattern_key` are always present

### FormulaNode (recursive)

```json
{ "tag": "atom", "name": "<string>" }
{ "tag": "bot" }
{ "tag": "imp", "left": <FormulaNode>, "right": <FormulaNode> }
{ "tag": "box", "child": <FormulaNode>, "event": <FormulaNode> }
{ "tag": "untl", "guard": <FormulaNode>, "child": <FormulaNode> }
{ "tag": "snce", "guard": <FormulaNode>, "child": <FormulaNode> }
```

### Formula Operator Reference

| JSON tag | Lean constructor | Symbol | Meaning |
|----------|-----------------|--------|---------|
| `atom`   | `.atom s`       | `p`, `q`, `r` | Propositional atom |
| `bot`    | `.bot`          | `⊥`    | Bottom (always false) |
| `imp`    | `.imp A B`      | `A → B` | Implication |
| `box`    | `.box A e`      | `[e]A`  | S4 modal box (event `e`) |
| `untl`   | `.untl P Q`     | `P U Q` | Until (LTL) |
| `snce`   | `.snce P Q`     | `P S Q` | Since (past-LTL) |

**Note**: Negation `¬A` is encoded as `A → ⊥` (i.e., `imp A bot`).  
**Note**: Diamond `⟨e⟩A` is encoded as `¬[e]¬A` (three nested nodes).

### PatternKey

```json
{
  "modal_depth": <int>,
  "temporal_depth": <int>,
  "imp_count": <int>,
  "complexity": <int>,
  "top_operator": "atom" | "bot" | "imp" | "box" | "untl" | "snce"
}
```

### SimpleCountermodel

```json
{
  "true_atoms":  ["p", "r", ...],
  "false_atoms": ["q", ...],
  "formula":     "<string representation>"
}
```

### RuleProfile

```json
{
  "imp_left":  <int>,
  "imp_right": <int>,
  "box_left":  <int>,
  "box_right": <int>,
  "untl_left": <int>,
  "untl_right": <int>,
  "snce_left": <int>
}
```

### ProofTrace

```json
{
  "height":        <int>,
  "axioms_used":   ["id", "bot", ...],
  "rules_applied": <RuleProfile>
}
```

### DifficultyMetrics

```json
{
  "complexity":        <int>,
  "modal_depth":       <int>,
  "temporal_depth":    <int>,
  "imp_count":         <int>,
  "atom_count":        <int>,
  "decision_time_ms":  <float>,
  "difficulty_tier":   1 | 2 | 3 | 4 | 5
}
```

## Version Compatibility Matrix

| Component | Version | Notes |
|-----------|---------|-------|
| Lean | v4.27.0-rc1 | BimodalLogic only; BimodalHarness has no Lean dep |
| Mathlib | matching Lean v4.27.0-rc1 | BimodalLogic only |
| Python | >= 3.12 | BimodalHarness requires 3.12+ |
| PyTorch | >= 2.12.0 | Training pipeline |
| model-checker | == 1.2.12 | Pinned; Z3-based bimodal semantics |
| z3-solver | >= 4.16.0.0 | Transitive dep of model-checker |
| datasets (HuggingFace) | >= 3.0.0 | Dataset loading/caching |
| numpy | >= 2.4.0 | Array operations |
| Schema Version | 1 | See `data/VERSION` |

**ModelChecker API surface used** (model-checker==1.2.12):
- `model_checker.theory_lib.bimodal.BimodalSemantics` — formula evaluation
- `model_checker.theory_lib.bimodal.BimodalStructure` — Kripke structure
- `model_checker.theory_lib.bimodal.BimodalProposition` — Z3 constraint encoding

## Data Sync Workflow

### Development

```bash
# Sync latest exports from local BimodalLogic checkout
make sync-data BIMODAL_LOGIC_PATH=/home/user/Projects/BimodalLogic

# Or use the default (assumes sibling directory ../BimodalLogic)
make sync-data

# Validate all JSONL files match the schema
make validate-data
```

After sync, update `data/VERSION` with the BimodalLogic Git commit hash:
```
BIMODAL_LOGIC_COMMIT=<git rev-parse HEAD in BimodalLogic>
SYNC_DATE=YYYY-MM-DD
```

### Production

For sharing large datasets across team members or CI:
- **GitHub Releases**: Attach JSONL archives as release assets (recommended for < 2 GB)
- **git LFS**: Track `data/bimodal/*.jsonl` with git LFS (for persistent versioning)
- **Cloud storage**: S3/GCS bucket with a download script

The `data/samples/` directory (synthetic fixtures, < 100 KB total) is always
tracked directly in git and available without any sync step.

## Integration Points by Downstream Task

| Task | Coupling type | Integration point |
|------|--------------|------------------|
| Task 4: Tokenizer | Schema consumer | Reads `FormulaNode` AST to build token vocabulary |
| Task 5: Text serializer | Schema consumer | Serializes `FormulaNode` to natural-language string |
| Task 7: PyTorch Dataset | JSONL consumer | Uses `load_jsonl()` over `data/bimodal/*.jsonl` |
| Task 8: Policy network | Indirect (via 7) | Consumes tensors from Task 7 Dataset |
| Task 9: Value network | Indirect (via 7) | Consumes tensors from Task 7 Dataset |
| Task 10: MCTS | Schema consumer | Uses `LabeledFormula` for proof state representation |
| Task 19: Z3 countermodel gen | ModelChecker | Uses `BimodalSemantics` to verify INVALID candidates |

**Note**: Tasks 4, 5, 7, and 10 directly import `bimodal_harness.data.schema`.
Tasks 8 and 9 consume tensors produced by Task 7 and do not import schema types.
Task 19 uses ModelChecker independently; the schema provides the formula AST input.

## Schema Evolution Policy

When BimodalLogic adds new formula tags or changes the JSON structure:

1. Bump `SCHEMA_VERSION` in `data/VERSION`
2. Update `FormulaTag` enum in `schema.py` with the new tag
3. Update `FormulaNode.from_json()` to handle the new tag
4. Add `FormulaNode.to_json()` case for the new tag
5. Update `data/samples/test_formulas.jsonl` with examples of the new tag
6. Run `pytest tests/test_schema.py` to verify round-trips
7. Update this document's operator reference table

The `FormulaTag` enum uses explicit values matching the Lean JSON tags. Adding
a new tag that is not in the enum will raise `ValueError` at load time, making
schema drift immediately visible.
