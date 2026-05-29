"""Unit tests for ValueTrainer, TrainerConfig, and value_collate_fn.

Tests:
- value_collate_fn: filtering, shape, empty batch handling
- TrainerConfig: instantiation, serialization
- ValueTrainer: train_epoch, evaluate, checkpoint round-trip
"""

from __future__ import annotations

import os
import tempfile

import pytest
import torch

from bimodal_harness.data.dataset import BimodalDataset, split_dataset
from bimodal_harness.models.value import ValueNetwork, ValueNetworkConfig
from bimodal_harness.schema.records import (
    DifficultyMetrics,
    PatternKey,
    ProofTrace,
    RuleProfile,
    TrainingRecord,
)
from bimodal_harness.training.value_trainer import (
    TrainerConfig,
    ValueTrainer,
    value_collate_fn,
)


# ---------------------------------------------------------------------------
# Test data helpers
# ---------------------------------------------------------------------------


def make_valid_record(
    height: int = 3,
    modal_depth: int = 1,
    top_operator: str = "Atom",
    difficulty_tier: str = "easy",
    record_id: str = "test-valid",
) -> TrainingRecord:
    """Create a valid TrainingRecord with a ProofTrace."""
    pk = PatternKey(
        modal_depth=modal_depth,
        temporal_depth=0,
        imp_count=1,
        complexity=max(1, modal_depth + 2),
        top_operator=top_operator,
    )
    dm = DifficultyMetrics(
        atom_count=2,
        modal_depth=modal_depth,
        temporal_depth=0,
        complexity=max(1, modal_depth + 2),
        decision_time_ms=100,
        search_depth=3,
        difficulty_tier=difficulty_tier,
    )
    pt = ProofTrace(height=height, rule_profile=RuleProfile(), axioms_used=())
    return TrainingRecord(
        record_id=record_id,
        formula_json={},
        formula_pretty="p",
        label="valid",
        pattern_key=pk,
        difficulty_metrics=dm,
        proof_trace=pt,
        countermodel=None,
    )


def make_invalid_record(
    record_id: str = "test-invalid",
    difficulty_tier: str = "easy",
) -> TrainingRecord:
    """Create an invalid TrainingRecord (no ProofTrace)."""
    pk = PatternKey(
        modal_depth=0,
        temporal_depth=0,
        imp_count=0,
        complexity=1,
        top_operator="Atom",
    )
    dm = DifficultyMetrics(
        atom_count=1,
        modal_depth=0,
        temporal_depth=0,
        complexity=1,
        decision_time_ms=50,
        search_depth=1,
        difficulty_tier=difficulty_tier,
    )
    return TrainingRecord(
        record_id=record_id,
        formula_json={},
        formula_pretty="p",
        label="invalid",
        pattern_key=pk,
        difficulty_metrics=dm,
        proof_trace=None,
        countermodel=None,
    )


def make_synthetic_dataset(
    n_valid: int = 30,
    n_invalid: int = 10,
    seed: int = 42,
) -> list[TrainingRecord]:
    """Create a mixed list of valid and invalid records."""
    records = []
    operators = ["Atom", "Box", "Implication", "Until", "Since", "Bottom", "AllFuture", "AllPast"]
    tiers = ["easy", "medium", "hard", "very_hard"]
    for i in range(n_valid):
        records.append(make_valid_record(
            height=i % 10 + 1,
            modal_depth=i % 4,
            top_operator=operators[i % len(operators)],
            difficulty_tier=tiers[i % len(tiers)],
            record_id=f"valid-{i}",
        ))
    for i in range(n_invalid):
        records.append(make_invalid_record(
            record_id=f"invalid-{i}",
            difficulty_tier=tiers[i % len(tiers)],
        ))
    return records


# ---------------------------------------------------------------------------
# value_collate_fn tests
# ---------------------------------------------------------------------------


class TestValueCollateFn:
    """Tests for the value_collate_fn DataLoader collate function."""

    def test_output_shapes_all_valid(self) -> None:
        """All-valid batch produces [N, 12] features and [N, 1] targets."""
        records = [make_valid_record(height=h, record_id=f"r{h}") for h in range(1, 6)]
        features, targets = value_collate_fn(records)
        assert features.shape == torch.Size([5, 12])
        assert targets.shape == torch.Size([5, 1])

    def test_output_dtypes(self) -> None:
        """Features and targets are float32."""
        records = [make_valid_record(record_id="r0")]
        features, targets = value_collate_fn(records)
        assert features.dtype == torch.float32
        assert targets.dtype == torch.float32

    def test_filters_invalid_records(self) -> None:
        """Invalid records are excluded from the output batch."""
        valid_records = [make_valid_record(record_id=f"v{i}") for i in range(4)]
        invalid_records = [make_invalid_record(record_id=f"i{i}") for i in range(6)]
        mixed = valid_records + invalid_records
        features, targets = value_collate_fn(mixed)
        # Only valid records should appear
        assert features.shape[0] == 4
        assert targets.shape[0] == 4

    def test_filters_valid_without_proof_trace(self) -> None:
        """Valid records with None proof_trace are excluded."""
        # Create a record labeled 'valid' but with no proof_trace
        pk = PatternKey(modal_depth=0, temporal_depth=0, imp_count=0, complexity=1, top_operator="Atom")
        dm = DifficultyMetrics(atom_count=1, modal_depth=0, temporal_depth=0, complexity=1, decision_time_ms=50, search_depth=1, difficulty_tier="easy")
        bad_record = TrainingRecord(
            record_id="bad-valid",
            formula_json={},
            formula_pretty="p",
            label="valid",
            pattern_key=pk,
            difficulty_metrics=dm,
            proof_trace=None,  # No proof trace despite valid label
            countermodel=None,
        )
        good_record = make_valid_record(record_id="good")
        features, targets = value_collate_fn([bad_record, good_record])
        # Only good_record passes
        assert features.shape[0] == 1

    def test_empty_batch_all_invalid(self) -> None:
        """All-invalid batch returns empty tensors with correct shapes."""
        records = [make_invalid_record(record_id=f"i{i}") for i in range(5)]
        features, targets = value_collate_fn(records)
        assert features.shape == torch.Size([0, 12])
        assert targets.shape == torch.Size([0, 1])
        assert features.dtype == torch.float32
        assert targets.dtype == torch.float32

    def test_empty_input_list(self) -> None:
        """Empty record list returns empty tensors."""
        features, targets = value_collate_fn([])
        assert features.shape == torch.Size([0, 12])
        assert targets.shape == torch.Size([0, 1])

    def test_target_values_match_heights(self) -> None:
        """Target values correspond to proof tree heights."""
        heights = [1, 3, 7, 12]
        records = [make_valid_record(height=h, record_id=f"r{h}") for h in heights]
        features, targets = value_collate_fn(records)
        assert targets.shape == torch.Size([4, 1])
        for i, h in enumerate(heights):
            assert targets[i, 0].item() == pytest.approx(float(h))

    def test_mixed_batch_ordering(self) -> None:
        """Valid records appear in their original order in the batch."""
        records = [
            make_invalid_record(record_id="i0"),
            make_valid_record(height=5, record_id="v5"),
            make_invalid_record(record_id="i1"),
            make_valid_record(height=2, record_id="v2"),
        ]
        features, targets = value_collate_fn(records)
        assert features.shape[0] == 2
        assert targets[0, 0].item() == pytest.approx(5.0)
        assert targets[1, 0].item() == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# TrainerConfig tests
# ---------------------------------------------------------------------------


class TestTrainerConfig:
    """Tests for TrainerConfig dataclass."""

    def test_default_values(self) -> None:
        """Default config has expected values."""
        cfg = TrainerConfig()
        assert cfg.learning_rate == pytest.approx(3e-4)
        assert cfg.batch_size == 64
        assert cfg.max_epochs == 50
        assert cfg.huber_delta == pytest.approx(1.0)
        assert cfg.weight_decay == pytest.approx(1e-4)
        assert cfg.patience == 7
        assert cfg.use_curriculum is True
        assert cfg.seed == 42

    def test_to_dict_from_dict_round_trip(self) -> None:
        """Config serializes and deserializes correctly."""
        cfg = TrainerConfig(
            learning_rate=1e-3,
            batch_size=32,
            max_epochs=20,
            huber_delta=2.0,
            weight_decay=5e-4,
            patience=5,
            use_curriculum=False,
            seed=123,
        )
        d = cfg.to_dict()
        restored = TrainerConfig.from_dict(d)
        assert restored.learning_rate == pytest.approx(cfg.learning_rate)
        assert restored.batch_size == cfg.batch_size
        assert restored.max_epochs == cfg.max_epochs
        assert restored.huber_delta == pytest.approx(cfg.huber_delta)
        assert restored.patience == cfg.patience
        assert restored.use_curriculum == cfg.use_curriculum
        assert restored.seed == cfg.seed

    def test_from_dict_with_defaults(self) -> None:
        """from_dict with empty dict uses all defaults."""
        cfg = TrainerConfig.from_dict({})
        default = TrainerConfig()
        assert cfg.learning_rate == pytest.approx(default.learning_rate)
        assert cfg.batch_size == default.batch_size


# ---------------------------------------------------------------------------
# ValueTrainer tests
# ---------------------------------------------------------------------------


@pytest.fixture
def small_datasets():
    """Create small train/val/test datasets for testing."""
    records = make_synthetic_dataset(n_valid=30, n_invalid=10)
    train_ds, val_ds, test_ds = split_dataset(records, seed=42)
    return train_ds, val_ds, test_ds


@pytest.fixture
def small_model():
    """Create a small ValueNetwork for fast testing."""
    config = ValueNetworkConfig(hidden_sizes=[32, 16], dropout=0.0)
    return ValueNetwork(config)


@pytest.fixture
def small_trainer(small_model, small_datasets):
    """Create a ValueTrainer configured for fast testing."""
    train_ds, val_ds, _ = small_datasets
    cfg = TrainerConfig(
        max_epochs=3,
        batch_size=8,
        patience=10,
        use_curriculum=True,
        seed=42,
    )
    return ValueTrainer(model=small_model, config=cfg, train_dataset=train_ds, val_dataset=val_ds)


class TestValueTrainer:
    """Tests for ValueTrainer class."""

    def test_instantiation(self, small_model, small_datasets) -> None:
        """ValueTrainer instantiates without error."""
        train_ds, val_ds, _ = small_datasets
        cfg = TrainerConfig(max_epochs=2, batch_size=8)
        trainer = ValueTrainer(model=small_model, config=cfg, train_dataset=train_ds, val_dataset=val_ds)
        assert trainer is not None

    def test_train_epoch_returns_float(self, small_trainer) -> None:
        """train_epoch returns a float loss value."""
        loss = small_trainer.train_epoch(0)
        assert isinstance(loss, float)
        assert loss >= 0.0

    def test_train_epoch_multiple_epochs(self, small_trainer) -> None:
        """Multiple train_epoch calls complete without error."""
        for epoch in range(3):
            loss = small_trainer.train_epoch(epoch)
            assert loss >= 0.0

    def test_train_epoch_without_curriculum(self, small_model, small_datasets) -> None:
        """train_epoch works with use_curriculum=False."""
        train_ds, val_ds, _ = small_datasets
        cfg = TrainerConfig(max_epochs=2, batch_size=8, use_curriculum=False)
        trainer = ValueTrainer(model=small_model, config=cfg, train_dataset=train_ds, val_dataset=val_ds)
        loss = trainer.train_epoch(0)
        assert loss >= 0.0

    def test_evaluate_returns_correct_keys(self, small_trainer, small_datasets) -> None:
        """evaluate() returns dict with 'mae', 'spearman', 'accuracy_at_1' keys."""
        _, val_ds, _ = small_datasets
        metrics = small_trainer.evaluate(val_ds)
        assert "mae" in metrics
        assert "spearman" in metrics
        assert "accuracy_at_1" in metrics

    def test_evaluate_metric_ranges(self, small_trainer, small_datasets) -> None:
        """Metric values are within expected ranges."""
        _, val_ds, _ = small_datasets
        metrics = small_trainer.evaluate(val_ds)
        assert metrics["mae"] >= 0.0
        assert -1.0 <= metrics["spearman"] <= 1.0
        assert 0.0 <= metrics["accuracy_at_1"] <= 1.0

    def test_evaluate_empty_dataset_valid_only(self, small_trainer) -> None:
        """evaluate() on a dataset with no valid records returns zeros."""
        invalid_records = [make_invalid_record(record_id=f"i{i}") for i in range(5)]
        empty_ds = BimodalDataset(invalid_records)
        metrics = small_trainer.evaluate(empty_ds)
        assert metrics["mae"] == pytest.approx(0.0)
        assert metrics["spearman"] == pytest.approx(0.0)
        assert metrics["accuracy_at_1"] == pytest.approx(0.0)

    def test_train_returns_result_dict(self, small_trainer) -> None:
        """train() returns a dict with expected keys."""
        results = small_trainer.train()
        assert "best_epoch" in results
        assert "best_val_mae" in results
        assert "final_epoch" in results
        assert "train_losses" in results
        assert "val_metrics" in results

    def test_train_losses_non_negative(self, small_trainer) -> None:
        """Train losses are non-negative."""
        results = small_trainer.train()
        for loss in results["train_losses"]:
            assert loss >= 0.0

    def test_train_best_val_mae_non_negative(self, small_trainer) -> None:
        """Best validation MAE is non-negative."""
        results = small_trainer.train()
        assert results["best_val_mae"] >= 0.0

    def test_early_stopping_respects_patience(self, small_model, small_datasets) -> None:
        """Training stops within patience+1 epochs after best_epoch."""
        train_ds, val_ds, _ = small_datasets
        cfg = TrainerConfig(max_epochs=20, batch_size=8, patience=2, use_curriculum=False, seed=0)
        trainer = ValueTrainer(model=small_model, config=cfg, train_dataset=train_ds, val_dataset=val_ds)
        results = trainer.train()
        best_epoch = results["best_epoch"]
        final_epoch = results["final_epoch"]
        # Should stop at most patience epochs after best
        assert final_epoch <= best_epoch + cfg.patience

    def test_checkpoint_save_load_round_trip(self, small_trainer, small_datasets, tmp_path) -> None:
        """save_checkpoint/load_checkpoint round-trips model weights correctly."""
        small_trainer.train_epoch(0)

        ckpt_path = str(tmp_path / "checkpoint.pt")
        small_trainer.save_checkpoint(ckpt_path)
        assert os.path.exists(ckpt_path)

        # Record output before reload
        small_trainer.model.eval()
        x = torch.randn(4, 12)
        with torch.no_grad():
            y_before = small_trainer.model(x)

        # Create fresh model and trainer, load checkpoint
        train_ds, val_ds, _ = small_datasets
        cfg2 = TrainerConfig(max_epochs=3, batch_size=8)
        net2 = ValueNetwork(ValueNetworkConfig(hidden_sizes=[32, 16], dropout=0.0))
        trainer2 = ValueTrainer(model=net2, config=cfg2, train_dataset=train_ds, val_dataset=val_ds)
        trainer2.load_checkpoint(ckpt_path)
        net2.eval()

        with torch.no_grad():
            y_after = net2(x)

        assert torch.allclose(y_before, y_after), (
            "Model outputs differ after checkpoint round-trip.\n"
            f"Before: {y_before[:2].tolist()}\n"
            f"After:  {y_after[:2].tolist()}"
        )

    def test_checkpoint_contains_required_fields(self, small_trainer, tmp_path) -> None:
        """Checkpoint file contains all required fields."""
        small_trainer.train_epoch(0)
        ckpt_path = str(tmp_path / "checkpoint.pt")
        small_trainer.save_checkpoint(ckpt_path)

        ckpt = torch.load(ckpt_path, weights_only=False)
        assert "model_state_dict" in ckpt
        assert "config" in ckpt
        assert "trainer_config" in ckpt
        assert "normalizer" in ckpt
        assert "epoch" in ckpt
        assert "best_val_mae" in ckpt

    def test_checkpoint_epoch_is_recorded(self, small_trainer, tmp_path) -> None:
        """Checkpoint records the current epoch."""
        small_trainer.train_epoch(2)  # epoch=2
        ckpt_path = str(tmp_path / "checkpoint.pt")
        small_trainer.save_checkpoint(ckpt_path)

        ckpt = torch.load(ckpt_path, weights_only=False)
        assert ckpt["epoch"] == 2

    def test_from_checkpoint_classmethod(self, small_trainer, small_datasets, tmp_path) -> None:
        """from_checkpoint creates a fully restored ValueTrainer."""
        small_trainer.train_epoch(0)
        ckpt_path = str(tmp_path / "checkpoint.pt")
        small_trainer.save_checkpoint(ckpt_path)

        train_ds, val_ds, _ = small_datasets
        trainer2 = ValueTrainer.from_checkpoint(
            path=ckpt_path,
            train_dataset=train_ds,
            val_dataset=val_ds,
        )
        assert isinstance(trainer2, ValueTrainer)
        assert isinstance(trainer2.model, ValueNetwork)

    def test_forward_outputs_match_after_checkpoint(self, small_trainer, small_datasets, tmp_path) -> None:
        """Model from from_checkpoint produces identical outputs to original."""
        small_trainer.train_epoch(0)
        ckpt_path = str(tmp_path / "checkpoint.pt")
        small_trainer.save_checkpoint(ckpt_path)

        train_ds, val_ds, _ = small_datasets
        trainer2 = ValueTrainer.from_checkpoint(
            path=ckpt_path,
            train_dataset=train_ds,
            val_dataset=val_ds,
        )

        x = torch.randn(8, 12)
        small_trainer.model.eval()
        trainer2.model.eval()
        with torch.no_grad():
            y1 = small_trainer.model(x)
            y2 = trainer2.model(x)

        assert torch.allclose(y1, y2), (
            "Outputs diverge after from_checkpoint round-trip."
        )
