"""Tests for bimodal_harness.schema.features.

Covers all 7 plan test vectors, all 6 formula constructors, edge cases,
and error conditions for extract_pattern_key and extract_atom_count.

Note on complexity values:
  The research report test vectors (01_patternkey-extractor.md) listed
  incorrect complexity values for vectors 4 and 5.  The correct values,
  matching the Lean Formula.complexity definition exactly, are used here:
  - imp(box(p), box(q)):   complexity = 5 (not 4 as listed in report)
  - untl(untl(p,q), r):   complexity = 5 (not 4 as listed in report)
"""

from __future__ import annotations

import pytest

from bimodal_harness.schema.features import extract_atom_count, extract_pattern_key
from bimodal_harness.schema.records import PatternKey

# ---------------------------------------------------------------------------
# Formula builders (helpers for readability)
# ---------------------------------------------------------------------------

_ATOM_P = {"tag": "atom", "name": "p"}
_ATOM_Q = {"tag": "atom", "name": "q"}
_ATOM_R = {"tag": "atom", "name": "r"}
_BOT = {"tag": "bot"}


def _box(child: dict) -> dict:
    return {"tag": "box", "child": child}


def _imp(left: dict, right: dict) -> dict:
    return {"tag": "imp", "left": left, "right": right}


def _untl(event: dict, guard: dict) -> dict:
    return {"tag": "untl", "event": event, "guard": guard}


def _snce(event: dict, guard: dict) -> dict:
    return {"tag": "snce", "event": event, "guard": guard}


# ---------------------------------------------------------------------------
# TestExtractPatternKeyBasicConstructors
# ---------------------------------------------------------------------------


class TestExtractPatternKeyBasicConstructors:
    """Test each of the 6 formula constructors in isolation."""

    def test_atom(self) -> None:
        """atom -> (modal=0, temporal=0, imp=0, complexity=1, Atom)."""
        pk = extract_pattern_key(_ATOM_P)
        assert pk == PatternKey(
            modal_depth=0,
            temporal_depth=0,
            imp_count=0,
            complexity=1,
            top_operator="Atom",
        )

    def test_bot(self) -> None:
        """bot -> (modal=0, temporal=0, imp=0, complexity=1, Bottom)."""
        pk = extract_pattern_key(_BOT)
        assert pk == PatternKey(
            modal_depth=0,
            temporal_depth=0,
            imp_count=0,
            complexity=1,
            top_operator="Bottom",
        )

    def test_box_of_atom(self) -> None:
        """box(atom) -> (modal=1, temporal=0, imp=0, complexity=2, Box).

        Test vector 3 from research report.
        """
        pk = extract_pattern_key(_box(_ATOM_P))
        assert pk == PatternKey(
            modal_depth=1,
            temporal_depth=0,
            imp_count=0,
            complexity=2,
            top_operator="Box",
        )

    def test_imp_of_atoms(self) -> None:
        """imp(atom, atom) -> (modal=0, temporal=0, imp=1, complexity=3, Implication)."""
        pk = extract_pattern_key(_imp(_ATOM_P, _ATOM_Q))
        assert pk == PatternKey(
            modal_depth=0,
            temporal_depth=0,
            imp_count=1,
            complexity=3,
            top_operator="Implication",
        )

    def test_untl_of_atoms(self) -> None:
        """untl(atom, atom) -> (modal=0, temporal=1, imp=0, complexity=3, Until)."""
        pk = extract_pattern_key(_untl(_ATOM_P, _ATOM_Q))
        assert pk == PatternKey(
            modal_depth=0,
            temporal_depth=1,
            imp_count=0,
            complexity=3,
            top_operator="Until",
        )

    def test_snce_of_atoms(self) -> None:
        """snce(atom, atom) -> (modal=0, temporal=1, imp=0, complexity=3, Since)."""
        pk = extract_pattern_key(_snce(_ATOM_P, _ATOM_Q))
        assert pk == PatternKey(
            modal_depth=0,
            temporal_depth=1,
            imp_count=0,
            complexity=3,
            top_operator="Since",
        )


# ---------------------------------------------------------------------------
# TestExtractPatternKeyPlanVectors
# ---------------------------------------------------------------------------


class TestExtractPatternKeyPlanVectors:
    """Test the 7 test vectors from the implementation plan.

    Note: plan listed complexity=4 for vectors 4 and 5.  The correct values
    per Lean Formula.complexity are 5; these tests use the correct values.
    """

    def test_vector_1_atom(self) -> None:
        """atom(p) -> (0, 0, 0, 1, "Atom")."""
        pk = extract_pattern_key(_ATOM_P)
        assert pk.modal_depth == 0
        assert pk.temporal_depth == 0
        assert pk.imp_count == 0
        assert pk.complexity == 1
        assert pk.top_operator == "Atom"

    def test_vector_2_bot(self) -> None:
        """bot -> (0, 0, 0, 1, "Bottom")."""
        pk = extract_pattern_key(_BOT)
        assert pk.modal_depth == 0
        assert pk.temporal_depth == 0
        assert pk.imp_count == 0
        assert pk.complexity == 1
        assert pk.top_operator == "Bottom"

    def test_vector_3_box_atom(self) -> None:
        """box(atom(p)) -> (1, 0, 0, 2, "Box")."""
        pk = extract_pattern_key(_box(_ATOM_P))
        assert pk.modal_depth == 1
        assert pk.temporal_depth == 0
        assert pk.imp_count == 0
        assert pk.complexity == 2
        assert pk.top_operator == "Box"

    def test_vector_4_imp_box_box(self) -> None:
        """imp(box(p), box(q)) -> (1, 0, 1, 5, "Implication").

        Note: research report listed complexity=4; correct value is 5.
        imp complexity: 1 + box(p).complexity + box(q).complexity = 1 + 2 + 2 = 5.
        """
        pk = extract_pattern_key(_imp(_box(_ATOM_P), _box(_ATOM_Q)))
        assert pk.modal_depth == 1
        assert pk.temporal_depth == 0
        assert pk.imp_count == 1
        assert pk.complexity == 5  # 1 + (1+1) + (1+1) = 5
        assert pk.top_operator == "Implication"

    def test_vector_5_untl_untl(self) -> None:
        """untl(untl(p, q), r) -> (0, 2, 0, 5, "Until").

        Note: research report listed complexity=4; correct value is 5.
        outer untl complexity: 1 + inner_untl.complexity + r.complexity = 1 + 3 + 1 = 5.
        """
        pk = extract_pattern_key(_untl(_untl(_ATOM_P, _ATOM_Q), _ATOM_R))
        assert pk.modal_depth == 0
        assert pk.temporal_depth == 2
        assert pk.imp_count == 0
        assert pk.complexity == 5  # 1 + (1+1+1) + 1 = 5
        assert pk.top_operator == "Until"

    def test_vector_6_box_untl(self) -> None:
        """box(untl(p, q)) -> (1, 1, 0, 4, "Box")."""
        pk = extract_pattern_key(_box(_untl(_ATOM_P, _ATOM_Q)))
        assert pk.modal_depth == 1
        assert pk.temporal_depth == 1
        assert pk.imp_count == 0
        assert pk.complexity == 4  # 1 + (1+1+1) = 4
        assert pk.top_operator == "Box"

    def test_vector_7_box_box_atom(self) -> None:
        """box(box(atom)) -> (2, 0, 0, 3, "Box")."""
        pk = extract_pattern_key(_box(_box(_ATOM_P)))
        assert pk.modal_depth == 2
        assert pk.temporal_depth == 0
        assert pk.imp_count == 0
        assert pk.complexity == 3  # 1 + (1+1) = 3
        assert pk.top_operator == "Box"


# ---------------------------------------------------------------------------
# TestTemporalDepthBoxPassThrough
# ---------------------------------------------------------------------------


class TestTemporalDepthBoxPassThrough:
    """Verify that box does NOT increment temporal depth."""

    def test_box_of_untl_temporal_depth_is_1(self) -> None:
        """box(untl(p, q)) must have temporal_depth=1, not 2.

        box passes through: temporal_depth(box(phi)) = temporal_depth(phi).
        """
        pk = extract_pattern_key(_box(_untl(_ATOM_P, _ATOM_Q)))
        assert pk.temporal_depth == 1

    def test_box_of_atom_temporal_depth_is_0(self) -> None:
        """box(atom) has temporal_depth=0 (box passes through to atom's 0)."""
        pk = extract_pattern_key(_box(_ATOM_P))
        assert pk.temporal_depth == 0

    def test_nested_box_around_untl_passes_through(self) -> None:
        """box(box(untl(p,q))) has temporal_depth=1 (two boxes, still passes through)."""
        pk = extract_pattern_key(_box(_box(_untl(_ATOM_P, _ATOM_Q))))
        assert pk.temporal_depth == 1

    def test_modal_depth_of_box_does_increment(self) -> None:
        """Confirm box DOES increment modal_depth (contrast with temporal passthrough)."""
        pk_box_untl = extract_pattern_key(_box(_untl(_ATOM_P, _ATOM_Q)))
        assert pk_box_untl.modal_depth == 1  # box adds 1
        assert pk_box_untl.temporal_depth == 1  # box passes through


# ---------------------------------------------------------------------------
# TestImpCountAccumulation
# ---------------------------------------------------------------------------


class TestImpCountAccumulation:
    """Test imp_count accumulates correctly through all operator types."""

    def test_imp_through_box(self) -> None:
        """box(imp(p,q)) has imp_count=1 (box propagates imp_count)."""
        pk = extract_pattern_key(_box(_imp(_ATOM_P, _ATOM_Q)))
        assert pk.imp_count == 1

    def test_imp_through_untl(self) -> None:
        """untl(imp(p,q), r) has imp_count=1."""
        pk = extract_pattern_key(_untl(_imp(_ATOM_P, _ATOM_Q), _ATOM_R))
        assert pk.imp_count == 1

    def test_nested_imps(self) -> None:
        """imp(imp(p,q), r) has imp_count=2."""
        pk = extract_pattern_key(_imp(_imp(_ATOM_P, _ATOM_Q), _ATOM_R))
        assert pk.imp_count == 2

    def test_imp_through_snce(self) -> None:
        """snce(imp(p,q), imp(q,r)) has imp_count=2."""
        pk = extract_pattern_key(_snce(_imp(_ATOM_P, _ATOM_Q), _imp(_ATOM_Q, _ATOM_R)))
        assert pk.imp_count == 2


# ---------------------------------------------------------------------------
# TestSnceConstructor
# ---------------------------------------------------------------------------


class TestSnceConstructor:
    """Test the snce (Since) constructor produces correct features."""

    def test_snce_goal_category_is_since(self) -> None:
        """snce at top level -> top_operator="Since"."""
        pk = extract_pattern_key(_snce(_ATOM_P, _ATOM_Q))
        assert pk.top_operator == "Since"

    def test_snce_increments_temporal_depth(self) -> None:
        """snce increments temporal_depth just like untl."""
        pk = extract_pattern_key(_snce(_ATOM_P, _ATOM_Q))
        assert pk.temporal_depth == 1

    def test_nested_snce_temporal_depth(self) -> None:
        """snce(snce(p,q), r) has temporal_depth=2."""
        pk = extract_pattern_key(_snce(_snce(_ATOM_P, _ATOM_Q), _ATOM_R))
        assert pk.temporal_depth == 2

    def test_mixed_untl_snce_temporal_depth(self) -> None:
        """untl(snce(p,q), r) has temporal_depth=2 (nested temporal ops)."""
        pk = extract_pattern_key(_untl(_snce(_ATOM_P, _ATOM_Q), _ATOM_R))
        assert pk.temporal_depth == 2


# ---------------------------------------------------------------------------
# TestMixedFormulas
# ---------------------------------------------------------------------------


class TestMixedFormulas:
    """Test formulas combining box and temporal operators at different branches."""

    def test_imp_box_branch_and_untl_branch(self) -> None:
        """imp(box(p), untl(p,q)) has modal=1, temporal=1, imp=1."""
        f = _imp(_box(_ATOM_P), _untl(_ATOM_P, _ATOM_Q))
        pk = extract_pattern_key(f)
        assert pk.modal_depth == 1   # from box branch
        assert pk.temporal_depth == 1  # from untl branch
        assert pk.imp_count == 1
        assert pk.top_operator == "Implication"

    def test_box_of_imp_with_temporal(self) -> None:
        """box(imp(untl(p,q), r)) has modal=1, temporal=1."""
        f = _box(_imp(_untl(_ATOM_P, _ATOM_Q), _ATOM_R))
        pk = extract_pattern_key(f)
        assert pk.modal_depth == 1
        assert pk.temporal_depth == 1
        assert pk.imp_count == 1
        assert pk.top_operator == "Box"

    def test_deep_nesting_counts(self) -> None:
        """box(box(imp(untl(p,q), box(snce(q,r))))) -- deep mixed formula."""
        # Structure: box(box(imp(untl(p,q), box(snce(q,r)))))
        # modal_depth: box -> box -> max(untl->0, box->1+snce->0=1) -> 2+1 = no...
        # Let's compute step by step:
        # snce(q,r): modal=0, temporal=1
        # box(snce(q,r)): modal=1, temporal=1 (box passes temporal through)
        # untl(p,q): modal=0, temporal=1
        # imp(untl(p,q), box(snce(q,r))): modal=max(0,1)=1, temporal=max(1,1)=1
        # box(imp(...)): modal=1+1=2, temporal=1 (box passes temporal through)
        # box(box(imp(...))): modal=1+2=3, temporal=1 (box passes temporal through)
        f = _box(_box(_imp(_untl(_ATOM_P, _ATOM_Q), _box(_snce(_ATOM_Q, _ATOM_R)))))
        pk = extract_pattern_key(f)
        assert pk.modal_depth == 3
        assert pk.temporal_depth == 1
        assert pk.imp_count == 1
        assert pk.top_operator == "Box"


# ---------------------------------------------------------------------------
# TestExtractAtomCount
# ---------------------------------------------------------------------------


class TestExtractAtomCount:
    """Test extract_atom_count with various formulas."""

    def test_single_atom(self) -> None:
        """Single atom -> count 1."""
        assert extract_atom_count(_ATOM_P) == 1

    def test_bot_has_no_atoms(self) -> None:
        """bot -> count 0."""
        assert extract_atom_count(_BOT) == 0

    def test_duplicate_atoms_deduplicated(self) -> None:
        """imp(p, p) -> count 1 (p appears twice but is one distinct atom)."""
        assert extract_atom_count(_imp(_ATOM_P, _ATOM_P)) == 1

    def test_distinct_atoms(self) -> None:
        """imp(p, q) -> count 2 (two distinct atoms)."""
        assert extract_atom_count(_imp(_ATOM_P, _ATOM_Q)) == 2

    def test_three_distinct_atoms(self) -> None:
        """untl(imp(p,q), r) -> count 3."""
        f = _untl(_imp(_ATOM_P, _ATOM_Q), _ATOM_R)
        assert extract_atom_count(f) == 3

    def test_deep_formula_deduplicates(self) -> None:
        """Deep formula with repeated atoms deduplicates correctly."""
        # untl(untl(p,p), imp(q,q)) has atoms p, q -> count 2
        f = _untl(_untl(_ATOM_P, _ATOM_P), _imp(_ATOM_Q, _ATOM_Q))
        assert extract_atom_count(f) == 2

    def test_box_passes_atoms_through(self) -> None:
        """box(imp(p, q)) -> count 2."""
        assert extract_atom_count(_box(_imp(_ATOM_P, _ATOM_Q))) == 2


# ---------------------------------------------------------------------------
# TestErrorHandling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Test that invalid formula tags raise ValueError."""

    def test_unrecognized_tag_raises_value_error(self) -> None:
        """Unrecognized formula tag raises ValueError with descriptive message."""
        with pytest.raises(ValueError, match="Unrecognized formula tag"):
            extract_pattern_key({"tag": "unknown_tag"})

    def test_unrecognized_tag_in_child_raises(self) -> None:
        """Unrecognized tag inside a valid outer formula raises ValueError."""
        with pytest.raises(ValueError, match="Unrecognized formula tag"):
            extract_pattern_key(_box({"tag": "and", "left": _ATOM_P, "right": _ATOM_Q}))

    def test_missing_tag_raises_value_error(self) -> None:
        """Dict without 'tag' key raises ValueError."""
        with pytest.raises(ValueError):
            extract_pattern_key({"name": "p"})

    def test_atom_count_unrecognized_tag_raises(self) -> None:
        """extract_atom_count also raises on unrecognized tags."""
        with pytest.raises(ValueError, match="Unrecognized formula tag"):
            extract_atom_count({"tag": "bad"})


# ---------------------------------------------------------------------------
# TestDuckTypingFallback
# ---------------------------------------------------------------------------


class TestDuckTypingFallback:
    """Test that objects with .tag attribute work alongside dicts."""

    def test_object_with_tag_attribute_atom(self) -> None:
        """An object with tag='atom' and name='p' works via duck-typing."""

        class FakeAtom:
            tag = "atom"
            name = "p"

        # _get_tag picks up .tag; _complexity for atom uses 'tag' and nothing else
        # for atom: no child access needed — just tag check
        # This tests the duck-typing path of _get_tag
        # Note: the full traversal would need the dict children for imp/box/etc.
        # For atom (leaf), only tag is needed.
        obj = FakeAtom()
        pk = extract_pattern_key(obj)  # type: ignore[arg-type]
        assert pk.top_operator == "Atom"
        assert pk.complexity == 1
        assert pk.modal_depth == 0

    def test_non_dict_non_tag_raises(self) -> None:
        """Object without tag attribute or dict key raises ValueError."""
        with pytest.raises(ValueError):
            extract_pattern_key(object())  # type: ignore[arg-type]
