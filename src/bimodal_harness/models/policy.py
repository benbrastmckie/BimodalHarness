"""Policy network for predicting proof step distributions.

Provides:
- PolicyNetworkConfig: Dataclass for model hyperparameters
- encode_proof_step: Encode a ProofStepRecord to a 25-dim feature tensor
- PolicyNetwork: PyTorch MLP predicting action logits over 49 actions
- PolicyFeatureEncoder: Serializable wrapper around encode_proof_step
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import torch
import torch.nn as nn

from bimodal_harness.models.value import encode_pattern_key
from bimodal_harness.schema.actions import FRAME_CLASS_MASKS
from bimodal_harness.schema.features import _complexity, extract_pattern_key
from bimodal_harness.schema.records import ProofStepRecord

# Frame class ordering for one-hot encoding (must be stable/sorted).
_FRAME_CLASSES: list[str] = ["Base", "Dense", "Discrete"]
_FRAME_CLASS_INDEX: dict[str, int] = {fc: i for i, fc in enumerate(_FRAME_CLASSES)}


# ---------------------------------------------------------------------------
# PolicyNetworkConfig
# ---------------------------------------------------------------------------


@dataclass
class PolicyNetworkConfig:
    """Configuration for the PolicyNetwork MLP.

    Parameters
    ----------
    input_dim:
        Dimensionality of the input feature vector. Default: 25.
    num_actions:
        Number of output actions. Default: 49.
    hidden_sizes:
        List of hidden layer sizes. Default: [1024, 512, 256].
    dropout:
        Dropout probability applied after each hidden layer. Default: 0.1.
    label_smoothing:
        Label smoothing epsilon for cross-entropy loss. Default: 0.1.
    """

    input_dim: int = 25
    num_actions: int = 49
    hidden_sizes: list[int] = field(default_factory=lambda: [1024, 512, 256])
    dropout: float = 0.1
    label_smoothing: float = 0.1

    def to_dict(self) -> dict[str, Any]:
        """Serialize config to a plain dictionary."""
        return {
            "input_dim": self.input_dim,
            "num_actions": self.num_actions,
            "hidden_sizes": list(self.hidden_sizes),
            "dropout": self.dropout,
            "label_smoothing": self.label_smoothing,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PolicyNetworkConfig:
        """Deserialize config from a plain dictionary."""
        return cls(
            input_dim=int(data.get("input_dim", 25)),
            num_actions=int(data.get("num_actions", 49)),
            hidden_sizes=list(data.get("hidden_sizes", [1024, 512, 256])),
            dropout=float(data.get("dropout", 0.1)),
            label_smoothing=float(data.get("label_smoothing", 0.1)),
        )


# ---------------------------------------------------------------------------
# encode_proof_step
# ---------------------------------------------------------------------------


def encode_proof_step(record: ProofStepRecord) -> torch.Tensor:
    """Encode a ProofStepRecord into a 25-dimensional feature tensor.

    Encoding layout:
    - Dims 0-11:  12-dim PatternKey from goal_json (via encode_pattern_key)
    - Dims 12-15: 4-dim context summary:
                    [log1p(len(context)), has_context,
                     max_context_complexity, mean_context_complexity]
    - Dims 16-17: 2-dim depth features: [log1p(depth), log1p(proof_height)]
    - Dims 18-20: 3-dim frame class one-hot: [Base, Dense, Discrete]
    - Dims 21-24: 4-dim subgoal summary:
                    [log1p(len(subgoals)), has_subgoals,
                     mean_subgoal_complexity, max_subgoal_depth]

    Parameters
    ----------
    record:
        ProofStepRecord to encode.

    Returns
    -------
    torch.Tensor
        Shape [25], dtype=float32.
    """
    # 12-dim PatternKey from goal formula
    goal_pattern_key = extract_pattern_key(record.goal_json)
    goal_features = encode_pattern_key(goal_pattern_key)  # [12]

    # 4-dim context features
    ctx_len = len(record.context)
    if ctx_len > 0:
        ctx_complexities = [
            float(_complexity({"tag": "atom", "name": s}) if not isinstance(s, dict) else _complexity(s))
            for s in record.context
        ]
        # context strings -> treat each as a simple atom of complexity 1
        # (we don't have context formula JSON, just pretty strings)
        ctx_complexities = [1.0] * ctx_len
        max_ctx_complexity = float(max(ctx_complexities))
        mean_ctx_complexity = float(sum(ctx_complexities)) / ctx_len
    else:
        max_ctx_complexity = 0.0
        mean_ctx_complexity = 0.0

    context_features = torch.tensor(
        [
            torch.log1p(torch.tensor(float(ctx_len))).item(),
            float(ctx_len > 0),
            max_ctx_complexity,
            mean_ctx_complexity,
        ],
        dtype=torch.float32,
    )  # [4]

    # 2-dim depth features
    depth_features = torch.tensor(
        [
            torch.log1p(torch.tensor(float(record.depth))).item(),
            torch.log1p(torch.tensor(float(record.proof_height))).item(),
        ],
        dtype=torch.float32,
    )  # [2]

    # 3-dim frame class one-hot
    frame_one_hot = torch.zeros(3, dtype=torch.float32)
    fc_idx = _FRAME_CLASS_INDEX.get(record.frame_class, 0)
    frame_one_hot[fc_idx] = 1.0  # [3]

    # 4-dim subgoal features
    n_subgoals = len(record.subgoals)
    if n_subgoals > 0:
        subgoal_complexities = [float(_complexity(sg)) for sg in record.subgoals]
        mean_sg_complexity = float(sum(subgoal_complexities)) / n_subgoals
        max_sg_depth = float(max(subgoal_complexities))  # use complexity as proxy for depth
    else:
        mean_sg_complexity = 0.0
        max_sg_depth = 0.0

    subgoal_features = torch.tensor(
        [
            torch.log1p(torch.tensor(float(n_subgoals))).item(),
            float(n_subgoals > 0),
            mean_sg_complexity,
            max_sg_depth,
        ],
        dtype=torch.float32,
    )  # [4]

    return torch.cat(
        [goal_features, context_features, depth_features, frame_one_hot, subgoal_features],
        dim=0,
    )  # [25]


# ---------------------------------------------------------------------------
# PolicyFeatureEncoder
# ---------------------------------------------------------------------------


class PolicyFeatureEncoder:
    """Serializable wrapper for proof step feature encoding.

    Wraps ``encode_proof_step`` with a dict-based serialization interface
    suitable for checkpoint save/load (mirrors FeatureNormalizer pattern).
    """

    def __init__(self) -> None:
        self._frame_classes: list[str] = list(_FRAME_CLASSES)

    def encode(self, record: ProofStepRecord) -> torch.Tensor:
        """Encode a ProofStepRecord to a 25-dim tensor.

        Parameters
        ----------
        record:
            ProofStepRecord instance to encode.

        Returns
        -------
        torch.Tensor
            Shape [25], dtype=float32.
        """
        return encode_proof_step(record)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the encoder state to a plain dictionary."""
        return {
            "frame_classes": self._frame_classes,
            "num_features": 25,
            "num_goal_features": 12,
            "num_context_features": 4,
            "num_depth_features": 2,
            "num_frame_features": 3,
            "num_subgoal_features": 4,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PolicyFeatureEncoder:
        """Deserialize a PolicyFeatureEncoder from a plain dictionary.

        Parameters
        ----------
        data:
            Dictionary previously produced by ``to_dict()``.

        Returns
        -------
        PolicyFeatureEncoder
            Restored encoder instance.
        """
        obj = cls()
        stored_classes = list(data.get("frame_classes", []))
        if stored_classes and stored_classes != obj._frame_classes:
            raise ValueError(
                f"Frame class order mismatch: stored {stored_classes} != current {obj._frame_classes}"
            )
        return obj

    def __repr__(self) -> str:
        return f"PolicyFeatureEncoder(num_features=25, frame_classes={self._frame_classes})"


# ---------------------------------------------------------------------------
# PolicyNetwork
# ---------------------------------------------------------------------------


class PolicyNetwork(nn.Module):
    """MLP policy network that predicts action logits over 49 proof actions.

    Architecture:
        For each hidden size h_i in hidden_sizes:
            Linear(prev_size -> h_i)
            LayerNorm(h_i)
            GELU()
            Dropout(dropout)
        Final: Linear(last_hidden -> num_actions)

    Parameters
    ----------
    config:
        PolicyNetworkConfig instance specifying architecture hyperparameters.

    Examples
    --------
    >>> config = PolicyNetworkConfig()
    >>> net = PolicyNetwork(config)
    >>> x = torch.randn(32, 25)
    >>> logits = net(x)
    >>> logits.shape
    torch.Size([32, 49])
    """

    def __init__(self, config: PolicyNetworkConfig | None = None) -> None:
        super().__init__()
        if config is None:
            config = PolicyNetworkConfig()
        self.config = config

        layers: list[nn.Module] = []
        in_size = config.input_dim
        for h_size in config.hidden_sizes:
            layers.append(nn.Linear(in_size, h_size))
            layers.append(nn.LayerNorm(h_size))
            layers.append(nn.GELU())
            layers.append(nn.Dropout(p=config.dropout))
            in_size = h_size

        layers.append(nn.Linear(in_size, config.num_actions))

        self.network = nn.Sequential(*layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Predict action logits from proof step features.

        Parameters
        ----------
        x:
            Input tensor of shape [B, input_dim] (default [B, 25]).

        Returns
        -------
        torch.Tensor
            Shape [B, num_actions] raw logits (before softmax).
        """
        return self.network(x)

    def apply_frame_class_mask(
        self, logits: torch.Tensor, mask: torch.Tensor
    ) -> torch.Tensor:
        """Apply a frame-class boolean mask to logits, setting invalid actions to -inf.

        Parameters
        ----------
        logits:
            Raw logits tensor of shape [B, num_actions] or [num_actions].
        mask:
            Boolean mask tensor of shape [B, num_actions] or [num_actions].
            True = valid action, False = invalid action.

        Returns
        -------
        torch.Tensor
            Logits with invalid action positions set to -inf (same shape as input).
        """
        masked = logits.clone()
        masked[~mask.bool()] = float("-inf")
        return masked

    @property
    def param_count(self) -> int:
        """Return total number of trainable parameters."""
        return sum(p.numel() for p in self.parameters() if p.requires_grad)
