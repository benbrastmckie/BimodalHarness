"""Near-miss mutation operators for BimodalHarness formula contrastive pair generation.

Provides 10 mutation operators that produce syntactically valid formulas
differing minimally from the input, for contrastive training pair generation.

All mutations are syntactic only; semantic filtering is deferred to the Z3 task.
"""

from __future__ import annotations

import random as _random_module
from collections.abc import Callable

from bimodal_harness.formula.ast import (
    Atom,
    Bot,
    Box,
    FormulaNode,
    Imp,
    Snce,
    Untl,
)

# ---------------------------------------------------------------------------
# Tree position utilities
# ---------------------------------------------------------------------------

# A path is a tuple of ints: each int indexes into the children of a node.
# Child indices:
#   Imp  -> left=0, right=1
#   Box  -> child=0
#   Untl -> event=0, guard=1
#   Snce -> event=0, guard=1
# Leaves (Atom, Bot) have no children.

Path = tuple[int, ...]


def collect_positions(f: FormulaNode) -> list[tuple[Path, FormulaNode]]:
    """Collect all (path, subtree) pairs in the formula tree.

    The root is included at path=().

    Returns
    -------
    list of (path, node) pairs in pre-order traversal order.
    """
    result: list[tuple[Path, FormulaNode]] = []
    _collect(f, (), result)
    return result


def _collect(f: FormulaNode, path: Path, acc: list[tuple[Path, FormulaNode]]) -> None:
    acc.append((path, f))
    match f:
        case Imp(left, right):
            _collect(left, (*path, 0), acc)
            _collect(right, (*path, 1), acc)
        case Box(child):
            _collect(child, (*path, 0), acc)
        case Untl(event, guard):
            _collect(event, (*path, 0), acc)
            _collect(guard, (*path, 1), acc)
        case Snce(event, guard):
            _collect(event, (*path, 0), acc)
            _collect(guard, (*path, 1), acc)


def rebuild_at(f: FormulaNode, path: Path, replacement: FormulaNode) -> FormulaNode:
    """Return a new tree identical to f except the node at path is replaced.

    Parameters
    ----------
    f:
        The formula tree to modify.
    path:
        Path to the node to replace (empty = replace root).
    replacement:
        New node to place at path.

    Returns
    -------
    FormulaNode
        New formula tree with the replacement applied.
    """
    if not path:
        return replacement

    idx = path[0]
    rest = path[1:]

    match f:
        case Imp(left, right):
            if idx == 0:
                return Imp(rebuild_at(left, rest, replacement), right)
            return Imp(left, rebuild_at(right, rest, replacement))
        case Box(child):
            return Box(rebuild_at(child, rest, replacement))
        case Untl(event, guard):
            if idx == 0:
                return Untl(rebuild_at(event, rest, replacement), guard)
            return Untl(event, rebuild_at(guard, rest, replacement))
        case Snce(event, guard):
            if idx == 0:
                return Snce(rebuild_at(event, rest, replacement), guard)
            return Snce(event, rebuild_at(guard, rest, replacement))
        case _:
            # Leaf at this path with remaining steps — path is invalid
            raise ValueError(f"Cannot descend into leaf {type(f).__name__} at path {path}")


# ---------------------------------------------------------------------------
# Individual mutation operators
# ---------------------------------------------------------------------------

MutationFn = Callable[[FormulaNode, _random_module.Random], FormulaNode | None]


def flip_operator(f: FormulaNode, rng: _random_module.Random) -> FormulaNode | None:
    """Replace the top-level binary temporal operator with the other one.

    untl -> snce and vice versa. No-op for non-temporal top-level ops.
    """
    match f:
        case Untl(event, guard):
            return Snce(event, guard)
        case Snce(event, guard):
            return Untl(event, guard)
        case _:
            # Find first temporal node in tree
            positions = collect_positions(f)
            candidates = [
                (path, node)
                for (path, node) in positions
                if isinstance(node, (Untl, Snce)) and path != ()
            ]
            if not candidates:
                return None
            path, node = rng.choice(candidates)
            if isinstance(node, Untl):
                return rebuild_at(f, path, Snce(node.event, node.guard))
            return rebuild_at(f, path, Untl(node.event, node.guard))


def flip_temporal_direction(f: FormulaNode, rng: _random_module.Random) -> FormulaNode | None:
    """Swap event and guard in a random temporal operator.

    For Untl(e, g) -> Untl(g, e) (same operator, children swapped).
    """
    positions = collect_positions(f)
    candidates = [
        (path, node) for (path, node) in positions if isinstance(node, (Untl, Snce))
    ]
    if not candidates:
        return None
    path, node = rng.choice(candidates)
    if isinstance(node, Untl):
        return rebuild_at(f, path, Untl(node.guard, node.event))
    return rebuild_at(f, path, Snce(node.guard, node.event))


def weaken_antecedent(f: FormulaNode, rng: _random_module.Random) -> FormulaNode | None:
    """Replace the antecedent of a random Imp with Bot (weakening the premise).

    For Imp(A, B) -> Imp(Bot(), B).
    """
    positions = collect_positions(f)
    candidates = [(path, node) for (path, node) in positions if isinstance(node, Imp)]
    if not candidates:
        return None
    path, node = rng.choice(candidates)
    assert isinstance(node, Imp)
    if isinstance(node.left, Bot):
        return None  # Already Bot, skip
    return rebuild_at(f, path, Imp(Bot(), node.right))


def strengthen_antecedent(f: FormulaNode, rng: _random_module.Random) -> FormulaNode | None:
    """Replace the antecedent of a random Imp with Box(antecedent) (strengthening the premise).

    For Imp(A, B) -> Imp(Box(A), B).
    """
    positions = collect_positions(f)
    candidates = [(path, node) for (path, node) in positions if isinstance(node, Imp)]
    if not candidates:
        return None
    path, node = rng.choice(candidates)
    assert isinstance(node, Imp)
    return rebuild_at(f, path, Imp(Box(node.left), node.right))


def change_atom(f: FormulaNode, rng: _random_module.Random) -> FormulaNode | None:
    """Replace a random Atom with a different atom from a fresh pool.

    Collects all atoms in the formula; replaces one with an atom not present
    (or a variant with suffix "_alt"). If only one unique atom, appends "_b".
    """
    positions = collect_positions(f)
    atom_positions = [(path, node) for (path, node) in positions if isinstance(node, Atom)]
    if not atom_positions:
        return None
    path, node = rng.choice(atom_positions)
    assert isinstance(node, Atom)

    # Gather all atom names in formula
    all_names = {n.name for (_, n) in positions if isinstance(n, Atom)}

    # Try to pick a different name
    candidates = sorted(all_names - {node.name})
    if candidates:
        new_name = rng.choice(candidates)
    else:
        # Only one atom name; create variant
        new_name = node.name + "_b"

    return rebuild_at(f, path, Atom(new_name))


def add_box(f: FormulaNode, rng: _random_module.Random) -> FormulaNode | None:
    """Wrap a random subformula in Box.

    Avoids wrapping a subformula that is already a Box to prevent trivial duplicates.
    """
    positions = collect_positions(f)
    # Avoid positions that are already Box nodes (would double-wrap unhelpfully at root)
    candidates = [(path, node) for (path, node) in positions if not isinstance(node, Box)]
    if not candidates:
        return None
    path, node = rng.choice(candidates)
    return rebuild_at(f, path, Box(node))


def remove_box(f: FormulaNode, rng: _random_module.Random) -> FormulaNode | None:
    """Remove a random Box, exposing its child.

    For Box(A) at some position -> A.
    """
    positions = collect_positions(f)
    candidates = [(path, node) for (path, node) in positions if isinstance(node, Box)]
    if not candidates:
        return None
    path, node = rng.choice(candidates)
    assert isinstance(node, Box)
    return rebuild_at(f, path, node.child)


def negate_guard(f: FormulaNode, rng: _random_module.Random) -> FormulaNode | None:
    """Negate the guard in a random temporal operator.

    For Untl(e, g) -> Untl(e, Imp(g, Bot())).
    (Negation is encoded as imp(g, bot) in this logic.)
    """
    positions = collect_positions(f)
    candidates = [(path, node) for (path, node) in positions if isinstance(node, (Untl, Snce))]
    if not candidates:
        return None
    path, node = rng.choice(candidates)
    # Encode negation as imp(g, bot)
    if isinstance(node, Untl):
        negated_guard = Imp(node.guard, Bot())
        return rebuild_at(f, path, Untl(node.event, negated_guard))
    assert isinstance(node, Snce)
    negated_guard = Imp(node.guard, Bot())
    return rebuild_at(f, path, Snce(node.event, negated_guard))


def swap_children(f: FormulaNode, rng: _random_module.Random) -> FormulaNode | None:
    """Swap the children of a random binary operator.

    For Imp(A, B) -> Imp(B, A).
    For Untl(e, g) -> Untl(g, e) (same as flip_temporal_direction but also handles Imp).
    """
    positions = collect_positions(f)
    candidates = [
        (path, node) for (path, node) in positions if isinstance(node, (Imp, Untl, Snce))
    ]
    if not candidates:
        return None
    path, node = rng.choice(candidates)
    if isinstance(node, Imp):
        return rebuild_at(f, path, Imp(node.right, node.left))
    if isinstance(node, Untl):
        return rebuild_at(f, path, Untl(node.guard, node.event))
    assert isinstance(node, Snce)
    return rebuild_at(f, path, Snce(node.guard, node.event))


def drop_modal(f: FormulaNode, rng: _random_module.Random) -> FormulaNode | None:
    """Replace a random Box with Bot (drop modal requirement entirely).

    For Box(A) -> Bot().
    """
    positions = collect_positions(f)
    candidates = [(path, node) for (path, node) in positions if isinstance(node, Box)]
    if not candidates:
        return None
    path, node = rng.choice(candidates)
    return rebuild_at(f, path, Bot())


# ---------------------------------------------------------------------------
# Registry and dispatch
# ---------------------------------------------------------------------------

_ALL_OPERATORS: dict[str, MutationFn] = {
    "flip_operator": flip_operator,
    "flip_temporal_direction": flip_temporal_direction,
    "weaken_antecedent": weaken_antecedent,
    "strengthen_antecedent": strengthen_antecedent,
    "change_atom": change_atom,
    "add_box": add_box,
    "remove_box": remove_box,
    "negate_guard": negate_guard,
    "swap_children": swap_children,
    "drop_modal": drop_modal,
}

OPERATOR_NAMES: list[str] = list(_ALL_OPERATORS.keys())


def mutate(
    f: FormulaNode,
    rng: _random_module.Random,
    *,
    operators: list[str] | None = None,
    max_attempts: int = 50,
) -> FormulaNode:
    """Apply a random compatible mutation to f.

    Tries operators in random order until one succeeds (returns non-None).

    Parameters
    ----------
    f:
        Formula to mutate.
    rng:
        Random number generator.
    operators:
        Optional subset of operator names to use. Defaults to all 10.
    max_attempts:
        Maximum tries before giving up (raises ValueError).

    Returns
    -------
    FormulaNode
        Mutated formula.

    Raises
    ------
    ValueError
        If no compatible mutation is found after max_attempts.
    """
    op_names = operators if operators is not None else OPERATOR_NAMES
    if not op_names:
        raise ValueError("operators list must be non-empty")

    shuffled = list(op_names)
    rng.shuffle(shuffled)

    for _ in range(max_attempts):
        op_name = rng.choice(op_names)
        op_fn = _ALL_OPERATORS.get(op_name)
        if op_fn is None:
            raise ValueError(f"Unknown mutation operator: {op_name!r}")
        result = op_fn(f, rng)
        if result is not None:
            return result

    raise ValueError(
        f"Could not find a compatible mutation for formula of type {type(f).__name__} "
        f"after {max_attempts} attempts with operators {op_names}"
    )


def generate_contrastive_pair(
    f: FormulaNode, rng: _random_module.Random
) -> tuple[FormulaNode, FormulaNode]:
    """Generate a (original, mutant) contrastive pair.

    Parameters
    ----------
    f:
        Original formula.
    rng:
        Random number generator.

    Returns
    -------
    tuple[FormulaNode, FormulaNode]
        (original, mutant) where mutant != original syntactically.
    """
    mutant = mutate(f, rng)
    return (f, mutant)
