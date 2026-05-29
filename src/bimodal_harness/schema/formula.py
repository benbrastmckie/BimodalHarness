"""Formula AST type definitions and validation for BimodalHarness training data.

This module defines Python type aliases and a validation function for the
JSON representation of Formula values exported by Bimodal.Automation.DataExport.

Lean correspondence (DataExport.lean Formula.toJson):
- atom  -> {"tag": "atom", "name": "<string>"}
- bot   -> {"tag": "bot"}
- imp   -> {"tag": "imp", "left": <formula>, "right": <formula>}
- box   -> {"tag": "box", "child": <formula>}
- untl  -> {"tag": "untl", "event": <formula>, "guard": <formula>}
- snce  -> {"tag": "snce", "event": <formula>, "guard": <formula>}

The 6 constructor names match Formula.toJson in DataExport.lean exactly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bimodal_harness.schema.constants import VALID_FORMULA_TAGS

# JSON type alias for a serialized formula tree.
# The raw dict type produced by json.loads() on a Formula.toJson output.
FormulaJson = dict[str, Any]


@dataclass(frozen=True, slots=True)
class AtomRepr:
    """Python representation of a Lean Atom value.

    Lean correspondence (Atom in Bimodal.Syntax.Atom):
    - base: the propositional variable name (string)
    - fresh_index: optional integer for fresh/renamed atoms (None if original)

    In formula JSON, atoms appear in the simplified form {"tag": "atom", "name": "<base>"}
    (see DataExport.lean Formula.toJson).  The fresh_index is not included in
    the formula JSON tag but is tracked separately in Atom.toJson.
    """

    base: str
    fresh_index: int | None = None

    def to_json_dict(self) -> dict[str, Any]:
        """Serialize to Lean Atom.toJson format."""
        return {
            "base": self.base,
            "fresh_index": self.fresh_index,
        }

    @classmethod
    def from_json_dict(cls, data: dict[str, Any]) -> AtomRepr:
        """Deserialize from Lean Atom.toJson format."""
        return cls(
            base=str(data["base"]),
            fresh_index=data.get("fresh_index"),
        )


# Required fields for each formula tag (beyond "tag" itself).
_REQUIRED_FIELDS: dict[str, frozenset[str]] = {
    "atom": frozenset({"name"}),
    "bot": frozenset(),
    "imp": frozenset({"left", "right"}),
    "box": frozenset({"child"}),
    "untl": frozenset({"event", "guard"}),
    "snce": frozenset({"event", "guard"}),
}


def validate_formula_json(data: Any, *, depth: int = 0, max_depth: int = 500) -> bool:
    """Recursively validate a formula JSON tree.

    Parameters
    ----------
    data:
        The Python object to validate (typically produced by json.loads).
    depth:
        Current recursion depth (used to prevent stack overflow on adversarial input).
    max_depth:
        Maximum allowed nesting depth.

    Returns
    -------
    bool
        True if the structure is a valid formula JSON tree; False otherwise.

    Examples
    --------
    >>> validate_formula_json({"tag": "bot"})
    True
    >>> validate_formula_json({"tag": "atom", "name": "p"})
    True
    >>> validate_formula_json({"tag": "imp", "left": {"tag": "bot"}, "right": {"tag": "bot"}})
    True
    >>> validate_formula_json({"tag": "unknown"})
    False
    >>> validate_formula_json({"tag": "atom"})  # missing 'name'
    False
    """
    if depth > max_depth:
        return False
    if not isinstance(data, dict):
        return False
    tag = data.get("tag")
    if tag not in VALID_FORMULA_TAGS:
        return False
    required = _REQUIRED_FIELDS[tag]
    if not required.issubset(data.keys()):
        return False
    # Recursively validate child nodes.
    if tag == "imp":
        return validate_formula_json(data["left"], depth=depth + 1, max_depth=max_depth) and \
               validate_formula_json(data["right"], depth=depth + 1, max_depth=max_depth)
    if tag == "box":
        return validate_formula_json(data["child"], depth=depth + 1, max_depth=max_depth)
    if tag in ("untl", "snce"):
        return validate_formula_json(data["event"], depth=depth + 1, max_depth=max_depth) and \
               validate_formula_json(data["guard"], depth=depth + 1, max_depth=max_depth)
    # "atom" and "bot" have no child nodes.
    return True


def formula_json_to_pretty(data: FormulaJson) -> str:
    """Convert a formula JSON tree to a human-readable string.

    Mirrors DataExport.lean Formula.prettyPrint:
    - atom  -> base name
    - bot   -> "⊥"
    - imp   -> "(left → right)"
    - box   -> "□child"
    - untl  -> "U(event, guard)"
    - snce  -> "S(event, guard)"

    Parameters
    ----------
    data:
        A valid formula JSON tree (as produced by DataExport.lean).

    Returns
    -------
    str
        Human-readable formula string.
    """
    tag = data.get("tag", "")
    if tag == "atom":
        return str(data.get("name", "?"))
    if tag == "bot":
        return "⊥"
    if tag == "imp":
        left = formula_json_to_pretty(data["left"])
        right = formula_json_to_pretty(data["right"])
        return f"({left} → {right})"
    if tag == "box":
        child = formula_json_to_pretty(data["child"])
        return f"□{child}"
    if tag == "untl":
        event = formula_json_to_pretty(data["event"])
        guard = formula_json_to_pretty(data["guard"])
        return f"U({event}, {guard})"
    if tag == "snce":
        event = formula_json_to_pretty(data["event"])
        guard = formula_json_to_pretty(data["guard"])
        return f"S({event}, {guard})"
    return f"<unknown:{tag}>"
