"""Training infrastructure: self-play loop and online learning."""

from __future__ import annotations

from bimodal_harness.training.value_trainer import (
    TrainerConfig,
    ValueTrainer,
    value_collate_fn,
)

__all__ = [
    "TrainerConfig",
    "ValueTrainer",
    "value_collate_fn",
]
