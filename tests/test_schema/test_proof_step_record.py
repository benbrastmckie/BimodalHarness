"""Tests for ProofStepRecord and step_to_action_index.

Verifies:
- step_to_action_index returns correct indices for all 42 axiom names
- step_to_action_index returns correct indices for all 7 rule names
- step_to_action_index raises ValueError/KeyError for invalid inputs
- ProofStepRecord can be instantiated with valid data
- ProofStepRecord.to_dict() / from_dict() round-trip preserves all fields
- ProofStepRecord.__post_init__ validates field ranges
"""

from __future__ import annotations

import pytest

from bimodal_harness.schema.actions import (
    ACTION_TO_INDEX,
    ALL_ACTIONS,
    AXIOM_ACTIONS,
    RULE_ACTIONS,
    step_to_action_index,
)
from bimodal_harness.schema.records import ProofStepRecord


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FORMULA_BOT: dict = {"tag": "bot"}
FORMULA_ATOM_P: dict = {"tag": "atom", "name": "p"}
FORMULA_IMP: dict = {"tag": "imp", "left": FORMULA_ATOM_P, "right": FORMULA_BOT}


def make_proof_step_record(**kwargs) -> ProofStepRecord:
    """Create a ProofStepRecord with sensible defaults, overriding with kwargs."""
    defaults: dict = {
        "step_id": "test_theorem/0",
        "theorem_name": "test_theorem",
        "context": (),
        "goal_json": FORMULA_BOT,
        "goal_pretty": "⊥",
        "rule": "axiom",
        "axiom_name": "ex_falso",
        "action_index": ACTION_TO_INDEX["ex_falso"],
        "subgoals": (),
        "depth": 0,
        "frame_class": "Base",
        "proof_height": 0,
    }
    defaults.update(kwargs)
    return ProofStepRecord(**defaults)


# ---------------------------------------------------------------------------
# Tests for step_to_action_index
# ---------------------------------------------------------------------------


class TestStepToActionIndexAxioms:
    """Test that step_to_action_index maps every axiom name to the correct index."""

    def test_axiom_prop_k_returns_0(self):
        """prop_k is the first axiom at index 0."""
        assert step_to_action_index("axiom", "prop_k") == 0

    def test_axiom_ex_falso(self):
        assert step_to_action_index("axiom", "ex_falso") == ACTION_TO_INDEX["ex_falso"]

    def test_all_42_axioms(self):
        """Every axiom in AXIOM_ACTIONS should map to its expected index."""
        for name in AXIOM_ACTIONS:
            expected = ACTION_TO_INDEX[name]
            result = step_to_action_index("axiom", name)
            assert result == expected, (
                f"step_to_action_index('axiom', {name!r}) = {result}, expected {expected}"
            )

    def test_axiom_indices_range_0_to_41(self):
        """All axiom indices must be in 0-41."""
        for name in AXIOM_ACTIONS:
            idx = step_to_action_index("axiom", name)
            assert 0 <= idx <= 41, (
                f"Axiom {name!r} has index {idx}, expected in [0, 41]"
            )

    def test_layer_8_density_axioms(self):
        """density and dense_indicator are the last two axioms (40, 41)."""
        assert step_to_action_index("axiom", "density") == 40
        assert step_to_action_index("axiom", "dense_indicator") == 41


class TestStepToActionIndexRules:
    """Test that step_to_action_index maps every rule name to the correct index."""

    def test_rule_axiom_wrapper_returns_rule_index(self):
        """rule='axiom' with axiom_name=None should raise ValueError."""
        # "axiom" rule itself is at index 42, but can only be looked up
        # when paired with a valid axiom_name (which dispatches to the axiom space).
        # Calling with axiom_name=None should raise.
        with pytest.raises(ValueError, match="axiom_name must not be None"):
            step_to_action_index("axiom", None)

    def test_modus_ponens_returns_44(self):
        """modus_ponens is the third rule at index 44."""
        assert step_to_action_index("modus_ponens", None) == 44

    def test_assumption_returns_43(self):
        assert step_to_action_index("assumption", None) == 43

    def test_all_7_rules_except_axiom(self):
        """Every rule in RULE_ACTIONS except 'axiom' should map to its expected index."""
        for name in RULE_ACTIONS:
            if name == "axiom":
                continue  # "axiom" rule requires an axiom_name
            expected = ACTION_TO_INDEX[name]
            result = step_to_action_index(name, None)
            assert result == expected, (
                f"step_to_action_index({name!r}, None) = {result}, expected {expected}"
            )

    def test_rule_indices_range_42_to_48(self):
        """All rule indices (except 'axiom' wrapper) must be in 42-48."""
        for name in RULE_ACTIONS:
            if name == "axiom":
                continue
            idx = step_to_action_index(name, None)
            assert 42 <= idx <= 48, (
                f"Rule {name!r} has index {idx}, expected in [42, 48]"
            )

    def test_weakening_returns_48(self):
        """weakening is the last rule at index 48."""
        assert step_to_action_index("weakening", None) == 48

    def test_necessitation(self):
        assert step_to_action_index("necessitation", None) == ACTION_TO_INDEX["necessitation"]

    def test_temporal_necessitation(self):
        assert step_to_action_index("temporal_necessitation", None) == ACTION_TO_INDEX["temporal_necessitation"]

    def test_temporal_duality(self):
        assert step_to_action_index("temporal_duality", None) == ACTION_TO_INDEX["temporal_duality"]


class TestStepToActionIndexErrors:
    """Test error handling in step_to_action_index."""

    def test_rule_axiom_with_none_raises_value_error(self):
        with pytest.raises(ValueError, match="axiom_name must not be None"):
            step_to_action_index("axiom", None)

    def test_non_axiom_rule_with_axiom_name_raises_value_error(self):
        with pytest.raises(ValueError, match="axiom_name must be None"):
            step_to_action_index("modus_ponens", "prop_k")

    def test_unknown_axiom_name_raises_key_error(self):
        with pytest.raises(KeyError):
            step_to_action_index("axiom", "nonexistent_axiom")

    def test_unknown_rule_raises_key_error(self):
        with pytest.raises(KeyError):
            step_to_action_index("unknown_rule", None)

    def test_empty_rule_raises_key_error(self):
        with pytest.raises(KeyError):
            step_to_action_index("", None)


# ---------------------------------------------------------------------------
# Tests for ProofStepRecord construction
# ---------------------------------------------------------------------------


class TestProofStepRecordConstruction:
    """Test ProofStepRecord instantiation and basic field access."""

    def test_basic_axiom_step(self):
        """Minimal axiom leaf node."""
        record = make_proof_step_record()
        assert record.step_id == "test_theorem/0"
        assert record.theorem_name == "test_theorem"
        assert record.context == ()
        assert record.rule == "axiom"
        assert record.axiom_name == "ex_falso"
        assert record.action_index == ACTION_TO_INDEX["ex_falso"]
        assert record.subgoals == ()
        assert record.depth == 0
        assert record.frame_class == "Base"
        assert record.proof_height == 0

    def test_modus_ponens_step(self):
        """Modus ponens step with two subgoals."""
        subgoal_a = {"tag": "imp", "left": FORMULA_ATOM_P, "right": FORMULA_BOT}
        subgoal_b = FORMULA_ATOM_P
        record = make_proof_step_record(
            rule="modus_ponens",
            axiom_name=None,
            action_index=ACTION_TO_INDEX["modus_ponens"],
            subgoals=(subgoal_a, subgoal_b),
            depth=1,
            proof_height=2,
        )
        assert record.rule == "modus_ponens"
        assert record.axiom_name is None
        assert len(record.subgoals) == 2
        assert record.depth == 1
        assert record.proof_height == 2

    def test_context_as_tuple(self):
        """Context must be stored as a tuple, not a list."""
        record = make_proof_step_record(context=("φ", "ψ"))
        assert isinstance(record.context, tuple)
        assert record.context == ("φ", "ψ")

    def test_subgoals_as_tuple(self):
        """Subgoals must be stored as a tuple."""
        sg = {"tag": "bot"}
        record = make_proof_step_record(
            rule="necessitation",
            axiom_name=None,
            action_index=ACTION_TO_INDEX["necessitation"],
            subgoals=(sg,),
        )
        assert isinstance(record.subgoals, tuple)
        assert len(record.subgoals) == 1

    def test_frozen_immutable(self):
        """ProofStepRecord is frozen; attribute assignment must raise."""
        record = make_proof_step_record()
        with pytest.raises((AttributeError, TypeError)):
            record.step_id = "other"  # type: ignore[misc]

    def test_frame_class_dense(self):
        record = make_proof_step_record(
            frame_class="Dense",
            action_index=ACTION_TO_INDEX["ex_falso"],
        )
        assert record.frame_class == "Dense"

    def test_frame_class_discrete(self):
        record = make_proof_step_record(
            frame_class="Discrete",
            axiom_name="prior_UZ",
            action_index=ACTION_TO_INDEX["prior_UZ"],
        )
        assert record.frame_class == "Discrete"


class TestProofStepRecordValidation:
    """Test __post_init__ validation in ProofStepRecord."""

    def test_invalid_action_index_negative_raises(self):
        with pytest.raises(ValueError, match="action_index must be in"):
            make_proof_step_record(action_index=-1)

    def test_invalid_action_index_too_large_raises(self):
        with pytest.raises(ValueError, match="action_index must be in"):
            make_proof_step_record(action_index=49)

    def test_invalid_frame_class_raises(self):
        with pytest.raises(ValueError, match="frame_class must be one of"):
            make_proof_step_record(frame_class="NonExistent")

    def test_negative_depth_raises(self):
        with pytest.raises(ValueError, match="depth must be >= 0"):
            make_proof_step_record(depth=-1)

    def test_negative_proof_height_raises(self):
        with pytest.raises(ValueError, match="proof_height must be >= 0"):
            make_proof_step_record(proof_height=-1)


# ---------------------------------------------------------------------------
# Tests for ProofStepRecord serialization (to_dict / from_dict)
# ---------------------------------------------------------------------------


class TestProofStepRecordSerialization:
    """Test to_dict and from_dict for round-trip fidelity."""

    def test_to_dict_returns_dict(self):
        record = make_proof_step_record()
        d = record.to_dict()
        assert isinstance(d, dict)

    def test_to_dict_has_all_keys(self):
        record = make_proof_step_record()
        d = record.to_dict()
        expected_keys = {
            "step_id", "theorem_name", "context", "goal_json", "goal_pretty",
            "rule", "axiom_name", "action_index", "subgoals", "depth",
            "frame_class", "proof_height",
        }
        assert set(d.keys()) == expected_keys

    def test_to_dict_context_is_list(self):
        """to_dict converts tuple[str, ...] context to list for JSON compat."""
        record = make_proof_step_record(context=("φ", "ψ"))
        d = record.to_dict()
        assert isinstance(d["context"], list)
        assert d["context"] == ["φ", "ψ"]

    def test_to_dict_subgoals_is_list(self):
        sg = {"tag": "bot"}
        record = make_proof_step_record(
            rule="necessitation",
            axiom_name=None,
            action_index=ACTION_TO_INDEX["necessitation"],
            subgoals=(sg,),
        )
        d = record.to_dict()
        assert isinstance(d["subgoals"], list)
        assert d["subgoals"] == [{"tag": "bot"}]

    def test_round_trip_axiom_leaf(self):
        """Axiom leaf: to_dict -> from_dict preserves all fields."""
        original = make_proof_step_record()
        reconstructed = ProofStepRecord.from_dict(original.to_dict())
        assert reconstructed == original

    def test_round_trip_modus_ponens(self):
        """Modus ponens step: round-trip."""
        subgoal_a = {"tag": "imp", "left": FORMULA_ATOM_P, "right": FORMULA_BOT}
        subgoal_b = FORMULA_ATOM_P
        original = make_proof_step_record(
            step_id="mp_theorem/1",
            theorem_name="mp_theorem",
            context=("p → q", "p"),
            goal_json=FORMULA_BOT,
            goal_pretty="q",
            rule="modus_ponens",
            axiom_name=None,
            action_index=ACTION_TO_INDEX["modus_ponens"],
            subgoals=(subgoal_a, subgoal_b),
            depth=2,
            frame_class="Base",
            proof_height=3,
        )
        reconstructed = ProofStepRecord.from_dict(original.to_dict())
        assert reconstructed == original

    def test_round_trip_with_all_frame_classes(self):
        """Round-trip round for each valid frame class."""
        for fc in ("Base", "Dense", "Discrete"):
            # Use discrete axioms only for Discrete frame class
            if fc == "Discrete":
                axiom = "prior_UZ"
            else:
                axiom = "prop_k"
            original = make_proof_step_record(
                frame_class=fc,
                axiom_name=axiom,
                action_index=ACTION_TO_INDEX[axiom],
            )
            reconstructed = ProofStepRecord.from_dict(original.to_dict())
            assert reconstructed == original

    def test_from_dict_coerces_context_list_to_tuple(self):
        """from_dict accepts a list for 'context' and converts it to a tuple."""
        d = make_proof_step_record(context=("φ",)).to_dict()
        assert isinstance(d["context"], list)  # to_dict gives list
        record = ProofStepRecord.from_dict(d)
        assert isinstance(record.context, tuple)
        assert record.context == ("φ",)

    def test_from_dict_coerces_subgoals_list_to_tuple(self):
        """from_dict accepts a list for 'subgoals' and converts it to a tuple."""
        sg = {"tag": "atom", "name": "q"}
        original = make_proof_step_record(
            rule="weakening",
            axiom_name=None,
            action_index=ACTION_TO_INDEX["weakening"],
            subgoals=(sg,),
        )
        d = original.to_dict()
        assert isinstance(d["subgoals"], list)
        record = ProofStepRecord.from_dict(d)
        assert isinstance(record.subgoals, tuple)
        assert record.subgoals == (sg,)

    def test_from_dict_axiom_name_none(self):
        """Axiom name of None is preserved through round-trip."""
        original = make_proof_step_record(
            rule="necessitation",
            axiom_name=None,
            action_index=ACTION_TO_INDEX["necessitation"],
        )
        reconstructed = ProofStepRecord.from_dict(original.to_dict())
        assert reconstructed.axiom_name is None

    def test_from_dict_missing_optional_fields_use_defaults(self):
        """from_dict with missing 'context' and 'subgoals' falls back to empty tuples."""
        d = {
            "step_id": "t/0",
            "theorem_name": "t",
            "goal_json": FORMULA_BOT,
            "goal_pretty": "⊥",
            "rule": "axiom",
            "axiom_name": "prop_k",
            "action_index": 0,
            "depth": 0,
            "proof_height": 0,
        }
        record = ProofStepRecord.from_dict(d)
        assert record.context == ()
        assert record.subgoals == ()
        assert record.frame_class == "Base"


# ---------------------------------------------------------------------------
# Tests verifying action_index consistency with step_to_action_index
# ---------------------------------------------------------------------------


class TestActionIndexConsistency:
    """Test that action_index field is consistent with step_to_action_index."""

    def test_axiom_action_index_matches(self):
        for axiom_name in AXIOM_ACTIONS:
            expected_idx = step_to_action_index("axiom", axiom_name)
            record = make_proof_step_record(
                axiom_name=axiom_name,
                action_index=expected_idx,
            )
            assert record.action_index == expected_idx

    def test_rule_action_indices_match(self):
        for rule in RULE_ACTIONS:
            if rule == "axiom":
                continue
            expected_idx = step_to_action_index(rule, None)
            record = make_proof_step_record(
                rule=rule,
                axiom_name=None,
                action_index=expected_idx,
            )
            assert record.action_index == expected_idx
