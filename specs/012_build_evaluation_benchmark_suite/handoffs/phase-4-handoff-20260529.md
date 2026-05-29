# Phase 4 Handoff: BenchmarkSuite Orchestrator and CLI

**Phase**: 4 - BenchmarkSuite Orchestrator and CLI (combined with Phase 5 integration tests)
**Status**: COMPLETED
**Timestamp**: 2026-05-29

## What Was Built

- `src/bimodal_harness/evaluation/benchmark.py`: BenchmarkSuite class, BenchmarkReport dataclass
- `src/bimodal_harness/evaluation/__init__.py`: Full exports for all evaluation symbols
- `scripts/evaluate.py`: Full argparse CLI with --generate and --benchmark-path modes
- `tests/test_evaluation/test_benchmark_suite.py`: 21 tests including integration test, all passing

## Key Design Decisions

- BenchmarkSuite loads problems lazily (only on first access to `.problems`)
- generate_and_save is a classmethod for one-shot generate + evaluate workflow
- save_report writes both report.json and comparison_table.txt
- BenchmarkReport.format_comparison_table() concatenates per-system tables
- CLI falls back to MockBaseline when Lean-requiring systems are requested (with warning)
- `_build_run_metadata` uses `datetime.UTC` alias (Python 3.11+ compatible)

## Plan Deviations

- Phase 5 (integration tests) was combined into Phase 4 test file - test_integration_full_pipeline covers the 50-formula end-to-end test
- Lean-gated integration tests (test_lean_integration.py) are deferred - not included since Lean is not available; @pytest.mark.lean would skip them anyway
- The multiple-systems test needed distinct class names since both MockBaseline instances have the same `name` property - documented as test infrastructure issue, not a production bug

## Test Coverage Summary

- Phase 1: 19 tests (generator, models, JSONL, checksums)
- Phase 2: 22 tests (metrics, SR@K, descriptive stats)  
- Phase 3: 20 tests (baselines, mock, success patterns, naive BFS)
- Phase 4: 21 tests (suite, report, CLI, integration)
- Total: 82 evaluation tests, all passing

## Verification Commands

```bash
# Run all evaluation tests
pytest tests/test_evaluation/ -v

# Full test suite (no regressions)
pytest --ignore=tests/test_lean -q

# Generate benchmark artifact  
python scripts/evaluate.py --generate --output-dir /tmp/bench --target-size 30

# Evaluate existing benchmark
python scripts/evaluate.py --benchmark-path /tmp/bench/benchmark.jsonl --systems mock

# Import check
python -c "from bimodal_harness.evaluation import BenchmarkSuite, BenchmarkGenerator, compute_metrics; print('OK')"
```
