# Implementation Summary: Task 12 - Build Evaluation Benchmark Suite

- **Task**: 12 - Build Evaluation Benchmark Suite
- **Status**: COMPLETED
- **Date**: 2026-05-29
- **Session**: sess_1780086457_029818

## Overview

Implemented a complete evaluation benchmark suite for the BimodalHarness neural-guided proof search system. The suite generates stratified 700-formula benchmarks, computes SR@K metrics at multiple node budgets, provides baseline runners, and includes an end-to-end orchestrator with JSONL I/O and a CLI.

## Deliverables

### Production Code

| File | Description |
|------|-------------|
| `src/bimodal_harness/evaluation/models.py` | BenchmarkProblem, BenchmarkConfig dataclasses |
| `src/bimodal_harness/evaluation/generator.py` | BenchmarkGenerator, JSONL I/O, checksums, stats |
| `src/bimodal_harness/evaluation/metrics.py` | SearchResult, DescriptiveStats, BenchmarkMetrics, SR@K |
| `src/bimodal_harness/evaluation/baseline.py` | BaselineRunner ABC, MockBaseline, SuccessPatternsBaseline, NaiveBFSBaseline |
| `src/bimodal_harness/evaluation/benchmark.py` | BenchmarkSuite, BenchmarkReport orchestrator |
| `src/bimodal_harness/evaluation/__init__.py` | Clean public API exports |
| `scripts/evaluate.py` | Full argparse CLI |

### Test Code

| File | Tests | Status |
|------|-------|--------|
| `tests/test_evaluation/test_generator.py` | 19 | All passing |
| `tests/test_evaluation/test_metrics.py` | 22 | All passing |
| `tests/test_evaluation/test_baseline.py` | 20 | All passing |
| `tests/test_evaluation/test_benchmark_suite.py` | 21 | All passing |
| **Total** | **82** | **All passing** |

## Design Decisions

1. **Formula storage**: BenchmarkProblem stores formula_json (dict) rather than FormulaNode objects for JSONL compatibility and to avoid circular import issues.

2. **Ground truth labels**: BenchmarkGenerator does not require Lean - ground_truth_label fields are set to None and can be filled later by the Lean labelling pipeline.

3. **Difficulty classification**: Uses complexity-based tiers matching the Lean boundaries (easy≤3, medium 4-6, hard 7-9, very_hard≥10).

4. **Deterministic seeds**: ENUM_SEED=42 for formula enumeration, SPLIT_SEED=137 for bucket shuffling, providing reproducible generation.

5. **SR@K metric**: Computes fraction of ALL problems (not just successes) where nodes_visited ≤ K AND success=True, matching miniF2F/LeanDojo conventions.

6. **MockBaseline**: Per-problem seeding via `hash(benchmark_id) ^ seed` ensures determinism regardless of evaluation order.

7. **CLI fallback**: Lean-requiring systems (success_patterns, naive_bfs) fall back to MockBaseline with a warning when Lean is unavailable.

## Plan Deviations

- Phase 5 (integration tests and documentation) was combined with Phase 4's test suite - `test_integration_full_pipeline` covers the 50-formula end-to-end scenario.
- Lean-gated integration tests (`test_lean_integration.py`) were not implemented since Lean is not installed in the test environment; they would be auto-skipped by the `@pytest.mark.lean` marker anyway.
- The formula field is stored as `formula_json` (dict) only, not as a dual FormulaNode + dict representation, simplifying serialization.

## Verification

```bash
# 82 new tests, all passing
pytest tests/test_evaluation/ -v

# No regressions in full test suite
pytest --ignore=tests/test_lean -q
# => 932 passed, 2 skipped

# Ruff lint clean
ruff check src/bimodal_harness/evaluation/

# CLI functional
python scripts/evaluate.py --generate --output-dir /tmp/bench --target-size 30
python scripts/evaluate.py --benchmark-path /tmp/bench/benchmark.jsonl --systems mock

# Module import clean
python -c "from bimodal_harness.evaluation import BenchmarkSuite, BenchmarkGenerator, compute_metrics"
```
