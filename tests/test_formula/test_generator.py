"""Tests for bimodal_harness.formula.generator module.

Covers:
- Enumeration counts for complexity 1-4 over 2-atom sets
- All enumerated formulas have the correct complexity
- Random generator respects complexity budget
- count_formulas helper correctness
- All enumerated formulas pass schema validation
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
from bimodal_harness.formula.generator import (
    count_formulas,
    enumerate_by_complexity,
    enumerate_up_to_complexity,
    random_formula,
)
from bimodal_harness.schema.formula import validate_formula_json


# ---------------------------------------------------------------------------
# Enumeration counts
# ---------------------------------------------------------------------------


class TestEnumerateByComplexity:
    def test_complexity_1_two_atoms(self) -> None:
        """complexity=1 over 2 atoms yields exactly 3 formulas: Bot, Atom(p), Atom(q)."""
        formulas = list(enumerate_by_complexity(1, ["p", "q"]))
        assert len(formulas) == 3
        assert Bot() in formulas
        assert Atom("p") in formulas
        assert Atom("q") in formulas

    def test_complexity_1_one_atom(self) -> None:
        """complexity=1 over 1 atom yields exactly 2 formulas."""
        formulas = list(enumerate_by_complexity(1, ["p"]))
        assert len(formulas) == 2
        assert Bot() in formulas
        assert Atom("p") in formulas

    def test_complexity_1_no_atoms(self) -> None:
        """complexity=1 over empty atoms yields exactly 1 formula (Bot)."""
        formulas = list(enumerate_by_complexity(1, []))
        assert len(formulas) == 1
        assert formulas[0] == Bot()

    def test_complexity_2_two_atoms(self) -> None:
        """complexity=2 over 2 atoms: box(leaf) for each of 3 leaves = 3 formulas."""
        formulas = list(enumerate_by_complexity(2, ["p", "q"]))
        # Only Box nodes (unary) at complexity 2: box(bot), box(atom_p), box(atom_q)
        # Binary ops need left_c + right_c = 1, which requires left_c >= 1 and right_c >= 0
        # but right_c must be >= 1 too, so no binary ops at complexity 2.
        assert len(formulas) == 3
        assert Box(Bot()) in formulas
        assert Box(Atom("p")) in formulas
        assert Box(Atom("q")) in formulas

    def test_complexity_3_two_atoms(self) -> None:
        """complexity=3 over 2 atoms: box(c2) + 3*binary with left_c=1, right_c=1."""
        formulas = list(enumerate_by_complexity(3, ["p", "q"]))
        # Box children at c=2: 3 choices -> 3 box formulas
        # Binary ops (3): each has left_c=1, right_c=1
        #   3 choices for left * 3 choices for right = 9 each -> 27 binary
        # Total: 3 + 27 = 30
        assert len(formulas) == 30
        # Verify count_formulas agrees
        assert count_formulas(3, 2) == 30

    def test_complexity_4_two_atoms(self) -> None:
        """complexity=4 over 2 atoms: verify against count_formulas."""
        formulas = list(enumerate_by_complexity(4, ["p", "q"]))
        expected = count_formulas(4, 2)
        assert len(formulas) == expected

    def test_complexity_0_yields_nothing(self) -> None:
        """complexity=0 is below minimum and yields nothing."""
        formulas = list(enumerate_by_complexity(0, ["p"]))
        assert formulas == []

    def test_complexity_negative_yields_nothing(self) -> None:
        """Negative complexity yields nothing."""
        formulas = list(enumerate_by_complexity(-1, ["p"]))
        assert formulas == []

    def test_all_have_correct_complexity(self) -> None:
        """All enumerated formulas have exactly the requested complexity."""
        atoms = ["p", "q"]
        for n in range(1, 5):
            for f in enumerate_by_complexity(n, atoms):
                assert complexity(f) == n, (
                    f"Formula {f} has complexity {complexity(f)}, expected {n}"
                )

    def test_no_duplicates_small(self) -> None:
        """No duplicate formulas at small complexities."""
        atoms = ["p", "q"]
        for n in range(1, 4):
            formulas = list(enumerate_by_complexity(n, atoms))
            unique = set(formulas)
            assert len(formulas) == len(unique), (
                f"Duplicates found at complexity {n}: {len(formulas)} vs {len(unique)} unique"
            )

    def test_all_pass_validate_json(self) -> None:
        """All enumerated formulas produce valid FormulaJson."""
        atoms = ["p", "q"]
        for n in range(1, 5):
            for f in enumerate_by_complexity(n, atoms):
                assert validate_formula_json(f.to_json()), (
                    f"Formula {f} at complexity {n} failed validation"
                )

    def test_deterministic_order(self) -> None:
        """Same call twice produces same order."""
        formulas1 = list(enumerate_by_complexity(3, ["p", "q"]))
        formulas2 = list(enumerate_by_complexity(3, ["p", "q"]))
        assert formulas1 == formulas2

    def test_is_lazy_iterator(self) -> None:
        """enumerate_by_complexity returns an iterator (generator), not a list."""
        result = enumerate_by_complexity(3, ["p", "q"])
        # Check it's an iterator
        assert hasattr(result, "__next__")


class TestEnumerateUpToComplexity:
    def test_up_to_2_two_atoms(self) -> None:
        """up_to=2 yields all formulas with complexity 1 and 2."""
        formulas = list(enumerate_up_to_complexity(2, ["p", "q"]))
        # complexity 1: 3, complexity 2: 3 -> total 6
        assert len(formulas) == 6

    def test_up_to_1_yields_leaves(self) -> None:
        """up_to=1 yields only leaves."""
        formulas = list(enumerate_up_to_complexity(1, ["p", "q"]))
        assert len(formulas) == 3

    def test_ascending_complexity_order(self) -> None:
        """Formulas are yielded in ascending complexity order."""
        formulas = list(enumerate_up_to_complexity(3, ["p"]))
        complexities = [complexity(f) for f in formulas]
        # Check non-decreasing
        for i in range(1, len(complexities)):
            assert complexities[i] >= complexities[i - 1], (
                f"Complexity decreased at index {i}: {complexities[i-1]} -> {complexities[i]}"
            )

    def test_count_matches_sum(self) -> None:
        """Total count matches sum of individual complexities."""
        atoms = ["p", "q"]
        total = list(enumerate_up_to_complexity(4, atoms))
        individual_total = sum(
            len(list(enumerate_by_complexity(n, atoms))) for n in range(1, 5)
        )
        assert len(total) == individual_total


# ---------------------------------------------------------------------------
# count_formulas helper
# ---------------------------------------------------------------------------


class TestCountFormulas:
    def test_complexity_0(self) -> None:
        assert count_formulas(0, 2) == 0

    def test_complexity_1_two_atoms(self) -> None:
        # Bot + 2 atoms
        assert count_formulas(1, 2) == 3

    def test_complexity_1_zero_atoms(self) -> None:
        # Bot only
        assert count_formulas(1, 0) == 1

    def test_complexity_2_two_atoms(self) -> None:
        # 3 box formulas
        assert count_formulas(2, 2) == 3

    def test_complexity_3_two_atoms(self) -> None:
        assert count_formulas(3, 2) == 30

    def test_matches_actual_enumeration(self) -> None:
        """count_formulas matches len(list(enumerate_by_complexity(...)))."""
        for n in range(1, 5):
            for num_atoms in range(1, 4):
                atoms = [chr(ord("p") + i) for i in range(num_atoms)]
                actual = len(list(enumerate_by_complexity(n, atoms)))
                predicted = count_formulas(n, num_atoms)
                assert actual == predicted, (
                    f"n={n}, num_atoms={num_atoms}: "
                    f"actual={actual}, predicted={predicted}"
                )


# ---------------------------------------------------------------------------
# Random generator
# ---------------------------------------------------------------------------


class TestRandomFormula:
    def test_returns_formula_node(self) -> None:
        rng = random.Random(42)
        f = random_formula(5, ["p", "q"], rng)
        assert f is not None
        assert validate_formula_json(f.to_json())

    def test_respects_complexity_budget(self) -> None:
        """random_formula always returns formulas with complexity <= max_complexity."""
        rng = random.Random(0)
        atoms = ["p", "q", "r"]
        for max_c in [1, 2, 3, 5, 8]:
            for _ in range(100):
                f = random_formula(max_c, atoms, rng)
                c = complexity(f)
                assert c <= max_c, (
                    f"Formula {f} has complexity {c} > max_complexity {max_c}"
                )

    def test_complexity_1_always_leaf(self) -> None:
        """With max_complexity=1, always produces a leaf."""
        rng = random.Random(7)
        atoms = ["p", "q"]
        for _ in range(50):
            f = random_formula(1, atoms, rng)
            assert isinstance(f, (Atom, Bot))

    def test_all_pass_validate_json(self) -> None:
        """1000 random formulas all pass schema validation."""
        rng = random.Random(123)
        atoms = ["p", "q", "r"]
        for _ in range(1000):
            f = random_formula(8, atoms, rng)
            assert validate_formula_json(f.to_json()), f"Validation failed for {f}"

    def test_custom_op_weights(self) -> None:
        """Custom op_weights are accepted without error."""
        rng = random.Random(42)
        f = random_formula(6, ["p"], rng, op_weights={"imp": 5.0, "box": 0.5})
        assert validate_formula_json(f.to_json())

    def test_empty_atoms_raises(self) -> None:
        rng = random.Random(0)
        with pytest.raises(ValueError, match="atoms"):
            random_formula(5, [], rng)

    def test_invalid_max_complexity_raises(self) -> None:
        rng = random.Random(0)
        with pytest.raises(ValueError, match="max_complexity"):
            random_formula(0, ["p"], rng)

    def test_operator_diversity_at_high_complexity(self) -> None:
        """High complexity allows all operator types to appear."""
        rng = random.Random(999)
        atoms = ["p", "q", "r"]
        seen_types: set[str] = set()
        for _ in range(500):
            f = random_formula(10, atoms, rng)
            # Check top-level type
            seen_types.add(type(f).__name__)

        # Should see a variety of types given 500 samples
        assert "Bot" in seen_types or "Atom" in seen_types, "Should see some leaves"
        # With 500 samples we expect to see multiple operator types
        assert len(seen_types) >= 3, f"Expected at least 3 op types, got {seen_types}"

    def test_reproducibility(self) -> None:
        """Same seed produces same formula."""
        atoms = ["p", "q"]
        f1 = random_formula(6, atoms, random.Random(42))
        f2 = random_formula(6, atoms, random.Random(42))
        assert f1 == f2
