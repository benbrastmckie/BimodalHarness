# Phase 1 Handoff: Benchmark Data Model and Generator

**Phase**: 1 - Benchmark Data Model and Generator
**Status**: COMPLETED
**Timestamp**: 2026-05-29

## What Was Built

- `src/bimodal_harness/evaluation/models.py`: BenchmarkProblem and BenchmarkConfig dataclasses with full serialization support
- `src/bimodal_harness/evaluation/generator.py`: BenchmarkGenerator class with stratified formula generation, JSONL I/O, compute_stats, and SHA-256 checksum utilities
- `tests/test_evaluation/__init__.py`: Test package init
- `tests/test_evaluation/test_generator.py`: 19 tests, all passing

## Key Design Decisions

- BenchmarkProblem uses `slots=True` (not frozen, since it needs to be mutable for label filling later)
- BenchmarkConfig uses a regular dataclass with `field(default_factory=...)` for mutable defaults
- Formula classification uses strict complexity-based tiers: easy<=3, medium 4-6, hard 7-9, very_hard>=10
- Generator uses ENUM_SEED=42 for enumeration, SPLIT_SEED=137 for shuffling buckets
- JSONL format: one JSON object per line, using BenchmarkProblem.to_dict() / from_dict()
- SHA-256 checksums use standard sha256sum format

## Plan Deviations

- The formula field is stored as formula_json (dict) only, not as a FormulaNode object — this avoids circular imports and makes serialization straightforward
- _has_modal_and_temporal check implemented but not actively filtering in current _sample_hard_very_hard (hard formulas don't require both operators)

## Next Phase Inputs

Phase 2 (Metrics) needs SearchResult, DescriptiveStats, BenchmarkMetrics — no dependencies on generator output format.
Phase 3 (Baseline) needs BenchmarkProblem from Phase 1.
