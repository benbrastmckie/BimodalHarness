"""Formula enumeration and random generation for BimodalHarness.

Provides:
- enumerate_by_complexity: exhaustive enumeration of all formulas at complexity n
- enumerate_up_to_complexity: enumerate all formulas up to complexity n
- random_formula: top-down stochastic generation with weighted operator sampling
- count_formulas: expected count of formulas at a given complexity

Complexity is the node count as defined in Lean Formula.complexity.
"""

from __future__ import annotations

import random as _random_module
from collections.abc import Iterator

from bimodal_harness.formula.ast import (
    Atom,
    Bot,
    Box,
    FormulaNode,
    Imp,
    Snce,
    Untl,
)

# Default operator weights for random generation.
# Leaves (Atom, Bot) are excluded from this table; their probability is
# determined by the leaf-probability schedule: 1/(budget + 1).
_DEFAULT_OP_WEIGHTS: dict[str, float] = {
    "imp": 2.0,
    "box": 1.5,
    "untl": 1.0,
    "snce": 1.0,
}

# Unary operators (require budget >= 2: 1 for operator + 1 for child)
_UNARY_OPS: frozenset[str] = frozenset({"box"})

# Binary operators (require budget >= 3: 1 + 1 + 1)
_BINARY_OPS: frozenset[str] = frozenset({"imp", "untl", "snce"})


def enumerate_by_complexity(n: int, atoms: list[str]) -> Iterator[FormulaNode]:
    """Enumerate all distinct formulas with complexity exactly n.

    Parameters
    ----------
    n:
        Target complexity (>= 1). complexity=1 yields leaves only.
    atoms:
        List of atom names to use (should be non-empty for n >= 1).

    Yields
    ------
    FormulaNode
        Formulas in a deterministic order (leaves first, then unary, then binary).
    """
    if n < 1:
        return

    # Leaves: complexity 1
    if n == 1:
        yield Bot()
        for a in atoms:
            yield Atom(a)
        return

    # Unary: box(child) where complexity(child) = n - 1
    for child in enumerate_by_complexity(n - 1, atoms):
        yield Box(child)

    # Binary: split remaining budget n-1 between two children
    # Each binary operator uses 1 node, leaving n-1 for left+right.
    # We need left_c >= 1 and right_c >= 1 with left_c + right_c = n - 1.
    for left_c in range(1, n - 1):
        right_c = n - 1 - left_c
        for left in enumerate_by_complexity(left_c, atoms):
            for right in enumerate_by_complexity(right_c, atoms):
                yield Imp(left, right)

    for left_c in range(1, n - 1):
        right_c = n - 1 - left_c
        for left in enumerate_by_complexity(left_c, atoms):
            for right in enumerate_by_complexity(right_c, atoms):
                yield Untl(left, right)

    for left_c in range(1, n - 1):
        right_c = n - 1 - left_c
        for left in enumerate_by_complexity(left_c, atoms):
            for right in enumerate_by_complexity(right_c, atoms):
                yield Snce(left, right)


def enumerate_up_to_complexity(max_n: int, atoms: list[str]) -> Iterator[FormulaNode]:
    """Enumerate all formulas with complexity 1..max_n (inclusive).

    Yields simpler formulas first (ascending complexity order).
    """
    for n in range(1, max_n + 1):
        yield from enumerate_by_complexity(n, atoms)


def count_formulas(n: int, num_atoms: int) -> int:
    """Count the number of distinct formulas with complexity exactly n.

    Uses the recurrence:
    - C(1) = 1 + num_atoms   (Bot plus one atom per name)
    - C(n) = C(n-1)           (box children)
             + 3 * sum_{k=1}^{n-2} C(k) * C(n-1-k)   (3 binary ops)

    Parameters
    ----------
    n:
        Target complexity (>= 1).
    num_atoms:
        Number of distinct atom names.

    Returns
    -------
    int
        Number of distinct formulas at complexity n.
    """
    if n < 1:
        return 0

    # Memoized table
    counts: list[int] = [0] * (n + 1)
    counts[1] = 1 + num_atoms  # Bot + atoms

    for c in range(2, n + 1):
        # Unary: box
        total = counts[c - 1]
        # Binary: imp, untl, snce (3 operators)
        for lc in range(1, c - 1):
            rc = c - 1 - lc
            total += 3 * counts[lc] * counts[rc]
        counts[c] = total

    return counts[n]


def random_formula(
    max_complexity: int,
    atoms: list[str],
    rng: _random_module.Random,
    *,
    op_weights: dict[str, float] | None = None,
) -> FormulaNode:
    """Generate a random formula with complexity <= max_complexity.

    Uses a top-down stochastic generation strategy:
    - At each node, decide leaf vs. operator using leaf probability 1/(budget+1)
    - If operator chosen, sample from weighted operator distribution
    - Binary operators split budget stochastically between children

    Parameters
    ----------
    max_complexity:
        Upper bound on formula complexity (>= 1).
    atoms:
        Non-empty list of atom names.
    rng:
        Random number generator instance.
    op_weights:
        Optional override for operator weights. Keys: "imp", "box", "untl", "snce".
        Missing keys fall back to _DEFAULT_OP_WEIGHTS.

    Returns
    -------
    FormulaNode
        A randomly generated formula.
    """
    if not atoms:
        raise ValueError("atoms must be non-empty")
    if max_complexity < 1:
        raise ValueError("max_complexity must be >= 1")

    weights = dict(_DEFAULT_OP_WEIGHTS)
    if op_weights:
        weights.update(op_weights)

    return _random_formula_inner(max_complexity, atoms, rng, weights)


def _random_formula_inner(
    budget: int,
    atoms: list[str],
    rng: _random_module.Random,
    weights: dict[str, float],
) -> FormulaNode:
    """Recursive helper for random_formula."""
    if budget <= 1:
        # Must produce a leaf
        return _random_leaf(atoms, rng)

    # Leaf probability schedule: 1/(budget + 1)
    leaf_prob = 1.0 / (budget + 1)
    if rng.random() < leaf_prob:
        return _random_leaf(atoms, rng)

    # Select an operator from those feasible at this budget
    feasible: list[str] = []
    feasible_weights: list[float] = []

    if budget >= 2:
        # box is feasible (needs 1 + 1 = 2 budget)
        if "box" in weights:
            feasible.append("box")
            feasible_weights.append(weights["box"])

    if budget >= 3:
        # binary ops need 1 + 1 + 1 = 3 budget
        for op in ("imp", "untl", "snce"):
            if op in weights:
                feasible.append(op)
                feasible_weights.append(weights[op])

    if not feasible:
        # Fallback: leaf
        return _random_leaf(atoms, rng)

    op = rng.choices(feasible, weights=feasible_weights, k=1)[0]

    if op == "box":
        child = _random_formula_inner(budget - 1, atoms, rng, weights)
        return Box(child)

    # Binary operator: split remaining budget (budget - 1) between two children
    remaining = budget - 1  # at least 2
    # Each child must have at least 1
    left_budget = rng.randint(1, remaining - 1)
    right_budget = remaining - left_budget

    left = _random_formula_inner(left_budget, atoms, rng, weights)
    right = _random_formula_inner(right_budget, atoms, rng, weights)

    if op == "imp":
        return Imp(left, right)
    if op == "untl":
        return Untl(left, right)
    return Snce(left, right)


def _random_leaf(atoms: list[str], rng: _random_module.Random) -> FormulaNode:
    """Return Bot or a random Atom."""
    choices: list[FormulaNode] = [Bot()] + [Atom(a) for a in atoms]
    return rng.choice(choices)
