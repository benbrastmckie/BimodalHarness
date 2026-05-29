# Benchmark Design: Neural-Guided Proof Search Evaluation

**Task**: 12 - Build Evaluation Benchmark Suite
**Date**: 2026-05-29
**Status**: Research Complete

---

## 1. Infrastructure Inventory

### 1.1 Formula Generation (Task 8)

`src/bimodal_harness/formula/generator.py` provides two generation strategies:

- `enumerate_by_complexity(n, atoms)` — exhaustive enumeration at exact complexity `n`
- `enumerate_up_to_complexity(max_n, atoms)` — exhaustive up to `max_n`
- `random_formula(max_complexity, atoms, rng)` — stochastic top-down with configurable operator weights
- `count_formulas(n, num_atoms)` — closed-form count via recurrence

Formula complexity is the node count (leaves count as 1). At complexity 8 with 3 atoms the space is already large; at complexity 10+ exhaustive enumeration is impractical.

The Lean side in `FormulaEnumerator.lean` mirrors this with `EnumConfig`:

```
smallConfig: maxModalDepth=2, maxTemporalDepth=2, maxSize=8, 3 atoms
mediumConfig: maxModalDepth=3, maxTemporalDepth=3, maxSize=12, 5 atoms
```

Both support deterministic seed-based LCG sampling (`sampleFormulas`), which is essential for reproducibility.

### 1.2 Difficulty Tiers (Existing)

`DatasetGenerator.lean` `classifyDifficulty`:

| Tier | Complexity |
|------|------------|
| `easy` | ≤ 3 |
| `medium` | 4-6 |
| `hard` | 7-9 |
| `very_hard` | ≥ 10 |

`DifficultyMetrics` (`schema/records.py`) already captures: `atom_count`, `modal_depth`, `temporal_depth`, `complexity`, `decision_time_ms`, `search_depth`.

### 1.3 Schema Records

`TrainingRecord` holds all required benchmark fields:
- `formula_json`, `formula_pretty`, `label` (valid/invalid/timeout)
- `pattern_key`: 5-dimensional structural feature vector (modal_depth, temporal_depth, imp_count, complexity, top_operator)
- `proof_trace`: height (= DerivationTree.height), rule_profile, axioms_used
- `countermodel`: true_atoms, false_atoms, formula_json
- `difficulty_metrics`: full difficulty characterization
- `frame_class`: Base / Dense / Discrete

### 1.4 Action Space

49 total actions = 42 axioms + 7 inference rules. Frame-class masks already implemented in `schema/actions.py`:
- `BASE_MASK`: 44 True (37 axioms + 7 rules)
- `DENSE_MASK`: 46 True
- `DISCRETE_MASK`: 47 True

### 1.5 Evaluation Stubs

`src/bimodal_harness/evaluation/benchmark.py` — empty stub (4 lines, just `from __future__ import annotations`).
`src/bimodal_harness/evaluation/__init__.py` — empty stub.
`scripts/evaluate.py` — raises `NotImplementedError`.

These are the primary files to implement.

---

## 2. Benchmark Design

### 2.1 Formula Selection Strategy

**Target: 700 formulas** (conservatively achievable, publishable as "700-formula benchmark").

Stratification across three dimensions:

**Dimension 1: Validity label**
- 50% valid (350), 50% invalid (350)
- Ground truth from Lean `decideAuto` decision procedure
- Ensures the classifier and prover are equally challenged

**Dimension 2: Difficulty tier**

| Tier | Formula Complexity | Count | Note |
|------|-------------------|-------|------|
| easy | 1-3 | 100 | Mostly propositional/trivial modal |
| medium | 4-6 | 250 | Core bimodal logic range |
| hard | 7-9 | 250 | Deep nesting, multiple temporal ops |
| very_hard | 10-12 | 100 | Tests limits of search budget |

**Dimension 3: Frame class**
- Base (50%), Dense (25%), Discrete (25%)
- Frame class affects which axioms are valid, changing problem character

**Dimension 4: Top-level operator (GoalCategory)**
Ensure coverage across all 8 GoalCategories: Atom, Bottom, Implication, Box, AllPast, AllFuture, Until, Since.

### 2.2 Formula Selection Algorithm

```
Phase 1 (Exhaustive, easy/medium):
  - enumerate_up_to_complexity(6, ["p", "q", "r"])
  - Apply passesFilter (complexity >= 3, has modal/temporal operator)
  - Run Lean decideAuto for ground truth labels
  - Deduplicate, stratify, sample to fill easy/medium quota

Phase 2 (Sampled, hard/very_hard):
  - random_formula(max_complexity=12, atoms=["p","q","r","s","t"], rng=seeded_rng)
  - Filter: complexity in [7,12], has modal AND temporal operators
  - Run Lean decideAuto; retry timeouts with decideOptimized
  - Discard persistent timeouts; resample to fill quota

Phase 3 (Frame-class coverage):
  - For Dense/Discrete subsets: include at least 1 Dense/Discrete-specific axiom
    in the formula's derivation (for valid formulas)
  - For invalid formulas: use frame-class-specific countermodels
```

### 2.3 Held-Out Split

80/10/10 train/val/test split on training data; the **full 700 formulas are the held-out benchmark** (not used during training). Ground truth stored in JSONL with SHA-256 checksums for integrity.

### 2.4 Seed and Reproducibility

Two fixed random seeds:
- `ENUM_SEED = 42` — formula selection
- `SPLIT_SEED = 137` — for any random tie-breaking

Both must be recorded in benchmark metadata for reproducibility.

---

## 3. Metrics

### 3.1 Primary Metrics

**Success Rate (SR@K)**
- Fraction of benchmark problems solved within node budget K
- Report SR@1000, SR@5000, SR@10000 nodes
- Mirrors the standard format from LeanDojo and miniF2F benchmarks

**Nodes Visited (NV)**
- Count of proof state expansions during search
- Primary measure of search efficiency
- Report: mean, median, 90th percentile per difficulty tier
- For failed searches: record NV = budget (node limit)

**Time to Proof (TTP)**
- Wall-clock seconds from query start to proof found
- Report: mean, median, 90th percentile
- Exclude failed searches from mean (or report separately as "conditional TTP")

**Proof Length (PL)**
- `DerivationTree.height` from ProofTrace
- Number of tactic application steps
- Only defined for successful proofs

### 3.2 Secondary Metrics

**Proof Quality Score (PQS)**
Composite: `PQS = (proof_height / optimal_height) * (nodes_visited / optimal_nodes)`
- Lower is better (1.0 = optimal)
- Requires running a complete baseline searcher to establish optima

**Axiom Diversity**
- Count of distinct axiom schemas used per proof
- High diversity = more complex proof, harder to learn

**Search Tree Shape**
- Mean branching factor during search
- Measured from MCTS/best-first search statistics

### 3.3 Reporting Tables

Standard table format for TABLEAUX/CADE:

```
| System       | SR@1000 | SR@5000 | NV (med) | TTP (med) | PL (mean) |
|--------------|---------|---------|----------|-----------|-----------|
| SuccessP. BL | xx.x%   | xx.x%   | xxx      | x.xx s    | x.x       |
| Neural-BFS   | xx.x%   | xx.x%   | xxx      | x.xx s    | x.x       |
| Neural-MCTS  | xx.x%   | xx.x%   | xxx      | x.xx s    | x.x       |
```

Results must be broken down by difficulty tier (easy/medium/hard/very_hard) and frame class (Base/Dense/Discrete).

---

## 4. SuccessPatterns Baseline

### 4.1 Baseline Characterization

`SuccessPatterns.lean` implements a **heuristic memoization** approach:

**Data structure**: `PatternDatabase` — HashMap from `PatternKey` to `SuccessData`

**PatternKey** (5 fields): modal_depth, temporal_depth, imp_count, complexity, top_operator

**SuccessData** records:
- `successCount`: total successes for this pattern
- `strategyCounts`: frequency of each ProofStrategy (Axiom, Assumption, ModusPonens, ModalK, TemporalK)
- `avgDepth`: average search depth at which proof was found
- `lastSuccess`: most recent ProofInfo

**Heuristic scoring** (`heuristicBonus`):
- >80% strategy success rate: -10 priority boost (strong)
- >50%: -5 (medium)
- >20%: -2 (small)
- otherwise: 0

**Depth guidance** (`suggestedDepth`): returns `min(avgDepth * 2, defaultDepth)`

**Baseline strategy**: `ProofSearch/Core.lean` implements IDDFS, BoundedDFS, and BestFirst. From existing benchmark results in the docstring:

```
| Category              | IDDFS        | BestFirst    |
|-----------------------|--------------|--------------|
| Modal axioms (5)      | 5/5, 5 vis   | 5/5, 5 vis   |
| Temporal axioms (3)   | 3/3, 3 vis   | 3/3, 3 vis   |
| Propositional (4)     | 4/4, 4 vis   | 4/4, 4 vis   |
| Context-based (3)     | 1/3, 39 vis  | 3/3, 6 vis   |
```

BestFirst significantly outperforms IDDFS on context-based goals.

### 4.2 Python Baseline Interface

The benchmark must be able to invoke the SuccessPatterns baseline via `LeanBridge`:

```python
# Conceptual interface
def run_success_patterns_baseline(
    formula: FormulaNode,
    frame_class: FrameClass,
    budget: int = 5000,
) -> BenchmarkResult:
    """
    Returns: BenchmarkResult(
        success: bool,
        nodes_visited: int,
        time_seconds: float,
        proof_height: int | None,
        strategy: str | None
    )
    """
```

The Lean side exposes `batch_search_with_learning` for batched evaluation.

### 4.3 Baseline Limitations

The SuccessPatterns baseline is:
1. **Pattern-level only**: generalizes by (modal_depth, temporal_depth, imp_count, complexity, top_operator) — no sub-formula structure
2. **Strategy-level only**: tracks ProofStrategy enum (5 values), not specific axiom sequences
3. **Context-free**: ignores assumption set beyond contextSize count
4. **No learned embeddings**: purely count-based, no neural components

This makes it a reasonable but limited baseline that neural approaches should substantially improve on for medium/hard formulas.

---

## 5. Publication Format (TABLEAUX/CADE)

### 5.1 Benchmark Paper Conventions

Based on related work:
- **miniF2F** (Zheng et al., 2022): 488 problems from MATH competitions; reports pass@1 with GPT-f and expert-iteration baselines. Table format: system × difficulty breakdown.
- **LeanDojo** (Yang et al., 2023): 98,734 theorem-proof pairs; evaluates retrieval-augmented proving. Reports SR@60min, proof rate by file.
- **ProofWriter** (Clark et al., 2021): Rule-based QA; tiered difficulty; reports per-tier accuracy.
- **MCTS for ATP** (Lample et al., 2022): Reports SR at various expansion budgets (SR@100, SR@500, SR@10000).

For TABLEAUX/CADE audience (automated deduction conference):

**Required elements**:
1. **Benchmark description**: formula language, operators, logic system (TM bimodal logic, BX axiom system), decision procedure used for ground truth
2. **Selection methodology**: enumeration algorithm, sampling seed, stratification strategy
3. **Statistics table**: count by tier/validity/frame-class, mean complexity, modal/temporal depth distribution
4. **Baseline results**: at minimum SuccessPatterns (heuristic) and naive BFS
5. **Comparison table**: SR@K, NV, TTP per system per tier

**Optional but recommended**:
- Difficulty calibration: correlation between complexity and solve rate
- Provability ratio per frame class (Base ~50%, Dense/Discrete may differ)
- Ablation: formula complexity vs. success rate curve

### 5.2 Benchmark Artifact Specification

The benchmark should be released as:

```
bimodal-benchmark-v1.0/
├── README.md               # Benchmark description
├── benchmark.jsonl         # 700 formulas (JSONL, one per line)
├── benchmark_stats.json    # Aggregate statistics
├── checksums.sha256        # SHA-256 checksums for integrity
└── generate.py             # Reproducible generation script
```

Each JSONL entry is a `TrainingRecord`-compatible dict (existing schema) plus:
```json
{
  "benchmark_id": "bm_001",
  "ground_truth_label": "valid",
  "ground_truth_proof_height": 4,
  "ground_truth_countermodel": null,
  "difficulty_tier": "medium",
  "frame_class": "Base",
  "formula_json": {...},
  "formula_pretty": "□p → p",
  "pattern_key": {...}
}
```

### 5.3 Ethics and Reproducibility Checklist

- [ ] Fixed random seeds documented in paper and code
- [ ] Generation script included in supplementary
- [ ] Ground truth verified by Lean decision procedure (not heuristic)
- [ ] No overlap with training data (benchmark is held-out)
- [ ] Benchmark publicly released (GitHub + Zenodo DOI)

---

## 6. Implementation Roadmap for Task 12

### Phase 1: Benchmark Generator
**File**: `src/bimodal_harness/evaluation/benchmark_generator.py`

```python
@dataclass
class BenchmarkConfig:
    target_size: int = 700
    seed: int = 42
    valid_ratio: float = 0.5
    tier_distribution: dict[str, float] = field(default_factory=lambda: {
        "easy": 0.14, "medium": 0.36, "hard": 0.36, "very_hard": 0.14
    })
    frame_class_distribution: dict[str, float] = field(default_factory=lambda: {
        "Base": 0.5, "Dense": 0.25, "Discrete": 0.25
    })

class BenchmarkGenerator:
    def generate(self, config: BenchmarkConfig) -> list[BenchmarkProblem]: ...
    def save_jsonl(self, problems: list[BenchmarkProblem], path: Path) -> None: ...
    def compute_stats(self, problems: list[BenchmarkProblem]) -> dict: ...
```

### Phase 2: Metrics Collector
**File**: `src/bimodal_harness/evaluation/metrics.py`

```python
@dataclass
class SearchResult:
    problem_id: str
    success: bool
    nodes_visited: int
    time_seconds: float
    proof_height: int | None
    node_budget: int

@dataclass
class BenchmarkMetrics:
    success_rate_at_k: dict[int, float]  # {1000: 0.72, 5000: 0.85, ...}
    nodes_visited_stats: DescriptiveStats
    time_to_proof_stats: DescriptiveStats
    proof_height_stats: DescriptiveStats
    per_tier: dict[str, "BenchmarkMetrics"]
    per_frame_class: dict[str, "BenchmarkMetrics"]

def compute_metrics(results: list[SearchResult], budget_ks: list[int] = [1000, 5000, 10000]) -> BenchmarkMetrics: ...
```

### Phase 3: Baseline Runner
**File**: `src/bimodal_harness/evaluation/baseline.py`

```python
class SuccessPatternsBaseline:
    """Wraps Lean SuccessPatterns proof search via LeanBridge."""
    
    def __init__(self, lean_bridge: LeanBridge, budget: int = 5000): ...
    
    def solve(self, problem: BenchmarkProblem) -> SearchResult: ...
    
    def solve_batch(self, problems: list[BenchmarkProblem]) -> list[SearchResult]: ...
```

### Phase 4: Benchmark Suite
**File**: `src/bimodal_harness/evaluation/benchmark.py` (fill in existing stub)

```python
class BenchmarkSuite:
    """End-to-end benchmark evaluation."""
    
    def __init__(self, benchmark_path: Path, systems: list[ProofSystem]): ...
    
    def run(self) -> BenchmarkReport: ...
    
    def save_report(self, report: BenchmarkReport, output_dir: Path) -> None: ...
```

---

## 7. Key Risks and Mitigations

**Risk 1: Ground truth labeling timeouts**
- Lean `decideAuto` may timeout on hard formulas (complexity ≥ 9)
- Mitigation: retry with `decideOptimized` (IDDFS + full tableau); discard persistent timeouts; resample

**Risk 2: Formula space imbalance**
- Random sampling skews toward medium complexity; easy formulas are rare
- Mitigation: exhaustive enumeration for easy tier; stratified sampling for others

**Risk 3: Valid/Invalid ratio instability**
- For Dense/Discrete frame classes, provability ratio may differ significantly from 50/50
- Mitigation: generate 2x quota, accept actual ratio within [40%, 60%]; document actual ratio

**Risk 4: Lean bridge latency for large batches**
- Labeling 700 formulas requires 700 Lean calls (~500ms each = ~350 seconds)
- Mitigation: batch via `labelBatch` in Lean; use warm REPL; parallelize Python-side

**Risk 5: Determinism across platforms**
- Wall-clock TTP varies by machine; NV is deterministic but TTP is not
- Mitigation: normalize TTP by CPU speed; report NV as primary efficiency metric

---

## 8. Related Work Summary

| Benchmark | Domain | Size | Metrics | Notes |
|-----------|--------|------|---------|-------|
| miniF2F | High school math (Lean4/Isabelle) | 488 | pass@1 | Expert iteration baseline |
| LeanDojo | Mathlib theorems | 98,734 | SR@60min | Retrieval-augmented |
| ProofWriter | Propositional logic rules | 600K | per-tier accuracy | NLP-oriented |
| MCTS-ATP | General ATP | varies | SR@K expansions | Pure MCTS |
| **BimodalBench** | TM bimodal logic (Lean4) | **700** | SR@K, NV, TTP, PL | **This work** |

BimodalBench is the first benchmark specifically for bimodal temporal-modal logic theorem proving, providing ground truth from a verified Lean decision procedure.
