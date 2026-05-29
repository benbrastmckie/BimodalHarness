# Implementation Plan: Task #12

- **Task**: 12 - Build Evaluation Benchmark Suite
- **Status**: [NOT STARTED]
- **Effort**: 10 hours
- **Dependencies**: Task 8 (formula generator - completed)
- **Research Inputs**: specs/012_build_evaluation_benchmark_suite/reports/01_benchmark-design.md
- **Artifacts**: plans/01_benchmark-plan.md (this file)
- **Standards**: plan-format.md, status-markers.md, artifact-management.md, tasks.md
- **Type**: python
- **Lean Intent**: false

## Overview

Build a 700-formula held-out evaluation benchmark for the BimodalHarness neural-guided proof search system. The benchmark is stratified by validity (50/50 valid/invalid), difficulty tier (easy/medium/hard/very_hard), and frame class (Base/Dense/Discrete), with ground truth from Lean's `decideAuto` decision procedure. The suite implements SR@K metrics at 1K/5K/10K node budgets, nodes-visited and time-to-proof statistics, and a SuccessPatterns baseline runner. The benchmark is designed as a publishable open artifact for TABLEAUX/CADE conferences.

### Research Integration

Key findings from the research report (01_benchmark-design.md) integrated into this plan:

- **700-formula target** with stratification across 4 dimensions (validity, difficulty, frame class, top-operator category)
- **Formula selection algorithm**: exhaustive enumeration for easy/medium tiers, seeded random sampling for hard/very_hard, with deterministic seeds (ENUM_SEED=42, SPLIT_SEED=137)
- **Metrics design**: SR@K as primary (matching miniF2F/LeanDojo conventions), plus NV, TTP, and PL with per-tier and per-frame-class breakdowns
- **SuccessPatterns baseline**: PatternDatabase + heuristicBonus scoring via LeanBridge, providing a non-neural comparison point
- **Publication format**: JSONL benchmark artifact with SHA-256 checksums and reproducible generation script
- **Existing infrastructure**: formula generator (Task 8), TrainingRecord schema, action space with frame-class masks, LeanBridge for Lean REPL access, empty evaluation stubs ready to fill

### Prior Plan Reference

No prior plan.

### Roadmap Alignment

No ROADMAP.md found.

## Goals & Non-Goals

**Goals**:
- Implement a deterministic, reproducible benchmark generator producing 700 stratified formulas
- Build a metrics collection framework computing SR@K, NV, TTP, and PL with per-tier/per-frame-class breakdowns
- Create a SuccessPatterns baseline runner that evaluates via LeanBridge
- Implement an end-to-end BenchmarkSuite orchestrator with JSONL I/O and reporting
- Produce a publishable benchmark artifact (JSONL + stats + checksums + generation script)
- Write comprehensive tests for all evaluation components

**Non-Goals**:
- Training or fine-tuning neural models (separate task)
- Implementing MCTS or best-first search strategies (covered by search module)
- Writing the conference paper itself (benchmark enables the paper)
- Optimizing Lean proof search performance (baseline uses existing Lean search as-is)
- Building a web-based leaderboard or submission system

## Risks & Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Lean `decideAuto` timeouts on hard formulas | H | M | Retry with `decideOptimized`; discard persistent timeouts; resample to fill quota |
| Valid/invalid ratio instability for Dense/Discrete | M | M | Generate 2x quota; accept ratio within [40%, 60%]; document actual ratio |
| LeanBridge latency for 700-formula labelling (~350s) | M | L | Batch via `labelBatch` if available; warm REPL; parallelize Python-side |
| Formula space imbalance (easy formulas rare) | M | L | Exhaustive enumeration for easy tier; stratified sampling for others |
| Wall-clock TTP non-determinism across machines | L | H | Report NV as primary efficiency metric; normalize TTP documentation |
| `lean-interact` not installed in test environment | M | M | Mock LeanBridge in unit tests; integration tests gated by `@pytest.mark.lean` |

## Implementation Phases

**Dependency Analysis**:
| Wave | Phases | Blocked by |
|------|--------|------------|
| 1 | 1 | -- |
| 2 | 2, 3 | 1 |
| 3 | 4 | 2, 3 |
| 4 | 5 | 4 |

Phases within the same wave can execute in parallel.

---

### Phase 1: Benchmark Data Model and Generator [COMPLETED]

**Goal**: Implement the BenchmarkProblem data model and BenchmarkGenerator class that produces stratified formula sets with ground-truth labels.

**Tasks**:
- [ ] Create `src/bimodal_harness/evaluation/models.py` with `BenchmarkProblem` and `BenchmarkConfig` dataclasses
  - `BenchmarkProblem`: benchmark_id, formula (FormulaNode), formula_json, formula_pretty, ground_truth_label, ground_truth_proof_height, ground_truth_countermodel, difficulty_tier, frame_class, pattern_key
  - `BenchmarkConfig`: target_size=700, seed=42, valid_ratio=0.5, tier_distribution, frame_class_distribution
- [ ] Create `src/bimodal_harness/evaluation/generator.py` with `BenchmarkGenerator` class
  - `generate(config) -> list[BenchmarkProblem]`: main entry point
  - `_enumerate_easy_medium(config)`: exhaustive enumeration via `enumerate_up_to_complexity(6, ["p","q","r"])` with dedup and filtering
  - `_sample_hard_very_hard(config)`: seeded `random_formula` with complexity 7-12 and modal+temporal operator requirement
  - `_stratify_and_select(candidates, config)`: balance across validity/tier/frame-class dimensions
  - `_classify_difficulty(formula)`: map complexity to tier using existing Lean tier boundaries (easy<=3, medium 4-6, hard 7-9, very_hard>=10)
- [ ] Implement JSONL serialization: `save_jsonl(problems, path)` and `load_jsonl(path) -> list[BenchmarkProblem]`
- [ ] Implement `compute_stats(problems) -> dict` returning aggregate statistics (counts by tier/validity/frame-class, mean complexity, depth distributions)
- [ ] Implement SHA-256 checksum generation for JSONL integrity verification
- [ ] Write unit tests in `tests/test_evaluation/test_generator.py`
  - Test BenchmarkProblem construction and serialization round-trip
  - Test BenchmarkConfig defaults and custom configurations
  - Test enumeration produces expected formula counts at small complexity
  - Test stratification logic with synthetic candidate sets
  - Test JSONL save/load round-trip with checksums

**Timing**: 2.5 hours

**Depends on**: none

**Files to modify**:
- `src/bimodal_harness/evaluation/models.py` - new: data model definitions
- `src/bimodal_harness/evaluation/generator.py` - new: benchmark generation logic
- `src/bimodal_harness/evaluation/__init__.py` - update: export new symbols
- `tests/test_evaluation/__init__.py` - new: test package init
- `tests/test_evaluation/test_generator.py` - new: generator tests

**Verification**:
- `pytest tests/test_evaluation/test_generator.py -v` passes
- BenchmarkProblem round-trips through JSONL without data loss
- Generator produces correct tier distribution for small configs (e.g., target_size=20)

---

### Phase 2: Metrics Collection Framework [COMPLETED]

**Goal**: Implement the metrics computation engine that calculates SR@K, NV, TTP, PL, and per-stratum breakdowns from a list of search results.

**Tasks**:
- [ ] Create `src/bimodal_harness/evaluation/metrics.py` with core metric types
  - `SearchResult` dataclass: problem_id, success, nodes_visited, time_seconds, proof_height, node_budget, difficulty_tier, frame_class
  - `DescriptiveStats` dataclass: mean, median, p90, min, max, count
  - `BenchmarkMetrics` dataclass: success_rate_at_k (dict[int, float]), nodes_visited_stats, time_to_proof_stats, proof_height_stats, per_tier (dict[str, BenchmarkMetrics]), per_frame_class (dict[str, BenchmarkMetrics])
- [ ] Implement `compute_metrics(results, budget_ks=[1000, 5000, 10000]) -> BenchmarkMetrics`
  - SR@K: fraction of problems where nodes_visited <= K and success=True
  - NV stats: descriptive stats over nodes_visited (failed searches capped at budget)
  - TTP stats: descriptive stats over time_seconds for successful searches only
  - PL stats: descriptive stats over proof_height for successful searches only
  - Recursive computation for per_tier and per_frame_class subgroups
- [ ] Implement `format_results_table(metrics, system_name) -> str` producing the TABLEAUX/CADE standard comparison table
- [ ] Implement `metrics_to_dict(metrics) -> dict` for JSON serialization of results
- [ ] Write unit tests in `tests/test_evaluation/test_metrics.py`
  - Test SR@K computation with known synthetic results
  - Test DescriptiveStats edge cases (empty list, single element, all same values)
  - Test per-tier breakdown correctly partitions results
  - Test table formatting produces expected columns

**Timing**: 2 hours

**Depends on**: 1

**Files to modify**:
- `src/bimodal_harness/evaluation/metrics.py` - new: metrics computation engine
- `src/bimodal_harness/evaluation/__init__.py` - update: export metrics symbols
- `tests/test_evaluation/test_metrics.py` - new: metrics tests

**Verification**:
- `pytest tests/test_evaluation/test_metrics.py -v` passes
- SR@K=1.0 when all synthetic results succeed within budget
- SR@K=0.0 when no results succeed
- Per-tier breakdown sums to overall count

---

### Phase 3: SuccessPatterns Baseline Runner [NOT STARTED]

**Goal**: Implement the baseline evaluation system that runs SuccessPatterns proof search via LeanBridge and collects SearchResult data for comparison.

**Tasks**:
- [ ] Create `src/bimodal_harness/evaluation/baseline.py` with `SuccessPatternsBaseline` class
  - `__init__(lean_bridge, budget=5000)`: configure baseline with LeanBridge instance
  - `solve(problem: BenchmarkProblem) -> SearchResult`: run single-formula evaluation
    - Construct Lean command to invoke `batch_search_with_learning` or `proofSearch`
    - Parse response for success/failure, nodes_visited, proof_height
    - Measure wall-clock time
  - `solve_batch(problems: list[BenchmarkProblem], progress_callback=None) -> list[SearchResult]`: batch evaluation with progress tracking
- [ ] Implement `NaiveBFSBaseline` as a second baseline
  - Uses BestFirst search without SuccessPatterns heuristic boost
  - Same interface as SuccessPatternsBaseline for comparison
- [ ] Implement a `MockBaseline` for testing without Lean
  - Generates deterministic synthetic SearchResults based on difficulty tier
  - Used in CI/CD and unit tests
- [ ] Write tests in `tests/test_evaluation/test_baseline.py`
  - Test MockBaseline produces expected results
  - Test SuccessPatternsBaseline with mocked LeanBridge (mock REPL responses)
  - Test solve_batch aggregation and progress callback invocation
  - Integration test with `@pytest.mark.lean` for real LeanBridge (skipped in CI)

**Timing**: 2 hours

**Depends on**: 1

**Files to modify**:
- `src/bimodal_harness/evaluation/baseline.py` - new: baseline runners
- `src/bimodal_harness/evaluation/__init__.py` - update: export baseline symbols
- `tests/test_evaluation/test_baseline.py` - new: baseline tests

**Verification**:
- `pytest tests/test_evaluation/test_baseline.py -v` passes (excluding @pytest.mark.lean)
- MockBaseline produces consistent results across runs with same seed
- SuccessPatternsBaseline correctly parses mocked Lean REPL output

---

### Phase 4: BenchmarkSuite Orchestrator and CLI [NOT STARTED]

**Goal**: Fill in the existing `benchmark.py` stub with the end-to-end BenchmarkSuite that ties together generation, evaluation, metrics, and reporting. Wire up the `scripts/evaluate.py` CLI.

**Tasks**:
- [ ] Implement `BenchmarkSuite` in `src/bimodal_harness/evaluation/benchmark.py`
  - `__init__(benchmark_path, systems: list[BaselineRunner])`: load benchmark from JSONL
  - `run() -> BenchmarkReport`: execute all systems on all problems, collect metrics
  - `BenchmarkReport` dataclass: per_system_metrics (dict[str, BenchmarkMetrics]), benchmark_stats, run_metadata (timestamp, machine info, budgets)
  - `save_report(report, output_dir)`: write JSON report + comparison tables
  - `generate_and_save(config, output_dir)`: one-shot generate + save benchmark artifact
- [ ] Implement `scripts/evaluate.py` CLI entry point (replace NotImplementedError)
  - `--generate`: generate benchmark to specified path
  - `--benchmark-path`: path to existing benchmark JSONL
  - `--systems`: comma-separated list of systems to evaluate (success_patterns, naive_bfs, mock)
  - `--budgets`: comma-separated node budgets (default: 1000,5000,10000)
  - `--output-dir`: where to write results
  - Uses `argparse` for argument parsing
- [ ] Implement benchmark artifact generation matching publication format
  - `benchmark.jsonl`: 700 problems
  - `benchmark_stats.json`: aggregate statistics
  - `checksums.sha256`: SHA-256 integrity verification
  - `generate.py`: self-contained reproducible generation script (copies relevant config)
- [ ] Write tests in `tests/test_evaluation/test_benchmark_suite.py`
  - Test BenchmarkSuite with MockBaseline and small benchmark (10 problems)
  - Test report generation produces valid JSON
  - Test CLI argument parsing (not full execution)
  - Test benchmark artifact directory structure

**Timing**: 2 hours

**Depends on**: 2, 3

**Files to modify**:
- `src/bimodal_harness/evaluation/benchmark.py` - update: fill in BenchmarkSuite (existing stub)
- `src/bimodal_harness/evaluation/__init__.py` - update: export suite symbols
- `scripts/evaluate.py` - update: replace NotImplementedError with CLI
- `tests/test_evaluation/test_benchmark_suite.py` - new: suite tests

**Verification**:
- `pytest tests/test_evaluation/test_benchmark_suite.py -v` passes
- `python scripts/evaluate.py --generate --output-dir /tmp/bench_test` creates valid artifact directory
- `python scripts/evaluate.py --benchmark-path /tmp/bench_test/benchmark.jsonl --systems mock` runs without error

---

### Phase 5: Integration Tests and Documentation [NOT STARTED]

**Goal**: Run end-to-end integration tests, validate the full 700-formula generation pipeline, and ensure the benchmark artifact is publication-ready.

**Tasks**:
- [ ] Create `tests/test_evaluation/test_integration.py` with full pipeline integration test
  - Generate a small benchmark (50 formulas) end-to-end
  - Run MockBaseline evaluation through BenchmarkSuite
  - Verify metrics computation produces expected structure
  - Verify JSONL round-trip preserves all fields
  - Verify checksums match
- [ ] Create `tests/test_evaluation/test_lean_integration.py` with Lean-dependent tests (gated by `@pytest.mark.lean`)
  - Generate 10 formulas with real Lean labelling
  - Run SuccessPatternsBaseline on generated formulas
  - Verify ground truth labels match Lean `decideAuto` output
- [ ] Run `ruff check src/bimodal_harness/evaluation/` and `ruff format src/bimodal_harness/evaluation/` to ensure code quality
- [ ] Run `mypy src/bimodal_harness/evaluation/` to verify type annotations
- [ ] Validate that `pytest tests/test_evaluation/ -v` passes all non-Lean tests
- [ ] Verify evaluation module exports are clean: `python -c "from bimodal_harness.evaluation import BenchmarkSuite, BenchmarkGenerator, compute_metrics"`

**Timing**: 1.5 hours

**Depends on**: 4

**Files to modify**:
- `tests/test_evaluation/test_integration.py` - new: integration tests
- `tests/test_evaluation/test_lean_integration.py` - new: Lean-gated integration tests
- `src/bimodal_harness/evaluation/*.py` - fix: any issues found during integration

**Verification**:
- `pytest tests/test_evaluation/ -v` passes (all non-Lean tests green)
- `ruff check src/bimodal_harness/evaluation/` reports no errors
- `mypy src/bimodal_harness/evaluation/` reports no type errors
- Module imports cleanly from Python REPL

## Testing & Validation

- [ ] Unit tests for BenchmarkProblem/BenchmarkConfig data models
- [ ] Unit tests for formula enumeration and stratification logic
- [ ] Unit tests for JSONL serialization round-trip with checksums
- [ ] Unit tests for SR@K, NV, TTP, PL metric computations
- [ ] Unit tests for DescriptiveStats edge cases
- [ ] Unit tests for per-tier and per-frame-class metric breakdowns
- [ ] Unit tests for MockBaseline deterministic output
- [ ] Unit tests for SuccessPatternsBaseline with mocked LeanBridge
- [ ] Unit tests for BenchmarkSuite end-to-end with MockBaseline
- [ ] Unit tests for CLI argument parsing
- [ ] Integration test: 50-formula generation + mock evaluation pipeline
- [ ] Integration test: JSONL artifact integrity (checksums, field completeness)
- [ ] Lean-gated integration test: real formula labelling via LeanBridge
- [ ] Code quality: ruff check + ruff format + mypy pass

## Artifacts & Outputs

- `src/bimodal_harness/evaluation/models.py` - BenchmarkProblem and BenchmarkConfig data models
- `src/bimodal_harness/evaluation/generator.py` - BenchmarkGenerator with stratified formula selection
- `src/bimodal_harness/evaluation/metrics.py` - Metrics computation engine (SR@K, NV, TTP, PL)
- `src/bimodal_harness/evaluation/baseline.py` - SuccessPatterns and NaiveBFS baseline runners
- `src/bimodal_harness/evaluation/benchmark.py` - BenchmarkSuite orchestrator (filled stub)
- `scripts/evaluate.py` - CLI entry point for benchmark generation and evaluation
- `tests/test_evaluation/` - Comprehensive test suite (6 test files)

## Rollback/Contingency

All implementation is additive (new files + one stub fill-in + one CLI update). Rollback is straightforward:

1. Revert `src/bimodal_harness/evaluation/benchmark.py` to stub state
2. Revert `scripts/evaluate.py` to NotImplementedError stub
3. Revert `src/bimodal_harness/evaluation/__init__.py` to empty stub
4. Delete new files: `models.py`, `generator.py`, `metrics.py`, `baseline.py`
5. Delete new test directory: `tests/test_evaluation/`

No existing code is modified beyond the three stub files, so rollback has zero risk of breaking existing functionality.
