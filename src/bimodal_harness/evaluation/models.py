"""Benchmark data models for bimodal logic evaluation.

Defines BenchmarkProblem and BenchmarkConfig dataclasses used throughout
the evaluation benchmark suite.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from bimodal_harness.schema.records import PatternKey


@dataclass(slots=True)
class BenchmarkProblem:
    """A single evaluation problem in the benchmark suite.

    Holds a formula with its ground truth label and structural metadata.
    For ground truth labels that require Lean verification, the label
    fields may be None until filled by the labelling pipeline.
    """

    benchmark_id: str
    """Unique identifier for this benchmark problem (e.g. 'bench_0001')."""

    formula_json: dict[str, Any]
    """Formula serialized as JSON tree (formula/ast.py FormulaNode.to_json format)."""

    formula_pretty: str
    """Human-readable formula string."""

    ground_truth_label: str | None
    """Classification label: 'valid', 'invalid', or None if not yet labelled."""

    ground_truth_proof_height: int | None
    """Derivation tree height for valid formulas; None if invalid or unlabelled."""

    ground_truth_countermodel: dict[str, Any] | None
    """Countermodel dict for invalid formulas; None if valid or unlabelled."""

    difficulty_tier: str
    """Difficulty tier: one of 'easy', 'medium', 'hard', 'very_hard'."""

    frame_class: str
    """Frame class: one of 'Base', 'Dense', 'Discrete'."""

    pattern_key: PatternKey
    """Structural feature vector for this formula."""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        return {
            "benchmark_id": self.benchmark_id,
            "formula_json": self.formula_json,
            "formula_pretty": self.formula_pretty,
            "ground_truth_label": self.ground_truth_label,
            "ground_truth_proof_height": self.ground_truth_proof_height,
            "ground_truth_countermodel": self.ground_truth_countermodel,
            "difficulty_tier": self.difficulty_tier,
            "frame_class": self.frame_class,
            "pattern_key": self.pattern_key.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BenchmarkProblem:
        """Deserialize from a JSON-compatible dict."""
        return cls(
            benchmark_id=str(data["benchmark_id"]),
            formula_json=dict(data["formula_json"]),
            formula_pretty=str(data["formula_pretty"]),
            ground_truth_label=data.get("ground_truth_label"),
            ground_truth_proof_height=(
                int(data["ground_truth_proof_height"])
                if data.get("ground_truth_proof_height") is not None
                else None
            ),
            ground_truth_countermodel=data.get("ground_truth_countermodel"),
            difficulty_tier=str(data["difficulty_tier"]),
            frame_class=str(data["frame_class"]),
            pattern_key=PatternKey.from_dict(data["pattern_key"]),
        )


@dataclass
class BenchmarkConfig:
    """Configuration for benchmark generation.

    Controls the size, stratification ratios, and random seeds used
    by BenchmarkGenerator to produce a reproducible benchmark artifact.
    """

    target_size: int = 700
    """Total number of problems in the benchmark."""

    seed: int = 42
    """Primary random seed for reproducibility."""

    valid_ratio: float = 0.5
    """Fraction of problems that should be labelled 'valid' (0 to 1)."""

    tier_distribution: dict[str, float] = field(
        default_factory=lambda: {
            "easy": 0.20,
            "medium": 0.35,
            "hard": 0.30,
            "very_hard": 0.15,
        }
    )
    """Target fraction of problems per difficulty tier (must sum to 1.0)."""

    frame_class_distribution: dict[str, float] = field(
        default_factory=lambda: {
            "Base": 0.50,
            "Dense": 0.25,
            "Discrete": 0.25,
        }
    )
    """Target fraction of problems per frame class (must sum to 1.0)."""

    atoms: list[str] = field(default_factory=lambda: ["p", "q", "r"])
    """Atom names to use in formula generation."""

    easy_medium_max_complexity: int = 6
    """Maximum complexity for exhaustive enumeration of easy/medium tiers."""

    hard_very_hard_min_complexity: int = 7
    """Minimum complexity for hard/very_hard random sampling."""

    hard_very_hard_max_complexity: int = 12
    """Maximum complexity for hard/very_hard random sampling."""
