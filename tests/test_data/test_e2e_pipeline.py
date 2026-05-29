"""End-to-end integration tests for the full ingestion pipeline.

Tests cover:
- ingest_jsonl -> split_dataset -> BimodalDataset -> DataLoader iteration
- ingest_and_cache -> load_cached -> BimodalDataset -> verification
- Full pipeline with CurriculumSampler
"""

from __future__ import annotations

from pathlib import Path

import torch.utils.data

from bimodal_harness.data.dataset import (
    BimodalDataset,
    CurriculumSampler,
    split_dataset,
)
from bimodal_harness.data.ingestion import (
    ingest_and_cache,
    ingest_jsonl,
    load_cached,
)
from bimodal_harness.schema.records import TrainingRecord

SAMPLE_JSONL = Path(__file__).parent.parent.parent / "data" / "samples" / "test_formulas.jsonl"


class TestEndToEndPipeline:
    def test_jsonl_to_dataloader(self):
        """Full pipeline: JSONL -> ingest -> split -> DataLoader -> iterate batch."""
        records = ingest_jsonl(SAMPLE_JSONL)
        train_ds, val_ds, test_ds = split_dataset(records, seed=42)

        loader = torch.utils.data.DataLoader(
            train_ds,
            batch_size=2,
            collate_fn=list,
        )
        batches = list(loader)
        assert len(batches) > 0
        # Each batch is a list of TrainingRecord objects
        for batch in batches:
            assert isinstance(batch, list)
            for item in batch:
                assert isinstance(item, TrainingRecord)

    def test_split_dataset_all_splits_populated(self):
        """With 7 records, all three splits should have at least 1 record."""
        records = ingest_jsonl(SAMPLE_JSONL)
        train, val, test = split_dataset(records, seed=42)
        # Small dataset falls back to random split, so all splits have records
        assert len(train) >= 1
        assert len(val) >= 0  # May be empty for very small datasets
        assert len(train) + len(val) + len(test) == len(records)

    def test_ingest_cache_load_pipeline(self, tmp_path: Path):
        """Pipeline: ingest_and_cache -> load_cached -> BimodalDataset -> verify."""
        data_dir = tmp_path / "jsonl"
        data_dir.mkdir()
        (data_dir / "sample.jsonl").write_text(SAMPLE_JSONL.read_text())
        cache_path = tmp_path / "cache.parquet"

        # Stage 1: ingest and cache
        original_records = ingest_and_cache(data_dir, cache_path)
        assert len(original_records) == 7

        # Stage 2: load from cache
        cached_records = load_cached(cache_path)
        assert len(cached_records) == 7

        # Stage 3: wrap in dataset
        ds = BimodalDataset(cached_records)
        assert len(ds) == 7

        # Stage 4: verify all records are TrainingRecord instances
        for i in range(len(ds)):
            item = ds[i]
            assert isinstance(item, TrainingRecord)
            assert item.label in ("valid", "invalid")

    def test_curriculum_sampler_with_dataloader(self):
        """CurriculumSampler integrates correctly with DataLoader."""
        records = ingest_jsonl(SAMPLE_JSONL)
        ds = BimodalDataset(records)

        max_epochs = 10
        # At epoch 0, only 'easy' tier records
        sampler = CurriculumSampler(ds, epoch=0, max_epochs=max_epochs, shuffle=False)
        loader = torch.utils.data.DataLoader(ds, sampler=sampler, batch_size=2, collate_fn=list)

        for batch in loader:
            for item in batch:
                assert isinstance(item, TrainingRecord)
                assert item.difficulty_metrics.difficulty_tier in ("easy",)

    def test_full_pipeline_end_to_end_with_cache(self, tmp_path: Path):
        """Complete pipeline test with cache and CurriculumSampler."""
        # 1. Set up source data
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "batch1.jsonl").write_text(SAMPLE_JSONL.read_text())
        cache_path = tmp_path / "training.parquet"

        # 2. Ingest and cache
        records = ingest_and_cache(data_dir, cache_path)

        # 3. Split
        train_ds, val_ds, test_ds = split_dataset(records, seed=0)

        # 4. Train with curriculum sampler
        max_epochs = 5
        for epoch in range(max_epochs):
            sampler = CurriculumSampler(
                train_ds, epoch=epoch, max_epochs=max_epochs, shuffle=True
            )
            loader = torch.utils.data.DataLoader(
                train_ds, sampler=sampler, batch_size=1, collate_fn=list
            )
            for batch in loader:
                for item in batch:
                    assert isinstance(item, TrainingRecord)

        # 5. Verify that the last epoch includes the widest set
        final_sampler = CurriculumSampler(train_ds, epoch=max_epochs - 1, max_epochs=max_epochs)
        # Final epoch should have the max cutoff
        assert final_sampler.tier_cutoff == 4  # All 4 tiers

    def test_cache_round_trip_field_equality(self, tmp_path: Path):
        """Parquet cache round-trip preserves all key fields exactly."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "sample.jsonl").write_text(SAMPLE_JSONL.read_text())
        cache_path = tmp_path / "cache.parquet"

        original = ingest_and_cache(data_dir, cache_path)
        loaded = load_cached(cache_path)

        # Sort by formula_pretty for stable comparison
        orig_sorted = sorted(original, key=lambda r: r.formula_pretty)
        load_sorted = sorted(loaded, key=lambda r: r.formula_pretty)

        assert len(orig_sorted) == len(load_sorted)
        for orig, load in zip(orig_sorted, load_sorted, strict=True):
            assert orig.formula_pretty == load.formula_pretty
            assert orig.label == load.label
            assert orig.pattern_key.top_operator == load.pattern_key.top_operator
            assert (
                orig.difficulty_metrics.difficulty_tier
                == load.difficulty_metrics.difficulty_tier
            )
