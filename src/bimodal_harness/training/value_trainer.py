"""Value network training infrastructure for BimodalHarness.

Provides:
- value_collate_fn: DataLoader collate function filtering valid records
- TrainerConfig: Training hyperparameter configuration
- ValueTrainer: Full train/evaluate/checkpoint orchestration
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from typing import Any

import torch
import torch.nn as nn
import torch.optim as optim
import torch.utils.data
from scipy.stats import spearmanr

from bimodal_harness.data.dataset import BimodalDataset, CurriculumSampler
from bimodal_harness.models.value import FeatureNormalizer, ValueNetwork, ValueNetworkConfig
from bimodal_harness.schema.records import TrainingRecord


# ---------------------------------------------------------------------------
# value_collate_fn
# ---------------------------------------------------------------------------


def value_collate_fn(
    records: list[TrainingRecord],
) -> tuple[torch.Tensor, torch.Tensor]:
    """Collate a list of TrainingRecords into feature and target tensors.

    Filters to records with ``label == "valid"`` and a non-None ``proof_trace``,
    then encodes PatternKey features and stacks proof tree heights as targets.

    Parameters
    ----------
    records:
        List of TrainingRecord items from a DataLoader batch.

    Returns
    -------
    tuple[Tensor, Tensor]
        - features: shape [N, 12] float32, where N is the number of valid records
        - targets: shape [N, 1] float32, proof tree heights

    Notes
    -----
    If all records are filtered out (empty valid batch), returns
    (zeros([0, 12]), zeros([0, 1])) with the correct dtype and shape semantics.
    """
    normalizer = FeatureNormalizer()
    feature_list: list[torch.Tensor] = []
    height_list: list[float] = []

    for rec in records:
        if rec.label == "valid" and rec.proof_trace is not None:
            feat = normalizer.encode(rec.pattern_key)  # [12]
            feature_list.append(feat)
            height_list.append(float(rec.proof_trace.height))

    if not feature_list:
        # Return empty tensors with correct shapes
        return torch.zeros((0, 12), dtype=torch.float32), torch.zeros((0, 1), dtype=torch.float32)

    features = torch.stack(feature_list, dim=0)  # [N, 12]
    targets = torch.tensor(height_list, dtype=torch.float32).unsqueeze(1)  # [N, 1]
    return features, targets


# ---------------------------------------------------------------------------
# TrainerConfig
# ---------------------------------------------------------------------------


@dataclass
class TrainerConfig:
    """Hyperparameter configuration for ValueTrainer.

    Parameters
    ----------
    learning_rate:
        Initial learning rate for Adam optimizer. Default: 3e-4.
    batch_size:
        Batch size for training DataLoader. Default: 64.
    max_epochs:
        Maximum number of training epochs. Default: 50.
    huber_delta:
        Delta parameter for HuberLoss. Default: 1.0.
    weight_decay:
        L2 regularization coefficient for Adam optimizer. Default: 1e-4.
    patience:
        Number of epochs without validation MAE improvement before early stopping.
        Default: 7.
    use_curriculum:
        Whether to use CurriculumSampler for epoch-gated difficulty progression.
        Default: True.
    seed:
        Random seed for reproducibility. Default: 42.
    """

    learning_rate: float = 3e-4
    batch_size: int = 64
    max_epochs: int = 50
    huber_delta: float = 1.0
    weight_decay: float = 1e-4
    patience: int = 7
    use_curriculum: bool = True
    seed: int = 42

    def to_dict(self) -> dict[str, Any]:
        """Serialize config to a plain dictionary."""
        return {
            "learning_rate": self.learning_rate,
            "batch_size": self.batch_size,
            "max_epochs": self.max_epochs,
            "huber_delta": self.huber_delta,
            "weight_decay": self.weight_decay,
            "patience": self.patience,
            "use_curriculum": self.use_curriculum,
            "seed": self.seed,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TrainerConfig:
        """Deserialize config from a plain dictionary."""
        return cls(
            learning_rate=float(data.get("learning_rate", 3e-4)),
            batch_size=int(data.get("batch_size", 64)),
            max_epochs=int(data.get("max_epochs", 50)),
            huber_delta=float(data.get("huber_delta", 1.0)),
            weight_decay=float(data.get("weight_decay", 1e-4)),
            patience=int(data.get("patience", 7)),
            use_curriculum=bool(data.get("use_curriculum", True)),
            seed=int(data.get("seed", 42)),
        )


# ---------------------------------------------------------------------------
# ValueTrainer
# ---------------------------------------------------------------------------


class ValueTrainer:
    """Orchestrates training, evaluation, and checkpointing of a ValueNetwork.

    Handles:
    - One training epoch with optional CurriculumSampler
    - Evaluation computing MAE, Spearman correlation, accuracy-at-1
    - Full training loop with early stopping on validation MAE
    - Checkpoint save/load (model state, config, normalizer, epoch, best_val_mae)

    Parameters
    ----------
    model:
        ValueNetwork instance to train.
    config:
        TrainerConfig with hyperparameters.
    train_dataset:
        BimodalDataset for training.
    val_dataset:
        BimodalDataset for validation.
    normalizer:
        Optional FeatureNormalizer; creates a default one if not provided.
    """

    def __init__(
        self,
        model: ValueNetwork,
        config: TrainerConfig,
        train_dataset: BimodalDataset,
        val_dataset: BimodalDataset,
        normalizer: FeatureNormalizer | None = None,
    ) -> None:
        self.model = model
        self.config = config
        self.train_dataset = train_dataset
        self.val_dataset = val_dataset
        self.normalizer = normalizer if normalizer is not None else FeatureNormalizer()

        # Set random seed
        torch.manual_seed(config.seed)

        self.optimizer = optim.Adam(
            model.parameters(),
            lr=config.learning_rate,
            weight_decay=config.weight_decay,
        )
        self.criterion = nn.HuberLoss(delta=config.huber_delta)
        self.scheduler = optim.lr_scheduler.CosineAnnealingLR(
            self.optimizer, T_max=config.max_epochs
        )

        self._current_epoch: int = 0
        self._best_val_mae: float = float("inf")

    def _make_train_loader(self, epoch: int) -> torch.utils.data.DataLoader:
        """Create a training DataLoader, optionally using CurriculumSampler."""
        if self.config.use_curriculum:
            sampler = CurriculumSampler(
                self.train_dataset,
                epoch=epoch,
                max_epochs=self.config.max_epochs,
                seed=self.config.seed,
            )
            return torch.utils.data.DataLoader(
                self.train_dataset,
                batch_size=self.config.batch_size,
                sampler=sampler,
                collate_fn=value_collate_fn,
                drop_last=False,
            )
        else:
            return torch.utils.data.DataLoader(
                self.train_dataset,
                batch_size=self.config.batch_size,
                shuffle=True,
                collate_fn=value_collate_fn,
                drop_last=False,
            )

    def train_epoch(self, epoch: int) -> float:
        """Run one training epoch.

        Parameters
        ----------
        epoch:
            Current epoch index (0-based). Used for CurriculumSampler.

        Returns
        -------
        float
            Mean Huber loss over the epoch. Returns 0.0 if no valid batches.
        """
        self.model.train()
        total_loss = 0.0
        total_batches = 0

        loader = self._make_train_loader(epoch)
        for features, targets in loader:
            if features.shape[0] == 0:
                # Skip empty batches (all records filtered out)
                continue

            self.optimizer.zero_grad()
            predictions = self.model(features)  # [B, 1]
            loss = self.criterion(predictions, targets)
            loss.backward()
            self.optimizer.step()

            total_loss += loss.item()
            total_batches += 1

        self._current_epoch = epoch
        return total_loss / total_batches if total_batches > 0 else 0.0

    def evaluate(self, dataset: BimodalDataset) -> dict[str, float]:
        """Evaluate the model on a dataset.

        Computes:
        - ``mae``: Mean Absolute Error between predictions and true heights
        - ``spearman``: Spearman rank correlation coefficient
        - ``accuracy_at_1``: Fraction of predictions within ±1 of true height

        Parameters
        ----------
        dataset:
            BimodalDataset to evaluate on.

        Returns
        -------
        dict[str, float]
            Dictionary with keys "mae", "spearman", "accuracy_at_1".
            Returns zeros when no valid records are present.
        """
        self.model.eval()
        all_predictions: list[float] = []
        all_targets: list[float] = []

        loader = torch.utils.data.DataLoader(
            dataset,
            batch_size=self.config.batch_size,
            shuffle=False,
            collate_fn=value_collate_fn,
            drop_last=False,
        )

        with torch.no_grad():
            for features, targets in loader:
                if features.shape[0] == 0:
                    continue
                predictions = self.model(features)  # [B, 1]
                all_predictions.extend(predictions.squeeze(1).tolist())
                all_targets.extend(targets.squeeze(1).tolist())

        if not all_predictions:
            return {"mae": 0.0, "spearman": 0.0, "accuracy_at_1": 0.0}

        pred_tensor = torch.tensor(all_predictions, dtype=torch.float32)
        tgt_tensor = torch.tensor(all_targets, dtype=torch.float32)

        mae = (pred_tensor - tgt_tensor).abs().mean().item()

        # Spearman correlation via scipy
        spearman_result = spearmanr(all_predictions, all_targets)
        spearman_val = float(spearman_result.statistic)
        if math.isnan(spearman_val):
            spearman_val = 0.0

        # Accuracy-at-1: fraction within ±1 of true height
        within_one = ((pred_tensor - tgt_tensor).abs() <= 1.0).float().mean().item()

        return {
            "mae": mae,
            "spearman": spearman_val,
            "accuracy_at_1": within_one,
        }

    def train(self) -> dict[str, Any]:
        """Run the full training loop with early stopping.

        Trains for up to ``config.max_epochs`` epochs, stopping early if
        validation MAE does not improve for ``config.patience`` consecutive epochs.

        Returns
        -------
        dict[str, Any]
            Summary of training results with keys:
            - "best_epoch": epoch with best validation MAE
            - "best_val_mae": best validation MAE achieved
            - "final_epoch": last epoch completed
            - "train_losses": list of per-epoch training losses
            - "val_metrics": list of per-epoch validation metric dicts
        """
        best_epoch = 0
        best_val_mae = float("inf")
        best_model_state: dict[str, torch.Tensor] = {}
        epochs_without_improvement = 0
        train_losses: list[float] = []
        val_metrics_history: list[dict[str, float]] = []

        for epoch in range(self.config.max_epochs):
            train_loss = self.train_epoch(epoch)
            val_metrics = self.evaluate(self.val_dataset)

            self.scheduler.step()

            train_losses.append(train_loss)
            val_metrics_history.append(val_metrics)

            current_val_mae = val_metrics["mae"]

            if current_val_mae < best_val_mae:
                best_val_mae = current_val_mae
                best_epoch = epoch
                best_model_state = {
                    k: v.clone() for k, v in self.model.state_dict().items()
                }
                epochs_without_improvement = 0
            else:
                epochs_without_improvement += 1

            if epochs_without_improvement >= self.config.patience:
                # Restore best weights before stopping
                if best_model_state:
                    self.model.load_state_dict(best_model_state)
                break

        # Ensure best weights are loaded
        if best_model_state:
            self.model.load_state_dict(best_model_state)
        self._best_val_mae = best_val_mae

        return {
            "best_epoch": best_epoch,
            "best_val_mae": best_val_mae,
            "final_epoch": epoch,
            "train_losses": train_losses,
            "val_metrics": val_metrics_history,
        }

    def save_checkpoint(self, path: str) -> None:
        """Save model state, config, normalizer, and training metadata.

        Parameters
        ----------
        path:
            File path where the checkpoint will be written.
            Parent directories are created if they don't exist.
        """
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        checkpoint = {
            "model_state_dict": self.model.state_dict(),
            "config": self.model.config.to_dict(),
            "trainer_config": self.config.to_dict(),
            "normalizer": self.normalizer.to_dict(),
            "epoch": self._current_epoch,
            "best_val_mae": self._best_val_mae,
            "format_version": "1.0",
        }
        torch.save(checkpoint, path)

    def load_checkpoint(self, path: str) -> dict[str, Any]:
        """Load model state and training metadata from a checkpoint.

        Parameters
        ----------
        path:
            Path to a checkpoint file previously saved by ``save_checkpoint``.

        Returns
        -------
        dict[str, Any]
            The full checkpoint dictionary (for metadata access).
        """
        checkpoint: dict[str, Any] = torch.load(path, weights_only=False)
        self.model.load_state_dict(checkpoint["model_state_dict"])
        self._current_epoch = int(checkpoint.get("epoch", 0))
        self._best_val_mae = float(checkpoint.get("best_val_mae", float("inf")))

        # Restore normalizer if present
        if "normalizer" in checkpoint:
            self.normalizer = FeatureNormalizer.from_dict(checkpoint["normalizer"])

        return checkpoint

    @classmethod
    def from_checkpoint(
        cls,
        path: str,
        train_dataset: BimodalDataset,
        val_dataset: BimodalDataset,
    ) -> ValueTrainer:
        """Create a ValueTrainer from a saved checkpoint.

        Parameters
        ----------
        path:
            Path to checkpoint file.
        train_dataset:
            Training dataset to associate with the trainer.
        val_dataset:
            Validation dataset to associate with the trainer.

        Returns
        -------
        ValueTrainer
            Trainer with model and state restored from checkpoint.
        """
        checkpoint: dict[str, Any] = torch.load(path, weights_only=False)
        model_config = ValueNetworkConfig.from_dict(checkpoint["config"])
        model = ValueNetwork(model_config)
        trainer_config = TrainerConfig.from_dict(checkpoint.get("trainer_config", {}))
        normalizer = FeatureNormalizer.from_dict(checkpoint.get("normalizer", {}))

        trainer = cls(
            model=model,
            config=trainer_config,
            train_dataset=train_dataset,
            val_dataset=val_dataset,
            normalizer=normalizer,
        )
        trainer.load_checkpoint(path)
        return trainer
