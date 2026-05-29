"""Tests for the action space module (bimodal_harness.schema.actions).

Verifies:
- Exact axiom constructor counts (42 axioms, 7 rules, 49 total)
- Index mapping bijectivity (no duplicates, no gaps)
- Frame-class mask counts (Base=44, Dense=46, Discrete=47)
- All axiom names match Lean constructor names in Axioms.lean
- Frame-class mask coverage (layer membership)
- FrameClass enum values
"""

from __future__ import annotations

import pytest

from bimodal_harness.schema.actions import (
    ACTION_TO_INDEX,
    ALL_ACTIONS,
    AXIOM_ACTIONS,
    BASE_MASK,
    DENSE_MASK,
    DISCRETE_MASK,
    FRAME_CLASS_MASKS,
    INDEX_TO_ACTION,
    RULE_ACTIONS,
    FrameClass,
    get_mask_for_frame_class,
)


class TestActionCounts:
    """Test canonical action list sizes."""

    def test_axiom_actions_count(self):
        assert len(AXIOM_ACTIONS) == 42, f"Expected 42 axiom constructors, got {len(AXIOM_ACTIONS)}"

    def test_rule_actions_count(self):
        assert len(RULE_ACTIONS) == 7, f"Expected 7 inference rules, got {len(RULE_ACTIONS)}"

    def test_all_actions_count(self):
        assert len(ALL_ACTIONS) == 49, f"Expected 49 total actions (42+7), got {len(ALL_ACTIONS)}"

    def test_all_actions_is_axioms_plus_rules(self):
        assert ALL_ACTIONS == AXIOM_ACTIONS + RULE_ACTIONS


class TestAxiomLayerCounts:
    """Test that each layer in AXIOM_ACTIONS has the expected size."""

    def test_layer_1_propositional(self):
        layer = ["prop_k", "prop_s", "ex_falso", "peirce"]
        for name in layer:
            assert name in AXIOM_ACTIONS, f"{name!r} missing from AXIOM_ACTIONS"

    def test_layer_2_s5_modal(self):
        layer = ["modal_t", "modal_4", "modal_b", "modal_5_collapse", "modal_k_dist"]
        for name in layer:
            assert name in AXIOM_ACTIONS, f"{name!r} missing from AXIOM_ACTIONS"

    def test_layer_3_bx_temporal_future(self):
        expected = [
            "serial_future",
            "left_mono_until_G",
            "right_mono_until",
            "connect_future",
            "enrichment_until",
            "self_accum_until",
            "absorb_until",
            "linear_until",
            "until_F",
            "temp_linearity",
            "F_until_equiv",
        ]
        for name in expected:
            assert name in AXIOM_ACTIONS, f"{name!r} missing from AXIOM_ACTIONS"

    def test_layer_3_bx_temporal_past(self):
        expected = [
            "serial_past",
            "left_mono_since_H",
            "right_mono_since",
            "connect_past",
            "enrichment_since",
            "self_accum_since",
            "absorb_since",
            "linear_since",
            "since_P",
            "temp_linearity_past",
            "P_since_equiv",
        ]
        for name in expected:
            assert name in AXIOM_ACTIONS, f"{name!r} missing from AXIOM_ACTIONS"

    def test_layer_4_interaction(self):
        assert "modal_future" in AXIOM_ACTIONS

    def test_layer_5_uniformity(self):
        layer = [
            "discrete_symm_fwd",
            "discrete_symm_bwd",
            "discrete_propagate_fwd",
            "discrete_propagate_bwd",
            "discrete_box_necessity",
        ]
        for name in layer:
            assert name in AXIOM_ACTIONS, f"{name!r} missing from AXIOM_ACTIONS"

    def test_layer_6_prior(self):
        assert "prior_UZ" in AXIOM_ACTIONS
        assert "prior_SZ" in AXIOM_ACTIONS

    def test_layer_7_z1(self):
        assert "z1" in AXIOM_ACTIONS

    def test_layer_8_density(self):
        assert "density" in AXIOM_ACTIONS
        assert "dense_indicator" in AXIOM_ACTIONS


class TestRuleNames:
    """Test that rule names match Lean DerivationTree constructor names."""

    def test_rule_names_exact(self):
        expected = [
            "axiom",
            "assumption",
            "modus_ponens",
            "necessitation",
            "temporal_necessitation",
            "temporal_duality",
            "weakening",
        ]
        assert RULE_ACTIONS == expected


class TestIndexMappings:
    """Test that ACTION_TO_INDEX and INDEX_TO_ACTION are bijective."""

    def test_action_to_index_length(self):
        assert len(ACTION_TO_INDEX) == 49

    def test_index_to_action_length(self):
        assert len(INDEX_TO_ACTION) == 49

    def test_no_duplicate_indices(self):
        indices = list(ACTION_TO_INDEX.values())
        assert len(set(indices)) == len(indices), "Duplicate indices detected"

    def test_indices_are_contiguous(self):
        indices = sorted(ACTION_TO_INDEX.values())
        assert indices == list(range(49)), "Indices are not 0..48"

    def test_round_trip_action_to_index_to_action(self):
        for action in ALL_ACTIONS:
            idx = ACTION_TO_INDEX[action]
            assert INDEX_TO_ACTION[idx] == action

    def test_round_trip_index_to_action_to_index(self):
        for idx in range(49):
            action = INDEX_TO_ACTION[idx]
            assert ACTION_TO_INDEX[action] == idx

    def test_axiom_actions_precede_rule_actions(self):
        """Axiom indices 0-41, rule indices 42-48."""
        for i, action in enumerate(AXIOM_ACTIONS):
            assert ACTION_TO_INDEX[action] == i
        for i, action in enumerate(RULE_ACTIONS):
            assert ACTION_TO_INDEX[action] == 42 + i


class TestFrameClassMasks:
    """Test frame-class boolean masks."""

    def test_base_mask_length(self):
        assert len(BASE_MASK) == 49

    def test_dense_mask_length(self):
        assert len(DENSE_MASK) == 49

    def test_discrete_mask_length(self):
        assert len(DISCRETE_MASK) == 49

    def test_base_mask_true_count(self):
        # 37 base axioms + 7 rules = 44
        assert sum(BASE_MASK) == 44, f"Expected 44 True in BASE_MASK, got {sum(BASE_MASK)}"

    def test_dense_mask_true_count(self):
        # 37 base + 2 dense = 39, plus 7 rules = 46
        assert sum(DENSE_MASK) == 46, f"Expected 46 True in DENSE_MASK, got {sum(DENSE_MASK)}"

    def test_discrete_mask_true_count(self):
        # 37 base + 3 discrete = 40, plus 7 rules = 47
        assert sum(DISCRETE_MASK) == 47, (
            f"Expected 47 True in DISCRETE_MASK, got {sum(DISCRETE_MASK)}"
        )

    def test_base_subset_of_dense(self):
        """Every True in BASE_MASK is also True in DENSE_MASK (for base axioms)."""
        for i, (b, d) in enumerate(zip(BASE_MASK, DENSE_MASK, strict=True)):
            action = ALL_ACTIONS[i]
            if b and action not in RULE_ACTIONS:
                assert d, f"Base axiom {action!r} not in DENSE_MASK"

    def test_base_subset_of_discrete(self):
        """Every True in BASE_MASK is also True in DISCRETE_MASK (for base axioms)."""
        for i, (b, disc) in enumerate(zip(BASE_MASK, DISCRETE_MASK, strict=True)):
            action = ALL_ACTIONS[i]
            if b and action not in RULE_ACTIONS:
                assert disc, f"Base axiom {action!r} not in DISCRETE_MASK"

    def test_discrete_only_axioms_not_in_base(self):
        """prior_UZ, prior_SZ, z1 must be False in BASE_MASK and DENSE_MASK."""
        discrete_only = ["prior_UZ", "prior_SZ", "z1"]
        for ax in discrete_only:
            idx = ACTION_TO_INDEX[ax]
            assert not BASE_MASK[idx], f"{ax!r} should NOT be in BASE_MASK"
            assert not DENSE_MASK[idx], f"{ax!r} should NOT be in DENSE_MASK"
            assert DISCRETE_MASK[idx], f"{ax!r} should be in DISCRETE_MASK"

    def test_dense_only_axioms_not_in_base(self):
        """density, dense_indicator must be False in BASE_MASK and DISCRETE_MASK."""
        dense_only = ["density", "dense_indicator"]
        for ax in dense_only:
            idx = ACTION_TO_INDEX[ax]
            assert not BASE_MASK[idx], f"{ax!r} should NOT be in BASE_MASK"
            assert DENSE_MASK[idx], f"{ax!r} should be in DENSE_MASK"
            assert not DISCRETE_MASK[idx], f"{ax!r} should NOT be in DISCRETE_MASK"

    def test_all_rules_true_in_all_masks(self):
        """All 7 rule actions are valid in all frame classes."""
        for action in RULE_ACTIONS:
            idx = ACTION_TO_INDEX[action]
            assert BASE_MASK[idx], f"Rule {action!r} should be True in BASE_MASK"
            assert DENSE_MASK[idx], f"Rule {action!r} should be True in DENSE_MASK"
            assert DISCRETE_MASK[idx], f"Rule {action!r} should be True in DISCRETE_MASK"

    def test_frame_class_masks_dict(self):
        assert FRAME_CLASS_MASKS["Base"] is BASE_MASK
        assert FRAME_CLASS_MASKS["Dense"] is DENSE_MASK
        assert FRAME_CLASS_MASKS["Discrete"] is DISCRETE_MASK


class TestFrameClassEnum:
    """Test FrameClass enum values."""

    def test_frame_class_values(self):
        assert FrameClass.BASE == "Base"
        assert FrameClass.DENSE == "Dense"
        assert FrameClass.DISCRETE == "Discrete"

    def test_get_mask_by_enum(self):
        assert get_mask_for_frame_class(FrameClass.BASE) is BASE_MASK
        assert get_mask_for_frame_class(FrameClass.DENSE) is DENSE_MASK
        assert get_mask_for_frame_class(FrameClass.DISCRETE) is DISCRETE_MASK

    def test_get_mask_by_string(self):
        assert get_mask_for_frame_class("Base") is BASE_MASK
        assert get_mask_for_frame_class("Dense") is DENSE_MASK
        assert get_mask_for_frame_class("Discrete") is DISCRETE_MASK

    def test_get_mask_invalid_raises(self):
        with pytest.raises(KeyError):
            get_mask_for_frame_class("Invalid")
