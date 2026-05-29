"""Tests for BenchmarkGenerator, BenchmarkProblem, and JSONL serialization."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from bimodal_harness.evaluation.generator import (
    BenchmarkGenerator,
    compute_checksum,
    compute_stats,
    load_jsonl,
    save_jsonl,
    write_checksums,
)
from bimodal_harness.evaluation.models import BenchmarkConfig, BenchmarkProblem
from bimodal_harness.formula.ast import Atom, Bot, Box, Imp, Untl
from bimodal_harness.schema.records import PatternKey


# ---------------------------------------------------------------------------
# BenchmarkProblem construction and serialization
# ---------------------------------------------------------------------------


def _make_sample_problem(benchmark_id: str = "bench_0001") -> BenchmarkProblem:
    """Create a sample BenchmarkProblem for testing."""
    formula_json = {"tag": "imp", "left": {"tag": "atom", "name": "p"}, "right": {"tag": "atom", "name": "q"}}
    pattern_key = PatternKey(
        modal_depth=0,
        temporal_depth=0,
        imp_count=1,
        complexity=3,
        top_operator="Implication",
    )
    return BenchmarkProblem(
        benchmark_id=benchmark_id,
        formula_json=formula_json,
        formula_pretty="(p → q)",
        ground_truth_label="valid",
        ground_truth_proof_height=2,
        ground_truth_countermodel=None,
        difficulty_tier="easy",
        frame_class="Base",
        pattern_key=pattern_key,
    )


def test_benchmark_problem_construction() -> None:
    """Test that BenchmarkProblem can be constructed with all fields."""
    problem = _make_sample_problem()
    assert problem.benchmark_id == "bench_0001"
    assert problem.ground_truth_label == "valid"
    assert problem.ground_truth_proof_height == 2
    assert problem.ground_truth_countermodel is None
    assert problem.difficulty_tier == "easy"
    assert problem.frame_class == "Base"
    assert problem.pattern_key.complexity == 3


def test_benchmark_problem_with_none_label() -> None:
    """Test BenchmarkProblem allows None label for unlabelled problems."""
    formula_json = {"tag": "atom", "name": "p"}
    pattern_key = PatternKey(
        modal_depth=0, temporal_depth=0, imp_count=0, complexity=1, top_operator="Atom"
    )
    problem = BenchmarkProblem(
        benchmark_id="bench_0002",
        formula_json=formula_json,
        formula_pretty="p",
        ground_truth_label=None,
        ground_truth_proof_height=None,
        ground_truth_countermodel=None,
        difficulty_tier="easy",
        frame_class="Dense",
        pattern_key=pattern_key,
    )
    assert problem.ground_truth_label is None


def test_benchmark_problem_serialization_roundtrip() -> None:
    """Test that BenchmarkProblem serializes and deserializes without data loss."""
    original = _make_sample_problem()
    data = original.to_dict()
    restored = BenchmarkProblem.from_dict(data)

    assert restored.benchmark_id == original.benchmark_id
    assert restored.formula_json == original.formula_json
    assert restored.formula_pretty == original.formula_pretty
    assert restored.ground_truth_label == original.ground_truth_label
    assert restored.ground_truth_proof_height == original.ground_truth_proof_height
    assert restored.ground_truth_countermodel == original.ground_truth_countermodel
    assert restored.difficulty_tier == original.difficulty_tier
    assert restored.frame_class == original.frame_class
    assert restored.pattern_key == original.pattern_key


def test_benchmark_problem_with_countermodel() -> None:
    """Test BenchmarkProblem with a countermodel dict."""
    formula_json = {"tag": "atom", "name": "p"}
    countermodel = {"trueAtoms": [], "falseAtoms": [{"base": "p"}], "formula": formula_json}
    pattern_key = PatternKey(
        modal_depth=0, temporal_depth=0, imp_count=0, complexity=1, top_operator="Atom"
    )
    problem = BenchmarkProblem(
        benchmark_id="bench_0003",
        formula_json=formula_json,
        formula_pretty="p",
        ground_truth_label="invalid",
        ground_truth_proof_height=None,
        ground_truth_countermodel=countermodel,
        difficulty_tier="easy",
        frame_class="Discrete",
        pattern_key=pattern_key,
    )
    assert problem.ground_truth_label == "invalid"
    assert problem.ground_truth_countermodel == countermodel
    # Round-trip
    data = problem.to_dict()
    restored = BenchmarkProblem.from_dict(data)
    assert restored.ground_truth_countermodel == countermodel


# ---------------------------------------------------------------------------
# BenchmarkConfig defaults and customization
# ---------------------------------------------------------------------------


def test_benchmark_config_defaults() -> None:
    """Test that BenchmarkConfig has expected default values."""
    config = BenchmarkConfig()
    assert config.target_size == 700
    assert config.seed == 42
    assert config.valid_ratio == 0.5
    assert "easy" in config.tier_distribution
    assert "medium" in config.tier_distribution
    assert "hard" in config.tier_distribution
    assert "very_hard" in config.tier_distribution
    assert "Base" in config.frame_class_distribution
    assert abs(sum(config.tier_distribution.values()) - 1.0) < 1e-9
    assert abs(sum(config.frame_class_distribution.values()) - 1.0) < 1e-9


def test_benchmark_config_custom() -> None:
    """Test that BenchmarkConfig accepts custom values."""
    config = BenchmarkConfig(
        target_size=50,
        seed=99,
        valid_ratio=0.6,
        tier_distribution={"easy": 0.5, "medium": 0.5, "hard": 0.0, "very_hard": 0.0},
        frame_class_distribution={"Base": 1.0, "Dense": 0.0, "Discrete": 0.0},
    )
    assert config.target_size == 50
    assert config.seed == 99
    assert config.valid_ratio == 0.6
    assert config.tier_distribution["easy"] == 0.5


# ---------------------------------------------------------------------------
# Generator tests
# ---------------------------------------------------------------------------


def test_generator_small_config() -> None:
    """Test that BenchmarkGenerator produces problems for a small config."""
    config = BenchmarkConfig(
        target_size=20,
        seed=42,
        tier_distribution={"easy": 0.5, "medium": 0.5, "hard": 0.0, "very_hard": 0.0},
        frame_class_distribution={"Base": 0.5, "Dense": 0.25, "Discrete": 0.25},
    )
    gen = BenchmarkGenerator()
    problems = gen.generate(config)
    assert len(problems) > 0
    # All problems have required fields
    for p in problems:
        assert p.benchmark_id.startswith("bench_")
        assert isinstance(p.formula_json, dict)
        assert isinstance(p.formula_pretty, str)
        assert p.difficulty_tier in ("easy", "medium", "hard", "very_hard")
        assert p.frame_class in ("Base", "Dense", "Discrete")
        assert p.pattern_key is not None


def test_generator_deterministic() -> None:
    """Test that generator produces identical results with same seed."""
    config = BenchmarkConfig(
        target_size=15,
        seed=42,
        tier_distribution={"easy": 0.5, "medium": 0.5, "hard": 0.0, "very_hard": 0.0},
        frame_class_distribution={"Base": 1.0, "Dense": 0.0, "Discrete": 0.0},
    )
    gen = BenchmarkGenerator()
    problems1 = gen.generate(config)
    problems2 = gen.generate(config)
    assert len(problems1) == len(problems2)
    for p1, p2 in zip(problems1, problems2):
        assert p1.formula_json == p2.formula_json
        assert p1.difficulty_tier == p2.difficulty_tier


def test_generator_enumerate_easy_medium() -> None:
    """Test that _enumerate_easy_medium produces formulas at expected complexities."""
    config = BenchmarkConfig(atoms=["p", "q"])
    gen = BenchmarkGenerator()
    formulas = gen._enumerate_easy_medium(config)
    # All should be easy or medium tier (complexity 1-6)
    from bimodal_harness.formula.ast import complexity
    for f in formulas:
        c = complexity(f)
        assert 1 <= c <= 6, f"Expected complexity 1-6, got {c} for {f}"
    # Should have at least some formulas
    assert len(formulas) > 0


def test_generator_tier_distribution() -> None:
    """Test that generator roughly matches tier distribution for valid inputs."""
    config = BenchmarkConfig(
        target_size=30,
        seed=42,
        tier_distribution={"easy": 0.5, "medium": 0.5, "hard": 0.0, "very_hard": 0.0},
        frame_class_distribution={"Base": 1.0, "Dense": 0.0, "Discrete": 0.0},
    )
    gen = BenchmarkGenerator()
    problems = gen.generate(config)
    tiers = [p.difficulty_tier for p in problems]
    # Should only have easy/medium
    for t in tiers:
        assert t in ("easy", "medium")


# ---------------------------------------------------------------------------
# JSONL save/load round-trip
# ---------------------------------------------------------------------------


def test_jsonl_roundtrip() -> None:
    """Test that save_jsonl and load_jsonl round-trip without data loss."""
    problems = [_make_sample_problem(f"bench_{i:04d}") for i in range(5)]
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "benchmark.jsonl"
        save_jsonl(problems, path)
        loaded = load_jsonl(path)
    assert len(loaded) == len(problems)
    for orig, restored in zip(problems, loaded):
        assert orig.benchmark_id == restored.benchmark_id
        assert orig.formula_json == restored.formula_json
        assert orig.ground_truth_label == restored.ground_truth_label
        assert orig.pattern_key == restored.pattern_key


def test_jsonl_empty_list() -> None:
    """Test saving and loading an empty list."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "empty.jsonl"
        save_jsonl([], path)
        loaded = load_jsonl(path)
    assert loaded == []


def test_jsonl_creates_parent_dir() -> None:
    """Test that save_jsonl creates parent directories if needed."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "nested" / "deep" / "benchmark.jsonl"
        save_jsonl([_make_sample_problem()], path)
        assert path.exists()


# ---------------------------------------------------------------------------
# Checksum tests
# ---------------------------------------------------------------------------


def test_compute_checksum() -> None:
    """Test that compute_checksum returns a non-empty hex string."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "test.txt"
        path.write_text("hello world\n", encoding="utf-8")
        checksum = compute_checksum(path)
    assert len(checksum) == 64  # SHA-256 produces 64 hex chars
    assert all(c in "0123456789abcdef" for c in checksum)


def test_compute_checksum_deterministic() -> None:
    """Test that checksum is deterministic for the same content."""
    content = "test content for checksum"
    with tempfile.TemporaryDirectory() as tmpdir:
        path1 = Path(tmpdir) / "file1.txt"
        path2 = Path(tmpdir) / "file2.txt"
        path1.write_text(content, encoding="utf-8")
        path2.write_text(content, encoding="utf-8")
        c1 = compute_checksum(path1)
        c2 = compute_checksum(path2)
    assert c1 == c2


def test_write_checksums() -> None:
    """Test that write_checksums creates a valid checksums file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        file1 = tmpdir / "file1.txt"
        file2 = tmpdir / "file2.txt"
        file1.write_text("content1\n", encoding="utf-8")
        file2.write_text("content2\n", encoding="utf-8")
        checksums_path = tmpdir / "checksums.sha256"
        write_checksums([file1, file2], checksums_path)
        lines = checksums_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2
    assert "file1.txt" in lines[0]
    assert "file2.txt" in lines[1]
    # Each line should be "checksum  filename"
    for line in lines:
        parts = line.split("  ")
        assert len(parts) == 2
        assert len(parts[0]) == 64  # SHA-256 hex length


# ---------------------------------------------------------------------------
# compute_stats tests
# ---------------------------------------------------------------------------


def test_compute_stats_empty() -> None:
    """Test compute_stats with an empty list."""
    stats = compute_stats([])
    assert stats["total"] == 0


def test_compute_stats_counts() -> None:
    """Test that compute_stats correctly counts by tier and frame class."""
    problems = []
    for i in range(3):
        p = _make_sample_problem(f"bench_{i:04d}")
        problems.append(p)
    # All are "easy" tier, "Base" frame class
    stats = compute_stats(problems)
    assert stats["total"] == 3
    assert stats["by_tier"]["easy"] == 3
    assert stats["by_frame_class"]["Base"] == 3
    assert stats["by_label"]["valid"] == 3


def test_compute_stats_complexity() -> None:
    """Test that compute_stats computes complexity statistics."""
    problems = [_make_sample_problem(f"bench_{i:04d}") for i in range(2)]
    stats = compute_stats(problems)
    assert "complexity_stats" in stats
    assert stats["complexity_stats"]["min"] == 3
    assert stats["complexity_stats"]["max"] == 3
    assert stats["complexity_stats"]["mean"] == 3.0
