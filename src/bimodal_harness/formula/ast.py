"""Algebraic AST types for BimodalHarness formula generation.

Mirrors the 6 Lean Formula constructors in Bimodal.Syntax.Formula:
- Atom  -> {"tag": "atom", "name": "<string>"}
- Bot   -> {"tag": "bot"}
- Imp   -> {"tag": "imp", "left": <formula>, "right": <formula>}
- Box   -> {"tag": "box", "child": <formula>}
- Untl  -> {"tag": "untl", "event": <formula>, "guard": <formula>}
- Snce  -> {"tag": "snce", "event": <formula>, "guard": <formula>}

Frozen dataclasses allow hashing, equality, and use as dict keys.
All metric functions mirror Lean Formula definitions exactly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Union

if TYPE_CHECKING:
    pass

# ---------------------------------------------------------------------------
# Forward-declared union type (populated after class definitions)
# ---------------------------------------------------------------------------

# FormulaNode is defined as a type alias after all classes are declared.


@dataclass(frozen=True, slots=True)
class Atom:
    """Propositional atom: Formula.atom in Lean."""

    name: str

    def to_json(self) -> dict[str, Any]:
        """Serialize to FormulaJson dict."""
        return {"tag": "atom", "name": self.name}

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "Atom":
        """Deserialize from FormulaJson dict."""
        if data.get("tag") != "atom":
            raise ValueError(f"Expected tag 'atom', got {data.get('tag')!r}")
        return cls(name=str(data["name"]))


@dataclass(frozen=True, slots=True)
class Bot:
    """Bottom (falsum): Formula.bot in Lean."""

    def to_json(self) -> dict[str, Any]:
        """Serialize to FormulaJson dict."""
        return {"tag": "bot"}

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "Bot":
        """Deserialize from FormulaJson dict."""
        if data.get("tag") != "bot":
            raise ValueError(f"Expected tag 'bot', got {data.get('tag')!r}")
        return cls()


@dataclass(frozen=True, slots=True)
class Imp:
    """Implication: Formula.imp in Lean."""

    left: "FormulaNode"
    right: "FormulaNode"

    def to_json(self) -> dict[str, Any]:
        """Serialize to FormulaJson dict."""
        return {"tag": "imp", "left": self.left.to_json(), "right": self.right.to_json()}

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "Imp":
        """Deserialize from FormulaJson dict."""
        if data.get("tag") != "imp":
            raise ValueError(f"Expected tag 'imp', got {data.get('tag')!r}")
        return cls(left=from_json(data["left"]), right=from_json(data["right"]))


@dataclass(frozen=True, slots=True)
class Box:
    """Modal necessity: Formula.box in Lean."""

    child: "FormulaNode"

    def to_json(self) -> dict[str, Any]:
        """Serialize to FormulaJson dict."""
        return {"tag": "box", "child": self.child.to_json()}

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "Box":
        """Deserialize from FormulaJson dict."""
        if data.get("tag") != "box":
            raise ValueError(f"Expected tag 'box', got {data.get('tag')!r}")
        return cls(child=from_json(data["child"]))


@dataclass(frozen=True, slots=True)
class Untl:
    """Until operator: Formula.untl in Lean.

    Burgess convention: event holds eventually, guard holds in between.
    """

    event: "FormulaNode"
    guard: "FormulaNode"

    def to_json(self) -> dict[str, Any]:
        """Serialize to FormulaJson dict."""
        return {"tag": "untl", "event": self.event.to_json(), "guard": self.guard.to_json()}

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "Untl":
        """Deserialize from FormulaJson dict."""
        if data.get("tag") != "untl":
            raise ValueError(f"Expected tag 'untl', got {data.get('tag')!r}")
        return cls(event=from_json(data["event"]), guard=from_json(data["guard"]))


@dataclass(frozen=True, slots=True)
class Snce:
    """Since operator: Formula.snce in Lean.

    Burgess convention: event was true, guard held in between.
    """

    event: "FormulaNode"
    guard: "FormulaNode"

    def to_json(self) -> dict[str, Any]:
        """Serialize to FormulaJson dict."""
        return {"tag": "snce", "event": self.event.to_json(), "guard": self.guard.to_json()}

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "Snce":
        """Deserialize from FormulaJson dict."""
        if data.get("tag") != "snce":
            raise ValueError(f"Expected tag 'snce', got {data.get('tag')!r}")
        return cls(event=from_json(data["event"]), guard=from_json(data["guard"]))


# ---------------------------------------------------------------------------
# Union type
# ---------------------------------------------------------------------------

FormulaNode = Union[Atom, Bot, Imp, Box, Untl, Snce]

# ---------------------------------------------------------------------------
# Dispatch table for from_json
# ---------------------------------------------------------------------------

_TAG_TO_CLASS: dict[str, type] = {
    "atom": Atom,
    "bot": Bot,
    "imp": Imp,
    "box": Box,
    "untl": Untl,
    "snce": Snce,
}


def from_json(data: dict[str, Any]) -> FormulaNode:
    """Deserialize a FormulaJson dict into a FormulaNode.

    Raises ValueError for unknown tags or missing required fields.
    """
    if not isinstance(data, dict):
        raise ValueError(f"Expected dict, got {type(data).__name__}")
    tag = data.get("tag")
    cls = _TAG_TO_CLASS.get(tag)  # type: ignore[arg-type]
    if cls is None:
        raise ValueError(f"Unknown formula tag: {tag!r}")
    return cls.from_json(data)  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Metric functions — mirror Lean Formula definitions exactly
# ---------------------------------------------------------------------------


def complexity(f: FormulaNode) -> int:
    """Structural complexity: number of nodes in the formula tree.

    Mirrors Lean Formula.complexity:
    - atom _ => 1
    - bot     => 1
    - imp φ ψ => 1 + complexity(φ) + complexity(ψ)
    - box φ   => 1 + complexity(φ)
    - untl φ ψ => 1 + complexity(φ) + complexity(ψ)
    - snce φ ψ => 1 + complexity(φ) + complexity(ψ)
    """
    match f:
        case Atom():
            return 1
        case Bot():
            return 1
        case Imp(left, right):
            return 1 + complexity(left) + complexity(right)
        case Box(child):
            return 1 + complexity(child)
        case Untl(event, guard):
            return 1 + complexity(event) + complexity(guard)
        case Snce(event, guard):
            return 1 + complexity(event) + complexity(guard)
        case _:
            raise TypeError(f"Unexpected formula node type: {type(f)}")


def modal_depth(f: FormulaNode) -> int:
    """Maximum nesting depth of modal box operators.

    Mirrors Lean Formula.modalDepth:
    - atom _ => 0
    - bot     => 0
    - imp φ ψ => max(modalDepth(φ), modalDepth(ψ))
    - box φ   => 1 + modalDepth(φ)
    - untl φ ψ => max(modalDepth(φ), modalDepth(ψ))
    - snce φ ψ => max(modalDepth(φ), modalDepth(ψ))
    """
    match f:
        case Atom():
            return 0
        case Bot():
            return 0
        case Imp(left, right):
            return max(modal_depth(left), modal_depth(right))
        case Box(child):
            return 1 + modal_depth(child)
        case Untl(event, guard):
            return max(modal_depth(event), modal_depth(guard))
        case Snce(event, guard):
            return max(modal_depth(event), modal_depth(guard))
        case _:
            raise TypeError(f"Unexpected formula node type: {type(f)}")


def temporal_depth(f: FormulaNode) -> int:
    """Maximum nesting depth of temporal (untl/snce) operators.

    Mirrors Lean Formula.temporalDepth:
    - atom _ => 0
    - bot     => 0
    - imp φ ψ => max(temporalDepth(φ), temporalDepth(ψ))
    - box φ   => temporalDepth(φ)    (box does NOT increment temporal depth)
    - untl φ ψ => 1 + max(temporalDepth(φ), temporalDepth(ψ))
    - snce φ ψ => 1 + max(temporalDepth(φ), temporalDepth(ψ))
    """
    match f:
        case Atom():
            return 0
        case Bot():
            return 0
        case Imp(left, right):
            return max(temporal_depth(left), temporal_depth(right))
        case Box(child):
            return temporal_depth(child)
        case Untl(event, guard):
            return 1 + max(temporal_depth(event), temporal_depth(guard))
        case Snce(event, guard):
            return 1 + max(temporal_depth(event), temporal_depth(guard))
        case _:
            raise TypeError(f"Unexpected formula node type: {type(f)}")


def imp_count(f: FormulaNode) -> int:
    """Count of implication (→) operators in the formula.

    Mirrors Lean Formula.countImplications:
    - atom _ => 0
    - bot     => 0
    - imp φ ψ => 1 + countImplications(φ) + countImplications(ψ)
    - box φ   => countImplications(φ)
    - untl φ ψ => countImplications(φ) + countImplications(ψ)
    - snce φ ψ => countImplications(φ) + countImplications(ψ)
    """
    match f:
        case Atom():
            return 0
        case Bot():
            return 0
        case Imp(left, right):
            return 1 + imp_count(left) + imp_count(right)
        case Box(child):
            return imp_count(child)
        case Untl(event, guard):
            return imp_count(event) + imp_count(guard)
        case Snce(event, guard):
            return imp_count(event) + imp_count(guard)
        case _:
            raise TypeError(f"Unexpected formula node type: {type(f)}")


def top_operator(f: FormulaNode) -> str:
    """Return GoalCategory name for the top-level operator.

    Maps to VALID_TOP_OPERATORS in schema/constants.py:
    - Atom(), Bot(), Imp(), Box(), Untl() -> "Atom", "Bottom", "Implication", "Box", "Until"
    - Snce() -> "Since"

    Note: AllPast and AllFuture are derived forms (built from imp/snce/untl) and
    cannot appear as top-level operators of primitive Formula nodes.
    """
    match f:
        case Atom():
            return "Atom"
        case Bot():
            return "Bottom"
        case Imp():
            return "Implication"
        case Box():
            return "Box"
        case Untl():
            return "Until"
        case Snce():
            return "Since"
        case _:
            raise TypeError(f"Unexpected formula node type: {type(f)}")
