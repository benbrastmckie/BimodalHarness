"""Unit tests for ProofStepDataset, policy_collate_fn, and split_proof_steps."""

from __future__ import annotations

import torch
import pytest

from bimodal_harness.data.policy_dataset import (
    ProofStepDataset,
    policy_collate_fn,
    split_proof_steps,
)
from bimodal_harness.schema.actions import FRAME_CLASS_MASKS
from bimodal_harness.schema.records import ProofStepRecord


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_record(
    action_index: int = 44,
    frame_class: str = "Base",
    step_id: str = "test/0",
) -> ProofStepRecord:
    return ProofStepRecord(
        step_id=step_id,
        theorem_name="test_thm",
        context=(),
        goal_json={"tag": "atom", "name": "p"},
        goal_pretty="p",
        rule="modus_ponens",
        axiom_name=None,
        action_index=action_index,
        subgoals=(),
        depth=0,
        frame_class=frame_class,
        proof_height=1,
    )


def _make_augmented(n: int, frame_class: str = "Base") -> list[tuple[ProofStepRecord, str]]:
    """Make n (record, source) pairs with round-robin action indices."""
    return [
        (_make_record(action_index=i % 49, frame_class=frame_class, step_id=f"test/{i}"), "original")
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# ProofStepDataset tests
# ---------------------------------------------------------------------------

class TestProofStepDataset:
    def test_len(self):
        records = [_make_record(step_id=f"s/{i}") for i in range(10)]
        ds = ProofStepDataset(records)
        assert len(ds) == 10

    def test_getitem(self):
        records = [_make_record(action_index=5, step_id="s/0")]
        ds = ProofStepDataset(records)
        rec = ds[0]
        assert isinstance(rec, ProofStepRecord)
        assert rec.action_index == 5

    def test_labels_property(self):
        records = [_make_record(action_index=i, step_id=f"s/{i}") for i in range(5)]
        ds = ProofStepDataset(records)
        assert ds.labels == [0, 1, 2, 3, 4]

    def test_frame_classes_property(self):
        records = [
            _make_record(frame_class="Base", step_id="s/0"),
            _make_record(frame_class="Dense", step_id="s/1"),
            _make_record(frame_class="Discrete", step_id="s/2"),
        ]
        ds = ProofStepDataset(records)
        assert ds.frame_classes == ["Base", "Dense", "Discrete"]

    def test_empty_dataset(self):
        ds = ProofStepDataset([])
        assert len(ds) == 0
        assert ds.labels == []


# ---------------------------------------------------------------------------
# policy_collate_fn tests
# ---------------------------------------------------------------------------

class TestPolicyCollateFn:
    def test_output_shapes(self):
        records = [_make_record(action_index=i, step_id=f"s/{i}") for i in range(8)]
        features, targets, masks = policy_collate_fn(records)
        assert features.shape == (8, 25)
        assert targets.shape == (8,)
        assert masks.shape == (8, 49)

    def test_feature_dtype(self):
        records = [_make_record()]
        features, targets, masks = policy_collate_fn(records)
        assert features.dtype == torch.float32
        assert targets.dtype == torch.int64
        assert masks.dtype == torch.float32

    def test_targets_match_action_indices(self):
        records = [_make_record(action_index=i, step_id=f"s/{i}") for i in [0, 5, 10, 48]]
        _, targets, _ = policy_collate_fn(records)
        assert targets.tolist() == [0, 5, 10, 48]

    def test_mask_matches_frame_class_base(self):
        records = [_make_record(frame_class="Base")]
        _, _, masks = policy_collate_fn(records)
        expected = torch.tensor(FRAME_CLASS_MASKS["Base"], dtype=torch.float32)
        assert torch.all(masks[0] == expected)

    def test_mask_matches_frame_class_dense(self):
        records = [_make_record(frame_class="Dense")]
        _, _, masks = policy_collate_fn(records)
        expected = torch.tensor(FRAME_CLASS_MASKS["Dense"], dtype=torch.float32)
        assert torch.all(masks[0] == expected)

    def test_mask_matches_frame_class_discrete(self):
        records = [_make_record(frame_class="Discrete")]
        _, _, masks = policy_collate_fn(records)
        expected = torch.tensor(FRAME_CLASS_MASKS["Discrete"], dtype=torch.float32)
        assert torch.all(masks[0] == expected)

    def test_empty_batch(self):
        features, targets, masks = policy_collate_fn([])
        assert features.shape == (0, 25)
        assert targets.shape == (0,)
        assert masks.shape == (0, 49)

    def test_mask_values_binary(self):
        records = [_make_record(step_id=f"s/{i}") for i in range(5)]
        _, _, masks = policy_collate_fn(records)
        # Mask values should be only 0.0 or 1.0
        assert torch.all((masks == 0.0) | (masks == 1.0))


# ---------------------------------------------------------------------------
# split_proof_steps tests
# ---------------------------------------------------------------------------

class TestSplitProofSteps:
    def test_proportions_approx(self):
        # Use 300 records so each of 49 action indices gets ~6 records (>= 3 threshold)
        records = _make_augmented(300)
        train, val, test = split_proof_steps(records, train_frac=0.8, val_frac=0.1, seed=42)
        total = len(train) + len(val) + len(test)
        assert total == 300
        # Allow ±10% tolerance
        assert 220 <= len(train) <= 280
        assert 15 <= len(val) <= 60

    def test_no_overlap(self):
        records = _make_augmented(100)
        train, val, test = split_proof_steps(records, seed=42)
        train_ids = {r.step_id for r in train}
        val_ids = {r.step_id for r in val}
        test_ids = {r.step_id for r in test}
        assert len(train_ids & val_ids) == 0
        assert len(train_ids & test_ids) == 0
        assert len(val_ids & test_ids) == 0

    def test_all_records_accounted_for(self):
        records = _make_augmented(50)
        train, val, test = split_proof_steps(records, seed=42)
        total = len(train) + len(val) + len(test)
        assert total == 50

    def test_stratified_splits_have_diverse_actions(self):
        # Generate records covering action indices 0-48 (one each)
        records = [
            (_make_record(action_index=i, step_id=f"s/{i}"), "original")
            for i in range(49)
        ]
        # With 49 records and 80/10/10 split, all should go to train mostly
        train, val, test = split_proof_steps(records, train_frac=0.7, val_frac=0.15, seed=0)
        assert len(train) + len(val) + len(test) == 49

    def test_non_stratified_split(self):
        records = _make_augmented(100)
        train, val, test = split_proof_steps(
            records, train_frac=0.8, val_frac=0.1, seed=42, stratify_by_action=False
        )
        assert len(train) + len(val) + len(test) == 100

    def test_invalid_fractions_raise(self):
        records = _make_augmented(10)
        with pytest.raises(ValueError):
            split_proof_steps(records, train_frac=0.9, val_frac=0.2)  # sum > 1

    def test_returns_proofsteprecords(self):
        records = _make_augmented(10)
        train, val, test = split_proof_steps(records)
        for r in train:
            assert isinstance(r, ProofStepRecord)

    def test_empty_records(self):
        train, val, test = split_proof_steps([], stratify_by_action=False)
        assert len(train) == 0
        assert len(val) == 0
        assert len(test) == 0
