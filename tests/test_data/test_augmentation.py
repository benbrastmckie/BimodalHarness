"""Tests for data augmentation strategies in bimodal_harness.data.augmentation.

Tests temporal dual augmentation, context variation augmentation,
combined augmentation, dataset statistics, and dataset splitting.
"""

from __future__ import annotations

import pytest

from bimodal_harness.data.augmentation import (
    _CONTEXT_STRINGS,
    _TEMPORAL_AXIOM_DUALS,
    _dual_axiom_name,
    _formula_has_temporal,
    _swap_temporal,
    augment_all,
    augmented_statistics,
    context_variation_augmentation,
    split_dataset,
    temporal_dual_augmentation,
)
from bimodal_harness.schema.actions import ACTION_TO_INDEX, AXIOM_ACTIONS
from bimodal_harness.schema.records import ProofStepRecord

# ---------------------------------------------------------------------------
# Formula fixtures
# ---------------------------------------------------------------------------

# Simple propositional formula (no temporal operators).
FORMULA_ATOM_P: dict = {"tag": "atom", "name": "p"}
FORMULA_BOT: dict = {"tag": "bot"}
FORMULA_IMP: dict = {"tag": "imp", "left": FORMULA_ATOM_P, "right": FORMULA_BOT}

# Formula with untl (Until) at top level: U(p, q)
FORMULA_UNTIL: dict = {
    "tag": "untl",
    "event": {"tag": "atom", "name": "p"},
    "guard": {"tag": "atom", "name": "q"},
}

# Formula with snce (Since) at top level: S(p, q)
FORMULA_SINCE: dict = {
    "tag": "snce",
    "event": {"tag": "atom", "name": "p"},
    "guard": {"tag": "atom", "name": "q"},
}

# Nested formula: box(untl(p, q)) = □U(p, q)
FORMULA_BOX_UNTIL: dict = {
    "tag": "box",
    "child": FORMULA_UNTIL,
}

# Imp with snce on right: p → S(q, r)
FORMULA_IMP_WITH_SINCE: dict = {
    "tag": "imp",
    "left": FORMULA_ATOM_P,
    "right": {
        "tag": "snce",
        "event": {"tag": "atom", "name": "q"},
        "guard": {"tag": "atom", "name": "r"},
    },
}


# ---------------------------------------------------------------------------
# ProofStepRecord factories
# ---------------------------------------------------------------------------


def make_record(
    step_id: str = "t/0",
    theorem_name: str = "t",
    context: tuple[str, ...] = (),
    goal_json: dict | None = None,
    goal_pretty: str = "⊥",
    rule: str = "axiom",
    axiom_name: str | None = "ex_falso",
    action_index: int | None = None,
    subgoals: tuple[dict, ...] = (),
    depth: int = 0,
    frame_class: str = "Base",
    proof_height: int = 0,
) -> ProofStepRecord:
    """Create a ProofStepRecord with sensible defaults."""
    if goal_json is None:
        goal_json = FORMULA_BOT
    if action_index is None:
        # Compute from rule/axiom_name.
        if rule == "axiom" and axiom_name is not None:
            action_index = ACTION_TO_INDEX[axiom_name]
        else:
            action_index = ACTION_TO_INDEX.get(rule, 43)
    return ProofStepRecord(
        step_id=step_id,
        theorem_name=theorem_name,
        context=context,
        goal_json=goal_json,
        goal_pretty=goal_pretty,
        rule=rule,
        axiom_name=axiom_name,
        action_index=action_index,
        subgoals=subgoals,
        depth=depth,
        frame_class=frame_class,
        proof_height=proof_height,
    )


def make_temporal_record(
    step_id: str = "t/0",
    goal_json: dict | None = None,
    axiom_name: str = "serial_future",
    **kwargs,
) -> ProofStepRecord:
    """Create a ProofStepRecord with a temporal goal formula."""
    if goal_json is None:
        goal_json = FORMULA_UNTIL
    return make_record(
        step_id=step_id,
        goal_json=goal_json,
        rule="axiom",
        axiom_name=axiom_name,
        action_index=ACTION_TO_INDEX[axiom_name],
        **kwargs,
    )


def make_rule_record(
    step_id: str = "t/0",
    rule: str = "modus_ponens",
    goal_json: dict | None = None,
    **kwargs,
) -> ProofStepRecord:
    """Create a ProofStepRecord with a non-axiom rule."""
    if goal_json is None:
        goal_json = FORMULA_UNTIL
    return make_record(
        step_id=step_id,
        goal_json=goal_json,
        rule=rule,
        axiom_name=None,
        action_index=ACTION_TO_INDEX[rule],
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Tests for _formula_has_temporal
# ---------------------------------------------------------------------------


class TestFormulaHasTemporal:
    """Tests for the _formula_has_temporal helper."""

    def test_atom_has_no_temporal(self):
        assert _formula_has_temporal(FORMULA_ATOM_P) is False

    def test_bot_has_no_temporal(self):
        assert _formula_has_temporal(FORMULA_BOT) is False

    def test_imp_has_no_temporal(self):
        assert _formula_has_temporal(FORMULA_IMP) is False

    def test_untl_has_temporal(self):
        assert _formula_has_temporal(FORMULA_UNTIL) is True

    def test_snce_has_temporal(self):
        assert _formula_has_temporal(FORMULA_SINCE) is True

    def test_box_with_untl_has_temporal(self):
        assert _formula_has_temporal(FORMULA_BOX_UNTIL) is True

    def test_imp_with_since_has_temporal(self):
        assert _formula_has_temporal(FORMULA_IMP_WITH_SINCE) is True

    def test_nested_no_temporal(self):
        nested = {"tag": "box", "child": {"tag": "imp", "left": FORMULA_ATOM_P, "right": FORMULA_BOT}}
        assert _formula_has_temporal(nested) is False


# ---------------------------------------------------------------------------
# Tests for _swap_temporal
# ---------------------------------------------------------------------------


class TestSwapTemporal:
    """Tests for the _swap_temporal formula transformation."""

    def test_atom_unchanged(self):
        result = _swap_temporal(FORMULA_ATOM_P)
        assert result == FORMULA_ATOM_P

    def test_bot_unchanged(self):
        result = _swap_temporal(FORMULA_BOT)
        assert result == FORMULA_BOT

    def test_imp_structure_preserved(self):
        result = _swap_temporal(FORMULA_IMP)
        assert result["tag"] == "imp"
        assert result["left"] == FORMULA_ATOM_P
        assert result["right"] == FORMULA_BOT

    def test_untl_becomes_snce(self):
        result = _swap_temporal(FORMULA_UNTIL)
        assert result["tag"] == "snce"
        assert result["event"] == FORMULA_UNTIL["event"]
        assert result["guard"] == FORMULA_UNTIL["guard"]

    def test_snce_becomes_untl(self):
        result = _swap_temporal(FORMULA_SINCE)
        assert result["tag"] == "untl"
        assert result["event"] == FORMULA_SINCE["event"]
        assert result["guard"] == FORMULA_SINCE["guard"]

    def test_box_child_transformed(self):
        result = _swap_temporal(FORMULA_BOX_UNTIL)
        assert result["tag"] == "box"
        assert result["child"]["tag"] == "snce"

    def test_double_swap_is_identity(self):
        """Applying _swap_temporal twice should recover the original."""
        for formula in [FORMULA_UNTIL, FORMULA_SINCE, FORMULA_BOX_UNTIL, FORMULA_IMP_WITH_SINCE]:
            assert _swap_temporal(_swap_temporal(formula)) == formula

    def test_original_not_mutated(self):
        """_swap_temporal must not mutate the input formula."""
        original = {"tag": "untl", "event": {"tag": "atom", "name": "p"}, "guard": {"tag": "bot"}}
        original_copy = dict(original)
        _swap_temporal(original)
        assert original["tag"] == original_copy["tag"]

    def test_nested_untl_snce_swapped(self):
        """Nested untl and snce are both swapped."""
        nested = {
            "tag": "imp",
            "left": FORMULA_UNTIL,
            "right": FORMULA_SINCE,
        }
        result = _swap_temporal(nested)
        assert result["left"]["tag"] == "snce"
        assert result["right"]["tag"] == "untl"


# ---------------------------------------------------------------------------
# Tests for _dual_axiom_name
# ---------------------------------------------------------------------------


class TestDualAxiomName:
    """Tests for the _dual_axiom_name helper."""

    def test_none_returns_none(self):
        assert _dual_axiom_name(None) is None

    def test_serial_future_returns_serial_past(self):
        assert _dual_axiom_name("serial_future") == "serial_past"

    def test_serial_past_returns_serial_future(self):
        assert _dual_axiom_name("serial_past") == "serial_future"

    def test_prop_k_returns_prop_k(self):
        """Propositional axioms have no dual; return unchanged."""
        assert _dual_axiom_name("prop_k") == "prop_k"

    def test_all_dual_pairs_are_symmetric(self):
        """If A maps to B, B must map to A."""
        for a, b in _TEMPORAL_AXIOM_DUALS.items():
            assert _TEMPORAL_AXIOM_DUALS.get(b) == a, (
                f"Dual mapping is not symmetric: {a!r} -> {b!r} but {b!r} -> {_TEMPORAL_AXIOM_DUALS.get(b)!r}"
            )

    def test_dual_keys_are_valid_axioms(self):
        """All keys in _TEMPORAL_AXIOM_DUALS should be valid axiom names."""
        for name in _TEMPORAL_AXIOM_DUALS:
            assert name in AXIOM_ACTIONS, (
                f"{name!r} in _TEMPORAL_AXIOM_DUALS is not a valid axiom"
            )


# ---------------------------------------------------------------------------
# Tests for temporal_dual_augmentation
# ---------------------------------------------------------------------------


class TestTemporalDualAugmentation:
    """Tests for temporal_dual_augmentation."""

    def test_empty_input_returns_empty(self):
        result = temporal_dual_augmentation([])
        assert result == []

    def test_non_temporal_record_excluded(self):
        """Records with no temporal operators in goal_json are not augmented."""
        records = [make_record(goal_json=FORMULA_BOT, axiom_name="ex_falso")]
        result = temporal_dual_augmentation(records)
        assert result == []

    def test_temporal_record_produces_dual(self):
        """A record with an Until goal produces one temporal dual."""
        record = make_temporal_record(
            goal_json=FORMULA_UNTIL,
            axiom_name="serial_future",
        )
        result = temporal_dual_augmentation([record])
        assert len(result) == 1

    def test_dual_step_id_has_dual_suffix(self):
        record = make_temporal_record(step_id="thm/0", goal_json=FORMULA_UNTIL, axiom_name="serial_future")
        result = temporal_dual_augmentation([record])
        aug_record, source = result[0]
        assert aug_record.step_id == "thm/0__dual"

    def test_source_label_correct(self):
        record = make_temporal_record(step_id="thm/0", goal_json=FORMULA_UNTIL, axiom_name="serial_future")
        result = temporal_dual_augmentation([record])
        _, source = result[0]
        assert source == "temporal_dual:thm/0"

    def test_dual_axiom_name_is_swapped(self):
        record = make_temporal_record(
            goal_json=FORMULA_UNTIL,
            axiom_name="serial_future",
        )
        result = temporal_dual_augmentation([record])
        aug_record, _ = result[0]
        assert aug_record.axiom_name == "serial_past"

    def test_dual_action_index_recomputed(self):
        record = make_temporal_record(
            goal_json=FORMULA_UNTIL,
            axiom_name="serial_future",
        )
        result = temporal_dual_augmentation([record])
        aug_record, _ = result[0]
        expected_idx = ACTION_TO_INDEX["serial_past"]
        assert aug_record.action_index == expected_idx

    def test_dual_goal_json_swapped(self):
        record = make_temporal_record(
            goal_json=FORMULA_UNTIL,
            axiom_name="serial_future",
        )
        result = temporal_dual_augmentation([record])
        aug_record, _ = result[0]
        assert aug_record.goal_json["tag"] == "snce"

    def test_dual_preserves_depth_and_height(self):
        record = make_temporal_record(
            goal_json=FORMULA_UNTIL,
            axiom_name="serial_future",
            depth=3,
            proof_height=7,
        )
        result = temporal_dual_augmentation([record])
        aug_record, _ = result[0]
        assert aug_record.depth == 3
        assert aug_record.proof_height == 7

    def test_dual_preserves_context(self):
        record = make_temporal_record(
            goal_json=FORMULA_UNTIL,
            axiom_name="serial_future",
            context=("p", "q"),
        )
        result = temporal_dual_augmentation([record])
        aug_record, _ = result[0]
        assert aug_record.context == ("p", "q")

    def test_dual_subgoals_swapped(self):
        """Subgoals containing temporal operators are also swapped."""
        record = make_record(
            goal_json=FORMULA_UNTIL,
            rule="modus_ponens",
            axiom_name=None,
            action_index=ACTION_TO_INDEX["modus_ponens"],
            subgoals=(FORMULA_UNTIL, FORMULA_ATOM_P),
        )
        result = temporal_dual_augmentation([record])
        aug_record, _ = result[0]
        assert aug_record.subgoals[0]["tag"] == "snce"
        assert aug_record.subgoals[1] == FORMULA_ATOM_P

    def test_non_temporal_axiom_name_preserved(self):
        """Axioms with no dual keep their original axiom_name after augmentation."""
        # Use a propositional axiom but add temporal content to goal.
        record = make_record(
            goal_json=FORMULA_UNTIL,
            rule="axiom",
            axiom_name="prop_k",
            action_index=ACTION_TO_INDEX["prop_k"],
        )
        result = temporal_dual_augmentation([record])
        assert len(result) == 1
        aug_record, _ = result[0]
        # prop_k has no dual, so axiom_name should be preserved.
        assert aug_record.axiom_name == "prop_k"

    def test_multiple_temporal_records(self):
        """Two temporal records produce two duals."""
        records = [
            make_temporal_record(step_id="t/0", goal_json=FORMULA_UNTIL, axiom_name="serial_future"),
            make_temporal_record(step_id="t/1", goal_json=FORMULA_SINCE, axiom_name="serial_past"),
        ]
        result = temporal_dual_augmentation(records)
        assert len(result) == 2

    def test_since_becomes_until_dual(self):
        """A Since goal produces an Until dual."""
        record = make_temporal_record(
            goal_json=FORMULA_SINCE,
            axiom_name="serial_past",
        )
        result = temporal_dual_augmentation([record])
        aug_record, _ = result[0]
        assert aug_record.goal_json["tag"] == "untl"
        assert aug_record.axiom_name == "serial_future"

    def test_augmented_records_are_valid_proof_step_records(self):
        """Augmented records must be valid (pass ProofStepRecord validation)."""
        records = [
            make_temporal_record(step_id="t/0", goal_json=FORMULA_UNTIL, axiom_name="serial_future"),
        ]
        result = temporal_dual_augmentation(records)
        for aug_record, _ in result:
            assert isinstance(aug_record, ProofStepRecord)
            assert 0 <= aug_record.action_index <= 48


# ---------------------------------------------------------------------------
# Tests for context_variation_augmentation
# ---------------------------------------------------------------------------


class TestContextVariationAugmentation:
    """Tests for context_variation_augmentation."""

    def test_empty_input_returns_empty(self):
        result = context_variation_augmentation([])
        assert result == []

    def test_record_with_context_excluded(self):
        """Records with non-empty context are not augmented."""
        record = make_record(context=("p",), goal_json=FORMULA_BOT, axiom_name="ex_falso")
        result = context_variation_augmentation([record])
        assert result == []

    def test_empty_context_record_produces_variants(self):
        """A record with empty context produces max_context_additions variants."""
        record = make_record(context=(), goal_json=FORMULA_BOT, axiom_name="ex_falso")
        result = context_variation_augmentation([record], max_context_additions=3)
        assert len(result) == 3

    def test_variant_step_ids_have_ctx_suffix(self):
        record = make_record(step_id="t/0", context=(), goal_json=FORMULA_BOT, axiom_name="ex_falso")
        result = context_variation_augmentation([record], max_context_additions=3)
        step_ids = [r.step_id for r, _ in result]
        assert "t/0__ctx1" in step_ids
        assert "t/0__ctx2" in step_ids
        assert "t/0__ctx3" in step_ids

    def test_variant_uses_weakening_rule(self):
        record = make_record(context=(), goal_json=FORMULA_BOT, axiom_name="ex_falso")
        result = context_variation_augmentation([record], max_context_additions=1)
        aug_record, _ = result[0]
        assert aug_record.rule == "weakening"
        assert aug_record.axiom_name is None
        assert aug_record.action_index == ACTION_TO_INDEX["weakening"]

    def test_variant_context_grows_with_k(self):
        """Context of k-th variant has k formulas."""
        record = make_record(step_id="t/0", context=(), goal_json=FORMULA_BOT, axiom_name="ex_falso")
        result = context_variation_augmentation([record], max_context_additions=3)
        by_id = {r.step_id: r for r, _ in result}
        assert len(by_id["t/0__ctx1"].context) == 1
        assert len(by_id["t/0__ctx2"].context) == 2
        assert len(by_id["t/0__ctx3"].context) == 3

    def test_variant_context_strings_come_from_bank(self):
        record = make_record(context=(), goal_json=FORMULA_BOT, axiom_name="ex_falso")
        result = context_variation_augmentation([record], max_context_additions=2)
        for aug_record, _ in result:
            for ctx_str in aug_record.context:
                assert ctx_str in _CONTEXT_STRINGS

    def test_variant_goal_unchanged(self):
        """The goal formula is preserved in the context variation step."""
        record = make_record(context=(), goal_json=FORMULA_ATOM_P, axiom_name="prop_k")
        result = context_variation_augmentation([record], max_context_additions=1)
        aug_record, _ = result[0]
        assert aug_record.goal_json == FORMULA_ATOM_P

    def test_variant_subgoal_is_original_goal(self):
        """The weakening step's subgoal is the original goal formula."""
        record = make_record(context=(), goal_json=FORMULA_ATOM_P, axiom_name="prop_k")
        result = context_variation_augmentation([record], max_context_additions=1)
        aug_record, _ = result[0]
        assert len(aug_record.subgoals) == 1
        assert aug_record.subgoals[0] == FORMULA_ATOM_P

    def test_source_label_correct(self):
        record = make_record(step_id="t/0", context=(), goal_json=FORMULA_BOT, axiom_name="ex_falso")
        result = context_variation_augmentation([record], max_context_additions=1)
        _, source = result[0]
        assert source.startswith("context_variation:t/0:")

    def test_max_context_additions_zero_raises(self):
        with pytest.raises(ValueError, match="max_context_additions must be >= 1"):
            context_variation_augmentation([], max_context_additions=0)

    def test_depth_and_height_preserved(self):
        record = make_record(
            context=(), goal_json=FORMULA_BOT, axiom_name="ex_falso",
            depth=5, proof_height=10,
        )
        result = context_variation_augmentation([record], max_context_additions=1)
        aug_record, _ = result[0]
        assert aug_record.depth == 5
        assert aug_record.proof_height == 10

    def test_frame_class_preserved(self):
        record = make_record(
            context=(), goal_json=FORMULA_BOT, axiom_name="ex_falso",
            frame_class="Dense",
        )
        result = context_variation_augmentation([record], max_context_additions=1)
        aug_record, _ = result[0]
        assert aug_record.frame_class == "Dense"

    def test_augmented_records_are_valid(self):
        """Context variation records must pass ProofStepRecord validation."""
        records = [make_record(context=(), goal_json=FORMULA_BOT, axiom_name="ex_falso")]
        result = context_variation_augmentation(records, max_context_additions=3)
        for aug_record, _ in result:
            assert isinstance(aug_record, ProofStepRecord)
            assert 0 <= aug_record.action_index <= 48


# ---------------------------------------------------------------------------
# Tests for augment_all
# ---------------------------------------------------------------------------


class TestAugmentAll:
    """Tests for the augment_all combinator."""

    def test_empty_input_returns_empty(self):
        result = augment_all([])
        assert result == []

    def test_originals_included_by_default(self):
        record = make_record(goal_json=FORMULA_BOT, axiom_name="ex_falso")
        result = augment_all([record])
        sources = [s for _, s in result]
        assert "original" in sources

    def test_originals_excluded_when_flag_set(self):
        record = make_record(goal_json=FORMULA_BOT, axiom_name="ex_falso")
        result = augment_all([record], include_originals=False)
        sources = [s for _, s in result]
        assert "original" not in sources

    def test_combined_includes_temporal_duals(self):
        record = make_temporal_record(goal_json=FORMULA_UNTIL, axiom_name="serial_future")
        result = augment_all([record])
        sources = [s for _, s in result]
        assert any(s.startswith("temporal_dual") for s in sources)

    def test_combined_includes_context_variations(self):
        record = make_record(context=(), goal_json=FORMULA_BOT, axiom_name="ex_falso")
        result = augment_all([record], max_context_additions=2)
        sources = [s for _, s in result]
        assert any(s.startswith("context_variation") for s in sources)

    def test_total_count_is_correct(self):
        """Total = 1 original + 1 temporal dual + max_context_additions context variants."""
        record = make_temporal_record(
            step_id="t/0",
            context=(),
            goal_json=FORMULA_UNTIL,
            axiom_name="serial_future",
        )
        result = augment_all([record], max_context_additions=2, include_originals=True)
        # 1 original + 1 temporal dual + 2 context variants = 4
        assert len(result) == 4

    def test_all_records_are_proof_step_records(self):
        records = [
            make_temporal_record(
                step_id="t/0",
                context=(),
                goal_json=FORMULA_UNTIL,
                axiom_name="serial_future",
            ),
        ]
        result = augment_all(records, max_context_additions=2)
        for aug_record, _ in result:
            assert isinstance(aug_record, ProofStepRecord)


# ---------------------------------------------------------------------------
# Tests for augmented_statistics
# ---------------------------------------------------------------------------


class TestAugmentedStatistics:
    """Tests for augmented_statistics."""

    def test_empty_returns_zeros(self):
        stats = augmented_statistics([])
        assert stats["total_steps"] == 0
        assert stats["unique_step_ids"] == 0
        assert stats["duplicate_step_ids"] == 0
        assert stats["action_index_coverage"] == 0

    def test_total_steps_count(self):
        records = [make_record(step_id=f"t/{i}", axiom_name="ex_falso") for i in range(5)]
        augmented = [(r, "original") for r in records]
        stats = augmented_statistics(augmented)
        assert stats["total_steps"] == 5

    def test_unique_step_ids_counted(self):
        records = [make_record(step_id=f"t/{i}", axiom_name="ex_falso") for i in range(3)]
        augmented = [(r, "original") for r in records]
        stats = augmented_statistics(augmented)
        assert stats["unique_step_ids"] == 3
        assert stats["duplicate_step_ids"] == 0

    def test_duplicate_step_ids_detected(self):
        r = make_record(step_id="t/0", axiom_name="ex_falso")
        augmented = [(r, "original"), (r, "original")]
        stats = augmented_statistics(augmented)
        assert stats["duplicate_step_ids"] == 1

    def test_action_index_coverage(self):
        records = [
            make_record(step_id="t/0", axiom_name="ex_falso"),
            make_record(step_id="t/1", rule="modus_ponens", axiom_name=None, action_index=ACTION_TO_INDEX["modus_ponens"]),
        ]
        augmented = [(r, "original") for r in records]
        stats = augmented_statistics(augmented)
        assert stats["action_index_coverage"] == 2

    def test_augmentation_source_counts(self):
        """augmentation_source_counts groups by category prefix."""
        records = [
            (make_record(step_id="t/0", axiom_name="ex_falso"), "original"),
            (make_record(step_id="t/0__dual", axiom_name="ex_falso"), "temporal_dual:t/0"),
            (make_record(step_id="t/0__ctx1", rule="weakening", axiom_name=None, action_index=ACTION_TO_INDEX["weakening"]), "context_variation:t/0:1ctx"),
        ]
        stats = augmented_statistics(records)
        assert stats["augmentation_source_counts"]["original"] == 1
        assert stats["augmentation_source_counts"]["temporal_dual"] == 1
        assert stats["augmentation_source_counts"]["context_variation"] == 1

    def test_rule_distribution_counted(self):
        records = [
            (make_record(step_id="t/0", axiom_name="ex_falso"), "original"),
            (make_record(step_id="t/1", rule="modus_ponens", axiom_name=None, action_index=ACTION_TO_INDEX["modus_ponens"]), "original"),
        ]
        stats = augmented_statistics(records)
        rd = stats["rule_distribution"]
        assert rd.get("axiom", 0) == 1
        assert rd.get("modus_ponens", 0) == 1

    def test_proof_height_distribution(self):
        records = [
            (make_record(step_id="t/0", axiom_name="ex_falso", proof_height=0), "original"),
            (make_record(step_id="t/1", axiom_name="prop_k", proof_height=2), "original"),
            (make_record(step_id="t/2", axiom_name="prop_s", proof_height=2), "original"),
        ]
        stats = augmented_statistics(records)
        hd = stats["proof_height_distribution"]
        assert hd[0] == 1
        assert hd[2] == 2


# ---------------------------------------------------------------------------
# Tests for split_dataset
# ---------------------------------------------------------------------------


class TestSplitDataset:
    """Tests for the split_dataset utility."""

    def _make_augmented(self, n: int) -> list[tuple[ProofStepRecord, str]]:
        """Create n augmented records with varying proof heights."""
        records = []
        for i in range(n):
            r = make_record(
                step_id=f"t/{i}",
                axiom_name="ex_falso",
                proof_height=i % 5,
            )
            records.append((r, "original"))
        return records

    def test_invalid_train_frac_raises(self):
        with pytest.raises(ValueError, match="train_frac must be in"):
            split_dataset([], train_frac=0.0)

    def test_invalid_val_frac_raises(self):
        with pytest.raises(ValueError, match="val_frac must be in"):
            split_dataset([], val_frac=0.0)

    def test_fracs_sum_to_one_raises(self):
        with pytest.raises(ValueError, match="train_frac \\+ val_frac must be < 1.0"):
            split_dataset([], train_frac=0.9, val_frac=0.1)

    def test_empty_input_returns_empty_splits(self):
        train, val, test = split_dataset([])
        assert train == []
        assert val == []
        assert test == []

    def test_total_records_preserved(self):
        augmented = self._make_augmented(100)
        train, val, test = split_dataset(augmented, train_frac=0.8, val_frac=0.1, seed=0)
        assert len(train) + len(val) + len(test) == 100

    def test_no_overlap_between_splits(self):
        augmented = self._make_augmented(50)
        train, val, test = split_dataset(augmented, seed=42)
        train_ids = set(r.step_id for r, _ in train)
        val_ids = set(r.step_id for r, _ in val)
        test_ids = set(r.step_id for r, _ in test)
        assert train_ids.isdisjoint(val_ids), "Train and val overlap!"
        assert train_ids.isdisjoint(test_ids), "Train and test overlap!"
        assert val_ids.isdisjoint(test_ids), "Val and test overlap!"

    def test_train_is_largest_split(self):
        augmented = self._make_augmented(100)
        train, val, test = split_dataset(augmented, train_frac=0.8, val_frac=0.1, seed=0)
        assert len(train) > len(val)
        assert len(train) > len(test)

    def test_reproducible_with_same_seed(self):
        augmented = self._make_augmented(30)
        train1, val1, test1 = split_dataset(augmented, seed=42)
        train2, val2, test2 = split_dataset(augmented, seed=42)
        assert [r.step_id for r, _ in train1] == [r.step_id for r, _ in train2]

    def test_different_seeds_produce_different_splits(self):
        augmented = self._make_augmented(30)
        train1, _, _ = split_dataset(augmented, seed=1, stratify_by_height=False)
        train2, _, _ = split_dataset(augmented, seed=2, stratify_by_height=False)
        # Very unlikely to be identical with 30 records and different seeds.
        ids1 = [r.step_id for r, _ in train1]
        ids2 = [r.step_id for r, _ in train2]
        assert ids1 != ids2

    def test_no_stratification_mode(self):
        augmented = self._make_augmented(30)
        train, val, test = split_dataset(augmented, stratify_by_height=False, seed=0)
        assert len(train) + len(val) + len(test) == 30

    def test_single_record_goes_to_train(self):
        augmented = self._make_augmented(1)
        train, val, test = split_dataset(augmented)
        assert len(train) == 1
        assert len(val) == 0
        assert len(test) == 0


# ---------------------------------------------------------------------------
# Integration: augment from fixture and run statistics
# ---------------------------------------------------------------------------


class TestAugmentationIntegration:
    """End-to-end integration tests using the proof_steps fixture."""

    FIXTURE = (
        __file__.replace(
            "tests/test_data/test_augmentation.py",
            "tests/fixtures/proof_steps_fixture.jsonl",
        )
    )

    def _load_fixture(self):
        """Load fixture records using ingestion pipeline."""
        from pathlib import Path

        from bimodal_harness.data.ingestion import load_proof_steps

        fixture_path = Path(__file__).parent.parent / "fixtures" / "proof_steps_fixture.jsonl"
        if not fixture_path.exists():
            pytest.skip(f"Fixture not found: {fixture_path}")
        return load_proof_steps(fixture_path)

    def test_augment_fixture_produces_more_records(self):
        records = self._load_fixture()
        augmented = augment_all(records, max_context_additions=3)
        assert len(augmented) > len(records)

    def test_augmented_fixture_stats_populated(self):
        records = self._load_fixture()
        augmented = augment_all(records, max_context_additions=3)
        stats = augmented_statistics(augmented)
        assert stats["total_steps"] > 0
        assert stats["action_index_coverage"] > 0

    def test_augmented_fixture_no_duplicate_ids(self):
        records = self._load_fixture()
        augmented = augment_all(records, max_context_additions=2)
        step_ids = [r.step_id for r, _ in augmented]
        assert len(step_ids) == len(set(step_ids)), (
            "Duplicate step_ids found in augmented fixture dataset"
        )

    def test_augmented_fixture_split_covers_all_records(self):
        records = self._load_fixture()
        augmented = augment_all(records, max_context_additions=2)
        train, val, test = split_dataset(augmented, seed=0)
        assert len(train) + len(val) + len(test) == len(augmented)

    def test_augmented_fixture_all_action_indices_valid(self):
        records = self._load_fixture()
        augmented = augment_all(records, max_context_additions=2)
        for aug_record, _ in augmented:
            assert 0 <= aug_record.action_index <= 48, (
                f"Invalid action_index {aug_record.action_index} for step {aug_record.step_id!r}"
            )

    def test_context_variation_augmentation_adds_weakening_steps(self):
        records = self._load_fixture()
        ctx_results = context_variation_augmentation(records, max_context_additions=2)
        # Should produce at least some weakening steps for records with empty context.
        empty_ctx_count = sum(1 for r in records if not r.context)
        assert len(ctx_results) == empty_ctx_count * 2

    def test_temporal_dual_augmentation_produces_valid_records(self):
        records = self._load_fixture()
        duals = temporal_dual_augmentation(records)
        for aug_record, source in duals:
            assert isinstance(aug_record, ProofStepRecord)
            assert source.startswith("temporal_dual:")
