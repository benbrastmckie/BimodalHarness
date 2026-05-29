"""Unit tests for FormulaTokenizer, FormulaTransformerEncoder, and PolicyNetworkV2."""

from __future__ import annotations

import torch
import pytest

from bimodal_harness.models.formula_encoder import (
    FormulaTokenizer,
    FormulaTransformerEncoder,
    PolicyNetworkV2,
    _PAD_ID,
    _BOS_ID,
    _EOS_ID,
    _TOKEN_TO_ID,
)
from bimodal_harness.schema.records import ProofStepRecord


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _atom(name: str) -> dict:
    return {"tag": "atom", "name": name}


def _imp(left: dict, right: dict) -> dict:
    return {"tag": "imp", "left": left, "right": right}


def _box(child: dict) -> dict:
    return {"tag": "box", "child": child}


def _untl(event: dict, guard: dict) -> dict:
    return {"tag": "untl", "event": event, "guard": guard}


def _snce(event: dict, guard: dict) -> dict:
    return {"tag": "snce", "event": event, "guard": guard}


SAMPLE_FORMULA = _imp(_atom("p"), _atom("q"))


def _make_record(goal_json: dict | None = None, frame_class: str = "Base") -> ProofStepRecord:
    goal = goal_json if goal_json is not None else SAMPLE_FORMULA
    return ProofStepRecord(
        step_id="test/0",
        theorem_name="test_thm",
        context=(),
        goal_json=goal,
        goal_pretty="p → q",
        rule="modus_ponens",
        axiom_name=None,
        action_index=44,
        subgoals=(),
        depth=1,
        frame_class=frame_class,
        proof_height=3,
    )


# ---------------------------------------------------------------------------
# FormulaTokenizer tests
# ---------------------------------------------------------------------------

class TestFormulaTokenizer:
    def test_vocab_size(self):
        tok = FormulaTokenizer()
        assert tok.vocab_size == 18  # 4 special + 6 tags + 8 buckets

    def test_starts_with_bos(self):
        tok = FormulaTokenizer()
        ids = tok.tokenize({"tag": "bot"})
        assert ids[0] == _BOS_ID

    def test_ends_with_eos(self):
        tok = FormulaTokenizer()
        ids = tok.tokenize({"tag": "bot"})
        assert ids[-1] == _EOS_ID

    def test_bot_formula(self):
        tok = FormulaTokenizer()
        ids = tok.tokenize({"tag": "bot"})
        # BOS, bot_id, EOS
        bot_id = _TOKEN_TO_ID["bot"]
        assert ids == [_BOS_ID, bot_id, _EOS_ID]

    def test_atom_formula_has_bucket(self):
        tok = FormulaTokenizer()
        ids = tok.tokenize({"tag": "atom", "name": "p"})
        # BOS, atom_id, bucket_id, EOS
        assert len(ids) == 4
        assert ids[0] == _BOS_ID
        assert ids[1] == _TOKEN_TO_ID["atom"]
        # Bucket id should be in the atom bucket range (10-17)
        assert 10 <= ids[2] <= 17
        assert ids[3] == _EOS_ID

    def test_imp_formula_structure(self):
        tok = FormulaTokenizer()
        formula = _imp(_atom("p"), _atom("q"))
        ids = tok.tokenize(formula)
        # BOS, imp_id, atom_id, bucket, atom_id, bucket, EOS
        assert len(ids) == 7
        assert ids[0] == _BOS_ID
        assert ids[1] == _TOKEN_TO_ID["imp"]
        assert ids[-1] == _EOS_ID

    def test_all_6_ast_tags_covered(self):
        tok = FormulaTokenizer()
        # Ordered pairs of (formula, expected_top_tag)
        test_cases = [
            ({"tag": "atom", "name": "p"}, "atom"),
            ({"tag": "bot"}, "bot"),
            (_imp(_atom("p"), _atom("q")), "imp"),
            (_box(_atom("p")), "box"),
            (_untl(_atom("p"), _atom("q")), "untl"),
            (_snce(_atom("p"), _atom("q")), "snce"),
        ]
        for formula, expected_tag in test_cases:
            ids = tok.tokenize(formula)
            # Tag token is at position 1 (after BOS)
            tag_id = ids[1]
            assert tag_id == _TOKEN_TO_ID[expected_tag], (
                f"Expected {expected_tag} (id={_TOKEN_TO_ID[expected_tag]}), got id={tag_id}"
            )

    def test_truncation_at_max_length(self):
        tok = FormulaTokenizer(max_length=10)
        # Create a deeply nested formula that would exceed max_length
        formula = _atom("p")
        for _ in range(20):
            formula = _imp(formula, _atom("q"))
        ids = tok.tokenize(formula)
        assert len(ids) <= 10
        assert ids[-1] == _EOS_ID

    def test_pad_to_max_length(self):
        tok = FormulaTokenizer(max_length=20)
        ids = tok.tokenize({"tag": "bot"})  # [BOS, bot, EOS] = 3 tokens
        padded = tok.pad(ids)
        assert len(padded) == 20
        assert padded[3:] == [_PAD_ID] * 17

    def test_to_dict_from_dict_roundtrip(self):
        tok = FormulaTokenizer(max_length=64)
        restored = FormulaTokenizer.from_dict(tok.to_dict())
        assert restored.max_length == 64
        assert restored.vocab_size == tok.vocab_size

    def test_different_atom_names_may_hash_differently(self):
        tok = FormulaTokenizer()
        # Different atom names can produce different bucket tokens
        # (not guaranteed, but p and q likely differ)
        ids_p = tok.tokenize({"tag": "atom", "name": "p"})
        ids_xyz = tok.tokenize({"tag": "atom", "name": "xyz_very_long_name"})
        # Both should be valid token IDs in atom bucket range
        assert 10 <= ids_p[2] <= 17
        assert 10 <= ids_xyz[2] <= 17


# ---------------------------------------------------------------------------
# FormulaTransformerEncoder tests
# ---------------------------------------------------------------------------

class TestFormulaTransformerEncoder:
    def test_forward_shape(self):
        enc = FormulaTransformerEncoder()
        token_ids = torch.randint(0, 18, (4, 32))
        out = enc(token_ids)
        assert out.shape == (4, 128)

    def test_forward_shape_with_mask(self):
        enc = FormulaTransformerEncoder()
        token_ids = torch.randint(0, 18, (4, 32))
        padding_mask = torch.zeros(4, 32, dtype=torch.bool)
        padding_mask[:, 20:] = True  # mask last 12 positions
        out = enc(token_ids, padding_mask)
        assert out.shape == (4, 128)

    def test_output_is_finite(self):
        enc = FormulaTransformerEncoder()
        token_ids = torch.randint(0, 18, (2, 16))
        out = enc(token_ids)
        assert torch.all(torch.isfinite(out))

    def test_param_count_approx(self):
        enc = FormulaTransformerEncoder()
        # Should be around 200K-500K params
        assert 50_000 < enc.param_count < 1_000_000

    def test_d_model_attribute(self):
        enc = FormulaTransformerEncoder(d_model=64)
        assert enc.d_model == 64
        token_ids = torch.randint(0, 18, (2, 16))
        out = enc(token_ids)
        assert out.shape == (2, 64)


# ---------------------------------------------------------------------------
# PolicyNetworkV2 tests
# ---------------------------------------------------------------------------

class TestPolicyNetworkV2:
    def test_forward_with_feature_tensor(self):
        net = PolicyNetworkV2()
        # 128 (transformer) + 9 (context/depth/frame) = 137-dim input
        x = torch.randn(8, 137)
        logits = net(x)
        assert logits.shape == (8, 49)

    def test_forward_records_shape(self):
        net = PolicyNetworkV2()
        records = [_make_record() for _ in range(4)]
        logits = net.forward_records(records)
        assert logits.shape == (4, 49)

    def test_forward_records_output_finite(self):
        net = PolicyNetworkV2()
        records = [_make_record(goal_json=_imp(_atom("p"), _atom("q"))) for _ in range(2)]
        logits = net.forward_records(records)
        assert torch.all(torch.isfinite(logits))

    def test_param_count_approx(self):
        net = PolicyNetworkV2()
        # Should be around 700K-2M params
        assert 300_000 < net.param_count < 3_000_000

    def test_apply_frame_class_mask(self):
        from bimodal_harness.schema.actions import FRAME_CLASS_MASKS
        net = PolicyNetworkV2()
        logits = torch.zeros(2, 49)
        mask_list = FRAME_CLASS_MASKS["Base"]
        mask = torch.tensor(mask_list, dtype=torch.bool).unsqueeze(0).expand(2, -1)
        masked = net.apply_frame_class_mask(logits, mask)
        for i, valid in enumerate(mask_list):
            if not valid:
                assert torch.all(masked[:, i] == float("-inf"))
            else:
                assert torch.all(masked[:, i] == 0.0)

    def test_different_formulas_different_embeddings(self):
        net = PolicyNetworkV2()
        net.eval()
        r1 = _make_record(goal_json=_atom("p"))
        r2 = _make_record(goal_json=_box(_atom("q")))
        with torch.no_grad():
            l1 = net.forward_records([r1])
            l2 = net.forward_records([r2])
        # Different formulas should produce different logits
        assert not torch.allclose(l1, l2)

    def test_forward_records_batch_vs_single(self):
        net = PolicyNetworkV2()
        net.eval()
        records = [_make_record(goal_json=_atom("p")), _make_record(goal_json=_atom("q"))]
        with torch.no_grad():
            batch_out = net.forward_records(records)
            single_out_0 = net.forward_records([records[0]])
            single_out_1 = net.forward_records([records[1]])
        # Batch and single results should match
        assert torch.allclose(batch_out[0:1], single_out_0, atol=1e-5)
        assert torch.allclose(batch_out[1:2], single_out_1, atol=1e-5)

    def test_various_formula_types(self):
        net = PolicyNetworkV2()
        net.eval()
        formulas = [
            {"tag": "bot"},
            _atom("p"),
            _imp(_atom("p"), _atom("q")),
            _box(_atom("p")),
            _untl(_atom("p"), _atom("q")),
            _snce(_atom("p"), _atom("q")),
        ]
        records = [_make_record(goal_json=f) for f in formulas]
        with torch.no_grad():
            logits = net.forward_records(records)
        assert logits.shape == (6, 49)
        assert torch.all(torch.isfinite(logits))
