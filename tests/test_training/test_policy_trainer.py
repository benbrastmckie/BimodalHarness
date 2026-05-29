"""Unit tests for PolicyTrainer."""

from __future__ import annotations

import os
import tempfile

import torch
import pytest

from bimodal_harness.models.policy import PolicyNetwork, PolicyNetworkConfig
from bimodal_harness.schema.records import ProofStepRecord
from bimodal_harness.training.policy_trainer import PolicyTrainer, PolicyTrainerConfig


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_record(
    action_index: int = 44,
    frame_class: str = "Base",
    rule: str = "modus_ponens",
    step_id: str = "test/0",
    depth: int = 0,
    proof_height: int = 2,
) -> ProofStepRecord:
    return ProofStepRecord(
        step_id=step_id,
        theorem_name="test_thm",
        context=(),
        goal_json={"tag": "imp", "left": {"tag": "atom", "name": "p"}, "right": {"tag": "atom", "name": "q"}},
        goal_pretty="p → q",
        rule=rule,
        axiom_name=None,
        action_index=action_index,
        subgoals=(),
        depth=depth,
        frame_class=frame_class,
        proof_height=proof_height,
    )


def _make_records(n: int = 64, frame_class: str = "Base") -> list[ProofStepRecord]:
    """Make n records with action indices cycling through valid actions for the frame class."""
    from bimodal_harness.schema.actions import FRAME_CLASS_MASKS
    mask = FRAME_CLASS_MASKS.get(frame_class, FRAME_CLASS_MASKS["Base"])
    valid_indices = [i for i, v in enumerate(mask) if v]
    return [
        _make_record(action_index=valid_indices[i % len(valid_indices)], step_id=f"s/{i}", frame_class=frame_class)
        for i in range(n)
    ]


def _small_trainer(
    n_train: int = 64,
    n_val: int = 16,
    max_epochs: int = 2,
    batch_size: int = 16,
) -> PolicyTrainer:
    train_records = _make_records(n_train)
    val_records = _make_records(n_val)
    config = PolicyNetworkConfig(hidden_sizes=[64, 32])
    model = PolicyNetwork(config)
    trainer_config = PolicyTrainerConfig(
        learning_rate=1e-3,
        batch_size=batch_size,
        max_epochs=max_epochs,
        patience=5,
        seed=42,
    )
    return PolicyTrainer(
        model=model,
        config=trainer_config,
        train_records=train_records,
        val_records=val_records,
    )


# ---------------------------------------------------------------------------
# PolicyTrainerConfig tests
# ---------------------------------------------------------------------------

class TestPolicyTrainerConfig:
    def test_defaults(self):
        cfg = PolicyTrainerConfig()
        assert cfg.learning_rate == pytest.approx(3e-4)
        assert cfg.batch_size == 64
        assert cfg.max_epochs == 50
        assert cfg.weight_decay == pytest.approx(1e-4)
        assert cfg.patience == 7
        assert cfg.label_smoothing == pytest.approx(0.1)
        assert cfg.focal_loss_gamma == pytest.approx(0.0)
        assert cfg.seed == 42
        assert cfg.gradient_clip_norm == pytest.approx(1.0)

    def test_to_dict_from_dict_roundtrip(self):
        cfg = PolicyTrainerConfig(learning_rate=1e-3, batch_size=32, max_epochs=10)
        restored = PolicyTrainerConfig.from_dict(cfg.to_dict())
        assert restored.learning_rate == pytest.approx(cfg.learning_rate)
        assert restored.batch_size == cfg.batch_size
        assert restored.max_epochs == cfg.max_epochs


# ---------------------------------------------------------------------------
# PolicyTrainer.train_epoch tests
# ---------------------------------------------------------------------------

class TestPolicyTrainerTrainEpoch:
    def test_single_epoch_runs(self):
        trainer = _small_trainer()
        loss = trainer.train_epoch(0)
        assert isinstance(loss, float)
        assert loss >= 0.0

    def test_loss_is_finite(self):
        trainer = _small_trainer()
        loss = trainer.train_epoch(0)
        assert torch.isfinite(torch.tensor(loss))


# ---------------------------------------------------------------------------
# PolicyTrainer.evaluate tests
# ---------------------------------------------------------------------------

class TestPolicyTrainerEvaluate:
    def test_evaluate_returns_required_keys(self):
        trainer = _small_trainer()
        records = _make_records(32)
        metrics = trainer.evaluate(records)
        required_keys = {"top1_acc", "top5_acc", "mrr", "per_rule_accuracy", "valid_prob_mass"}
        assert required_keys <= set(metrics.keys())

    def test_evaluate_top1_in_range(self):
        trainer = _small_trainer()
        records = _make_records(32)
        metrics = trainer.evaluate(records)
        assert 0.0 <= metrics["top1_acc"] <= 1.0

    def test_evaluate_top5_in_range(self):
        trainer = _small_trainer()
        records = _make_records(32)
        metrics = trainer.evaluate(records)
        assert 0.0 <= metrics["top5_acc"] <= 1.0

    def test_evaluate_mrr_in_range(self):
        trainer = _small_trainer()
        records = _make_records(32)
        metrics = trainer.evaluate(records)
        assert 0.0 <= metrics["mrr"] <= 1.0

    def test_evaluate_valid_prob_mass_near_1(self):
        trainer = _small_trainer()
        records = _make_records(32)
        metrics = trainer.evaluate(records)
        # Valid prob mass should be 1.0 since mask zeroes invalid, softmax on remaining sums to 1
        assert metrics["valid_prob_mass"] == pytest.approx(1.0, abs=0.01)

    def test_evaluate_per_rule_accuracy_is_dict(self):
        trainer = _small_trainer()
        records = _make_records(32)
        metrics = trainer.evaluate(records)
        assert isinstance(metrics["per_rule_accuracy"], dict)

    def test_evaluate_empty_records(self):
        trainer = _small_trainer()
        metrics = trainer.evaluate([])
        assert metrics["top1_acc"] == 0.0
        assert metrics["mrr"] == 0.0


# ---------------------------------------------------------------------------
# PolicyTrainer.train tests
# ---------------------------------------------------------------------------

class TestPolicyTrainerTrain:
    def test_train_returns_history(self):
        trainer = _small_trainer(max_epochs=2)
        results = trainer.train()
        required_keys = {"best_epoch", "best_val_top1", "final_epoch", "train_losses", "val_metrics"}
        assert required_keys <= set(results.keys())

    def test_train_loss_list_not_empty(self):
        trainer = _small_trainer(max_epochs=2)
        results = trainer.train()
        assert len(results["train_losses"]) > 0

    def test_val_metrics_list_has_required_keys(self):
        trainer = _small_trainer(max_epochs=2)
        results = trainer.train()
        for vm in results["val_metrics"]:
            assert "top1_acc" in vm
            assert "mrr" in vm


# ---------------------------------------------------------------------------
# PolicyTrainer checkpoint tests
# ---------------------------------------------------------------------------

class TestPolicyTrainerCheckpoint:
    def test_checkpoint_roundtrip_weights(self):
        trainer = _small_trainer(max_epochs=1)
        trainer.train()

        with tempfile.NamedTemporaryFile(suffix=".pt", delete=False) as f:
            path = f.name

        try:
            trainer.save_checkpoint(path)

            # Load checkpoint into a fresh model and verify predictions match
            cfg = trainer.model.config
            model2 = PolicyNetwork(cfg)
            trainer2 = PolicyTrainer(
                model=model2,
                config=trainer.config,
                train_records=trainer.train_records,
                val_records=trainer.val_records,
            )
            trainer2.load_checkpoint(path)

            # Compare predictions on same input
            x = torch.randn(4, 25)
            trainer.model.eval()
            model2.eval()
            with torch.no_grad():
                out1 = trainer.model(x)
                out2 = model2(x)
            assert torch.allclose(out1, out2, atol=1e-6)
        finally:
            os.unlink(path)

    def test_from_checkpoint_classmethod(self):
        trainer = _small_trainer(max_epochs=1)
        trainer.train()

        with tempfile.NamedTemporaryFile(suffix=".pt", delete=False) as f:
            path = f.name

        try:
            trainer.save_checkpoint(path)
            restored = PolicyTrainer.from_checkpoint(
                path,
                train_records=trainer.train_records,
                val_records=trainer.val_records,
            )
            assert restored.model.config.hidden_sizes == trainer.model.config.hidden_sizes
        finally:
            os.unlink(path)

    def test_checkpoint_saves_epoch(self):
        trainer = _small_trainer(max_epochs=1)
        trainer.train_epoch(0)

        with tempfile.NamedTemporaryFile(suffix=".pt", delete=False) as f:
            path = f.name

        try:
            trainer.save_checkpoint(path)
            ckpt = torch.load(path, weights_only=False)
            assert "epoch" in ckpt
        finally:
            os.unlink(path)
