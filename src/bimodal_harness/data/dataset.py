"""PyTorch dataset classes for BimodalHarness training data.

Provides:
- BimodalDataset: torch.utils.data.Dataset wrapping list[TrainingRecord]
- split_dataset: Stratified train/val/test partitioning
- CurriculumSampler: Epoch-gated difficulty progression sampler
"""

from __future__ import annotations

import random
from collections import defaultdict
from typing import TYPE_CHECKING

import torch.utils.data

from bimodal_harness.schema.records import TrainingRecord

if TYPE_CHECKING:
    pass


# ---------------------------------------------------------------------------
# BimodalDataset
# ---------------------------------------------------------------------------


class BimodalDataset(torch.utils.data.Dataset):
    """PyTorch Dataset wrapping a list of TrainingRecord objects.

    Each item is returned as-is (a TrainingRecord). Tensor encoding of
    formula ASTs is deferred to task 20 and is handled in a custom
    collate_fn or a transform layer.

    Parameters
    ----------
    records:
        List of training records to wrap.
    """

    def __init__(self, records: list[TrainingRecord]) -> None:
        self._records = list(records)

    def __len__(self) -> int:
        """Return the number of records in the dataset."""
        return len(self._records)

    def __getitem__(self, index: int) -> TrainingRecord:
        """Return the record at the given index.

        Parameters
        ----------
        index:
            Integer index into the dataset.

        Returns
        -------
        TrainingRecord
            The record at the given position.
        """
        return self._records[index]

    @property
    def records(self) -> list[TrainingRecord]:
        """Return the underlying list of records (read-only view)."""
        return list(self._records)

    @property
    def labels(self) -> list[str]:
        """Return label strings for all records (useful for stratification)."""
        return [r.label for r in self._records]

    @property
    def difficulty_tiers(self) -> list[str]:
        """Return difficulty tier strings for all records."""
        return [r.difficulty_metrics.difficulty_tier for r in self._records]


# ---------------------------------------------------------------------------
# split_dataset
# ---------------------------------------------------------------------------


def split_dataset(
    records: list[TrainingRecord],
    *,
    train_ratio: float = 0.8,
    val_ratio: float = 0.1,
    test_ratio: float = 0.1,
    stratify: bool = True,
    seed: int = 42,
) -> tuple[BimodalDataset, BimodalDataset, BimodalDataset]:
    """Partition records into train, validation, and test BimodalDatasets.

    When stratify=True, performs stratified sampling on (label, difficulty_tier)
    to preserve class proportions. Falls back to a random (unstratified) split
    when there are too few records for stratification (< 10 total records) or
    when any stratum is too small to include in all three splits.

    Parameters
    ----------
    records:
        List of training records to split.
    train_ratio:
        Fraction of data for training (default: 0.8).
    val_ratio:
        Fraction of data for validation (default: 0.1).
    test_ratio:
        Fraction of data for testing (default: 0.1).
    stratify:
        Whether to perform stratified splitting (default: True).
    seed:
        Random seed for reproducibility (default: 42).

    Returns
    -------
    tuple[BimodalDataset, BimodalDataset, BimodalDataset]
        (train_dataset, val_dataset, test_dataset)

    Raises
    ------
    ValueError
        If ratios do not sum to approximately 1.0, or if records is empty.
    """
    if not records:
        raise ValueError("Cannot split an empty list of records.")

    total = abs(train_ratio + val_ratio + test_ratio - 1.0)
    if total > 1e-6:
        raise ValueError(
            f"train_ratio + val_ratio + test_ratio must sum to 1.0, "
            f"got {train_ratio + val_ratio + test_ratio:.6f}"
        )

    rng = random.Random(seed)

    # Too few records for meaningful stratification (fallback threshold)
    if len(records) < 10:
        stratify = False

    if stratify:
        train_recs, val_recs, test_recs = _stratified_split(
            records, train_ratio=train_ratio, val_ratio=val_ratio, rng=rng
        )
    else:
        train_recs, val_recs, test_recs = _random_split(
            records, train_ratio=train_ratio, val_ratio=val_ratio, rng=rng
        )

    return BimodalDataset(train_recs), BimodalDataset(val_recs), BimodalDataset(test_recs)


def _random_split(
    records: list[TrainingRecord],
    *,
    train_ratio: float,
    val_ratio: float,
    rng: random.Random,
) -> tuple[list[TrainingRecord], list[TrainingRecord], list[TrainingRecord]]:
    """Perform a random (unstratified) split."""
    shuffled = list(records)
    rng.shuffle(shuffled)
    n = len(shuffled)
    train_end = max(1, int(n * train_ratio))
    val_end = train_end + max(0, int(n * val_ratio))
    return shuffled[:train_end], shuffled[train_end:val_end], shuffled[val_end:]


def _stratified_split(
    records: list[TrainingRecord],
    *,
    train_ratio: float,
    val_ratio: float,
    rng: random.Random,
) -> tuple[list[TrainingRecord], list[TrainingRecord], list[TrainingRecord]]:
    """Perform stratified split on (label, difficulty_tier).

    Falls back to random split if any stratum has fewer than 3 records.
    """
    # Group records by (label, difficulty_tier)
    strata: dict[tuple[str, str], list[TrainingRecord]] = defaultdict(list)
    for rec in records:
        key = (rec.label, rec.difficulty_metrics.difficulty_tier)
        strata[key].append(rec)

    train_recs: list[TrainingRecord] = []
    val_recs: list[TrainingRecord] = []
    test_recs: list[TrainingRecord] = []

    for stratum_records in strata.values():
        # Fall back to random split for strata too small to split across 3 splits
        if len(stratum_records) < 3:
            # Add all to train as fallback
            train_recs.extend(stratum_records)
            continue

        shuffled = list(stratum_records)
        rng.shuffle(shuffled)
        n = len(shuffled)
        train_end = max(1, int(n * train_ratio))
        val_end = train_end + max(1, int(n * val_ratio))
        # Ensure at least one record goes to test
        if val_end >= n:
            val_end = n - 1
        if train_end >= val_end:
            train_end = val_end - 1

        train_recs.extend(shuffled[:train_end])
        val_recs.extend(shuffled[train_end:val_end])
        test_recs.extend(shuffled[val_end:])

    # If stratification produced empty val/test, fall back to random
    if not val_recs or not test_recs:
        return _random_split(records, train_ratio=train_ratio, val_ratio=val_ratio, rng=rng)

    return train_recs, val_recs, test_recs


# ---------------------------------------------------------------------------
# CurriculumSampler
# ---------------------------------------------------------------------------

# Ordered list of difficulty tiers from easiest to hardest, for curriculum gating.
DIFFICULTY_TIER_ORDER: list[str] = ["easy", "medium", "hard", "very_hard"]

#: Maps difficulty tier string to ordinal (1-based), for tier cutoff comparison.
DIFFICULTY_TIER_ORDINAL: dict[str, int] = {
    tier: i + 1 for i, tier in enumerate(DIFFICULTY_TIER_ORDER)
}


class CurriculumSampler(torch.utils.data.Sampler):
    """Epoch-gated difficulty progression sampler for curriculum learning.

    At each epoch, only records with difficulty_tier <= tier_cutoff are eligible.
    The cutoff advances linearly from tier 1 (easy-only) at epoch 0 to tier 4
    (all tiers) at epoch max_epochs-1, ensuring the model sees progressively
    harder examples as training progresses.

    Tier cutoff formula:
        tier_cutoff = 1 + int(3 * epoch / max_epochs)
        clamped to [1, len(DIFFICULTY_TIER_ORDER)]

    Parameters
    ----------
    dataset:
        BimodalDataset to sample from.
    epoch:
        Current training epoch (0-indexed).
    max_epochs:
        Total number of training epochs.
    shuffle:
        Whether to shuffle the eligible indices at each call to __iter__
        (default: True).
    seed:
        Random seed for shuffle reproducibility (default: 42).
    """

    def __init__(
        self,
        dataset: BimodalDataset,
        *,
        epoch: int,
        max_epochs: int,
        shuffle: bool = True,
        seed: int = 42,
    ) -> None:
        if max_epochs <= 0:
            raise ValueError(f"max_epochs must be > 0, got {max_epochs}")
        if epoch < 0:
            raise ValueError(f"epoch must be >= 0, got {epoch}")

        self._dataset = dataset
        self._epoch = epoch
        self._max_epochs = max_epochs
        self._shuffle = shuffle
        self._seed = seed

        # Compute tier cutoff for this epoch.
        # Scale 0..max_epochs-1 linearly to 0..3 (4 tiers total)
        n_tiers = len(DIFFICULTY_TIER_ORDER)
        tier_cutoff = 1 + int((n_tiers - 1) * epoch / max(max_epochs - 1, 1))
        self._tier_cutoff = min(tier_cutoff, n_tiers)

        # Compute eligible indices once at construction.
        self._eligible_indices = [
            i
            for i, rec in enumerate(dataset.records)
            if DIFFICULTY_TIER_ORDINAL.get(rec.difficulty_metrics.difficulty_tier, 1)
            <= self._tier_cutoff
        ]

    @property
    def tier_cutoff(self) -> int:
        """Current tier cutoff ordinal (1 = easy-only, 4 = all tiers)."""
        return self._tier_cutoff

    def __len__(self) -> int:
        """Return the number of eligible samples for this epoch."""
        return len(self._eligible_indices)

    def __iter__(self):
        """Yield eligible indices, optionally shuffled."""
        indices = list(self._eligible_indices)
        if self._shuffle:
            # Use a deterministic seed per epoch to ensure reproducibility
            rng = random.Random(self._seed + self._epoch)
            rng.shuffle(indices)
        yield from indices
