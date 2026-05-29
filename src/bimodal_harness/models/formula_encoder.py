"""Formula AST tokenizer and transformer encoder for the policy network.

Provides:
- FormulaTokenizer: Tokenizes formula JSON trees via prefix-order linearization
- FormulaTransformerEncoder: Small transformer producing CLS-token embeddings
- PolicyNetworkV2: Upgraded policy network using transformer + context/depth/frame features
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import torch
import torch.nn as nn

from bimodal_harness.schema.actions import FRAME_CLASS_MASKS
from bimodal_harness.schema.records import ProofStepRecord

# ---------------------------------------------------------------------------
# FormulaTokenizer
# ---------------------------------------------------------------------------

# AST tag tokens (6)
_TAG_TOKENS = ["atom", "bot", "imp", "box", "untl", "snce"]

# Special tokens
_SPECIAL_TOKENS = ["PAD", "UNK", "BOS", "EOS"]

# Atom name hash buckets (8) for open-ended atom coverage
_ATOM_BUCKETS = [f"ATOM_{i}" for i in range(8)]

# Full vocabulary (ordered)
_VOCAB = _SPECIAL_TOKENS + _TAG_TOKENS + _ATOM_BUCKETS
_VOCAB_SIZE = len(_VOCAB)  # 4 + 6 + 8 = 18

_TOKEN_TO_ID: dict[str, int] = {tok: i for i, tok in enumerate(_VOCAB)}
_PAD_ID = _TOKEN_TO_ID["PAD"]
_UNK_ID = _TOKEN_TO_ID["UNK"]
_BOS_ID = _TOKEN_TO_ID["BOS"]
_EOS_ID = _TOKEN_TO_ID["EOS"]


def _atom_bucket(name: str) -> str:
    """Hash an atom name to one of 8 bucket tokens."""
    return _ATOM_BUCKETS[hash(name) % 8]


def _linearize(formula: dict[str, Any], tokens: list[int]) -> None:
    """Recursively linearize a formula JSON tree in prefix order.

    Appends token IDs to `tokens` in-place. Does NOT include BOS/EOS.
    """
    tag = formula.get("tag", "")
    tag_id = _TOKEN_TO_ID.get(tag, _UNK_ID)
    tokens.append(tag_id)

    if tag == "atom":
        name = str(formula.get("name", ""))
        bucket = _atom_bucket(name)
        tokens.append(_TOKEN_TO_ID[bucket])
    elif tag == "imp":
        _linearize(formula["left"], tokens)
        _linearize(formula["right"], tokens)
    elif tag == "box":
        _linearize(formula.get("child", formula.get("arg", {})), tokens)
    elif tag in ("untl", "snce"):
        _linearize(formula["event"], tokens)
        _linearize(formula["guard"], tokens)
    # atom, bot, UNK: no children


class FormulaTokenizer:
    """Tokenizes formula JSON trees via prefix-order linearization.

    Vocabulary (18 tokens):
    - 4 special: PAD(0), UNK(1), BOS(2), EOS(3)
    - 6 AST tags: atom(4), bot(5), imp(6), box(7), untl(8), snce(9)
    - 8 atom buckets: ATOM_0..ATOM_7 (10-17)

    Parameters
    ----------
    max_length:
        Maximum sequence length (including BOS and EOS tokens).
        Sequences are truncated to this length. Default: 128.
    """

    vocab_size: int = _VOCAB_SIZE

    def __init__(self, max_length: int = 128) -> None:
        self.max_length = max_length
        self._vocab = list(_VOCAB)
        self._token_to_id = dict(_TOKEN_TO_ID)

    def tokenize(self, formula_json: dict[str, Any]) -> list[int]:
        """Tokenize a formula JSON tree.

        Returns a list of token IDs starting with BOS and ending with EOS,
        truncated to max_length. Sequences longer than max_length - 1 are
        truncated before EOS is appended.

        Parameters
        ----------
        formula_json:
            Formula JSON tree (DataExport.lean format).

        Returns
        -------
        list[int]
            List of token IDs, length <= max_length.
        """
        tokens: list[int] = [_BOS_ID]
        _linearize(formula_json, tokens)

        # Truncate to leave room for EOS
        if len(tokens) >= self.max_length:
            tokens = tokens[: self.max_length - 1]
        tokens.append(_EOS_ID)
        return tokens

    def pad(self, token_ids: list[int]) -> list[int]:
        """Pad a token list to max_length with PAD tokens."""
        return token_ids + [_PAD_ID] * (self.max_length - len(token_ids))

    def to_dict(self) -> dict[str, Any]:
        """Serialize tokenizer state."""
        return {
            "vocab": self._vocab,
            "max_length": self.max_length,
            "vocab_size": self.vocab_size,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FormulaTokenizer:
        """Deserialize a FormulaTokenizer from a plain dictionary."""
        return cls(max_length=int(data.get("max_length", 128)))


# ---------------------------------------------------------------------------
# FormulaTransformerEncoder
# ---------------------------------------------------------------------------


class _PositionalEncoding(nn.Module):
    """Sinusoidal positional encoding."""

    def __init__(self, d_model: int, max_len: int = 128, dropout: float = 0.1) -> None:
        super().__init__()
        self.dropout = nn.Dropout(p=dropout)
        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(
            torch.arange(0, d_model, 2, dtype=torch.float) * (-math.log(10000.0) / d_model)
        )
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        pe = pe.unsqueeze(0)  # [1, max_len, d_model]
        self.register_buffer("pe", pe)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = x + self.pe[:, : x.size(1)]
        return self.dropout(x)


class FormulaTransformerEncoder(nn.Module):
    """Small transformer encoder producing a CLS-token embedding for formula JSON trees.

    Architecture:
        token embedding (vocab_size -> d_model)
        + positional encoding
        -> 3-layer TransformerEncoder (4 heads, d_ff=256)
        -> CLS token output [B, d_model]

    Parameters
    ----------
    d_model:
        Embedding dimension. Default: 128.
    nhead:
        Number of attention heads. Default: 4.
    num_layers:
        Number of TransformerEncoder layers. Default: 3.
    dim_feedforward:
        Feed-forward hidden size. Default: 256.
    dropout:
        Dropout probability. Default: 0.1.
    max_len:
        Maximum sequence length. Default: 128.
    vocab_size:
        Vocabulary size. Default: 18.
    """

    def __init__(
        self,
        d_model: int = 128,
        nhead: int = 4,
        num_layers: int = 3,
        dim_feedforward: int = 256,
        dropout: float = 0.1,
        max_len: int = 128,
        vocab_size: int = _VOCAB_SIZE,
    ) -> None:
        super().__init__()
        self.d_model = d_model
        self.embedding = nn.Embedding(vocab_size, d_model, padding_idx=_PAD_ID)
        self.pos_encoder = _PositionalEncoding(d_model, max_len=max_len, dropout=dropout)

        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model,
            nhead=nhead,
            dim_feedforward=dim_feedforward,
            dropout=dropout,
            batch_first=True,
        )
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)

    def forward(
        self, token_ids: torch.Tensor, padding_mask: torch.Tensor | None = None
    ) -> torch.Tensor:
        """Encode token sequences to CLS-token embeddings.

        Parameters
        ----------
        token_ids:
            Token id tensor of shape [B, seq_len], dtype int64.
        padding_mask:
            Boolean mask of shape [B, seq_len] where True indicates a padded
            position. If None, no masking is applied.

        Returns
        -------
        torch.Tensor
            CLS-token embeddings of shape [B, d_model].
        """
        x = self.embedding(token_ids)  # [B, seq_len, d_model]
        x = self.pos_encoder(x)  # [B, seq_len, d_model]
        x = self.transformer(x, src_key_padding_mask=padding_mask)  # [B, seq_len, d_model]
        return x[:, 0, :]  # CLS token at position 0: [B, d_model]

    @property
    def param_count(self) -> int:
        """Return total number of trainable parameters."""
        return sum(p.numel() for p in self.parameters() if p.requires_grad)


# ---------------------------------------------------------------------------
# PolicyNetworkV2
# ---------------------------------------------------------------------------

# Frame class ordering (must match policy.py)
_FRAME_CLASSES_V2: list[str] = ["Base", "Dense", "Discrete"]
_FRAME_CLASS_INDEX_V2: dict[str, int] = {fc: i for i, fc in enumerate(_FRAME_CLASSES_V2)}


def _encode_context_depth_frame(record: ProofStepRecord) -> torch.Tensor:
    """Encode context + depth + frame class to a 9-dim tensor.

    Layout:
    - Dims 0-3: 4-dim context summary (log1p len, has_context, max complexity, mean complexity)
    - Dims 4-5: 2-dim depth (log1p depth, log1p proof_height)
    - Dims 6-8: 3-dim frame class one-hot
    """
    ctx_len = len(record.context)
    ctx_features = torch.tensor(
        [
            math.log1p(ctx_len),
            float(ctx_len > 0),
            1.0 if ctx_len > 0 else 0.0,  # max context complexity (simplified)
            1.0 if ctx_len > 0 else 0.0,  # mean context complexity (simplified)
        ],
        dtype=torch.float32,
    )
    depth_features = torch.tensor(
        [math.log1p(record.depth), math.log1p(record.proof_height)],
        dtype=torch.float32,
    )
    frame_one_hot = torch.zeros(3, dtype=torch.float32)
    fc_idx = _FRAME_CLASS_INDEX_V2.get(record.frame_class, 0)
    frame_one_hot[fc_idx] = 1.0

    return torch.cat([ctx_features, depth_features, frame_one_hot], dim=0)  # [9]


class PolicyNetworkV2(nn.Module):
    """Upgraded policy network using a formula AST transformer + context features.

    Architecture:
        FormulaTransformerEncoder(goal) -> [B, 128]   (CLS-token embedding)
        + context/depth/frame features  -> [B, 9]
        concat                          -> [B, 137]
        MLP [512, 256]                  -> [B, 49] logits

    Exposes the same `forward()` -> [B, 49] interface as `PolicyNetwork`.

    Parameters
    ----------
    num_actions:
        Output dimension (default: 49).
    d_model:
        Transformer embedding dimension (default: 128).
    dropout:
        Dropout probability (default: 0.1).
    """

    def __init__(
        self,
        num_actions: int = 49,
        d_model: int = 128,
        dropout: float = 0.1,
    ) -> None:
        super().__init__()
        self.num_actions = num_actions
        self.d_model = d_model

        self.tokenizer = FormulaTokenizer(max_length=128)
        self.transformer = FormulaTransformerEncoder(d_model=d_model, dropout=dropout)

        # MLP head: 128 (transformer) + 9 (context/depth/frame) -> 49
        concat_dim = d_model + 9
        self.mlp = nn.Sequential(
            nn.Linear(concat_dim, 512),
            nn.LayerNorm(512),
            nn.GELU(),
            nn.Dropout(p=dropout),
            nn.Linear(512, 256),
            nn.LayerNorm(256),
            nn.GELU(),
            nn.Dropout(p=dropout),
            nn.Linear(256, num_actions),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Forward pass (direct feature tensor input).

        For use with pre-encoded feature tensors of shape [B, 137] where
        the first 128 dims are transformer embeddings and last 9 are
        context/depth/frame features.

        Parameters
        ----------
        x:
            Feature tensor of shape [B, 137].

        Returns
        -------
        torch.Tensor
            Logits of shape [B, 49].
        """
        return self.mlp(x)

    def forward_records(self, records: list[ProofStepRecord]) -> torch.Tensor:
        """Encode a batch of ProofStepRecords and produce logits.

        Parameters
        ----------
        records:
            List of B ProofStepRecord instances.

        Returns
        -------
        torch.Tensor
            Logits of shape [B, 49].
        """
        # Tokenize and pad goal formulas
        token_lists = [self.tokenizer.tokenize(r.goal_json) for r in records]
        max_len = max(len(t) for t in token_lists)
        padded = [t + [_PAD_ID] * (max_len - len(t)) for t in token_lists]

        token_ids = torch.tensor(padded, dtype=torch.long)  # [B, max_len]
        padding_mask = token_ids == _PAD_ID  # [B, max_len], True for padded positions

        # Transformer encoding
        goal_emb = self.transformer(token_ids, padding_mask)  # [B, 128]

        # Context/depth/frame features
        extra = torch.stack(
            [_encode_context_depth_frame(r) for r in records], dim=0
        )  # [B, 9]

        x = torch.cat([goal_emb, extra], dim=-1)  # [B, 137]
        return self.mlp(x)  # [B, 49]

    def apply_frame_class_mask(
        self, logits: torch.Tensor, mask: torch.Tensor
    ) -> torch.Tensor:
        """Apply frame-class mask, setting invalid action logits to -inf."""
        masked = logits.clone()
        masked[~mask.bool()] = float("-inf")
        return masked

    @property
    def param_count(self) -> int:
        """Return total number of trainable parameters."""
        return sum(p.numel() for p in self.parameters() if p.requires_grad)
