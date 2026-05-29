"""Unit tests for the policy network and feature encoder."""

from __future__ import annotations

import torch
import pytest

from bimodal_harness.models.policy import (
    PolicyFeatureEncoder,
    PolicyNetwork,
    PolicyNetworkConfig,
    encode_proof_step,
)
from bimodal_harness.schema.records import ProofStepRecord


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_record(
    rule: str = "modus_ponens",
    axiom_name: str | None = None,
    action_index: int = 44,
    frame_class: str = "Base",
    depth: int = 0,
    proof_height: int = 3,
    context: tuple[str, ...] = (),
    subgoals: tuple[dict, ...] = (),
) -> ProofStepRecord:
    goal_json = {"tag": "imp", "left": {"tag": "atom", "name": "p"}, "right": {"tag": "atom", "name": "q"}}
    return ProofStepRecord(
        step_id="test/0",
        theorem_name="test_theorem",
        context=context,
        goal_json=goal_json,
        goal_pretty="p → q",
        rule=rule,
        axiom_name=axiom_name,
        action_index=action_index,
        subgoals=subgoals,
        depth=depth,
        frame_class=frame_class,
        proof_height=proof_height,
    )


# ---------------------------------------------------------------------------
# PolicyNetworkConfig tests
# ---------------------------------------------------------------------------

class TestPolicyNetworkConfig:
    def test_defaults(self):
        cfg = PolicyNetworkConfig()
        assert cfg.input_dim == 25
        assert cfg.num_actions == 49
        assert cfg.hidden_sizes == [1024, 512, 256]
        assert cfg.dropout == 0.1
        assert cfg.label_smoothing == 0.1

    def test_to_dict_from_dict_roundtrip(self):
        cfg = PolicyNetworkConfig(
            input_dim=25,
            num_actions=49,
            hidden_sizes=[512, 256],
            dropout=0.2,
            label_smoothing=0.05,
        )
        restored = PolicyNetworkConfig.from_dict(cfg.to_dict())
        assert restored.input_dim == cfg.input_dim
        assert restored.num_actions == cfg.num_actions
        assert restored.hidden_sizes == cfg.hidden_sizes
        assert restored.dropout == pytest.approx(cfg.dropout)
        assert restored.label_smoothing == pytest.approx(cfg.label_smoothing)


# ---------------------------------------------------------------------------
# encode_proof_step tests
# ---------------------------------------------------------------------------

class TestEncodeProofStep:
    def test_output_shape(self):
        record = _make_record()
        feat = encode_proof_step(record)
        assert feat.shape == (25,)
        assert feat.dtype == torch.float32

    def test_no_context_no_subgoals(self):
        record = _make_record(context=(), subgoals=())
        feat = encode_proof_step(record)
        # has_context flag should be 0
        assert feat[13].item() == pytest.approx(0.0)
        # has_subgoals flag should be 0
        assert feat[22].item() == pytest.approx(0.0)

    def test_with_context(self):
        record = _make_record(context=("p", "q"))
        feat = encode_proof_step(record)
        # has_context flag should be 1
        assert feat[13].item() == pytest.approx(1.0)

    def test_with_subgoals(self):
        subgoal = {"tag": "atom", "name": "p"}
        record = _make_record(subgoals=(subgoal,))
        feat = encode_proof_step(record)
        # has_subgoals flag should be 1
        assert feat[22].item() == pytest.approx(1.0)

    def test_frame_class_onehot_base(self):
        record = _make_record(frame_class="Base")
        feat = encode_proof_step(record)
        assert feat[18].item() == pytest.approx(1.0)  # Base = index 0
        assert feat[19].item() == pytest.approx(0.0)  # Dense = index 1
        assert feat[20].item() == pytest.approx(0.0)  # Discrete = index 2

    def test_frame_class_onehot_dense(self):
        record = _make_record(frame_class="Dense")
        feat = encode_proof_step(record)
        assert feat[18].item() == pytest.approx(0.0)
        assert feat[19].item() == pytest.approx(1.0)
        assert feat[20].item() == pytest.approx(0.0)

    def test_frame_class_onehot_discrete(self):
        record = _make_record(frame_class="Discrete")
        feat = encode_proof_step(record)
        assert feat[18].item() == pytest.approx(0.0)
        assert feat[19].item() == pytest.approx(0.0)
        assert feat[20].item() == pytest.approx(1.0)

    def test_depth_features_log1p(self):
        import math
        record = _make_record(depth=2, proof_height=5)
        feat = encode_proof_step(record)
        assert feat[16].item() == pytest.approx(math.log1p(2), abs=1e-5)
        assert feat[17].item() == pytest.approx(math.log1p(5), abs=1e-5)

    def test_all_finite(self):
        record = _make_record()
        feat = encode_proof_step(record)
        assert torch.all(torch.isfinite(feat))


# ---------------------------------------------------------------------------
# PolicyFeatureEncoder tests
# ---------------------------------------------------------------------------

class TestPolicyFeatureEncoder:
    def test_encode_shape(self):
        enc = PolicyFeatureEncoder()
        record = _make_record()
        feat = enc.encode(record)
        assert feat.shape == (25,)

    def test_to_dict_from_dict_roundtrip(self):
        enc = PolicyFeatureEncoder()
        restored = PolicyFeatureEncoder.from_dict(enc.to_dict())
        assert restored._frame_classes == enc._frame_classes

    def test_num_features(self):
        enc = PolicyFeatureEncoder()
        d = enc.to_dict()
        assert d["num_features"] == 25


# ---------------------------------------------------------------------------
# PolicyNetwork tests
# ---------------------------------------------------------------------------

class TestPolicyNetwork:
    def test_forward_shape_batch(self):
        cfg = PolicyNetworkConfig()
        net = PolicyNetwork(cfg)
        x = torch.randn(32, 25)
        logits = net(x)
        assert logits.shape == (32, 49)

    def test_forward_single(self):
        net = PolicyNetwork()
        x = torch.randn(1, 25)
        logits = net(x)
        assert logits.shape == (1, 49)

    def test_param_count_approx(self):
        net = PolicyNetwork()
        # Default [1024, 512, 256]: 25*1024+1024 + 1024*512+512 + 512*256+256 + 256*49+49
        # = 26600 + 524800 + 131328 + 12593 = ~695K
        # Should be roughly 699K (within 10% is sufficient)
        assert 500_000 < net.param_count < 900_000

    def test_default_config(self):
        net = PolicyNetwork()
        assert net.config.input_dim == 25
        assert net.config.num_actions == 49

    def test_apply_frame_class_mask_batch(self):
        from bimodal_harness.schema.actions import FRAME_CLASS_MASKS
        net = PolicyNetwork()
        logits = torch.zeros(4, 49)
        mask_list = FRAME_CLASS_MASKS["Base"]
        mask = torch.tensor(mask_list, dtype=torch.bool).unsqueeze(0).expand(4, -1)
        masked = net.apply_frame_class_mask(logits, mask)
        # Invalid actions in Base mask should be -inf
        for i, valid in enumerate(mask_list):
            if not valid:
                assert torch.all(masked[:, i] == float("-inf")), f"Action {i} should be -inf"
            else:
                assert torch.all(masked[:, i] == 0.0), f"Action {i} should be 0.0"

    def test_apply_frame_class_mask_1d(self):
        from bimodal_harness.schema.actions import FRAME_CLASS_MASKS
        net = PolicyNetwork()
        logits = torch.zeros(49)
        mask_list = FRAME_CLASS_MASKS["Discrete"]
        mask = torch.tensor(mask_list, dtype=torch.bool)
        masked = net.apply_frame_class_mask(logits, mask)
        for i, valid in enumerate(mask_list):
            if not valid:
                assert masked[i].item() == float("-inf")
            else:
                assert masked[i].item() == pytest.approx(0.0)

    def test_no_grad_inference(self):
        net = PolicyNetwork()
        net.eval()
        x = torch.randn(8, 25)
        with torch.no_grad():
            logits = net(x)
        assert logits.shape == (8, 49)
        assert torch.all(torch.isfinite(logits))
