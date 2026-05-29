# Phase 2 Handoff: Metrics Collection Framework

**Phase**: 2 - Metrics Collection Framework
**Status**: COMPLETED
**Timestamp**: 2026-05-29

## What Was Built

- `src/bimodal_harness/evaluation/metrics.py`: SearchResult, DescriptiveStats, BenchmarkMetrics dataclasses; compute_metrics, format_results_table, metrics_to_dict functions
- `tests/test_evaluation/test_metrics.py`: 22 tests, all passing

## Key Design Decisions

- DescriptiveStats uses fractional-index linear interpolation for percentiles (standard approach)
- SR@K computes fraction of ALL problems (not just successes) where nodes_visited <= K AND success=True
- Nested BenchmarkMetrics for per_tier and per_frame_class (recursive but shallow, only one level deep)
- format_results_table uses fixed-width column formatting compatible with plain-text tables

## Plan Deviations

- DescriptiveStats P90 test initially had wrong expected value (9.9 vs actual 9.1 for [1..10]) - fixed in test
- per_tier and per_frame_class in BenchmarkMetrics don't recurse further (no nested breakdowns inside breakdowns) to avoid complexity

## Next Phase Inputs

Phase 3 (Baseline) uses SearchResult from this phase as the return type for all baseline runners.
