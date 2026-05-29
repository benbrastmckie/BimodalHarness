"""Unit tests for the ValueNetwork model and feature encoding.

Tests:
- encode_pattern_key: correct 12-dim tensor encoding
- TOP_OPERATOR_INDEX: correct sorted ordering
- ValueNetwork: forward pass shapes, non-negative output, param count
- ValueNetworkConfig: instantiation and serialization
- FeatureNormalizer: to_dict/from_dict round-trip
"""

from __future__ import annotations

import math

import pytest
import torch

from bimodal_harness.models.value import (
    TOP_OPERATOR_INDEX,
    FeatureNormalizer,
    ValueNetwork,
    ValueNetworkConfig,
    encode_pattern_key,
)
from bimodal_harness.schema.constants import VALID_TOP_OPERATORS
from bimodal_harness.schema.records import PatternKey


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def make_pattern_key(
    modal_depth: int = 0,
    temporal_depth: int = 0,
    imp_count: int = 0,
    complexity: int = 1,
    top_operator: str = "Atom",
) -> PatternKey:
    """Helper to create PatternKey with defaults."""
    return PatternKey(
        modal_depth=modal_depth,
        temporal_depth=temporal_depth,
        imp_count=imp_count,
        complexity=complexity,
        top_operator=top_operator,
    )


# ---------------------------------------------------------------------------
# TOP_OPERATOR_INDEX tests
# ---------------------------------------------------------------------------


class TestTopOperatorIndex:
    """Tests for TOP_OPERATOR_INDEX constant."""

    def test_all_operators_present(self) -> None:
        """All VALID_TOP_OPERATORS are in the index."""
        for op in VALID_TOP_OPERATORS:
            assert op in TOP_OPERATOR_INDEX, f"Missing operator: {op}"

    def test_exactly_eight_operators(self) -> None:
        """Index has exactly 8 entries."""
        assert len(TOP_OPERATOR_INDEX) == 8

    def test_indices_are_zero_to_seven(self) -> None:
        """Indices cover 0-7 without gaps."""
        assert set(TOP_OPERATOR_INDEX.values()) == set(range(8))

    def test_sorted_alphabetical_order(self) -> None:
        """Operators are indexed in alphabetical order."""
        sorted_ops = sorted(VALID_TOP_OPERATORS)
        for idx, op in enumerate(sorted_ops):
            assert TOP_OPERATOR_INDEX[op] == idx, (
                f"Expected {op} at index {idx}, got {TOP_OPERATOR_INDEX[op]}"
            )

    def test_specific_operator_indices(self) -> None:
        """Verify specific known operator indices."""
        assert TOP_OPERATOR_INDEX["AllFuture"] == 0
        assert TOP_OPERATOR_INDEX["AllPast"] == 1
        assert TOP_OPERATOR_INDEX["Atom"] == 2
        assert TOP_OPERATOR_INDEX["Bottom"] == 3
        assert TOP_OPERATOR_INDEX["Box"] == 4
        assert TOP_OPERATOR_INDEX["Implication"] == 5
        assert TOP_OPERATOR_INDEX["Since"] == 6
        assert TOP_OPERATOR_INDEX["Until"] == 7


# ---------------------------------------------------------------------------
# encode_pattern_key tests
# ---------------------------------------------------------------------------


class TestEncodePatternKey:
    """Tests for encode_pattern_key function."""

    def test_output_shape(self) -> None:
        """Output has shape [12]."""
        pk = make_pattern_key()
        feat = encode_pattern_key(pk)
        assert feat.shape == torch.Size([12])

    def test_output_dtype(self) -> None:
        """Output is float32."""
        pk = make_pattern_key()
        feat = encode_pattern_key(pk)
        assert feat.dtype == torch.float32

    def test_atom_formula_one_hot(self) -> None:
        """Atom operator sets one-hot at index 2 (sorted position)."""
        pk = make_pattern_key(top_operator="Atom")
        feat = encode_pattern_key(pk)
        # First 4 are numeric, next 8 are one-hot
        one_hot = feat[4:]
        assert one_hot[TOP_OPERATOR_INDEX["Atom"]].item() == pytest.approx(1.0)
        # All other one-hot positions are 0
        expected_zero_mask = one_hot.clone()
        expected_zero_mask[TOP_OPERATOR_INDEX["Atom"]] = 0.0
        assert expected_zero_mask.sum().item() == pytest.approx(0.0)

    def test_numeric_features_log1p(self) -> None:
        """Numeric features are log1p-transformed."""
        pk = make_pattern_key(modal_depth=1, temporal_depth=0, imp_count=2, complexity=5)
        feat = encode_pattern_key(pk)
        expected_numerics = [
            math.log1p(1),
            math.log1p(0),
            math.log1p(2),
            math.log1p(5),
        ]
        for i, expected in enumerate(expected_numerics):
            assert feat[i].item() == pytest.approx(expected, abs=1e-6), (
                f"Numeric feature {i} mismatch: {feat[i].item()} != {expected}"
            )

    def test_zero_numeric_features(self) -> None:
        """Zero numeric features produce log1p(0) = 0 in tensor."""
        pk = make_pattern_key(modal_depth=0, temporal_depth=0, imp_count=0, complexity=1)
        feat = encode_pattern_key(pk)
        assert feat[0].item() == pytest.approx(0.0)  # log1p(0)
        assert feat[1].item() == pytest.approx(0.0)  # log1p(0)
        assert feat[2].item() == pytest.approx(0.0)  # log1p(0)
        assert feat[3].item() == pytest.approx(math.log1p(1))  # log1p(1) = log(2)

    def test_each_operator_produces_unique_one_hot(self) -> None:
        """Each of the 8 operators produces a distinct one-hot encoding."""
        encodings = []
        for op in sorted(VALID_TOP_OPERATORS):
            pk = make_pattern_key(top_operator=op)
            feat = encode_pattern_key(pk)
            encodings.append(feat[4:].tolist())

        # All encodings should be distinct
        assert len(encodings) == len({tuple(e) for e in encodings}), (
            "Two operators produced the same one-hot encoding"
        )

    def test_one_hot_sums_to_one(self) -> None:
        """One-hot portion sums to exactly 1.0 for any operator."""
        for op in VALID_TOP_OPERATORS:
            pk = make_pattern_key(top_operator=op)
            feat = encode_pattern_key(pk)
            one_hot_sum = feat[4:].sum().item()
            assert one_hot_sum == pytest.approx(1.0), (
                f"One-hot sum for {op} is {one_hot_sum}, expected 1.0"
            )

    def test_large_values_bounded(self) -> None:
        """log1p compression keeps large values manageable."""
        pk = make_pattern_key(modal_depth=100, temporal_depth=50, imp_count=200, complexity=1000)
        feat = encode_pattern_key(pk)
        # log1p(1000) ≈ 6.9, not 1000 - values should be < 10
        assert feat[:4].max().item() < 10.0


# ---------------------------------------------------------------------------
# ValueNetworkConfig tests
# ---------------------------------------------------------------------------


class TestValueNetworkConfig:
    """Tests for ValueNetworkConfig dataclass."""

    def test_default_config(self) -> None:
        """Default config has expected values."""
        config = ValueNetworkConfig()
        assert config.input_dim == 12
        assert config.hidden_sizes == [2048, 1024, 512, 256]
        assert config.dropout == pytest.approx(0.1)
        assert config.output_activation == "softplus"

    def test_to_dict_from_dict_round_trip(self) -> None:
        """Config serializes and deserializes correctly."""
        config = ValueNetworkConfig(
            input_dim=12,
            hidden_sizes=[128, 64],
            dropout=0.2,
            output_activation="relu",
        )
        d = config.to_dict()
        restored = ValueNetworkConfig.from_dict(d)
        assert restored.input_dim == config.input_dim
        assert restored.hidden_sizes == config.hidden_sizes
        assert restored.dropout == pytest.approx(config.dropout)
        assert restored.output_activation == config.output_activation

    def test_custom_hidden_sizes(self) -> None:
        """Custom hidden sizes are preserved."""
        sizes = [512, 256, 128, 64, 32]
        config = ValueNetworkConfig(hidden_sizes=sizes)
        assert config.hidden_sizes == sizes


# ---------------------------------------------------------------------------
# ValueNetwork tests
# ---------------------------------------------------------------------------


class TestValueNetwork:
    """Tests for ValueNetwork nn.Module."""

    def test_instantiation_default_config(self) -> None:
        """ValueNetwork instantiates with default config."""
        net = ValueNetwork()
        assert net is not None

    def test_instantiation_custom_config(self) -> None:
        """ValueNetwork instantiates with custom config."""
        config = ValueNetworkConfig(input_dim=12, hidden_sizes=[64, 32], dropout=0.0)
        net = ValueNetwork(config)
        assert net is not None

    def test_forward_shape_single(self) -> None:
        """forward([1, 12]) produces shape [1, 1]."""
        net = ValueNetwork(ValueNetworkConfig(hidden_sizes=[64, 32]))
        x = torch.randn(1, 12)
        net.eval()
        with torch.no_grad():
            y = net(x)
        assert y.shape == torch.Size([1, 1])

    def test_forward_shape_batch(self) -> None:
        """forward([B, 12]) produces shape [B, 1]."""
        net = ValueNetwork(ValueNetworkConfig(hidden_sizes=[64, 32]))
        for batch_size in [1, 4, 32, 128]:
            x = torch.randn(batch_size, 12)
            net.eval()
            with torch.no_grad():
                y = net(x)
            assert y.shape == torch.Size([batch_size, 1]), (
                f"Shape mismatch for batch_size={batch_size}: {y.shape}"
            )

    def test_output_non_negative(self) -> None:
        """All outputs are non-negative (Softplus activation)."""
        net = ValueNetwork(ValueNetworkConfig(hidden_sizes=[64, 32]))
        # Use deterministic inputs to test
        x = torch.randn(100, 12) * 10  # large inputs to stress Softplus
        net.eval()
        with torch.no_grad():
            y = net(x)
        assert (y >= 0).all(), f"Found negative outputs: {y[y < 0]}"

    def test_param_count_default_config(self) -> None:
        """Default config produces approximately 2.78M parameters."""
        net = ValueNetwork()
        # Default: input(12) -> 2048 -> 1024 -> 512 -> 256 -> 1
        # Params = (12*2048+2048) + (2048*1024+1024) + (1024*512+512) + (512*256+256) + (256*1+1)
        # = 26624 + 2098176 + 525312 + 131328 + 257 = 2781697... let's compute exactly
        expected = (
            (12 * 2048 + 2048)   # Linear(12, 2048) weight + bias
            + (2048)              # LayerNorm(2048) weight
            + (2048)              # LayerNorm(2048) bias
            + (2048 * 1024 + 1024)  # Linear(2048, 1024)
            + (1024)              # LayerNorm(1024) weight
            + (1024)              # LayerNorm(1024) bias
            + (1024 * 512 + 512)   # Linear(1024, 512)
            + (512)               # LayerNorm(512) weight
            + (512)               # LayerNorm(512) bias
            + (512 * 256 + 256)    # Linear(512, 256)
            + (256)               # LayerNorm(256) weight
            + (256)               # LayerNorm(256) bias
            + (256 * 1 + 1)       # Linear(256, 1) output
        )
        assert net.param_count == expected, (
            f"Expected {expected:,} params, got {net.param_count:,}"
        )

    def test_param_count_custom_small(self) -> None:
        """Custom small config has correct param count."""
        config = ValueNetworkConfig(input_dim=12, hidden_sizes=[32, 16], dropout=0.0)
        net = ValueNetwork(config)
        expected = (
            (12 * 32 + 32)  # Linear + LayerNorm(w) + LayerNorm(b)
            + 32 + 32
            + (32 * 16 + 16)
            + 16 + 16
            + (16 * 1 + 1)
        )
        assert net.param_count == expected

    def test_param_count_property_is_int(self) -> None:
        """param_count returns an int."""
        net = ValueNetwork(ValueNetworkConfig(hidden_sizes=[32]))
        assert isinstance(net.param_count, int)

    def test_config_is_stored(self) -> None:
        """ValueNetwork stores the config as an attribute."""
        config = ValueNetworkConfig(hidden_sizes=[64, 32])
        net = ValueNetwork(config)
        assert net.config is config

    def test_gradient_flows(self) -> None:
        """Gradients flow through the network during backward pass."""
        net = ValueNetwork(ValueNetworkConfig(hidden_sizes=[32, 16]))
        x = torch.randn(4, 12, requires_grad=True)
        y = net(x)
        loss = y.sum()
        loss.backward()
        assert x.grad is not None
        assert not torch.isnan(x.grad).any()

    def test_unknown_output_activation_raises(self) -> None:
        """Unknown output_activation raises ValueError."""
        with pytest.raises(ValueError, match="Unknown output_activation"):
            ValueNetwork(ValueNetworkConfig(output_activation="tanh"))

    def test_output_large_negative_input(self) -> None:
        """Very negative inputs still produce non-negative outputs (Softplus)."""
        net = ValueNetwork(ValueNetworkConfig(hidden_sizes=[32, 16]))
        x = torch.full((4, 12), -100.0)
        net.eval()
        with torch.no_grad():
            y = net(x)
        assert (y >= 0).all()


# ---------------------------------------------------------------------------
# FeatureNormalizer tests
# ---------------------------------------------------------------------------


class TestFeatureNormalizer:
    """Tests for FeatureNormalizer class."""

    def test_instantiation(self) -> None:
        """FeatureNormalizer instantiates without arguments."""
        norm = FeatureNormalizer()
        assert norm is not None

    def test_encode_shape(self) -> None:
        """encode() returns shape [12]."""
        norm = FeatureNormalizer()
        pk = make_pattern_key()
        feat = norm.encode(pk)
        assert feat.shape == torch.Size([12])

    def test_encode_matches_encode_pattern_key(self) -> None:
        """encode() matches the standalone encode_pattern_key function."""
        norm = FeatureNormalizer()
        for op in sorted(VALID_TOP_OPERATORS):
            pk = make_pattern_key(modal_depth=2, top_operator=op)
            feat_norm = norm.encode(pk)
            feat_fn = encode_pattern_key(pk)
            assert torch.allclose(feat_norm, feat_fn), (
                f"Mismatch for operator {op}"
            )

    def test_to_dict_from_dict_round_trip(self) -> None:
        """to_dict/from_dict restores an equivalent normalizer."""
        norm = FeatureNormalizer()
        d = norm.to_dict()
        norm2 = FeatureNormalizer.from_dict(d)
        # Both should produce the same output
        pk = make_pattern_key(modal_depth=3, temporal_depth=1, imp_count=2, complexity=8, top_operator="Box")
        feat1 = norm.encode(pk)
        feat2 = norm2.encode(pk)
        assert torch.allclose(feat1, feat2)

    def test_to_dict_contains_expected_keys(self) -> None:
        """to_dict contains expected keys."""
        norm = FeatureNormalizer()
        d = norm.to_dict()
        assert "operator_index" in d
        assert "num_features" in d
        assert d["num_features"] == 12

    def test_from_dict_empty_dict(self) -> None:
        """from_dict with empty dict returns a valid normalizer."""
        norm = FeatureNormalizer.from_dict({})
        pk = make_pattern_key()
        feat = norm.encode(pk)
        assert feat.shape == torch.Size([12])

    def test_from_dict_operator_index_mismatch_raises(self) -> None:
        """from_dict raises ValueError if operator index doesn't match."""
        bad_dict = {
            "operator_index": {"WrongOp": 0, "AnotherWrong": 1}
        }
        with pytest.raises(ValueError, match="Operator index mismatch"):
            FeatureNormalizer.from_dict(bad_dict)

    def test_repr_contains_key_info(self) -> None:
        """repr() includes useful information."""
        norm = FeatureNormalizer()
        r = repr(norm)
        assert "FeatureNormalizer" in r
        assert "num_features=12" in r
