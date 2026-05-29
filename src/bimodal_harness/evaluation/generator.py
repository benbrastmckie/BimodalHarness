"""Benchmark generator for bimodal logic evaluation.

Produces a stratified set of BenchmarkProblems from the formula space,
using exhaustive enumeration for easy/medium tiers and seeded random
sampling for hard/very_hard tiers.

Seeds:
- ENUM_SEED=42: used for deterministic sub-sampling from enumerated formulas
- SPLIT_SEED=137: used for train/test split decisions
"""

from __future__ import annotations

import hashlib
import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Any

from bimodal_harness.evaluation.models import BenchmarkConfig, BenchmarkProblem
from bimodal_harness.formula.ast import (
    Atom,
    Bot,
    Box,
    FormulaNode,
    Imp,
    Snce,
    Untl,
    complexity,
    imp_count,
    modal_depth,
    temporal_depth,
    top_operator,
)
from bimodal_harness.formula.generator import (
    enumerate_up_to_complexity,
    random_formula,
)
from bimodal_harness.schema.constants import VALID_FRAME_CLASSES
from bimodal_harness.schema.records import PatternKey

# Deterministic seeds matching research plan
ENUM_SEED = 42
SPLIT_SEED = 137

# Difficulty tier boundaries (complexity-based)
_TIER_BOUNDARIES: dict[str, tuple[int, int]] = {
    "easy": (1, 3),
    "medium": (4, 6),
    "hard": (7, 9),
    "very_hard": (10, 999),
}


def _classify_difficulty(formula: FormulaNode) -> str:
    """Map formula complexity to difficulty tier.

    Boundaries:
    - easy: complexity 1-3
    - medium: complexity 4-6
    - hard: complexity 7-9
    - very_hard: complexity >= 10
    """
    c = complexity(formula)
    if c <= 3:
        return "easy"
    elif c <= 6:
        return "medium"
    elif c <= 9:
        return "hard"
    else:
        return "very_hard"


def _formula_to_pretty(formula: FormulaNode) -> str:
    """Convert a FormulaNode to a human-readable string."""
    match formula:
        case Atom(name):
            return name
        case Bot():
            return "⊥"
        case Imp(left, right):
            return f"({_formula_to_pretty(left)} → {_formula_to_pretty(right)})"
        case Box(child):
            return f"□{_formula_to_pretty(child)}"
        case Untl(event, guard):
            return f"U({_formula_to_pretty(event)}, {_formula_to_pretty(guard)})"
        case Snce(event, guard):
            return f"S({_formula_to_pretty(event)}, {_formula_to_pretty(guard)})"
        case _:
            return str(formula)


def _extract_pattern_key(formula: FormulaNode) -> PatternKey:
    """Extract a PatternKey from a FormulaNode."""
    return PatternKey(
        modal_depth=modal_depth(formula),
        temporal_depth=temporal_depth(formula),
        imp_count=imp_count(formula),
        complexity=complexity(formula),
        top_operator=top_operator(formula),
    )


def _has_modal_and_temporal(formula: FormulaNode) -> bool:
    """Check if formula contains both modal (Box) and temporal (Untl/Snce) operators."""
    has_modal = _has_box(formula)
    has_temporal = _has_temporal_op(formula)
    return has_modal and has_temporal


def _has_box(formula: FormulaNode) -> bool:
    """Recursively check if formula contains a Box operator."""
    match formula:
        case Box():
            return True
        case Imp(left, right):
            return _has_box(left) or _has_box(right)
        case Untl(event, guard):
            return _has_box(event) or _has_box(guard)
        case Snce(event, guard):
            return _has_box(event) or _has_box(guard)
        case _:
            return False


def _has_temporal_op(formula: FormulaNode) -> bool:
    """Recursively check if formula contains a temporal (Until/Since) operator."""
    match formula:
        case Untl() | Snce():
            return True
        case Imp(left, right):
            return _has_temporal_op(left) or _has_temporal_op(right)
        case Box(child):
            return _has_temporal_op(child)
        case _:
            return False


class BenchmarkGenerator:
    """Generator for stratified benchmark problem sets.

    Produces a reproducible set of BenchmarkProblems stratified by
    difficulty tier and frame class, without requiring Lean verification
    (ground truth labels are set to None by default).
    """

    def generate(self, config: BenchmarkConfig) -> list[BenchmarkProblem]:
        """Generate a list of BenchmarkProblems according to config.

        Parameters
        ----------
        config:
            Configuration specifying target size, ratios, and seeds.

        Returns
        -------
        list[BenchmarkProblem]
            Stratified list of benchmark problems (without ground truth labels).
        """
        rng = random.Random(config.seed)

        # Step 1: Enumerate easy/medium formulas
        easy_medium = list(self._enumerate_easy_medium(config))

        # Step 2: Sample hard/very_hard formulas
        hard_very_hard = list(self._sample_hard_very_hard(config, rng))

        # Step 3: Combine all candidates
        all_candidates = easy_medium + hard_very_hard

        # Step 4: Stratify and select
        selected = self._stratify_and_select(all_candidates, config, rng)

        # Step 5: Assign frame classes and create BenchmarkProblem objects
        problems = self._assign_and_create(selected, config, rng)

        return problems

    def _enumerate_easy_medium(self, config: BenchmarkConfig) -> list[FormulaNode]:
        """Exhaustively enumerate easy and medium tier formulas.

        Uses enumerate_up_to_complexity with max_complexity=6 for
        the standard atoms ["p", "q", "r"].
        """
        candidates: list[FormulaNode] = []
        seen: set[str] = set()

        for formula in enumerate_up_to_complexity(
            config.easy_medium_max_complexity, config.atoms
        ):
            tier = _classify_difficulty(formula)
            if tier in ("easy", "medium"):
                # Dedup by JSON repr
                key = json.dumps(formula.to_json(), sort_keys=True)
                if key not in seen:
                    seen.add(key)
                    candidates.append(formula)

        return candidates

    def _sample_hard_very_hard(
        self, config: BenchmarkConfig, rng: random.Random
    ) -> list[FormulaNode]:
        """Sample hard and very_hard tier formulas via random generation.

        Generates random formulas with complexity in the range
        [hard_very_hard_min_complexity, hard_very_hard_max_complexity].
        Requires formulas to have both modal and temporal operators
        to ensure coverage of bimodal logic features.
        """
        candidates: list[FormulaNode] = []
        seen: set[str] = set()

        # Target: enough candidates for hard+very_hard quota with headroom
        target_count = config.target_size * 3  # 3x oversampling
        attempts = 0
        max_attempts = target_count * 20

        while len(candidates) < target_count and attempts < max_attempts:
            attempts += 1
            # Sample complexity uniformly in range
            c = rng.randint(
                config.hard_very_hard_min_complexity,
                config.hard_very_hard_max_complexity,
            )
            formula = random_formula(c, config.atoms, rng)
            tier = _classify_difficulty(formula)
            if tier in ("hard", "very_hard"):
                key = json.dumps(formula.to_json(), sort_keys=True)
                if key not in seen:
                    seen.add(key)
                    candidates.append(formula)

        return candidates

    def _stratify_and_select(
        self,
        candidates: list[FormulaNode],
        config: BenchmarkConfig,
        rng: random.Random,
    ) -> list[FormulaNode]:
        """Select a stratified subset of candidates matching tier distribution.

        Attempts to fill the tier quotas from config.tier_distribution.
        If a tier has fewer candidates than quota, uses all available.
        """
        # Bucket candidates by tier
        by_tier: dict[str, list[FormulaNode]] = defaultdict(list)
        for formula in candidates:
            tier = _classify_difficulty(formula)
            by_tier[tier].append(formula)

        # Shuffle each bucket deterministically
        split_rng = random.Random(SPLIT_SEED)
        for tier in by_tier:
            split_rng.shuffle(by_tier[tier])

        # Calculate quotas
        selected: list[FormulaNode] = []
        for tier, ratio in config.tier_distribution.items():
            quota = int(config.target_size * ratio)
            available = by_tier.get(tier, [])
            selected.extend(available[:quota])

        # Shuffle final selection
        rng.shuffle(selected)
        return selected[: config.target_size]

    def _assign_and_create(
        self,
        formulas: list[FormulaNode],
        config: BenchmarkConfig,
        rng: random.Random,
    ) -> list[BenchmarkProblem]:
        """Assign frame classes and create BenchmarkProblem objects.

        Frame classes are assigned round-robin according to config ratios.
        """
        problems: list[BenchmarkProblem] = []

        # Build a frame class assignment schedule
        n = len(formulas)
        frame_classes: list[str] = []
        for fc, ratio in config.frame_class_distribution.items():
            count = int(n * ratio)
            frame_classes.extend([fc] * count)
        # Fill any remainder with the first frame class
        while len(frame_classes) < n:
            first_fc = next(iter(config.frame_class_distribution))
            frame_classes.append(first_fc)
        frame_classes = frame_classes[:n]

        # Shuffle frame class assignments
        rng.shuffle(frame_classes)

        for idx, (formula, frame_class) in enumerate(zip(formulas, frame_classes)):
            benchmark_id = f"bench_{idx:04d}"
            formula_json = formula.to_json()
            formula_pretty = _formula_to_pretty(formula)
            pattern_key = _extract_pattern_key(formula)
            difficulty_tier = _classify_difficulty(formula)

            problem = BenchmarkProblem(
                benchmark_id=benchmark_id,
                formula_json=formula_json,
                formula_pretty=formula_pretty,
                ground_truth_label=None,
                ground_truth_proof_height=None,
                ground_truth_countermodel=None,
                difficulty_tier=difficulty_tier,
                frame_class=frame_class,
                pattern_key=pattern_key,
            )
            problems.append(problem)

        return problems


def save_jsonl(problems: list[BenchmarkProblem], path: str | Path) -> None:
    """Save a list of BenchmarkProblems to a JSONL file.

    Each line is a JSON-serialized BenchmarkProblem dict.

    Parameters
    ----------
    problems:
        List of BenchmarkProblem instances to save.
    path:
        Output file path (will be created or overwritten).
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for problem in problems:
            f.write(json.dumps(problem.to_dict(), ensure_ascii=False) + "\n")


def load_jsonl(path: str | Path) -> list[BenchmarkProblem]:
    """Load a list of BenchmarkProblems from a JSONL file.

    Parameters
    ----------
    path:
        Input file path.

    Returns
    -------
    list[BenchmarkProblem]
        Deserialized list of BenchmarkProblem instances.
    """
    path = Path(path)
    problems: list[BenchmarkProblem] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                data = json.loads(line)
                problems.append(BenchmarkProblem.from_dict(data))
    return problems


def compute_stats(problems: list[BenchmarkProblem]) -> dict[str, Any]:
    """Compute aggregate statistics for a set of benchmark problems.

    Returns a dict with counts by tier, validity, frame class,
    and structural statistics (complexity, modal depth, etc.).

    Parameters
    ----------
    problems:
        List of BenchmarkProblem instances.

    Returns
    -------
    dict[str, Any]
        Statistics dict with the following keys:
        - total: total number of problems
        - by_tier: count per difficulty tier
        - by_label: count per ground truth label (including None)
        - by_frame_class: count per frame class
        - complexity_stats: min/max/mean complexity
        - modal_depth_stats: min/max/mean modal depth
        - temporal_depth_stats: min/max/mean temporal depth
    """
    if not problems:
        return {
            "total": 0,
            "by_tier": {},
            "by_label": {},
            "by_frame_class": {},
            "complexity_stats": {},
            "modal_depth_stats": {},
            "temporal_depth_stats": {},
        }

    by_tier: dict[str, int] = defaultdict(int)
    by_label: dict[str | None, int] = defaultdict(int)
    by_frame_class: dict[str, int] = defaultdict(int)
    complexities: list[int] = []
    modal_depths: list[int] = []
    temporal_depths: list[int] = []

    for p in problems:
        by_tier[p.difficulty_tier] += 1
        by_label[p.ground_truth_label] += 1
        by_frame_class[p.frame_class] += 1
        complexities.append(p.pattern_key.complexity)
        modal_depths.append(p.pattern_key.modal_depth)
        temporal_depths.append(p.pattern_key.temporal_depth)

    def _stats(values: list[int]) -> dict[str, float]:
        if not values:
            return {}
        return {
            "min": min(values),
            "max": max(values),
            "mean": sum(values) / len(values),
        }

    # Convert defaultdict keys to strings for JSON serialization
    label_counts: dict[str, int] = {
        str(k) if k is not None else "null": v for k, v in by_label.items()
    }

    return {
        "total": len(problems),
        "by_tier": dict(by_tier),
        "by_label": label_counts,
        "by_frame_class": dict(by_frame_class),
        "complexity_stats": _stats(complexities),
        "modal_depth_stats": _stats(modal_depths),
        "temporal_depth_stats": _stats(temporal_depths),
    }


def compute_checksum(path: str | Path) -> str:
    """Compute a SHA-256 checksum for a file.

    Parameters
    ----------
    path:
        Path to the file to checksum.

    Returns
    -------
    str
        Hex-encoded SHA-256 digest.
    """
    path = Path(path)
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def write_checksums(paths: list[Path], output_path: Path) -> None:
    """Write SHA-256 checksums for a list of files to an output file.

    Output format: ``{checksum}  {filename}`` (one per line),
    matching the standard sha256sum format.

    Parameters
    ----------
    paths:
        List of file paths to checksum.
    output_path:
        Path to write the checksums file.
    """
    lines: list[str] = []
    for path in paths:
        checksum = compute_checksum(path)
        lines.append(f"{checksum}  {path.name}")
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
