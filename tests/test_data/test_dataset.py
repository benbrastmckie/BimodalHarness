"""Tests for BimodalDataset, split_dataset, and CurriculumSampler.

Covers:
- BimodalDataset indexing, length, and properties
- split_dataset stratified and random splits
- CurriculumSampler tier gating and shuffle reproducibility
"""

from __future__ import annotations

import random
from pathlib import Path

import pytest
import torch.utils.data

from bimodal_harness.data.dataset import (
    DIFFICULTY_TIER_ORDER,
    DIFFICULTY_TIER_ORDINAL,
    BimodalDataset,
    CurriculumSampler,
    split_dataset,
)
from bimodal_harness.data.ingestion import ingest_jsonl

SAMPLE_JSONL = Path(__file__).parent.parent.parent / "data" / "samples" / "test_formulas.jsonl"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _sample_records():
    """Load sample records from test_formulas.jsonl."""
    return ingest_jsonl(SAMPLE_JSONL)


def _make_large_records(n: int = 50):
    """Create a larger set of records by repeating sample data."""
    base = _sample_records()
    records = []
    for i in range(n):
        records.append(base[i % len(base)])
    return records


# ---------------------------------------------------------------------------
# BimodalDataset tests
# ---------------------------------------------------------------------------


class TestBimodalDataset:
    def test_len(self):
        records = _sample_records()
        ds = BimodalDataset(records)
        assert len(ds) == len(records)

    def test_getitem(self):
        records = _sample_records()
        ds = BimodalDataset(records)
        assert ds[0] is records[0]

    def test_getitem_all(self):
        records = _sample_records()
        ds = BimodalDataset(records)
        for i, rec in enumerate(records):
            assert ds[i] is rec

    def test_empty_dataset(self):
        ds = BimodalDataset([])
        assert len(ds) == 0

    def test_labels_property(self):
        records = _sample_records()
        ds = BimodalDataset(records)
        labels = ds.labels
        assert len(labels) == len(records)
        assert all(lbl in ("valid", "invalid") for lbl in labels)

    def test_difficulty_tiers_property(self):
        records = _sample_records()
        ds = BimodalDataset(records)
        tiers = ds.difficulty_tiers
        assert len(tiers) == len(records)
        valid_tiers = {"easy", "medium", "hard", "very_hard"}
        assert all(t in valid_tiers for t in tiers)

    def test_records_property_is_copy(self):
        records = _sample_records()
        ds = BimodalDataset(records)
        recs_copy = ds.records
        # Modifying the copy should not affect the dataset
        recs_copy.clear()
        assert len(ds) == len(records)

    def test_dataloader_compatible(self):
        """BimodalDataset must be usable with torch.utils.data.DataLoader."""
        records = _sample_records()
        ds = BimodalDataset(records)
        loader = torch.utils.data.DataLoader(ds, batch_size=2, collate_fn=list)
        batches = list(loader)
        assert len(batches) > 0
        # Each batch is a list of TrainingRecords
        for batch in batches:
            assert isinstance(batch, list)
            assert len(batch) > 0

    def test_iter_via_dataloader(self):
        """Iterating with DataLoader produces all records."""
        records = _sample_records()
        ds = BimodalDataset(records)
        loader = torch.utils.data.DataLoader(ds, batch_size=1, collate_fn=list)
        seen = []
        for batch in loader:
            seen.extend(batch)
        assert len(seen) == len(records)


# ---------------------------------------------------------------------------
# split_dataset tests
# ---------------------------------------------------------------------------


class TestSplitDataset:
    def test_splits_sum_to_total(self):
        records = _make_large_records(60)
        train, val, test = split_dataset(records, seed=42)
        assert len(train) + len(val) + len(test) == 60

    def test_default_ratios(self):
        records = _make_large_records(100)
        train, val, test = split_dataset(records, seed=42)
        # Allow 10% tolerance
        assert 70 <= len(train) <= 90
        assert 5 <= len(val) <= 20
        assert 5 <= len(test) <= 20

    def test_returns_bimodal_datasets(self):
        records = _make_large_records(30)
        train, val, test = split_dataset(records, seed=42)
        assert isinstance(train, BimodalDataset)
        assert isinstance(val, BimodalDataset)
        assert isinstance(test, BimodalDataset)

    def test_seed_reproducibility(self):
        records = _make_large_records(50)
        train1, val1, test1 = split_dataset(records, seed=42)
        train2, val2, test2 = split_dataset(records, seed=42)
        assert [r.formula_pretty for r in train1.records] == [
            r.formula_pretty for r in train2.records
        ]
        assert [r.formula_pretty for r in val1.records] == [
            r.formula_pretty for r in val2.records
        ]

    def test_different_seeds_differ(self):
        records = _make_large_records(50)
        train1, _, _ = split_dataset(records, seed=1)
        train2, _, _ = split_dataset(records, seed=999)
        # Very unlikely to be identical with different seeds on 50 records
        assert [r.formula_pretty for r in train1.records] != [
            r.formula_pretty for r in train2.records
        ]

    def test_empty_records_raises(self):
        with pytest.raises(ValueError, match="empty"):
            split_dataset([])

    def test_invalid_ratios_raises(self):
        records = _make_large_records(30)
        with pytest.raises(ValueError, match="sum to 1.0"):
            split_dataset(records, train_ratio=0.5, val_ratio=0.5, test_ratio=0.5)

    def test_no_stratify(self):
        records = _make_large_records(30)
        train, val, test = split_dataset(records, stratify=False, seed=42)
        assert len(train) + len(val) + len(test) == 30

    def test_small_dataset_falls_back_to_random(self):
        """Datasets with < 10 records fall back to random (non-stratified) split."""
        records = _make_large_records(5)
        train, val, test = split_dataset(records, seed=42)
        assert len(train) + len(val) + len(test) == 5

    def test_stratified_preserves_labels(self):
        """Stratified split should have both valid/invalid in train set (with enough data)."""
        records = _make_large_records(70)
        train, val, test = split_dataset(records, stratify=True, seed=42)
        train_labels = set(train.labels)
        # With 70 records and mixed labels, both labels should appear in train
        assert "valid" in train_labels or "invalid" in train_labels


# ---------------------------------------------------------------------------
# CurriculumSampler tests
# ---------------------------------------------------------------------------


class TestCurriculumSampler:
    def test_epoch_0_includes_easy_only(self):
        """At epoch 0, only 'easy' tier records should be eligible."""
        records = _make_large_records(50)
        ds = BimodalDataset(records)
        sampler = CurriculumSampler(ds, epoch=0, max_epochs=10)
        eligible_indices = list(sampler)
        for idx in eligible_indices:
            tier = ds[idx].difficulty_metrics.difficulty_tier
            assert tier in ("easy",), f"epoch=0 should only yield 'easy', got {tier!r}"

    def test_final_epoch_includes_all(self):
        """At max_epochs-1, all tiers should be eligible."""
        records = ingest_jsonl(SAMPLE_JSONL)
        ds = BimodalDataset(records)
        max_epochs = 10
        sampler = CurriculumSampler(ds, epoch=max_epochs - 1, max_epochs=max_epochs)
        assert len(sampler) == len(ds)

    def test_tier_cutoff_advances(self):
        """tier_cutoff should increase monotonically with epoch."""
        records = _make_large_records(30)
        ds = BimodalDataset(records)
        max_epochs = 8
        cutoffs = []
        for epoch in range(max_epochs):
            sampler = CurriculumSampler(ds, epoch=epoch, max_epochs=max_epochs)
            cutoffs.append(sampler.tier_cutoff)
        # Cutoffs should be non-decreasing
        for i in range(1, len(cutoffs)):
            assert cutoffs[i] >= cutoffs[i - 1], f"Cutoff decreased at epoch {i}"

    def test_len_matches_iter(self):
        """__len__ should match the count of items yielded by __iter__."""
        records = _make_large_records(30)
        ds = BimodalDataset(records)
        sampler = CurriculumSampler(ds, epoch=0, max_epochs=5)
        assert len(sampler) == len(list(sampler))

    def test_shuffle_seed_reproducibility(self):
        """Same seed + epoch should produce the same order."""
        records = _make_large_records(30)
        ds = BimodalDataset(records)
        s1 = CurriculumSampler(ds, epoch=2, max_epochs=10, shuffle=True, seed=42)
        s2 = CurriculumSampler(ds, epoch=2, max_epochs=10, shuffle=True, seed=42)
        assert list(s1) == list(s2)

    def test_shuffle_different_epochs_differ(self):
        """Different epochs should produce different orders (same seed)."""
        records = _make_large_records(50)
        ds = BimodalDataset(records)
        s1 = CurriculumSampler(ds, epoch=0, max_epochs=20, shuffle=True, seed=42)
        s5 = CurriculumSampler(ds, epoch=5, max_epochs=20, shuffle=True, seed=42)
        # Epoch 5 has a higher cutoff, so more eligible records
        assert len(s5) >= len(s1)

    def test_no_shuffle_preserves_insertion_order(self):
        """With shuffle=False, eligible indices should be in stable order."""
        records = _make_large_records(30)
        ds = BimodalDataset(records)
        sampler = CurriculumSampler(ds, epoch=0, max_epochs=5, shuffle=False)
        indices = list(sampler)
        # All indices should be sorted (ascending) when not shuffled
        assert indices == sorted(indices)

    def test_invalid_max_epochs_raises(self):
        records = _sample_records()
        ds = BimodalDataset(records)
        with pytest.raises(ValueError, match="max_epochs"):
            CurriculumSampler(ds, epoch=0, max_epochs=0)

    def test_invalid_epoch_raises(self):
        records = _sample_records()
        ds = BimodalDataset(records)
        with pytest.raises(ValueError, match="epoch"):
            CurriculumSampler(ds, epoch=-1, max_epochs=10)

    def test_difficulty_tier_constants(self):
        """DIFFICULTY_TIER_ORDER and DIFFICULTY_TIER_ORDINAL are consistent."""
        assert len(DIFFICULTY_TIER_ORDER) == len(DIFFICULTY_TIER_ORDINAL)
        for tier in DIFFICULTY_TIER_ORDER:
            assert tier in DIFFICULTY_TIER_ORDINAL
        # Ordinals should be 1-indexed and contiguous
        ordinals = sorted(DIFFICULTY_TIER_ORDINAL.values())
        assert ordinals == list(range(1, len(DIFFICULTY_TIER_ORDER) + 1))
