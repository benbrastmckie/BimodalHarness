"""Integration tests for bimodal_harness.formula package.

Cross-module tests verifying:
- Round-trip serialization for random formulas
- Random generate -> mutate -> validate pipeline
- Enumeration count/validity at complexity 4
- Public API export completeness
- formula_json_to_pretty compatibility
"""

from __future__ import annotations

import random

from bimodal_harness.formula import (
    Atom,
    Bot,
    Box,
    FormulaNode,
    Imp,
    Snce,
    Untl,
    complexity,
    count_formulas,
    enumerate_by_complexity,
    from_json,
    generate_contrastive_pair,
    imp_count,
    modal_depth,
    mutate,
    random_formula,
    temporal_depth,
    top_operator,
)
from bimodal_harness.schema.formula import formula_json_to_pretty, validate_formula_json


# ---------------------------------------------------------------------------
# Public API completeness
# ---------------------------------------------------------------------------


class TestPublicAPI:
    def test_all_ast_types_exported(self) -> None:
        """All 6 AST types are importable from the package root."""
        assert Atom is not None
        assert Bot is not None
        assert Imp is not None
        assert Box is not None
        assert Untl is not None
        assert Snce is not None
        assert FormulaNode is not None

    def test_serialization_exported(self) -> None:
        """from_json is importable from package root."""
        assert from_json is not None

    def test_metrics_exported(self) -> None:
        """All metric functions are importable from package root."""
        assert complexity is not None
        assert modal_depth is not None
        assert temporal_depth is not None
        assert imp_count is not None
        assert top_operator is not None

    def test_generators_exported(self) -> None:
        """All generator functions are importable from package root."""
        assert enumerate_by_complexity is not None
        assert random_formula is not None
        assert count_formulas is not None

    def test_mutators_exported(self) -> None:
        """Mutation functions are importable from package root."""
        assert mutate is not None
        assert generate_contrastive_pair is not None


# ---------------------------------------------------------------------------
# Round-trip serialization
# ---------------------------------------------------------------------------


class TestRoundTrip:
    def test_all_constructor_types(self) -> None:
        """from_json(to_json(f)) == f for all constructor types."""
        nodes = [
            Atom("p"),
            Bot(),
            Imp(Atom("p"), Bot()),
            Box(Atom("q")),
            Untl(Atom("p"), Atom("q")),
            Snce(Atom("p"), Bot()),
        ]
        for node in nodes:
            assert from_json(node.to_json()) == node

    def test_100_random_formulas(self) -> None:
        """from_json(to_json(f)) == f for 100 random formulas."""
        rng = random.Random(42)
        atoms = ["p", "q", "r"]
        for _ in range(100):
            f = random_formula(10, atoms, rng)
            assert from_json(f.to_json()) == f, f"Round-trip failed for {f}"

    def test_nested_formula(self) -> None:
        """Deeply nested formulas round-trip correctly."""
        f = Imp(Box(Untl(Atom("p"), Snce(Atom("q"), Bot()))), Imp(Atom("r"), Box(Bot())))
        assert from_json(f.to_json()) == f


# ---------------------------------------------------------------------------
# Generate -> mutate -> validate pipeline
# ---------------------------------------------------------------------------


class TestGenerateMutatePipeline:
    def test_100_generate_mutate_validate(self) -> None:
        """Generate N random formulas, mutate each, verify both pass schema validation."""
        rng = random.Random(0)
        atoms = ["p", "q", "r"]
        for _ in range(100):
            f = random_formula(8, atoms, rng)
            assert validate_formula_json(f.to_json()), f"Original failed validation: {f}"
            if complexity(f) >= 2:
                original, mutant = generate_contrastive_pair(f, rng)
                assert validate_formula_json(original.to_json()), (
                    f"Original failed validation: {original}"
                )
                assert validate_formula_json(mutant.to_json()), (
                    f"Mutant failed validation: {mutant}"
                )

    def test_contrastive_pairs_are_distinct(self) -> None:
        """Most contrastive pairs should have distinct formulas."""
        rng = random.Random(123)
        atoms = ["p", "q", "r"]
        distinct_count = 0
        total = 0
        for _ in range(100):
            f = random_formula(8, atoms, rng)
            if complexity(f) >= 2:
                original, mutant = generate_contrastive_pair(f, rng)
                total += 1
                if original != mutant:
                    distinct_count += 1

        # Most pairs should differ
        assert distinct_count >= total * 0.8, (
            f"Only {distinct_count}/{total} pairs were distinct"
        )


# ---------------------------------------------------------------------------
# Enumeration at complexity 4
# ---------------------------------------------------------------------------


class TestEnumerationComplexity4:
    def test_count_matches_expected(self) -> None:
        """enumerate_by_complexity(4, 2_atoms) has count matching count_formulas(4, 2)."""
        atoms = ["p", "q"]
        formulas = list(enumerate_by_complexity(4, atoms))
        expected = count_formulas(4, 2)
        assert len(formulas) == expected

    def test_all_have_complexity_4(self) -> None:
        """All enumerated formulas have exactly complexity 4."""
        atoms = ["p", "q"]
        for f in enumerate_by_complexity(4, atoms):
            c = complexity(f)
            assert c == 4, f"Formula {f} has complexity {c}, expected 4"

    def test_all_pass_validation(self) -> None:
        """All enumerated formulas pass schema validation."""
        atoms = ["p", "q"]
        for f in enumerate_by_complexity(4, atoms):
            assert validate_formula_json(f.to_json()), f"Validation failed for {f}"


# ---------------------------------------------------------------------------
# formula_json_to_pretty compatibility
# ---------------------------------------------------------------------------


class TestPrettyPrint:
    def test_basic_formulas(self) -> None:
        """formula_json_to_pretty produces non-empty strings for all basic types."""
        nodes = [
            Atom("p"),
            Bot(),
            Imp(Atom("p"), Bot()),
            Box(Atom("q")),
            Untl(Atom("p"), Atom("q")),
            Snce(Atom("p"), Bot()),
        ]
        for node in nodes:
            pretty = formula_json_to_pretty(node.to_json())
            assert isinstance(pretty, str)
            assert len(pretty) > 0, f"Empty pretty string for {node}"

    def test_atom_pretty(self) -> None:
        assert formula_json_to_pretty(Atom("p").to_json()) == "p"

    def test_bot_pretty(self) -> None:
        assert formula_json_to_pretty(Bot().to_json()) == "⊥"

    def test_imp_pretty(self) -> None:
        f = Imp(Atom("p"), Atom("q"))
        assert formula_json_to_pretty(f.to_json()) == "(p → q)"

    def test_box_pretty(self) -> None:
        f = Box(Atom("p"))
        assert formula_json_to_pretty(f.to_json()) == "□p"

    def test_untl_pretty(self) -> None:
        f = Untl(Atom("p"), Atom("q"))
        assert formula_json_to_pretty(f.to_json()) == "U(p, q)"

    def test_snce_pretty(self) -> None:
        f = Snce(Atom("p"), Atom("q"))
        assert formula_json_to_pretty(f.to_json()) == "S(p, q)"

    def test_random_formulas_render(self) -> None:
        """100 random formulas all render to non-empty strings."""
        rng = random.Random(99)
        atoms = ["p", "q", "r"]
        for _ in range(100):
            f = random_formula(8, atoms, rng)
            pretty = formula_json_to_pretty(f.to_json())
            assert isinstance(pretty, str) and len(pretty) > 0, (
                f"Empty pretty string for {f}"
            )
