"""Value network for estimating proof state quality.

Provides:
- ValueNetworkConfig: Dataclass for model hyperparameters
- TOP_OPERATOR_INDEX: Stable sorted mapping of VALID_TOP_OPERATORS to indices 0-7
- encode_pattern_key: Encode a PatternKey to a 12-dim feature tensor
- FeatureNormalizer: Serializable wrapper around encode_pattern_key
- ValueNetwork: PyTorch MLP predicting derivation tree height
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import torch
import torch.nn as nn

from bimodal_harness.schema.constants import VALID_TOP_OPERATORS
from bimodal_harness.schema.records import PatternKey

# ---------------------------------------------------------------------------
# TOP_OPERATOR_INDEX
# ---------------------------------------------------------------------------

#: Stable sorted mapping from VALID_TOP_OPERATORS to indices 0-7.
#: Uses alphabetical sort for deterministic, reproducible encoding.
TOP_OPERATOR_INDEX: dict[str, int] = {
    op: idx for idx, op in enumerate(sorted(VALID_TOP_OPERATORS))
}

# The sorted order is:
#   0: AllFuture
#   1: AllPast
#   2: Atom
#   3: Bottom
#   4: Box
#   5: Implication
#   6: Since
#   7: Until

_NUM_TOP_OPERATORS: int = len(TOP_OPERATOR_INDEX)
assert _NUM_TOP_OPERATORS == 8, f"Expected 8 top operators, got {_NUM_TOP_OPERATORS}"


# ---------------------------------------------------------------------------
# ValueNetworkConfig
# ---------------------------------------------------------------------------


@dataclass
class ValueNetworkConfig:
    """Configuration for the ValueNetwork MLP.

    Parameters
    ----------
    input_dim:
        Dimensionality of the input feature vector. Default: 12
        (4 log1p-normalized numeric features + 8 one-hot top_operator).
    hidden_sizes:
        List of hidden layer sizes. Default: [2048, 1024, 512, 256].
    dropout:
        Dropout probability applied after each hidden layer. Default: 0.1.
    output_activation:
        Output activation function name. "softplus" ensures non-negative
        height predictions. Default: "softplus".
    """

    input_dim: int = 12
    hidden_sizes: list[int] = field(default_factory=lambda: [2048, 1024, 512, 256])
    dropout: float = 0.1
    output_activation: str = "softplus"

    def to_dict(self) -> dict[str, Any]:
        """Serialize config to a plain dictionary."""
        return {
            "input_dim": self.input_dim,
            "hidden_sizes": list(self.hidden_sizes),
            "dropout": self.dropout,
            "output_activation": self.output_activation,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ValueNetworkConfig:
        """Deserialize config from a plain dictionary."""
        return cls(
            input_dim=int(data["input_dim"]),
            hidden_sizes=list(data["hidden_sizes"]),
            dropout=float(data["dropout"]),
            output_activation=str(data["output_activation"]),
        )


# ---------------------------------------------------------------------------
# encode_pattern_key
# ---------------------------------------------------------------------------


def encode_pattern_key(pattern_key: PatternKey) -> torch.Tensor:
    """Encode a PatternKey into a 12-dimensional feature tensor.

    Encoding:
    - Dimensions 0-3: log1p of [modal_depth, temporal_depth, imp_count, complexity]
    - Dimensions 4-11: one-hot encoding of top_operator (8 categories, sorted order)

    Parameters
    ----------
    pattern_key:
        PatternKey dataclass instance to encode.

    Returns
    -------
    torch.Tensor
        Shape [12], dtype=float32.
    """
    # 4 numeric features: apply log1p for scale normalization
    numeric = torch.tensor(
        [
            pattern_key.modal_depth,
            pattern_key.temporal_depth,
            pattern_key.imp_count,
            pattern_key.complexity,
        ],
        dtype=torch.float32,
    )
    numeric = torch.log1p(numeric)  # shape [4]

    # 8-dim one-hot for top_operator
    one_hot = torch.zeros(_NUM_TOP_OPERATORS, dtype=torch.float32)
    op_idx = TOP_OPERATOR_INDEX[pattern_key.top_operator]
    one_hot[op_idx] = 1.0  # shape [8]

    return torch.cat([numeric, one_hot], dim=0)  # shape [12]


# ---------------------------------------------------------------------------
# FeatureNormalizer
# ---------------------------------------------------------------------------


class FeatureNormalizer:
    """Serializable wrapper for PatternKey feature encoding.

    Wraps ``encode_pattern_key`` with a dict-based serialization interface
    suitable for checkpoint save/load.

    Currently, normalization is fixed (log1p for numerics, one-hot for
    categoricals) and requires no fitted statistics, so ``to_dict`` /
    ``from_dict`` store only the operator index for verification.
    """

    def __init__(self) -> None:
        # Store the operator index for round-trip verification.
        self._operator_index: dict[str, int] = dict(TOP_OPERATOR_INDEX)

    def encode(self, pattern_key: PatternKey) -> torch.Tensor:
        """Encode a PatternKey to a 12-dim tensor.

        Parameters
        ----------
        pattern_key:
            PatternKey instance to encode.

        Returns
        -------
        torch.Tensor
            Shape [12], dtype=float32.
        """
        return encode_pattern_key(pattern_key)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the normalizer state to a plain dictionary."""
        return {
            "operator_index": self._operator_index,
            "num_features": 12,
            "num_numeric": 4,
            "num_categorical": _NUM_TOP_OPERATORS,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FeatureNormalizer:
        """Deserialize a FeatureNormalizer from a plain dictionary.

        Parameters
        ----------
        data:
            Dictionary previously produced by ``to_dict()``.

        Returns
        -------
        FeatureNormalizer
            Restored normalizer instance.
        """
        obj = cls()
        # Validate operator index for compatibility
        stored_index = dict(data.get("operator_index", {}))
        if stored_index and stored_index != obj._operator_index:
            raise ValueError(
                f"Operator index mismatch: stored {stored_index} != current {obj._operator_index}"
            )
        return obj

    def __repr__(self) -> str:
        return f"FeatureNormalizer(num_features=12, operators={sorted(self._operator_index.keys())})"


# ---------------------------------------------------------------------------
# ValueNetwork
# ---------------------------------------------------------------------------


class ValueNetwork(nn.Module):
    """MLP value network that predicts derivation tree height.

    Architecture:
        For each hidden size h_i in hidden_sizes:
            Linear(prev_size -> h_i)
            LayerNorm(h_i)
            GELU()
            Dropout(dropout)
        Final: Linear(last_hidden -> 1) -> Softplus()

    Parameters
    ----------
    config:
        ValueNetworkConfig instance specifying architecture hyperparameters.

    Examples
    --------
    >>> config = ValueNetworkConfig()
    >>> net = ValueNetwork(config)
    >>> x = torch.randn(32, 12)
    >>> y = net(x)
    >>> y.shape
    torch.Size([32, 1])
    """

    def __init__(self, config: ValueNetworkConfig | None = None) -> None:
        super().__init__()
        if config is None:
            config = ValueNetworkConfig()
        self.config = config

        # Build hidden blocks
        layers: list[nn.Module] = []
        in_size = config.input_dim
        for h_size in config.hidden_sizes:
            layers.append(nn.Linear(in_size, h_size))
            layers.append(nn.LayerNorm(h_size))
            layers.append(nn.GELU())
            layers.append(nn.Dropout(p=config.dropout))
            in_size = h_size

        # Final projection to scalar
        layers.append(nn.Linear(in_size, 1))

        # Output activation
        if config.output_activation == "softplus":
            layers.append(nn.Softplus())
        elif config.output_activation == "relu":
            layers.append(nn.ReLU())
        elif config.output_activation == "none":
            pass
        else:
            raise ValueError(
                f"Unknown output_activation: {config.output_activation!r}. "
                "Expected 'softplus', 'relu', or 'none'."
            )

        self.network = nn.Sequential(*layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Predict derivation tree height from PatternKey features.

        Parameters
        ----------
        x:
            Input tensor of shape [B, input_dim] (default [B, 12]).

        Returns
        -------
        torch.Tensor
            Shape [B, 1], non-negative predicted heights (via Softplus).
        """
        return self.network(x)

    @property
    def param_count(self) -> int:
        """Return total number of trainable parameters."""
        return sum(p.numel() for p in self.parameters() if p.requires_grad)
