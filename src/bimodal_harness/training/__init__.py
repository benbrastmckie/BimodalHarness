"""Training infrastructure: self-play loop and online learning."""

from __future__ import annotations

from bimodal_harness.training.policy_trainer import (
    PolicyTrainer,
    PolicyTrainerConfig,
)
from bimodal_harness.training.value_trainer import (
    TrainerConfig,
    ValueTrainer,
    value_collate_fn,
)

__all__ = [
    # Policy network trainer
    "PolicyTrainer",
    "PolicyTrainerConfig",
    # Value network trainer
    "TrainerConfig",
    "ValueTrainer",
    "value_collate_fn",
]
