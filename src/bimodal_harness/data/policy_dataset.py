"""Dataset and collate utilities for policy network training on ProofStepRecords.

Provides:
- ProofStepDataset: PyTorch Dataset wrapping a list of ProofStepRecords
- policy_collate_fn: Collate function returning (features, targets, masks)
- split_proof_steps: Train/val/test split with optional action-index stratification
"""

from __future__ import annotations

import random
from collections import defaultdict
from typing import Any

import torch
import torch.utils.data

from bimodal_harness.models.policy import encode_proof_step
from bimodal_harness.schema.actions import FRAME_CLASS_MASKS
from bimodal_harness.schema.records import ProofStepRecord


# ---------------------------------------------------------------------------
# ProofStepDataset
# ---------------------------------------------------------------------------


class ProofStepDataset(torch.utils.data.Dataset):
    """PyTorch Dataset wrapping a list of ProofStepRecords.

    Parameters
    ----------
    records:
        List of ProofStepRecord instances.
    """

    def __init__(self, records: list[ProofStepRecord]) -> None:
        self._records = records

    def __len__(self) -> int:
        return len(self._records)

    def __getitem__(self, idx: int) -> ProofStepRecord:
        return self._records[idx]

    @property
    def labels(self) -> list[int]:
        """Return action indices for all records."""
        return [r.action_index for r in self._records]

    @property
    def frame_classes(self) -> list[str]:
        """Return frame class strings for all records."""
        return [r.frame_class for r in self._records]


# ---------------------------------------------------------------------------
# policy_collate_fn
# ---------------------------------------------------------------------------


def policy_collate_fn(
    records: list[ProofStepRecord],
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    """Collate a list of ProofStepRecords into feature, target, and mask tensors.

    Parameters
    ----------
    records:
        List of ProofStepRecord items from a DataLoader batch.

    Returns
    -------
    tuple[Tensor, Tensor, Tensor]
        - features: shape [B, 25] float32
        - targets: shape [B] int64, action indices
        - masks: shape [B, 49] float32, 1.0 for valid actions, 0.0 for invalid
    """
    feature_list: list[torch.Tensor] = []
    target_list: list[int] = []
    mask_list: list[torch.Tensor] = []

    for rec in records:
        feat = encode_proof_step(rec)  # [25]
        feature_list.append(feat)
        target_list.append(rec.action_index)

        fc_mask = FRAME_CLASS_MASKS.get(rec.frame_class, FRAME_CLASS_MASKS["Base"])
        mask_tensor = torch.tensor(fc_mask, dtype=torch.float32)  # [49]
        mask_list.append(mask_tensor)

    if not feature_list:
        return (
            torch.zeros((0, 25), dtype=torch.float32),
            torch.zeros(0, dtype=torch.int64),
            torch.zeros((0, 49), dtype=torch.float32),
        )

    features = torch.stack(feature_list, dim=0)  # [B, 25]
    targets = torch.tensor(target_list, dtype=torch.int64)  # [B]
    masks = torch.stack(mask_list, dim=0)  # [B, 49]
    return features, targets, masks


# ---------------------------------------------------------------------------
# split_proof_steps
# ---------------------------------------------------------------------------


def split_proof_steps(
    records: list[tuple[ProofStepRecord, str]],
    *,
    train_frac: float = 0.8,
    val_frac: float = 0.1,
    seed: int = 42,
    stratify_by_action: bool = True,
) -> tuple[
    list[ProofStepRecord],
    list[ProofStepRecord],
    list[ProofStepRecord],
]:
    """Split (ProofStepRecord, source) tuples into train/val/test sets.

    Parameters
    ----------
    records:
        List of (ProofStepRecord, augmentation_source) tuples.
    train_frac:
        Fraction of records assigned to training split. Default: 0.8.
    val_frac:
        Fraction of records assigned to validation split. Default: 0.1.
    seed:
        Random seed for reproducibility. Default: 42.
    stratify_by_action:
        If True, stratify split by action_index to preserve class balance.
        Default: True.

    Returns
    -------
    tuple[list[ProofStepRecord], list[ProofStepRecord], list[ProofStepRecord]]
        (train, val, test) lists of ProofStepRecord.

    Raises
    ------
    ValueError
        If fractions are out of range or sum to >= 1.0.
    """
    if train_frac <= 0 or train_frac >= 1:
        raise ValueError(f"train_frac must be in (0, 1), got {train_frac}")
    if val_frac <= 0 or val_frac >= 1:
        raise ValueError(f"val_frac must be in (0, 1), got {val_frac}")
    if train_frac + val_frac >= 1.0:
        raise ValueError(
            f"train_frac + val_frac must be < 1.0, got {train_frac + val_frac}"
        )

    rng = random.Random(seed)
    # Extract just the records (discard sources)
    items = [r for r, _ in records]

    train: list[ProofStepRecord] = []
    val: list[ProofStepRecord] = []
    test: list[ProofStepRecord] = []

    if stratify_by_action and items:
        strata: dict[int, list[ProofStepRecord]] = defaultdict(list)
        for rec in items:
            strata[rec.action_index].append(rec)

        for action_idx in sorted(strata):
            stratum = list(strata[action_idx])
            rng.shuffle(stratum)
            n = len(stratum)
            n_train = max(1, round(n * train_frac)) if n >= 3 else n
            n_val = max(0, round(n * val_frac)) if n >= 3 else 0
            if n_train + n_val > n:
                n_val = max(0, n - n_train)
            train.extend(stratum[:n_train])
            val.extend(stratum[n_train : n_train + n_val])
            test.extend(stratum[n_train + n_val :])
    else:
        shuffled = list(items)
        rng.shuffle(shuffled)
        n = len(shuffled)
        n_train = round(n * train_frac)
        n_val = round(n * val_frac)
        train = shuffled[:n_train]
        val = shuffled[n_train : n_train + n_val]
        test = shuffled[n_train + n_val :]

    return train, val, test
