"""Policy network training infrastructure for BimodalHarness.

Provides:
- PolicyTrainerConfig: Training hyperparameter configuration
- PolicyTrainer: Full train/evaluate/checkpoint orchestration with masked CE loss
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import torch
import torch.nn as nn
import torch.optim as optim
import torch.utils.data

from bimodal_harness.data.policy_dataset import ProofStepDataset, policy_collate_fn
from bimodal_harness.models.policy import PolicyFeatureEncoder, PolicyNetwork, PolicyNetworkConfig
from bimodal_harness.schema.records import ProofStepRecord


# ---------------------------------------------------------------------------
# PolicyTrainerConfig
# ---------------------------------------------------------------------------


@dataclass
class PolicyTrainerConfig:
    """Hyperparameter configuration for PolicyTrainer.

    Parameters
    ----------
    learning_rate:
        Initial learning rate for AdamW optimizer. Default: 3e-4.
    batch_size:
        Batch size for training DataLoader. Default: 64.
    max_epochs:
        Maximum number of training epochs. Default: 50.
    weight_decay:
        L2 regularization coefficient for AdamW optimizer. Default: 1e-4.
    patience:
        Number of epochs without validation top-1 improvement before early stopping.
        Default: 7.
    label_smoothing:
        Label smoothing epsilon for CrossEntropyLoss. Default: 0.1.
    focal_loss_gamma:
        Focal loss gamma. 0.0 disables focal loss (standard CE). Default: 0.0.
    seed:
        Random seed for reproducibility. Default: 42.
    gradient_clip_norm:
        Max gradient norm for gradient clipping. Default: 1.0.
    """

    learning_rate: float = 3e-4
    batch_size: int = 64
    max_epochs: int = 50
    weight_decay: float = 1e-4
    patience: int = 7
    label_smoothing: float = 0.1
    focal_loss_gamma: float = 0.0
    seed: int = 42
    gradient_clip_norm: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize config to a plain dictionary."""
        return {
            "learning_rate": self.learning_rate,
            "batch_size": self.batch_size,
            "max_epochs": self.max_epochs,
            "weight_decay": self.weight_decay,
            "patience": self.patience,
            "label_smoothing": self.label_smoothing,
            "focal_loss_gamma": self.focal_loss_gamma,
            "seed": self.seed,
            "gradient_clip_norm": self.gradient_clip_norm,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PolicyTrainerConfig:
        """Deserialize config from a plain dictionary."""
        return cls(
            learning_rate=float(data.get("learning_rate", 3e-4)),
            batch_size=int(data.get("batch_size", 64)),
            max_epochs=int(data.get("max_epochs", 50)),
            weight_decay=float(data.get("weight_decay", 1e-4)),
            patience=int(data.get("patience", 7)),
            label_smoothing=float(data.get("label_smoothing", 0.1)),
            focal_loss_gamma=float(data.get("focal_loss_gamma", 0.0)),
            seed=int(data.get("seed", 42)),
            gradient_clip_norm=float(data.get("gradient_clip_norm", 1.0)),
        )


# ---------------------------------------------------------------------------
# PolicyTrainer
# ---------------------------------------------------------------------------


class PolicyTrainer:
    """Orchestrates training, evaluation, and checkpointing of a PolicyNetwork.

    Uses masked cross-entropy loss: the frame-class mask is applied to logits
    before loss computation so invalid actions receive effectively zero probability.

    Parameters
    ----------
    model:
        PolicyNetwork instance to train.
    config:
        PolicyTrainerConfig with hyperparameters.
    train_records:
        List of ProofStepRecord for training.
    val_records:
        List of ProofStepRecord for validation.
    encoder:
        Optional PolicyFeatureEncoder; creates a default one if not provided.
    """

    def __init__(
        self,
        model: PolicyNetwork,
        config: PolicyTrainerConfig,
        train_records: list[ProofStepRecord],
        val_records: list[ProofStepRecord],
        encoder: PolicyFeatureEncoder | None = None,
    ) -> None:
        self.model = model
        self.config = config
        self.train_records = train_records
        self.val_records = val_records
        self.encoder = encoder if encoder is not None else PolicyFeatureEncoder()

        torch.manual_seed(config.seed)

        self.optimizer = optim.AdamW(
            model.parameters(),
            lr=config.learning_rate,
            weight_decay=config.weight_decay,
        )
        self.scheduler = optim.lr_scheduler.CosineAnnealingLR(
            self.optimizer, T_max=config.max_epochs
        )
        # Use reduction='none' to implement mask-aware label smoothing manually
        self._ce_loss = nn.CrossEntropyLoss(reduction="none")

        self._current_epoch: int = 0
        self._best_val_top1: float = 0.0

    def _make_train_loader(self) -> torch.utils.data.DataLoader:
        ds = ProofStepDataset(self.train_records)
        return torch.utils.data.DataLoader(
            ds,
            batch_size=self.config.batch_size,
            shuffle=True,
            collate_fn=policy_collate_fn,
            drop_last=False,
        )

    def _masked_loss(
        self, logits: torch.Tensor, targets: torch.Tensor, masks: torch.Tensor
    ) -> torch.Tensor:
        """Compute mask-aware cross-entropy loss with label smoothing.

        Applies frame-class mask to logits before softmax so invalid actions
        receive zero probability. Label smoothing is distributed only over
        valid actions to avoid -inf log-probability from masked positions.

        Parameters
        ----------
        logits:
            Raw model logits of shape [B, num_actions].
        targets:
            Action index targets of shape [B], dtype int64.
        masks:
            Float mask of shape [B, num_actions], 1.0 = valid, 0.0 = invalid.

        Returns
        -------
        torch.Tensor
            Scalar loss value.
        """
        smoothing = self.config.label_smoothing
        bool_mask = masks.bool()

        # Set invalid action logits to -inf so they get zero softmax probability
        masked_logits = logits.clone()
        masked_logits[~bool_mask] = float("-inf")

        if smoothing == 0.0:
            return self._ce_loss(masked_logits, targets).mean()

        # Custom label smoothing over valid actions only:
        # loss = (1 - eps) * -log(p_target) + eps * (-1/n_valid) * sum_valid(log p_i)
        log_probs = torch.log_softmax(masked_logits, dim=-1)  # [B, 49]

        # Hard-target CE component
        target_log_probs = log_probs.gather(1, targets.unsqueeze(1)).squeeze(1)  # [B]
        hard_loss = -target_log_probs

        # Smooth component: mean log-prob over valid actions only.
        # Replace -inf log_probs with 0 before masking to avoid NaN from -inf * 0.
        log_probs_safe = log_probs.clone()
        log_probs_safe[~bool_mask] = 0.0
        n_valid = masks.sum(dim=-1).clamp(min=1)  # [B]
        smooth_loss = -(log_probs_safe * masks).sum(dim=-1) / n_valid  # [B]

        loss = (1.0 - smoothing) * hard_loss + smoothing * smooth_loss
        return loss.mean()

    def train_epoch(self, epoch: int) -> float:
        """Run one training epoch.

        Parameters
        ----------
        epoch:
            Current epoch index (0-based).

        Returns
        -------
        float
            Mean cross-entropy loss over the epoch. Returns 0.0 if no batches.
        """
        self.model.train()
        total_loss = 0.0
        total_batches = 0

        loader = self._make_train_loader()
        for features, targets, masks in loader:
            if features.shape[0] == 0:
                continue

            self.optimizer.zero_grad()
            logits = self.model(features)  # [B, 49]
            loss = self._masked_loss(logits, targets, masks)
            loss.backward()

            nn.utils.clip_grad_norm_(
                self.model.parameters(), self.config.gradient_clip_norm
            )
            self.optimizer.step()

            total_loss += loss.item()
            total_batches += 1

        self._current_epoch = epoch
        return total_loss / total_batches if total_batches > 0 else 0.0

    def evaluate(self, records: list[ProofStepRecord]) -> dict[str, Any]:
        """Evaluate the model on a list of records.

        Computes:
        - ``top1_acc``: Top-1 accuracy
        - ``top5_acc``: Top-5 accuracy
        - ``mrr``: Mean Reciprocal Rank
        - ``per_rule_accuracy``: dict mapping rule name -> top-1 accuracy
        - ``valid_prob_mass``: mean fraction of softmax probability on valid actions

        Parameters
        ----------
        records:
            List of ProofStepRecord to evaluate on.

        Returns
        -------
        dict[str, Any]
            Dictionary with evaluation metrics.
        """
        self.model.eval()
        ds = ProofStepDataset(records)
        loader = torch.utils.data.DataLoader(
            ds,
            batch_size=self.config.batch_size,
            shuffle=False,
            collate_fn=policy_collate_fn,
            drop_last=False,
        )

        all_top1: list[float] = []
        all_top5: list[float] = []
        all_rr: list[float] = []
        all_valid_mass: list[float] = []
        # For per-rule accuracy: need record-level access
        # We'll collect predictions alongside records
        all_preds: list[int] = []
        all_targets_list: list[int] = []
        rule_lookup: list[str] = [r.rule for r in records]

        with torch.no_grad():
            for features, targets, masks in loader:
                if features.shape[0] == 0:
                    continue

                logits = self.model(features)  # [B, 49]

                # Apply mask for probability computation
                bool_mask = masks.bool()
                masked_logits = logits.clone()
                masked_logits[~bool_mask] = float("-inf")
                probs = torch.softmax(masked_logits, dim=-1)  # [B, 49]

                # Top-1
                preds = probs.argmax(dim=-1)  # [B]
                top1 = (preds == targets).float().tolist()
                all_top1.extend(top1)

                # Top-5
                top5_indices = probs.topk(5, dim=-1).indices  # [B, 5]
                top5_hits = (top5_indices == targets.unsqueeze(1)).any(dim=1).float().tolist()
                all_top5.extend(top5_hits)

                # MRR
                sorted_indices = probs.argsort(dim=-1, descending=True)  # [B, 49]
                for b in range(targets.shape[0]):
                    target_idx = targets[b].item()
                    rank_positions = (sorted_indices[b] == target_idx).nonzero(as_tuple=True)[0]
                    if len(rank_positions) > 0:
                        rank = rank_positions[0].item() + 1  # 1-indexed
                        all_rr.append(1.0 / rank)
                    else:
                        all_rr.append(0.0)

                # Valid probability mass
                valid_mass = probs[bool_mask.reshape(probs.shape[0], -1)].reshape(probs.shape[0], -1).sum(dim=-1)
                all_valid_mass.extend(valid_mass.tolist())

                all_preds.extend(preds.tolist())
                all_targets_list.extend(targets.tolist())

        if not all_top1:
            return {
                "top1_acc": 0.0,
                "top5_acc": 0.0,
                "mrr": 0.0,
                "per_rule_accuracy": {},
                "valid_prob_mass": 0.0,
            }

        # Per-rule accuracy
        rule_correct: dict[str, list[float]] = {}
        for i, (pred, target) in enumerate(zip(all_preds, all_targets_list)):
            rule = rule_lookup[i] if i < len(rule_lookup) else "unknown"
            if rule not in rule_correct:
                rule_correct[rule] = []
            rule_correct[rule].append(float(pred == target))

        per_rule_acc = {
            rule: float(sum(hits)) / len(hits)
            for rule, hits in rule_correct.items()
        }

        return {
            "top1_acc": float(sum(all_top1)) / len(all_top1),
            "top5_acc": float(sum(all_top5)) / len(all_top5),
            "mrr": float(sum(all_rr)) / len(all_rr),
            "per_rule_accuracy": per_rule_acc,
            "valid_prob_mass": float(sum(all_valid_mass)) / len(all_valid_mass),
        }

    def train(self) -> dict[str, Any]:
        """Run the full training loop with early stopping.

        Trains for up to ``config.max_epochs`` epochs, stopping early if
        validation top-1 accuracy does not improve for ``config.patience``
        consecutive epochs.

        Returns
        -------
        dict[str, Any]
            Summary with keys:
            - "best_epoch": epoch with best validation top-1
            - "best_val_top1": best validation top-1 accuracy achieved
            - "final_epoch": last epoch completed
            - "train_losses": list of per-epoch training losses
            - "val_metrics": list of per-epoch validation metric dicts
        """
        best_epoch = 0
        best_val_top1 = 0.0
        best_model_state: dict[str, torch.Tensor] = {}
        epochs_without_improvement = 0
        train_losses: list[float] = []
        val_metrics_history: list[dict[str, Any]] = []

        for epoch in range(self.config.max_epochs):
            train_loss = self.train_epoch(epoch)
            val_metrics = self.evaluate(self.val_records)

            self.scheduler.step()

            train_losses.append(train_loss)
            val_metrics_history.append(val_metrics)

            current_val_top1 = val_metrics["top1_acc"]

            if current_val_top1 > best_val_top1:
                best_val_top1 = current_val_top1
                best_epoch = epoch
                best_model_state = {
                    k: v.clone() for k, v in self.model.state_dict().items()
                }
                epochs_without_improvement = 0
            else:
                epochs_without_improvement += 1

            if epochs_without_improvement >= self.config.patience:
                if best_model_state:
                    self.model.load_state_dict(best_model_state)
                break

        if best_model_state:
            self.model.load_state_dict(best_model_state)
        self._best_val_top1 = best_val_top1

        return {
            "best_epoch": best_epoch,
            "best_val_top1": best_val_top1,
            "final_epoch": epoch,
            "train_losses": train_losses,
            "val_metrics": val_metrics_history,
        }

    def save_checkpoint(self, path: str) -> None:
        """Save model state, config, encoder, and training metadata.

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
            "encoder": self.encoder.to_dict(),
            "epoch": self._current_epoch,
            "best_val_top1": self._best_val_top1,
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
            The full checkpoint dictionary.
        """
        checkpoint: dict[str, Any] = torch.load(path, weights_only=False)
        self.model.load_state_dict(checkpoint["model_state_dict"])
        self._current_epoch = int(checkpoint.get("epoch", 0))
        self._best_val_top1 = float(checkpoint.get("best_val_top1", 0.0))

        if "encoder" in checkpoint:
            self.encoder = PolicyFeatureEncoder.from_dict(checkpoint["encoder"])

        return checkpoint

    @classmethod
    def from_checkpoint(
        cls,
        path: str,
        train_records: list[ProofStepRecord],
        val_records: list[ProofStepRecord],
    ) -> PolicyTrainer:
        """Create a PolicyTrainer from a saved checkpoint.

        Parameters
        ----------
        path:
            Path to checkpoint file.
        train_records:
            Training records to associate with the trainer.
        val_records:
            Validation records to associate with the trainer.

        Returns
        -------
        PolicyTrainer
            Trainer with model and state restored from checkpoint.
        """
        checkpoint: dict[str, Any] = torch.load(path, weights_only=False)
        model_config = PolicyNetworkConfig.from_dict(checkpoint["config"])
        model = PolicyNetwork(model_config)
        trainer_config = PolicyTrainerConfig.from_dict(checkpoint.get("trainer_config", {}))
        encoder = PolicyFeatureEncoder.from_dict(checkpoint.get("encoder", {}))

        trainer = cls(
            model=model,
            config=trainer_config,
            train_records=train_records,
            val_records=val_records,
            encoder=encoder,
        )
        trainer.load_checkpoint(path)
        return trainer
