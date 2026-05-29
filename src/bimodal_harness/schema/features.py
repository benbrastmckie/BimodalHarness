"""Feature extraction for formula pattern keys.

Ports the five structural feature algorithms from Lean
(Bimodal.Syntax.Formula and Bimodal.Automation.SuccessPatterns) to Python,
operating on the formula JSON tree produced by DataExport.lean.

Public API
----------
- extract_pattern_key(formula_json) -> PatternKey
- extract_atom_count(formula_json) -> int

Lean correspondence
-------------------
- _complexity      : Formula.complexity       (Formula.lean lines 162-168)
- _modal_depth     : Formula.modalDepth       (Formula.lean lines 262-268)
- _temporal_depth  : Formula.temporalDepth    (Formula.lean lines 283-289)
- _imp_count       : Formula.countImplications (Formula.lean lines 303-309)
- _top_operator    : goalCategory             (SuccessPatterns.lean lines 76-83)
- extract_pattern_key : PatternKey.fromFormula (SuccessPatterns.lean lines 115-121)

Formula JSON tags (DataExport.lean Formula.toJson):
- atom  -> {"tag": "atom", "name": "<string>"}
- bot   -> {"tag": "bot"}
- imp   -> {"tag": "imp", "left": <formula>, "right": <formula>}
- box   -> {"tag": "box", "child": <formula>}
- untl  -> {"tag": "untl", "event": <formula>, "guard": <formula>}
- snce  -> {"tag": "snce", "event": <formula>, "guard": <formula>}
"""

from __future__ import annotations

from typing import Any

from bimodal_harness.schema.formula import FormulaJson
from bimodal_harness.schema.records import PatternKey

# Map from formula JSON tag to GoalCategory name.
# Mirrors goalCategory in SuccessPatterns.lean.
_TAG_TO_GOAL_CATEGORY: dict[str, str] = {
    "atom": "Atom",
    "bot": "Bottom",
    "imp": "Implication",
    "box": "Box",
    "untl": "Until",
    "snce": "Since",
}

# Maximum recursion depth guard (matches validate_formula_json convention).
_MAX_DEPTH: int = 500


def _complexity(data: Any, depth: int = 0) -> int:
    """Compute structural complexity: total connective count + 1.

    Lean correspondence: Formula.complexity (Formula.lean lines 162-168).

    Rules:
    - atom _ => 1
    - bot     => 1
    - imp φ ψ => 1 + complexity(φ) + complexity(ψ)
    - box φ   => 1 + complexity(φ)
    - untl φ ψ => 1 + complexity(φ) + complexity(ψ)
    - snce φ ψ => 1 + complexity(φ) + complexity(ψ)
    """
    if depth > _MAX_DEPTH:
        raise RecursionError(
            f"Formula nesting depth exceeds maximum ({_MAX_DEPTH}). "
            "Use validate_formula_json to check for adversarial input."
        )
    tag = _get_tag(data)
    if tag in ("atom", "bot"):
        return 1
    if tag == "imp":
        return 1 + _complexity(data["left"], depth + 1) + _complexity(data["right"], depth + 1)
    if tag == "box":
        return 1 + _complexity(data["child"], depth + 1)
    if tag in ("untl", "snce"):
        return 1 + _complexity(data["event"], depth + 1) + _complexity(data["guard"], depth + 1)
    raise ValueError(
        f"Unrecognized formula tag {tag!r}. "
        f"Valid tags are: {sorted(_TAG_TO_GOAL_CATEGORY)}"
    )


def _modal_depth(data: Any, depth: int = 0) -> int:
    """Compute modal nesting depth (max number of box operators on any path).

    Lean correspondence: Formula.modalDepth (Formula.lean lines 262-268).

    Rules:
    - atom _ => 0
    - bot     => 0
    - imp φ ψ => max(modalDepth(φ), modalDepth(ψ))
    - box φ   => 1 + modalDepth(φ)
    - untl φ ψ => max(modalDepth(φ), modalDepth(ψ))
    - snce φ ψ => max(modalDepth(φ), modalDepth(ψ))
    """
    if depth > _MAX_DEPTH:
        raise RecursionError(
            f"Formula nesting depth exceeds maximum ({_MAX_DEPTH})."
        )
    tag = _get_tag(data)
    if tag in ("atom", "bot"):
        return 0
    if tag == "imp":
        return max(_modal_depth(data["left"], depth + 1), _modal_depth(data["right"], depth + 1))
    if tag == "box":
        return 1 + _modal_depth(data["child"], depth + 1)
    if tag in ("untl", "snce"):
        return max(_modal_depth(data["event"], depth + 1), _modal_depth(data["guard"], depth + 1))
    raise ValueError(
        f"Unrecognized formula tag {tag!r}. "
        f"Valid tags are: {sorted(_TAG_TO_GOAL_CATEGORY)}"
    )


def _temporal_depth(data: Any, depth: int = 0) -> int:
    """Compute temporal nesting depth (max number of untl/snce operators on any path).

    Lean correspondence: Formula.temporalDepth (Formula.lean lines 283-289).

    Rules:
    - atom _ => 0
    - bot     => 0
    - imp φ ψ => max(temporalDepth(φ), temporalDepth(ψ))
    - box φ   => temporalDepth(φ)   -- box PASSES THROUGH (does not increment)
    - untl φ ψ => 1 + max(temporalDepth(φ), temporalDepth(ψ))
    - snce φ ψ => 1 + max(temporalDepth(φ), temporalDepth(ψ))

    Note: box does NOT increment temporal depth; it merely passes through.
    """
    if depth > _MAX_DEPTH:
        raise RecursionError(
            f"Formula nesting depth exceeds maximum ({_MAX_DEPTH})."
        )
    tag = _get_tag(data)
    if tag in ("atom", "bot"):
        return 0
    if tag == "imp":
        return max(
            _temporal_depth(data["left"], depth + 1),
            _temporal_depth(data["right"], depth + 1),
        )
    if tag == "box":
        # box passes through: does NOT add 1
        return _temporal_depth(data["child"], depth + 1)
    if tag in ("untl", "snce"):
        return 1 + max(
            _temporal_depth(data["event"], depth + 1),
            _temporal_depth(data["guard"], depth + 1),
        )
    raise ValueError(
        f"Unrecognized formula tag {tag!r}. "
        f"Valid tags are: {sorted(_TAG_TO_GOAL_CATEGORY)}"
    )


def _imp_count(data: Any, depth: int = 0) -> int:
    """Count total number of implication operators in the formula.

    Lean correspondence: Formula.countImplications (Formula.lean lines 303-309).

    Rules:
    - atom _ => 0
    - bot     => 0
    - imp φ ψ => 1 + countImplications(φ) + countImplications(ψ)
    - box φ   => countImplications(φ)
    - untl φ ψ => countImplications(φ) + countImplications(ψ)
    - snce φ ψ => countImplications(φ) + countImplications(ψ)
    """
    if depth > _MAX_DEPTH:
        raise RecursionError(
            f"Formula nesting depth exceeds maximum ({_MAX_DEPTH})."
        )
    tag = _get_tag(data)
    if tag in ("atom", "bot"):
        return 0
    if tag == "imp":
        return 1 + _imp_count(data["left"], depth + 1) + _imp_count(data["right"], depth + 1)
    if tag == "box":
        return _imp_count(data["child"], depth + 1)
    if tag in ("untl", "snce"):
        return _imp_count(data["event"], depth + 1) + _imp_count(data["guard"], depth + 1)
    raise ValueError(
        f"Unrecognized formula tag {tag!r}. "
        f"Valid tags are: {sorted(_TAG_TO_GOAL_CATEGORY)}"
    )


def _top_operator(data: Any) -> str:
    """Extract the GoalCategory name from the top-level operator.

    Lean correspondence: goalCategory (SuccessPatterns.lean lines 76-83).

    Returns one of: "Atom", "Bottom", "Implication", "Box", "Until", "Since".
    """
    tag = _get_tag(data)
    try:
        return _TAG_TO_GOAL_CATEGORY[tag]
    except KeyError:
        raise ValueError(
            f"Unrecognized formula tag {tag!r}. "
            f"Valid tags are: {sorted(_TAG_TO_GOAL_CATEGORY)}"
        ) from None


def _collect_atoms(data: Any, atoms: set[str], depth: int = 0) -> None:
    """Collect all distinct atom base names from a formula tree."""
    if depth > _MAX_DEPTH:
        raise RecursionError(
            f"Formula nesting depth exceeds maximum ({_MAX_DEPTH})."
        )
    tag = _get_tag(data)
    if tag == "atom":
        atoms.add(str(data["name"]))
    elif tag == "bot":
        pass
    elif tag == "imp":
        _collect_atoms(data["left"], atoms, depth + 1)
        _collect_atoms(data["right"], atoms, depth + 1)
    elif tag == "box":
        _collect_atoms(data["child"], atoms, depth + 1)
    elif tag in ("untl", "snce"):
        _collect_atoms(data["event"], atoms, depth + 1)
        _collect_atoms(data["guard"], atoms, depth + 1)
    else:
        raise ValueError(
            f"Unrecognized formula tag {tag!r}. "
            f"Valid tags are: {sorted(_TAG_TO_GOAL_CATEGORY)}"
        )


def _get_tag(data: Any) -> str:
    """Extract and validate the formula tag from a dict node.

    Accepts both FormulaJson (dict) and any object with a ``tag`` attribute,
    to support duck-typed algebraic AST types that may be introduced by
    the parallel formula generator task (task 8).
    """
    if isinstance(data, dict):
        tag = data.get("tag")
        if not isinstance(tag, str):
            raise ValueError(
                f"Formula node must have a string 'tag' field, got {type(tag).__name__!r}: {data!r}"
            )
        return tag
    # Duck-typing fallback for algebraic AST objects (e.g. from formula/ast.py).
    tag = getattr(data, "tag", None)
    if tag is None:
        raise ValueError(
            f"Formula node must have a 'tag' attribute or dict key, got: {type(data).__name__!r}"
        )
    return str(tag)


def extract_pattern_key(formula_json: FormulaJson) -> PatternKey:
    """Extract a PatternKey from a formula JSON tree.

    Ports PatternKey.fromFormula from SuccessPatterns.lean (lines 115-121).
    Computes all five structural features from the formula tree and returns
    a PatternKey dataclass.

    Parameters
    ----------
    formula_json:
        A valid formula JSON tree (as produced by DataExport.lean or compatible
        algebraic AST objects with a ``tag`` attribute).

    Returns
    -------
    PatternKey
        Feature vector with modal_depth, temporal_depth, imp_count, complexity,
        and top_operator.

    Raises
    ------
    ValueError
        If the formula contains an unrecognized tag.
    RecursionError
        If the formula nesting depth exceeds 500.

    Examples
    --------
    >>> extract_pattern_key({"tag": "atom", "name": "p"})
    PatternKey(modal_depth=0, temporal_depth=0, imp_count=0, complexity=1, top_operator='Atom')

    >>> extract_pattern_key({"tag": "bot"})
    PatternKey(modal_depth=0, temporal_depth=0, imp_count=0, complexity=1, top_operator='Bottom')
    """
    return PatternKey(
        modal_depth=_modal_depth(formula_json),
        temporal_depth=_temporal_depth(formula_json),
        imp_count=_imp_count(formula_json),
        complexity=_complexity(formula_json),
        top_operator=_top_operator(formula_json),
    )


def extract_atom_count(formula_json: FormulaJson) -> int:
    """Count the number of distinct atom base names in a formula.

    Useful for populating DifficultyMetrics.atom_count.
    Deduplicates by atom base name (e.g. two occurrences of "p" count as 1).

    Parameters
    ----------
    formula_json:
        A valid formula JSON tree.

    Returns
    -------
    int
        Number of distinct atom names (>= 0).

    Examples
    --------
    >>> extract_atom_count({"tag": "atom", "name": "p"})
    1
    >>> extract_atom_count({"tag": "bot"})
    0
    >>> extract_atom_count({"tag": "imp", "left": {"tag": "atom", "name": "p"},
    ...                     "right": {"tag": "atom", "name": "p"}})
    1
    """
    atoms: set[str] = set()
    _collect_atoms(formula_json, atoms)
    return len(atoms)
