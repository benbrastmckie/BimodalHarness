"""Tests for bimodal_harness.formula.ast module.

Covers:
- Construction and equality of all 6 formula types
- Hashing (frozenness)
- to_json / from_json round-trip for all types
- Compatibility with schema validate_formula_json
- Metric functions against hand-computed values
"""

from __future__ import annotations

import pytest

from bimodal_harness.formula.ast import (
    Atom,
    Bot,
    Box,
    Imp,
    Snce,
    Untl,
    complexity,
    from_json,
    imp_count,
    modal_depth,
    temporal_depth,
    top_operator,
)
from bimodal_harness.schema.formula import validate_formula_json


# ---------------------------------------------------------------------------
# Construction and equality
# ---------------------------------------------------------------------------


class TestAtom:
    def test_construction(self) -> None:
        a = Atom("p")
        assert a.name == "p"

    def test_equality(self) -> None:
        assert Atom("p") == Atom("p")
        assert Atom("p") != Atom("q")

    def test_hashable(self) -> None:
        s = {Atom("p"), Atom("p"), Atom("q")}
        assert len(s) == 2

    def test_to_json(self) -> None:
        assert Atom("p").to_json() == {"tag": "atom", "name": "p"}

    def test_from_json(self) -> None:
        assert Atom.from_json({"tag": "atom", "name": "p"}) == Atom("p")

    def test_from_json_wrong_tag(self) -> None:
        with pytest.raises(ValueError, match="atom"):
            Atom.from_json({"tag": "bot"})

    def test_round_trip(self) -> None:
        node = Atom("hello")
        assert from_json(node.to_json()) == node

    def test_validate_json(self) -> None:
        assert validate_formula_json(Atom("p").to_json())


class TestBot:
    def test_construction(self) -> None:
        b = Bot()
        assert isinstance(b, Bot)

    def test_equality(self) -> None:
        assert Bot() == Bot()

    def test_hashable(self) -> None:
        s = {Bot(), Bot()}
        assert len(s) == 1

    def test_to_json(self) -> None:
        assert Bot().to_json() == {"tag": "bot"}

    def test_from_json(self) -> None:
        assert Bot.from_json({"tag": "bot"}) == Bot()

    def test_from_json_wrong_tag(self) -> None:
        with pytest.raises(ValueError, match="bot"):
            Bot.from_json({"tag": "atom", "name": "p"})

    def test_round_trip(self) -> None:
        node = Bot()
        assert from_json(node.to_json()) == node

    def test_validate_json(self) -> None:
        assert validate_formula_json(Bot().to_json())


class TestImp:
    def test_construction(self) -> None:
        node = Imp(Atom("p"), Bot())
        assert node.left == Atom("p")
        assert node.right == Bot()

    def test_equality(self) -> None:
        assert Imp(Atom("p"), Bot()) == Imp(Atom("p"), Bot())
        assert Imp(Atom("p"), Bot()) != Imp(Bot(), Atom("p"))

    def test_hashable(self) -> None:
        s = {Imp(Atom("p"), Bot()), Imp(Atom("p"), Bot())}
        assert len(s) == 1

    def test_to_json(self) -> None:
        j = Imp(Atom("p"), Bot()).to_json()
        assert j == {"tag": "imp", "left": {"tag": "atom", "name": "p"}, "right": {"tag": "bot"}}

    def test_from_json(self) -> None:
        j = {"tag": "imp", "left": {"tag": "atom", "name": "p"}, "right": {"tag": "bot"}}
        assert Imp.from_json(j) == Imp(Atom("p"), Bot())

    def test_from_json_wrong_tag(self) -> None:
        with pytest.raises(ValueError, match="imp"):
            Imp.from_json({"tag": "box", "child": {"tag": "bot"}})

    def test_round_trip(self) -> None:
        node = Imp(Box(Atom("p")), Bot())
        assert from_json(node.to_json()) == node

    def test_validate_json(self) -> None:
        assert validate_formula_json(Imp(Atom("p"), Bot()).to_json())


class TestBox:
    def test_construction(self) -> None:
        node = Box(Atom("p"))
        assert node.child == Atom("p")

    def test_equality(self) -> None:
        assert Box(Atom("p")) == Box(Atom("p"))
        assert Box(Atom("p")) != Box(Bot())

    def test_hashable(self) -> None:
        s = {Box(Atom("p")), Box(Atom("p")), Box(Bot())}
        assert len(s) == 2

    def test_to_json(self) -> None:
        j = Box(Atom("p")).to_json()
        assert j == {"tag": "box", "child": {"tag": "atom", "name": "p"}}

    def test_from_json(self) -> None:
        j = {"tag": "box", "child": {"tag": "atom", "name": "p"}}
        assert Box.from_json(j) == Box(Atom("p"))

    def test_from_json_wrong_tag(self) -> None:
        with pytest.raises(ValueError, match="box"):
            Box.from_json({"tag": "atom", "name": "p"})

    def test_round_trip(self) -> None:
        node = Box(Box(Atom("q")))
        assert from_json(node.to_json()) == node

    def test_validate_json(self) -> None:
        assert validate_formula_json(Box(Atom("p")).to_json())


class TestUntl:
    def test_construction(self) -> None:
        node = Untl(Atom("p"), Atom("q"))
        assert node.event == Atom("p")
        assert node.guard == Atom("q")

    def test_equality(self) -> None:
        assert Untl(Atom("p"), Atom("q")) == Untl(Atom("p"), Atom("q"))
        assert Untl(Atom("p"), Atom("q")) != Untl(Atom("q"), Atom("p"))

    def test_hashable(self) -> None:
        s = {Untl(Atom("p"), Atom("q")), Untl(Atom("p"), Atom("q"))}
        assert len(s) == 1

    def test_to_json(self) -> None:
        j = Untl(Atom("p"), Bot()).to_json()
        assert j == {
            "tag": "untl",
            "event": {"tag": "atom", "name": "p"},
            "guard": {"tag": "bot"},
        }

    def test_from_json(self) -> None:
        j = {"tag": "untl", "event": {"tag": "atom", "name": "p"}, "guard": {"tag": "bot"}}
        assert Untl.from_json(j) == Untl(Atom("p"), Bot())

    def test_from_json_wrong_tag(self) -> None:
        with pytest.raises(ValueError, match="untl"):
            Untl.from_json({"tag": "snce", "event": {"tag": "bot"}, "guard": {"tag": "bot"}})

    def test_round_trip(self) -> None:
        node = Untl(Box(Atom("p")), Atom("q"))
        assert from_json(node.to_json()) == node

    def test_validate_json(self) -> None:
        assert validate_formula_json(Untl(Atom("p"), Bot()).to_json())


class TestSnce:
    def test_construction(self) -> None:
        node = Snce(Atom("p"), Atom("q"))
        assert node.event == Atom("p")
        assert node.guard == Atom("q")

    def test_equality(self) -> None:
        assert Snce(Atom("p"), Atom("q")) == Snce(Atom("p"), Atom("q"))
        assert Snce(Atom("p"), Atom("q")) != Snce(Atom("q"), Atom("p"))

    def test_hashable(self) -> None:
        s = {Snce(Atom("p"), Atom("q")), Snce(Atom("p"), Atom("q"))}
        assert len(s) == 1

    def test_to_json(self) -> None:
        j = Snce(Atom("p"), Bot()).to_json()
        assert j == {
            "tag": "snce",
            "event": {"tag": "atom", "name": "p"},
            "guard": {"tag": "bot"},
        }

    def test_from_json(self) -> None:
        j = {"tag": "snce", "event": {"tag": "atom", "name": "p"}, "guard": {"tag": "bot"}}
        assert Snce.from_json(j) == Snce(Atom("p"), Bot())

    def test_from_json_wrong_tag(self) -> None:
        with pytest.raises(ValueError, match="snce"):
            Snce.from_json({"tag": "untl", "event": {"tag": "bot"}, "guard": {"tag": "bot"}})

    def test_round_trip(self) -> None:
        node = Snce(Atom("q"), Box(Atom("p")))
        assert from_json(node.to_json()) == node

    def test_validate_json(self) -> None:
        assert validate_formula_json(Snce(Atom("p"), Bot()).to_json())


# ---------------------------------------------------------------------------
# from_json dispatch
# ---------------------------------------------------------------------------


class TestFromJson:
    def test_dispatch_atom(self) -> None:
        assert from_json({"tag": "atom", "name": "x"}) == Atom("x")

    def test_dispatch_bot(self) -> None:
        assert from_json({"tag": "bot"}) == Bot()

    def test_dispatch_imp(self) -> None:
        j = {"tag": "imp", "left": {"tag": "bot"}, "right": {"tag": "bot"}}
        assert from_json(j) == Imp(Bot(), Bot())

    def test_dispatch_box(self) -> None:
        j = {"tag": "box", "child": {"tag": "bot"}}
        assert from_json(j) == Box(Bot())

    def test_dispatch_untl(self) -> None:
        j = {"tag": "untl", "event": {"tag": "bot"}, "guard": {"tag": "bot"}}
        assert from_json(j) == Untl(Bot(), Bot())

    def test_dispatch_snce(self) -> None:
        j = {"tag": "snce", "event": {"tag": "bot"}, "guard": {"tag": "bot"}}
        assert from_json(j) == Snce(Bot(), Bot())

    def test_unknown_tag_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown formula tag"):
            from_json({"tag": "neg"})

    def test_non_dict_raises(self) -> None:
        with pytest.raises(ValueError, match="Expected dict"):
            from_json("atom")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Metric functions — verified against Lean definitions
# ---------------------------------------------------------------------------

# Reference formula: imp(atom("p"), box(atom("q")))
# complexity = 1 + 1 + (1 + 1) = 4
# modal_depth = max(0, 1 + 0) = 1
# temporal_depth = max(0, 0) = 0
# imp_count = 1 + 0 + 0 = 1
_REF = Imp(Atom("p"), Box(Atom("q")))


class TestComplexity:
    def test_atom(self) -> None:
        assert complexity(Atom("p")) == 1

    def test_bot(self) -> None:
        assert complexity(Bot()) == 1

    def test_imp(self) -> None:
        # imp(p, q) = 1 + 1 + 1 = 3
        assert complexity(Imp(Atom("p"), Atom("q"))) == 3

    def test_box(self) -> None:
        # box(p) = 1 + 1 = 2
        assert complexity(Box(Atom("p"))) == 2

    def test_untl(self) -> None:
        # untl(p, q) = 1 + 1 + 1 = 3
        assert complexity(Untl(Atom("p"), Atom("q"))) == 3

    def test_snce(self) -> None:
        # snce(p, q) = 1 + 1 + 1 = 3
        assert complexity(Snce(Atom("p"), Atom("q"))) == 3

    def test_reference_formula(self) -> None:
        # imp(atom("p"), box(atom("q"))) = 1 + 1 + (1 + 1) = 4
        assert complexity(_REF) == 4

    def test_nested(self) -> None:
        # imp(imp(p, q), box(bot)) = 1 + (1+1+1) + (1+1) = 6
        f = Imp(Imp(Atom("p"), Atom("q")), Box(Bot()))
        assert complexity(f) == 6


class TestModalDepth:
    def test_atom(self) -> None:
        assert modal_depth(Atom("p")) == 0

    def test_bot(self) -> None:
        assert modal_depth(Bot()) == 0

    def test_box_one(self) -> None:
        assert modal_depth(Box(Atom("p"))) == 1

    def test_box_nested(self) -> None:
        assert modal_depth(Box(Box(Atom("p")))) == 2

    def test_imp_max(self) -> None:
        # imp(box(p), box(q)) = max(1, 1) = 1
        assert modal_depth(Imp(Box(Atom("p")), Box(Atom("q")))) == 1

    def test_reference_formula(self) -> None:
        # imp(atom("p"), box(atom("q"))) = max(0, 1+0) = 1
        assert modal_depth(_REF) == 1

    def test_untl_no_increment(self) -> None:
        # untl(p, q) — temporal, not modal
        assert modal_depth(Untl(Atom("p"), Atom("q"))) == 0

    def test_snce_no_increment(self) -> None:
        assert modal_depth(Snce(Atom("p"), Atom("q"))) == 0


class TestTemporalDepth:
    def test_atom(self) -> None:
        assert temporal_depth(Atom("p")) == 0

    def test_bot(self) -> None:
        assert temporal_depth(Bot()) == 0

    def test_box_passes_through(self) -> None:
        # box does NOT increment temporal depth
        assert temporal_depth(Box(Atom("p"))) == 0
        assert temporal_depth(Box(Untl(Atom("p"), Atom("q")))) == 1

    def test_untl_one(self) -> None:
        assert temporal_depth(Untl(Atom("p"), Atom("q"))) == 1

    def test_snce_one(self) -> None:
        assert temporal_depth(Snce(Atom("p"), Atom("q"))) == 1

    def test_nested_temporal(self) -> None:
        # untl(untl(p, q), r) = 1 + max(1, 0) = 2
        assert temporal_depth(Untl(Untl(Atom("p"), Atom("q")), Atom("r"))) == 2

    def test_reference_formula(self) -> None:
        # imp(atom("p"), box(atom("q"))) = max(0, 0) = 0
        assert temporal_depth(_REF) == 0


class TestImpCount:
    def test_atom(self) -> None:
        assert imp_count(Atom("p")) == 0

    def test_bot(self) -> None:
        assert imp_count(Bot()) == 0

    def test_imp_one(self) -> None:
        assert imp_count(Imp(Atom("p"), Atom("q"))) == 1

    def test_imp_nested(self) -> None:
        # imp(imp(p, q), r) = 1 + 1 + 0 = 2
        assert imp_count(Imp(Imp(Atom("p"), Atom("q")), Atom("r"))) == 2
        # imp(p, imp(q, r)) = 1 + 0 + 1 = 2
        assert imp_count(Imp(Atom("p"), Imp(Atom("q"), Atom("r")))) == 2

    def test_box_transparent(self) -> None:
        assert imp_count(Box(Imp(Atom("p"), Atom("q")))) == 1

    def test_untl_transparent(self) -> None:
        assert imp_count(Untl(Imp(Atom("p"), Atom("q")), Atom("r"))) == 1

    def test_snce_transparent(self) -> None:
        assert imp_count(Snce(Atom("p"), Imp(Atom("q"), Atom("r")))) == 1

    def test_reference_formula(self) -> None:
        # imp(atom("p"), box(atom("q"))) = 1 + 0 + 0 = 1
        assert imp_count(_REF) == 1


# ---------------------------------------------------------------------------
# top_operator
# ---------------------------------------------------------------------------


class TestTopOperator:
    def test_atom(self) -> None:
        assert top_operator(Atom("p")) == "Atom"

    def test_bot(self) -> None:
        assert top_operator(Bot()) == "Bottom"

    def test_imp(self) -> None:
        assert top_operator(Imp(Atom("p"), Bot())) == "Implication"

    def test_box(self) -> None:
        assert top_operator(Box(Atom("p"))) == "Box"

    def test_untl(self) -> None:
        assert top_operator(Untl(Atom("p"), Bot())) == "Until"

    def test_snce(self) -> None:
        assert top_operator(Snce(Atom("p"), Bot())) == "Since"
