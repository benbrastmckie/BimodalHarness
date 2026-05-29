"""Tests for bimodal_harness.formula.mutator module.

Covers:
- collect_positions returns all subtree positions
- rebuild_at replaces nodes at paths correctly
- Each of the 10 mutation operators tested independently
- All mutated formulas pass schema validation
- mutate() never raises on valid formulas of complexity >= 2
- generate_contrastive_pair returns valid pairs
"""

from __future__ import annotations

import random

import pytest

from bimodal_harness.formula.ast import (
    Atom,
    Bot,
    Box,
    Imp,
    Snce,
    Untl,
    complexity,
)
from bimodal_harness.formula.mutator import (
    OPERATOR_NAMES,
    add_box,
    change_atom,
    collect_positions,
    drop_modal,
    flip_operator,
    flip_temporal_direction,
    generate_contrastive_pair,
    mutate,
    negate_guard,
    rebuild_at,
    remove_box,
    strengthen_antecedent,
    swap_children,
    weaken_antecedent,
)
from bimodal_harness.schema.formula import validate_formula_json

# Reference formula used across many tests:
# imp(atom("p"), box(untl(atom("q"), atom("r"))))
_REF = Imp(Atom("p"), Box(Untl(Atom("q"), Atom("r"))))


# ---------------------------------------------------------------------------
# collect_positions
# ---------------------------------------------------------------------------


class TestCollectPositions:
    def test_leaf_has_one_position(self) -> None:
        positions = collect_positions(Atom("p"))
        assert len(positions) == 1
        assert positions[0] == ((), Atom("p"))

    def test_bot_has_one_position(self) -> None:
        positions = collect_positions(Bot())
        assert len(positions) == 1

    def test_box_has_two_positions(self) -> None:
        f = Box(Atom("p"))
        positions = collect_positions(f)
        assert len(positions) == 2
        paths = [p for (p, _) in positions]
        assert () in paths
        assert (0,) in paths

    def test_imp_has_three_positions(self) -> None:
        f = Imp(Atom("p"), Bot())
        positions = collect_positions(f)
        assert len(positions) == 3
        paths = [p for (p, _) in positions]
        assert () in paths
        assert (0,) in paths
        assert (1,) in paths

    def test_nested_positions(self) -> None:
        # imp(p, box(q)) has positions: (), (0,), (1,), (1,0)
        f = Imp(Atom("p"), Box(Atom("q")))
        positions = collect_positions(f)
        assert len(positions) == 4
        paths = {p for (p, _) in positions}
        assert () in paths
        assert (0,) in paths
        assert (1,) in paths
        assert (1, 0) in paths

    def test_reference_formula_positions(self) -> None:
        # imp(p, box(untl(q, r))) has 6 nodes
        positions = collect_positions(_REF)
        assert len(positions) == 6


# ---------------------------------------------------------------------------
# rebuild_at
# ---------------------------------------------------------------------------


class TestRebuildAt:
    def test_replace_root(self) -> None:
        f = Atom("p")
        result = rebuild_at(f, (), Bot())
        assert result == Bot()

    def test_replace_left_of_imp(self) -> None:
        f = Imp(Atom("p"), Atom("q"))
        result = rebuild_at(f, (0,), Bot())
        assert result == Imp(Bot(), Atom("q"))

    def test_replace_right_of_imp(self) -> None:
        f = Imp(Atom("p"), Atom("q"))
        result = rebuild_at(f, (1,), Bot())
        assert result == Imp(Atom("p"), Bot())

    def test_replace_child_of_box(self) -> None:
        f = Box(Atom("p"))
        result = rebuild_at(f, (0,), Bot())
        assert result == Box(Bot())

    def test_replace_event_of_untl(self) -> None:
        f = Untl(Atom("p"), Atom("q"))
        result = rebuild_at(f, (0,), Bot())
        assert result == Untl(Bot(), Atom("q"))

    def test_replace_guard_of_untl(self) -> None:
        f = Untl(Atom("p"), Atom("q"))
        result = rebuild_at(f, (1,), Bot())
        assert result == Untl(Atom("p"), Bot())

    def test_deep_replacement(self) -> None:
        # imp(p, box(untl(q, r))) - replace (1,0,0) which is atom("q")
        result = rebuild_at(_REF, (1, 0, 0), Bot())
        expected = Imp(Atom("p"), Box(Untl(Bot(), Atom("r"))))
        assert result == expected

    def test_original_unchanged(self) -> None:
        f = Imp(Atom("p"), Atom("q"))
        _ = rebuild_at(f, (0,), Bot())
        assert f == Imp(Atom("p"), Atom("q"))  # Frozen, unchanged


# ---------------------------------------------------------------------------
# Individual mutation operators
# ---------------------------------------------------------------------------


class TestFlipOperator:
    def test_untl_to_snce(self) -> None:
        f = Untl(Atom("p"), Atom("q"))
        rng = random.Random(0)
        result = flip_operator(f, rng)
        assert result == Snce(Atom("p"), Atom("q"))

    def test_snce_to_untl(self) -> None:
        f = Snce(Atom("p"), Atom("q"))
        rng = random.Random(0)
        result = flip_operator(f, rng)
        assert result == Untl(Atom("p"), Atom("q"))

    def test_finds_temporal_in_subtree(self) -> None:
        # imp(p, untl(q, r)) -> should flip the untl
        f = Imp(Atom("p"), Untl(Atom("q"), Atom("r")))
        rng = random.Random(0)
        result = flip_operator(f, rng)
        assert result == Imp(Atom("p"), Snce(Atom("q"), Atom("r")))

    def test_returns_none_for_pure_atom(self) -> None:
        f = Atom("p")
        rng = random.Random(0)
        result = flip_operator(f, rng)
        assert result is None

    def test_produces_valid_json(self) -> None:
        f = Untl(Atom("p"), Bot())
        rng = random.Random(1)
        result = flip_operator(f, rng)
        assert result is not None
        assert validate_formula_json(result.to_json())


class TestFlipTemporalDirection:
    def test_untl_swaps_event_guard(self) -> None:
        f = Untl(Atom("p"), Atom("q"))
        rng = random.Random(0)
        result = flip_temporal_direction(f, rng)
        assert result == Untl(Atom("q"), Atom("p"))

    def test_snce_swaps_event_guard(self) -> None:
        f = Snce(Atom("p"), Atom("q"))
        rng = random.Random(0)
        result = flip_temporal_direction(f, rng)
        assert result == Snce(Atom("q"), Atom("p"))

    def test_returns_none_for_no_temporal(self) -> None:
        f = Imp(Atom("p"), Atom("q"))
        rng = random.Random(0)
        result = flip_temporal_direction(f, rng)
        assert result is None

    def test_produces_valid_json(self) -> None:
        f = Untl(Atom("p"), Box(Atom("q")))
        rng = random.Random(2)
        result = flip_temporal_direction(f, rng)
        assert result is not None
        assert validate_formula_json(result.to_json())


class TestWeakenAntecedent:
    def test_replaces_antecedent_with_bot(self) -> None:
        f = Imp(Atom("p"), Atom("q"))
        rng = random.Random(0)
        result = weaken_antecedent(f, rng)
        assert result == Imp(Bot(), Atom("q"))

    def test_returns_none_when_already_bot(self) -> None:
        f = Imp(Bot(), Atom("q"))
        rng = random.Random(0)
        result = weaken_antecedent(f, rng)
        assert result is None

    def test_returns_none_for_no_imp(self) -> None:
        f = Atom("p")
        rng = random.Random(0)
        result = weaken_antecedent(f, rng)
        assert result is None

    def test_produces_valid_json(self) -> None:
        f = Imp(Box(Atom("p")), Atom("q"))
        rng = random.Random(3)
        result = weaken_antecedent(f, rng)
        assert result is not None
        assert validate_formula_json(result.to_json())


class TestStrengthenAntecedent:
    def test_wraps_antecedent_in_box(self) -> None:
        f = Imp(Atom("p"), Atom("q"))
        rng = random.Random(0)
        result = strengthen_antecedent(f, rng)
        assert result == Imp(Box(Atom("p")), Atom("q"))

    def test_returns_none_for_no_imp(self) -> None:
        f = Atom("p")
        rng = random.Random(0)
        result = strengthen_antecedent(f, rng)
        assert result is None

    def test_produces_valid_json(self) -> None:
        f = Imp(Atom("p"), Bot())
        rng = random.Random(4)
        result = strengthen_antecedent(f, rng)
        assert result is not None
        assert validate_formula_json(result.to_json())


class TestChangeAtom:
    def test_replaces_single_atom_with_variant(self) -> None:
        f = Atom("p")
        rng = random.Random(0)
        result = change_atom(f, rng)
        assert result is not None
        assert isinstance(result, Atom)
        assert result.name != "p"
        assert result.name == "p_b"

    def test_picks_different_atom_when_multiple(self) -> None:
        f = Imp(Atom("p"), Atom("q"))
        rng = random.Random(0)
        result = change_atom(f, rng)
        assert result is not None
        # Result should have changed one atom
        assert result != f

    def test_returns_none_for_no_atom(self) -> None:
        f = Bot()
        rng = random.Random(0)
        result = change_atom(f, rng)
        assert result is None

    def test_produces_valid_json(self) -> None:
        f = Imp(Atom("p"), Atom("q"))
        rng = random.Random(5)
        result = change_atom(f, rng)
        assert result is not None
        assert validate_formula_json(result.to_json())


class TestAddBox:
    def test_wraps_subformula_in_box(self) -> None:
        f = Atom("p")
        rng = random.Random(0)
        result = add_box(f, rng)
        assert result == Box(Atom("p"))

    def test_produces_valid_json(self) -> None:
        f = Imp(Atom("p"), Atom("q"))
        rng = random.Random(6)
        result = add_box(f, rng)
        assert result is not None
        assert validate_formula_json(result.to_json())

    def test_increases_modal_depth(self) -> None:
        from bimodal_harness.formula.ast import modal_depth
        f = Atom("p")
        rng = random.Random(0)
        result = add_box(f, rng)
        assert result is not None
        assert modal_depth(result) >= 1


class TestRemoveBox:
    def test_removes_box(self) -> None:
        f = Box(Atom("p"))
        rng = random.Random(0)
        result = remove_box(f, rng)
        assert result == Atom("p")

    def test_returns_none_for_no_box(self) -> None:
        f = Atom("p")
        rng = random.Random(0)
        result = remove_box(f, rng)
        assert result is None

    def test_produces_valid_json(self) -> None:
        f = Box(Imp(Atom("p"), Bot()))
        rng = random.Random(7)
        result = remove_box(f, rng)
        assert result is not None
        assert validate_formula_json(result.to_json())


class TestNegateGuard:
    def test_negates_guard_in_untl(self) -> None:
        f = Untl(Atom("p"), Atom("q"))
        rng = random.Random(0)
        result = negate_guard(f, rng)
        expected = Untl(Atom("p"), Imp(Atom("q"), Bot()))
        assert result == expected

    def test_negates_guard_in_snce(self) -> None:
        f = Snce(Atom("p"), Atom("q"))
        rng = random.Random(0)
        result = negate_guard(f, rng)
        expected = Snce(Atom("p"), Imp(Atom("q"), Bot()))
        assert result == expected

    def test_returns_none_for_no_temporal(self) -> None:
        f = Imp(Atom("p"), Atom("q"))
        rng = random.Random(0)
        result = negate_guard(f, rng)
        assert result is None

    def test_produces_valid_json(self) -> None:
        f = Untl(Atom("p"), Bot())
        rng = random.Random(8)
        result = negate_guard(f, rng)
        assert result is not None
        assert validate_formula_json(result.to_json())


class TestSwapChildren:
    def test_swaps_imp_children(self) -> None:
        f = Imp(Atom("p"), Atom("q"))
        rng = random.Random(0)
        result = swap_children(f, rng)
        assert result == Imp(Atom("q"), Atom("p"))

    def test_swaps_untl_children(self) -> None:
        f = Untl(Atom("p"), Atom("q"))
        rng = random.Random(0)
        result = swap_children(f, rng)
        assert result == Untl(Atom("q"), Atom("p"))

    def test_swaps_snce_children(self) -> None:
        f = Snce(Atom("p"), Atom("q"))
        rng = random.Random(0)
        result = swap_children(f, rng)
        assert result == Snce(Atom("q"), Atom("p"))

    def test_returns_none_for_no_binary(self) -> None:
        f = Box(Atom("p"))
        rng = random.Random(0)
        result = swap_children(f, rng)
        assert result is None

    def test_produces_valid_json(self) -> None:
        f = Imp(Box(Atom("p")), Atom("q"))
        rng = random.Random(9)
        result = swap_children(f, rng)
        assert result is not None
        assert validate_formula_json(result.to_json())


class TestDropModal:
    def test_drops_box_to_bot(self) -> None:
        f = Box(Atom("p"))
        rng = random.Random(0)
        result = drop_modal(f, rng)
        assert result == Bot()

    def test_drops_nested_box(self) -> None:
        f = Imp(Atom("p"), Box(Atom("q")))
        rng = random.Random(0)
        result = drop_modal(f, rng)
        assert result == Imp(Atom("p"), Bot())

    def test_returns_none_for_no_box(self) -> None:
        f = Atom("p")
        rng = random.Random(0)
        result = drop_modal(f, rng)
        assert result is None

    def test_produces_valid_json(self) -> None:
        f = Box(Untl(Atom("p"), Bot()))
        rng = random.Random(10)
        result = drop_modal(f, rng)
        assert result is not None
        assert validate_formula_json(result.to_json())


# ---------------------------------------------------------------------------
# OPERATOR_NAMES registry
# ---------------------------------------------------------------------------


class TestOperatorNames:
    def test_has_exactly_10_operators(self) -> None:
        assert len(OPERATOR_NAMES) == 10

    def test_all_expected_names_present(self) -> None:
        expected = {
            "flip_operator",
            "flip_temporal_direction",
            "weaken_antecedent",
            "strengthen_antecedent",
            "change_atom",
            "add_box",
            "remove_box",
            "negate_guard",
            "swap_children",
            "drop_modal",
        }
        assert set(OPERATOR_NAMES) == expected


# ---------------------------------------------------------------------------
# mutate() dispatch
# ---------------------------------------------------------------------------


class TestMutate:
    def test_mutates_complex_formula(self) -> None:
        rng = random.Random(0)
        result = mutate(_REF, rng)
        assert result is not None
        assert validate_formula_json(result.to_json())

    def test_never_raises_on_complexity_2_plus(self) -> None:
        """mutate() never raises on valid formulas of complexity >= 2."""
        from bimodal_harness.formula.generator import random_formula
        rng = random.Random(42)
        atoms = ["p", "q", "r"]
        for _ in range(200):
            f = random_formula(8, atoms, rng)
            if complexity(f) >= 2:
                result = mutate(f, rng)
                assert validate_formula_json(result.to_json())

    def test_custom_operators_subset(self) -> None:
        rng = random.Random(0)
        result = mutate(_REF, rng, operators=["swap_children", "add_box"])
        assert result is not None
        assert validate_formula_json(result.to_json())

    def test_unknown_operator_raises(self) -> None:
        rng = random.Random(0)
        with pytest.raises(ValueError, match="Unknown mutation operator"):
            mutate(_REF, rng, operators=["nonexistent_op"])

    def test_at_least_8_of_10_operators_produce_distinct_output(self) -> None:
        """At least 8 of 10 operators produce a formula different from _REF."""
        rng = random.Random(0)
        from bimodal_harness.formula.mutator import _ALL_OPERATORS

        distinct_count = 0
        for name, fn in _ALL_OPERATORS.items():
            result = fn(_REF, rng)
            if result is not None and result != _REF:
                distinct_count += 1

        assert distinct_count >= 8, (
            f"Only {distinct_count}/10 operators produced distinct output on reference formula"
        )

    def test_empty_operators_raises(self) -> None:
        rng = random.Random(0)
        with pytest.raises(ValueError, match="non-empty"):
            mutate(_REF, rng, operators=[])


# ---------------------------------------------------------------------------
# generate_contrastive_pair
# ---------------------------------------------------------------------------


class TestGenerateContrastivePair:
    def test_returns_tuple(self) -> None:
        rng = random.Random(0)
        original, mutant = generate_contrastive_pair(_REF, rng)
        assert original == _REF
        assert mutant is not None

    def test_both_valid_json(self) -> None:
        rng = random.Random(0)
        original, mutant = generate_contrastive_pair(_REF, rng)
        assert validate_formula_json(original.to_json())
        assert validate_formula_json(mutant.to_json())

    def test_100_pairs_all_valid(self) -> None:
        from bimodal_harness.formula.generator import random_formula
        rng = random.Random(42)
        atoms = ["p", "q", "r"]
        for _ in range(100):
            f = random_formula(8, atoms, rng)
            if complexity(f) < 2:
                continue
            original, mutant = generate_contrastive_pair(f, rng)
            assert validate_formula_json(original.to_json())
            assert validate_formula_json(mutant.to_json())
