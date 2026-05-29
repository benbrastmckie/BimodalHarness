"""Best-first search implementation for bimodal logic proof search.

Implements a Python-driven A* search loop with:
- Rule-based heuristic scoring ported from Lean's Core.lean
- Optional neural value network integration (additive bonus)
- A/B comparison infrastructure with McNemar statistical testing

Lean correspondence:
- heuristic_score: Core.lean lines 650-668
- advanced_heuristic_score: Core.lean lines 686-692
- bestFirst_search: Strategies.lean (Python re-implementation)
"""

from __future__ import annotations

import heapq
import math
import time
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from bimodal_harness.schema.constants import VALID_TOP_OPERATORS
from bimodal_harness.schema.features import extract_pattern_key
from bimodal_harness.schema.records import PatternKey

# ---------------------------------------------------------------------------
# Stable sorted index for top operators (matches models/value.py convention)
# ---------------------------------------------------------------------------

#: Stable sorted mapping from VALID_TOP_OPERATORS to indices 0-7.
TOP_OPERATOR_INDEX: dict[str, int] = {
    op: idx for idx, op in enumerate(sorted(VALID_TOP_OPERATORS))
}

# ---------------------------------------------------------------------------
# Phase 1: Data Structures and Rule-Based Heuristics
# ---------------------------------------------------------------------------


@dataclass
class HeuristicWeights:
    """Weights for the rule-based heuristic scoring function.

    Mirrors the weight constants in Lean's Core.lean.

    Parameters
    ----------
    mp_base:
        Base cost for modus ponens application.
    modal_base:
        Base cost for modal rule (box introduction / necessitation).
    temporal_base:
        Base cost for temporal rule (until/since unfolding).
    mp_complexity_weight:
        Scaling factor applied to formula complexity for modus ponens.
    context_penalty_weight:
        Penalty per formula in the context (large context = more expensive search).
    dead_end:
        Cost assigned to formulas that cannot be proved (dead-end sentinel).
    """

    mp_base: float = 2.0
    modal_base: float = 5.0
    temporal_base: float = 5.0
    mp_complexity_weight: float = 0.5
    context_penalty_weight: float = 0.1
    dead_end: float = 100.0


@dataclass
class SearchNode:
    """A node in the best-first search tree.

    Represents a proof state (context, goal) with associated cost and
    heuristic scores for priority queue ordering.

    Parameters
    ----------
    context:
        List of formula JSON dicts in the current proof context (Gamma).
    goal:
        The current goal formula as a JSON dict.
    cost:
        Accumulated cost (g-score) from the root to this node.
    heuristic:
        Estimated cost to proof (h-score) from this node.
    fscore:
        Total estimated cost f = g + h.
    parent:
        Reference to the parent SearchNode, or None for the root.
    action:
        Human-readable description of the rule applied to reach this node.
    """

    context: list[dict[str, Any]]
    goal: dict[str, Any]
    cost: float
    heuristic: float
    fscore: float
    parent: SearchNode | None = field(default=None, repr=False, compare=False)
    action: str | None = None

    def __lt__(self, other: SearchNode) -> bool:
        """Enable heapq ordering by fscore."""
        return self.fscore < other.fscore

    def __le__(self, other: SearchNode) -> bool:
        return self.fscore <= other.fscore


@dataclass
class SearchStats:
    """Statistics collected during a search run.

    Parameters
    ----------
    visited:
        Number of nodes added to the priority queue.
    expanded:
        Number of nodes popped and expanded from the queue.
    pruned_by_limit:
        Number of nodes pruned because max_expansions was reached.
    max_queue_size:
        Peak size of the priority queue during the search.
    wall_clock_seconds:
        Total elapsed wall-clock time for the search.
    """

    visited: int = 0
    expanded: int = 0
    pruned_by_limit: int = 0
    max_queue_size: int = 0
    wall_clock_seconds: float = 0.0


@dataclass
class SearchResult:
    """Result returned by PythonBestFirstSearch.search().

    Parameters
    ----------
    proved:
        Whether the goal was successfully proved.
    stats:
        Search statistics for this run.
    proof_steps:
        Ordered list of (action, goal) pairs tracing the proof path,
        or None if the search did not find a proof.
    """

    proved: bool
    stats: SearchStats
    proof_steps: list[tuple[str, dict[str, Any]]] | None = None


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def formula_eq(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """Structural equality for formula JSON dicts.

    Performs deep equality comparison on the formula JSON tree structure.

    Parameters
    ----------
    a, b:
        Formula JSON dicts to compare.

    Returns
    -------
    bool
        True iff the two formulas are structurally identical.
    """
    if not isinstance(a, dict) or not isinstance(b, dict):
        return a == b
    if a.get("tag") != b.get("tag"):
        return False
    tag = a.get("tag")
    if tag in ("atom",):
        return a.get("name") == b.get("name")
    if tag == "bot":
        return True
    if tag == "imp":
        return formula_eq(a.get("left", {}), b.get("left", {})) and formula_eq(
            a.get("right", {}), b.get("right", {})
        )
    if tag == "box":
        return formula_eq(a.get("child", {}), b.get("child", {}))
    if tag in ("untl", "snce"):
        return formula_eq(a.get("event", {}), b.get("event", {})) and formula_eq(
            a.get("guard", {}), b.get("guard", {})
        )
    # Unknown tags: fall back to dict equality
    return a == b


def is_assumption(context: list[dict[str, Any]], goal: dict[str, Any]) -> bool:
    """Check if the goal is directly in the context.

    Mirrors Lean's assumption rule: if the goal appears in Gamma,
    the proof is trivially complete via the assumption rule.

    Parameters
    ----------
    context:
        Current proof context (list of formula JSON dicts).
    goal:
        Goal formula to check.

    Returns
    -------
    bool
        True iff goal is structurally equal to some formula in context.
    """
    return any(formula_eq(goal, ctx_formula) for ctx_formula in context)


def is_axiom(goal: dict[str, Any]) -> bool:
    """Check if a formula matches a known axiom schema.

    Implements a simplified axiom check for common propositional and
    modal/temporal axioms of bimodal logic.

    Axiom schemas checked:
    - K axiom (prop_k): p -> (q -> p)
    - S axiom (prop_s): (p -> q -> r) -> (p -> q) -> p -> r
    - Modus ponens closure: if p and p -> q are both trivial
    - Bot elimination: bot -> p

    Parameters
    ----------
    goal:
        Goal formula to check.

    Returns
    -------
    bool
        True iff the goal matches a recognized axiom schema.
    """
    tag = goal.get("tag")

    # bot -> p  (ex falso)
    if tag == "imp":
        left = goal.get("left", {})
        if left.get("tag") == "bot":
            return True

    # p -> (q -> p)  (K combinator / prop_k)
    if tag == "imp":
        right = goal.get("right", {})
        if right.get("tag") == "imp":
            # p -> (q -> p): right side's right must equal left side
            if formula_eq(goal.get("left", {}), right.get("right", {})):
                return True

    # (p -> q -> r) -> (p -> q) -> p -> r  (S combinator / prop_s)
    if tag == "imp":
        left = goal.get("left", {})
        right = goal.get("right", {})
        if left.get("tag") == "imp" and right.get("tag") == "imp":
            inner_left = left.get("right", {})
            outer_right = right.get("right", {})
            # Simplified check: the antecedent of right matches antecedent of left
            if formula_eq(left.get("left", {}), right.get("left", {})):
                if inner_left.get("tag") == "imp" and formula_eq(
                    inner_left.get("left", {}), outer_right.get("left", {})
                ):
                    return True

    return False


def structure_heuristic(goal: dict[str, Any]) -> float:
    """Estimate proof difficulty from formula structure.

    Provides a secondary heuristic based on formula complexity and
    operator type. More complex formulas are generally harder to prove.

    Parameters
    ----------
    goal:
        Goal formula.

    Returns
    -------
    float
        Heuristic penalty (0.0 = simple, higher = more complex).
    """
    tag = goal.get("tag", "")
    if tag in ("atom", "bot"):
        return 0.0
    if tag == "imp":
        # Implication goals: cost depends on right side
        right = goal.get("right", {})
        return 0.5 + 0.25 * structure_heuristic(right)
    if tag == "box":
        # Modal goal: fixed penalty
        child = goal.get("child", {})
        return 1.0 + 0.5 * structure_heuristic(child)
    if tag in ("untl", "snce"):
        # Temporal goal: slightly higher base penalty
        event = goal.get("event", {})
        guard = goal.get("guard", {})
        return 1.5 + 0.25 * (structure_heuristic(event) + structure_heuristic(guard))
    return 1.0


def heuristic_score(
    context: list[dict[str, Any]],
    goal: dict[str, Any],
    weights: HeuristicWeights,
) -> float:
    """Compute rule-based heuristic score for a (context, goal) pair.

    Ports Core.lean lines 650-668. Lower score = more promising node.

    Scoring rules:
    - Axiom match: 0.0 (immediately provable)
    - Assumption match: 1.0 (trivially provable from context)
    - Modus ponens applicable: mp_base + complexity * mp_complexity_weight
    - Modal goal (box): modal_base
    - Temporal goal (until/since): temporal_base
    - Otherwise (dead end): dead_end

    Parameters
    ----------
    context:
        Current proof context.
    goal:
        Goal formula.
    weights:
        Heuristic weight configuration.

    Returns
    -------
    float
        Estimated cost. Lower = more promising.
    """
    # Immediate proof: axiom
    if is_axiom(goal):
        return 0.0

    # Immediate proof: assumption
    if is_assumption(context, goal):
        return 1.0

    tag = goal.get("tag", "")

    # Modus ponens: goal is the conclusion of some implication in context
    # or we can build the proof via MP
    if tag == "imp":
        try:
            key = extract_pattern_key(goal)
            complexity_cost = key.complexity * weights.mp_complexity_weight
        except (ValueError, RecursionError):
            complexity_cost = 1.0
        return weights.mp_base + complexity_cost

    # Modal goal: box introduction (necessitation rule)
    if tag == "box":
        return weights.modal_base

    # Temporal goal: until/since unfolding
    if tag in ("untl", "snce"):
        return weights.temporal_base

    # Dead end: atom or bot that is not in context (unprovable without more context)
    return weights.dead_end


def advanced_heuristic_score(
    context: list[dict[str, Any]],
    goal: dict[str, Any],
    weights: HeuristicWeights,
) -> float:
    """Enhanced heuristic with domain bonuses for modal/temporal goals.

    Ports Core.lean lines 686-692. Extends heuristic_score with:
    - Domain bonuses when the goal type matches available context
    - Structure penalty for deeply nested formulas

    Parameters
    ----------
    context:
        Current proof context.
    goal:
        Goal formula.
    weights:
        Heuristic weight configuration.

    Returns
    -------
    float
        Estimated cost with domain-aware bonuses.
    """
    base = heuristic_score(context, goal, weights)

    # Already at base extremes - no improvement possible
    if base == 0.0 or base >= weights.dead_end:
        return base

    tag = goal.get("tag", "")

    # Domain bonus: modal goal with modal formulas in context
    if tag == "box":
        modal_in_context = sum(1 for f in context if f.get("tag") == "box")
        domain_bonus = -min(modal_in_context * 0.5, 2.0)  # up to -2.0 reduction
        return max(0.1, base + domain_bonus)

    # Domain bonus: temporal goal with temporal formulas in context
    if tag in ("untl", "snce"):
        temporal_in_context = sum(
            1 for f in context if f.get("tag") in ("untl", "snce")
        )
        domain_bonus = -min(temporal_in_context * 0.5, 2.0)
        return max(0.1, base + domain_bonus)

    # Structure penalty for deeply complex formulas
    struct_penalty = structure_heuristic(goal) * 0.1
    context_penalty = len(context) * weights.context_penalty_weight

    return base + struct_penalty + context_penalty


# ---------------------------------------------------------------------------
# Phase 3: Value Network Protocol and Mock
# ---------------------------------------------------------------------------


@runtime_checkable
class ValueNetworkProtocol(Protocol):
    """Protocol for value networks used in neural-augmented search.

    Any object implementing these two methods can serve as a value network
    in PythonBestFirstSearch, regardless of the underlying implementation.
    """

    def predict(self, key: PatternKey) -> float:
        """Predict proof difficulty for a single pattern key.

        Parameters
        ----------
        key:
            PatternKey feature vector for the goal formula.

        Returns
        -------
        float
            Predicted value in [0, 1] (higher = easier to prove).
        """
        ...

    def predict_batch(self, keys: list[PatternKey]) -> list[float]:
        """Predict proof difficulty for a batch of pattern keys.

        Parameters
        ----------
        keys:
            List of PatternKey feature vectors.

        Returns
        -------
        list[float]
            Predicted values in [0, 1], one per key.
        """
        ...


@dataclass
class MockValueNetwork:
    """Mock value network for testing, returning a configurable constant.

    Parameters
    ----------
    constant:
        Value returned for all queries. Default: 0.5.
    """

    constant: float = 0.5

    def predict(self, key: PatternKey) -> float:
        """Return the configured constant for any pattern key."""
        return self.constant

    def predict_batch(self, keys: list[PatternKey]) -> list[float]:
        """Return the configured constant for each key in the batch."""
        return [self.constant] * len(keys)


# ---------------------------------------------------------------------------
# Tensor encoding and score blending utilities
# ---------------------------------------------------------------------------


def _pattern_key_to_tensor(key: PatternKey) -> list[float]:
    """Encode a PatternKey into a 12-dimensional feature vector.

    Encoding:
    - Dimensions 0-3: log1p of [modal_depth, temporal_depth, imp_count, complexity]
    - Dimensions 4-11: one-hot encoding of top_operator (8 categories, sorted)

    Parameters
    ----------
    key:
        PatternKey to encode.

    Returns
    -------
    list[float]
        12-dimensional feature vector.
    """
    # 4 numeric features with log1p normalization
    numeric = [
        math.log1p(key.modal_depth),
        math.log1p(key.temporal_depth),
        math.log1p(key.imp_count),
        math.log1p(key.complexity),
    ]

    # 8-dim one-hot for top_operator (sorted alphabetical order)
    one_hot = [0.0] * len(TOP_OPERATOR_INDEX)
    op_idx = TOP_OPERATOR_INDEX.get(key.top_operator, 0)
    one_hot[op_idx] = 1.0

    return numeric + one_hot


def _scale_value(raw_value: float, temperature: float) -> float:
    """Apply temperature-scaled sigmoid to a raw value network output.

    Uses sigmoid(logit(v) / T) which:
    - Preserves 0.5 as a fixed point
    - Flattens toward 0.5 as temperature increases (reduces overconfidence)
    - Sharpens toward 0/1 as temperature decreases

    Includes numerical stability guards for values near 0 and 1.

    Parameters
    ----------
    raw_value:
        Input value in (0, 1). Values outside this range are clipped.
    temperature:
        Temperature parameter T > 0. Higher T = more conservative scores.

    Returns
    -------
    float
        Temperature-scaled value in (0, 1).
    """
    # Clip to avoid numerical issues in logit
    eps = 1e-7
    v = max(eps, min(1.0 - eps, raw_value))

    if abs(temperature) < eps:
        # Zero temperature: return raw value unchanged
        return v

    # logit = log(v / (1-v))
    logit = math.log(v / (1.0 - v))
    scaled_logit = logit / temperature

    # Sigmoid: 1 / (1 + exp(-x))
    try:
        if scaled_logit >= 500:
            return 1.0 - eps
        if scaled_logit <= -500:
            return eps
        return 1.0 / (1.0 + math.exp(-scaled_logit))
    except OverflowError:
        return 0.5


def _batch_score_nodes(
    nodes: list[SearchNode],
    value_net: ValueNetworkProtocol,
    temperature: float,
) -> list[float]:
    """Compute temperature-scaled neural bonuses for a batch of nodes.

    Extracts PatternKeys from each node's goal, runs batched inference,
    and applies temperature scaling.

    Parameters
    ----------
    nodes:
        Batch of SearchNodes to score.
    value_net:
        Value network implementing ValueNetworkProtocol.
    temperature:
        Temperature parameter for sigmoid scaling.

    Returns
    -------
    list[float]
        Temperature-scaled neural bonus values, one per node.
    """
    keys: list[PatternKey] = []
    valid_indices: list[int] = []

    for i, node in enumerate(nodes):
        try:
            key = extract_pattern_key(node.goal)
            keys.append(key)
            valid_indices.append(i)
        except (ValueError, RecursionError):
            pass

    if not keys:
        return [0.5] * len(nodes)

    raw_values = value_net.predict_batch(keys)
    scaled = [_scale_value(v, temperature) for v in raw_values]

    result = [0.5] * len(nodes)
    for list_pos, node_idx in enumerate(valid_indices):
        result[node_idx] = scaled[list_pos]

    return result


# ---------------------------------------------------------------------------
# Phase 2: Best-First Search Loop
# ---------------------------------------------------------------------------


class PythonBestFirstSearch:
    """Python-driven best-first proof search with optional neural scoring.

    Implements an A* search over proof states (context, goal) pairs.
    The priority queue is ordered by f-score (g + h), where g is the
    accumulated rule application cost and h is the heuristic estimate.

    When a value network is provided, the heuristic is augmented with
    an additive neural bonus: h' = h - alpha * neural_score.

    Parameters
    ----------
    value_net:
        Optional value network for neural-augmented scoring.
        If None, pure rule-based search is used.
    weights:
        Heuristic weight configuration. If None, defaults are used.
    alpha:
        Weight for neural bonus. Higher = more influence from neural scorer.
    temperature:
        Temperature for sigmoid scaling of neural outputs.
        Higher = more conservative (closer to 0.5).
    max_expansions:
        Maximum number of nodes to expand before giving up.
    use_advanced_heuristic:
        If True, use advanced_heuristic_score; else use heuristic_score.
    """

    def __init__(
        self,
        value_net: ValueNetworkProtocol | None = None,
        weights: HeuristicWeights | None = None,
        alpha: float = 5.0,
        temperature: float = 1.5,
        max_expansions: int = 10_000,
        use_advanced_heuristic: bool = True,
    ) -> None:
        self.value_net = value_net
        self.weights = weights or HeuristicWeights()
        self.alpha = alpha
        self.temperature = temperature
        self.max_expansions = max_expansions
        self.use_advanced_heuristic = use_advanced_heuristic

    def _compute_heuristic(
        self,
        context: list[dict[str, Any]],
        goal: dict[str, Any],
        neural_bonus: float = 0.5,
    ) -> float:
        """Compute combined heuristic score.

        Combines rule-based score with optional neural bonus:
        h = rule_based_h - alpha * (neural_score - 0.5)

        Centering at 0.5 ensures the neural bonus is zero-mean for
        untrained networks, preserving pure rule-based behavior at
        initialization.

        Parameters
        ----------
        context:
            Current proof context.
        goal:
            Goal formula.
        neural_bonus:
            Temperature-scaled neural value (0.5 = neutral).

        Returns
        -------
        float
            Combined heuristic score (lower = more promising).
        """
        if self.use_advanced_heuristic:
            rule_score = advanced_heuristic_score(context, goal, self.weights)
        else:
            rule_score = heuristic_score(context, goal, self.weights)

        if self.value_net is not None:
            # Higher neural_bonus means easier to prove -> reduce heuristic cost
            neural_adjustment = self.alpha * (neural_bonus - 0.5)
            return max(0.0, rule_score - neural_adjustment)

        return rule_score

    def _expand_node(
        self,
        node: SearchNode,
    ) -> list[SearchNode]:
        """Generate successor nodes from the current proof state.

        Applies applicable inference rules to the (context, goal) pair
        and generates successor nodes for each possible rule application.

        Rules applied:
        1. Modus Ponens: if phi -> goal in context, add phi as subgoal
        2. Modal Rule: if goal is box(phi), add phi as new goal (necessitation)
        3. Temporal Rule: if goal is untl/snce(phi, psi), unfold to subgoals

        Parameters
        ----------
        node:
            Current search node to expand.

        Returns
        -------
        list[SearchNode]
            List of successor nodes. May be empty for dead-end states.
        """
        successors: list[SearchNode] = []
        goal = node.goal
        context = node.context
        tag = goal.get("tag", "")

        # Rule 1: Modus Ponens applications
        # For each phi -> goal in context, create subgoal for phi
        for ctx_formula in context:
            if ctx_formula.get("tag") == "imp":
                imp_right = ctx_formula.get("right", {})
                if formula_eq(imp_right, goal):
                    # Found phi -> goal in context; need to prove phi
                    subgoal = ctx_formula.get("left", {})
                    cost = node.cost + self.weights.mp_base
                    h = self._compute_heuristic(context, subgoal)
                    successors.append(
                        SearchNode(
                            context=context,
                            goal=subgoal,
                            cost=cost,
                            heuristic=h,
                            fscore=cost + h,
                            parent=node,
                            action=f"modus_ponens({_formula_tag(ctx_formula)})",
                        )
                    )

        # Rule 2: Implication introduction (deduction theorem)
        # If goal is phi -> psi, add phi to context and try to prove psi
        if tag == "imp":
            phi = goal.get("left", {})
            psi = goal.get("right", {})
            new_context = context + [phi]
            cost = node.cost + self.weights.mp_base
            h = self._compute_heuristic(new_context, psi)
            successors.append(
                SearchNode(
                    context=new_context,
                    goal=psi,
                    cost=cost,
                    heuristic=h,
                    fscore=cost + h,
                    parent=node,
                    action="imp_intro",
                )
            )

        # Rule 3: Modal rule (necessitation / box introduction)
        # If goal is box(phi), prove phi in empty context
        if tag == "box":
            phi = goal.get("child", {})
            cost = node.cost + self.weights.modal_base
            h = self._compute_heuristic([], phi)
            successors.append(
                SearchNode(
                    context=[],
                    goal=phi,
                    cost=cost,
                    heuristic=h,
                    fscore=cost + h,
                    parent=node,
                    action="necessitation",
                )
            )

        # Rule 4: Temporal unfolding
        # until(phi, psi) -> either psi (base case) or phi & next until(phi, psi)
        # Since(phi, psi) similarly
        if tag in ("untl", "snce"):
            psi = goal.get("guard", {})  # the "now" component
            phi = goal.get("event", {})  # the "while" component

            # Base case: prove psi directly
            cost_base = node.cost + self.weights.temporal_base
            h_base = self._compute_heuristic(context, psi)
            successors.append(
                SearchNode(
                    context=context,
                    goal=psi,
                    cost=cost_base,
                    heuristic=h_base,
                    fscore=cost_base + h_base,
                    parent=node,
                    action=f"{tag}_base",
                )
            )

            # Recursive case: prove phi
            cost_rec = node.cost + self.weights.temporal_base
            h_rec = self._compute_heuristic(context, phi)
            successors.append(
                SearchNode(
                    context=context,
                    goal=phi,
                    cost=cost_rec,
                    heuristic=h_rec,
                    fscore=cost_rec + h_rec,
                    parent=node,
                    action=f"{tag}_step",
                )
            )

        return successors

    def search(
        self,
        context: list[dict[str, Any]],
        goal: dict[str, Any],
        bridge: Any = None,
    ) -> SearchResult:
        """Run best-first proof search.

        Implements A* search with the priority queue ordered by f-score.
        The search terminates when:
        1. A proof is found (leaf node is verified)
        2. max_expansions is reached
        3. The priority queue is exhausted

        Leaf verification: axioms and assumptions are verified locally
        without calling the bridge. If a bridge is provided, it is called
        for non-trivial leaves as a final check.

        Parameters
        ----------
        context:
            Initial proof context (list of formula JSON dicts).
        goal:
            Goal formula to prove.
        bridge:
            Optional LeanBridge or mock bridge for leaf verification.
            Must support: label_formula(formula_json) -> dict with
            "label" key ("valid"|"invalid") and optional "proof_height".

        Returns
        -------
        SearchResult
            Contains proved flag, statistics, and proof path if found.
        """
        t_start = time.monotonic()
        stats = SearchStats()

        # Compute initial heuristic
        initial_h = self._compute_heuristic(context, goal)
        root = SearchNode(
            context=list(context),
            goal=goal,
            cost=0.0,
            heuristic=initial_h,
            fscore=initial_h,
        )

        # Priority queue: list of (fscore, counter, node) tuples
        # counter breaks ties in fscore ordering (FIFO among equal fscores)
        counter = 0
        pq: list[tuple[float, int, SearchNode]] = [(root.fscore, counter, root)]
        stats.visited = 1
        stats.max_queue_size = 1

        # Visited states: set of (context_hash, goal_hash) to avoid cycles
        visited: set[tuple[int, str]] = set()

        while pq:
            if stats.expanded >= self.max_expansions:
                stats.pruned_by_limit += len(pq)
                break

            _, _, node = heapq.heappop(pq)
            stats.expanded += 1

            # State deduplication
            state_key = (_context_hash(node.context), _formula_hash(node.goal))
            if state_key in visited:
                continue
            visited.add(state_key)

            # Check if this node is a proof leaf
            if self._is_proved(node, bridge):
                stats.wall_clock_seconds = time.monotonic() - t_start
                proof_steps = _extract_proof_path(node)
                return SearchResult(
                    proved=True,
                    stats=stats,
                    proof_steps=proof_steps,
                )

            # Expand the node
            successors = self._expand_node(node)

            # If we have a value network, batch-score all successors
            if self.value_net is not None and successors:
                neural_bonuses = _batch_score_nodes(
                    successors, self.value_net, self.temperature
                )
                updated_successors = []
                for succ, bonus in zip(successors, neural_bonuses, strict=True):
                    new_h = self._compute_heuristic(succ.context, succ.goal, bonus)
                    updated_successors.append(
                        SearchNode(
                            context=succ.context,
                            goal=succ.goal,
                            cost=succ.cost,
                            heuristic=new_h,
                            fscore=succ.cost + new_h,
                            parent=succ.parent,
                            action=succ.action,
                        )
                    )
                successors = updated_successors

            for succ in successors:
                counter += 1
                heapq.heappush(pq, (succ.fscore, counter, succ))
                stats.visited += 1

            stats.max_queue_size = max(stats.max_queue_size, len(pq))

        stats.wall_clock_seconds = time.monotonic() - t_start
        return SearchResult(proved=False, stats=stats)

    def _is_proved(
        self,
        node: SearchNode,
        bridge: Any = None,
    ) -> bool:
        """Check if a search node represents a proved goal.

        Checks in order:
        1. Axiom: goal matches known axiom schema (no bridge needed)
        2. Assumption: goal is in context (no bridge needed)
        3. Bridge verification: call bridge.label_formula if provided

        Parameters
        ----------
        node:
            Search node to check.
        bridge:
            Optional bridge for external verification.

        Returns
        -------
        bool
            True iff the goal is proved.
        """
        if is_axiom(node.goal):
            return True
        if is_assumption(node.context, node.goal):
            return True

        if bridge is not None:
            try:
                result = bridge.label_formula(node.goal)
                label = result.get("label") if isinstance(result, dict) else None
                return label == "valid"
            except Exception:
                pass

        return False


# ---------------------------------------------------------------------------
# Phase 4: A/B Comparison Infrastructure
# ---------------------------------------------------------------------------


@dataclass
class FormulaResult:
    """Result for a single formula in a comparison run.

    Parameters
    ----------
    formula:
        The formula that was searched.
    baseline_proved:
        Whether the baseline (rule-based) searcher proved it.
    neural_proved:
        Whether the neural-augmented searcher proved it.
    baseline_stats:
        Search statistics from the baseline run.
    neural_stats:
        Search statistics from the neural run.
    """

    formula: dict[str, Any]
    baseline_proved: bool
    neural_proved: bool
    baseline_stats: SearchStats
    neural_stats: SearchStats


@dataclass
class ComparisonResult:
    """Result of a baseline vs. neural search comparison.

    Parameters
    ----------
    per_formula:
        Per-formula paired results.
    baseline_proof_rate:
        Fraction of formulas proved by baseline.
    neural_proof_rate:
        Fraction of formulas proved by neural searcher.
    baseline_mean_expansions:
        Mean number of node expansions for baseline runs.
    neural_mean_expansions:
        Mean number of node expansions for neural runs.
    baseline_mean_time:
        Mean wall-clock time for baseline runs (seconds).
    neural_mean_time:
        Mean wall-clock time for neural runs (seconds).
    mcnemar_chi2:
        Chi-squared statistic from McNemar's test.
    mcnemar_p_value:
        P-value from McNemar's test (None if scipy unavailable or b+c==0).
    contingency_table:
        2x2 contingency table [[a, b], [c, d]] where:
        a = both proved, b = baseline-only, c = neural-only, d = neither.
    """

    per_formula: list[FormulaResult]
    baseline_proof_rate: float
    neural_proof_rate: float
    baseline_mean_expansions: float
    neural_mean_expansions: float
    baseline_mean_time: float
    neural_mean_time: float
    mcnemar_chi2: float
    mcnemar_p_value: float | None
    contingency_table: list[list[int]]


def run_comparison(
    baseline_searcher: PythonBestFirstSearch,
    neural_searcher: PythonBestFirstSearch,
    formulas: list[dict[str, Any]],
    context: list[dict[str, Any]] | None = None,
    bridge: Any = None,
) -> ComparisonResult:
    """Run A/B comparison between baseline and neural search.

    Runs both searchers on each formula and collects paired outcomes
    for statistical comparison via McNemar's test.

    McNemar's test statistic:
    chi2 = (b - c)^2 / (b + c)
    where b = baseline_only_solved, c = neural_only_solved.

    Parameters
    ----------
    baseline_searcher:
        Searcher without value network (pure rule-based).
    neural_searcher:
        Searcher with value network enabled.
    formulas:
        List of goal formula JSON dicts to evaluate on.
    context:
        Shared initial context for all formulas. Defaults to empty.
    bridge:
        Optional bridge for leaf verification.

    Returns
    -------
    ComparisonResult
        Aggregate metrics and statistical test results.
    """
    ctx = context or []
    per_formula: list[FormulaResult] = []

    for formula in formulas:
        baseline_result = baseline_searcher.search(ctx, formula, bridge)
        neural_result = neural_searcher.search(ctx, formula, bridge)

        per_formula.append(
            FormulaResult(
                formula=formula,
                baseline_proved=baseline_result.proved,
                neural_proved=neural_result.proved,
                baseline_stats=baseline_result.stats,
                neural_stats=neural_result.stats,
            )
        )

    n = len(per_formula)
    if n == 0:
        return ComparisonResult(
            per_formula=[],
            baseline_proof_rate=0.0,
            neural_proof_rate=0.0,
            baseline_mean_expansions=0.0,
            neural_mean_expansions=0.0,
            baseline_mean_time=0.0,
            neural_mean_time=0.0,
            mcnemar_chi2=0.0,
            mcnemar_p_value=None,
            contingency_table=[[0, 0], [0, 0]],
        )

    # Aggregate metrics
    baseline_proved = sum(1 for r in per_formula if r.baseline_proved)
    neural_proved_count = sum(1 for r in per_formula if r.neural_proved)
    both_proved = sum(1 for r in per_formula if r.baseline_proved and r.neural_proved)
    baseline_only = sum(
        1 for r in per_formula if r.baseline_proved and not r.neural_proved
    )
    neural_only = sum(
        1 for r in per_formula if not r.baseline_proved and r.neural_proved
    )
    neither = sum(
        1 for r in per_formula if not r.baseline_proved and not r.neural_proved
    )

    baseline_proof_rate = baseline_proved / n
    neural_proof_rate = neural_proved_count / n
    baseline_mean_exp = sum(r.baseline_stats.expanded for r in per_formula) / n
    neural_mean_exp = sum(r.neural_stats.expanded for r in per_formula) / n
    baseline_mean_time = sum(r.baseline_stats.wall_clock_seconds for r in per_formula) / n
    neural_mean_time = sum(r.neural_stats.wall_clock_seconds for r in per_formula) / n

    # McNemar's test: chi2 = (b - c)^2 / (b + c)
    b = baseline_only
    c = neural_only
    contingency_table = [[both_proved, b], [c, neither]]

    mcnemar_chi2 = 0.0
    mcnemar_p_value: float | None = None

    if b + c > 0:
        mcnemar_chi2 = (b - c) ** 2 / (b + c)
        try:
            from scipy.stats import chi2 as scipy_chi2  # noqa: PLC0415

            # McNemar's test uses chi2 with 1 degree of freedom
            mcnemar_p_value = float(1.0 - scipy_chi2.cdf(mcnemar_chi2, df=1))
        except ImportError:
            # scipy not available; p-value left as None
            pass

    return ComparisonResult(
        per_formula=per_formula,
        baseline_proof_rate=baseline_proof_rate,
        neural_proof_rate=neural_proof_rate,
        baseline_mean_expansions=baseline_mean_exp,
        neural_mean_expansions=neural_mean_exp,
        baseline_mean_time=baseline_mean_time,
        neural_mean_time=neural_mean_time,
        mcnemar_chi2=mcnemar_chi2,
        mcnemar_p_value=mcnemar_p_value,
        contingency_table=contingency_table,
    )


def run_benchmark_comparison(
    formulas: list[dict[str, Any]],
    value_net: ValueNetworkProtocol | None = None,
    alpha: float = 5.0,
    temperature: float = 1.5,
    max_expansions: int = 10_000,
    context: list[dict[str, Any]] | None = None,
    bridge: Any = None,
) -> ComparisonResult:
    """CLI-compatible entry point for benchmark comparison.

    Creates baseline and neural searchers and runs a full comparison.

    Parameters
    ----------
    formulas:
        List of goal formula JSON dicts to evaluate.
    value_net:
        Value network for neural-augmented search. If None, both
        searchers use pure rule-based scoring (identical results).
    alpha:
        Neural bonus weight.
    temperature:
        Temperature for sigmoid scaling.
    max_expansions:
        Maximum node expansions per search.
    context:
        Shared initial proof context.
    bridge:
        Optional bridge for leaf verification.

    Returns
    -------
    ComparisonResult
        Full comparison results with McNemar statistics.
    """
    baseline = PythonBestFirstSearch(
        value_net=None,
        alpha=alpha,
        temperature=temperature,
        max_expansions=max_expansions,
    )
    neural = PythonBestFirstSearch(
        value_net=value_net,
        alpha=alpha,
        temperature=temperature,
        max_expansions=max_expansions,
    )
    return run_comparison(baseline, neural, formulas, context=context, bridge=bridge)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _formula_tag(formula: dict[str, Any]) -> str:
    """Extract the tag from a formula dict, with fallback."""
    return str(formula.get("tag", "unknown"))


def _formula_hash(formula: dict[str, Any]) -> str:
    """Compute a hash string for a formula dict for deduplication."""
    # Use sorted repr for consistent hashing
    try:
        import json  # noqa: PLC0415

        return json.dumps(formula, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError):
        return repr(formula)


def _context_hash(context: list[dict[str, Any]]) -> int:
    """Compute a hash for a context list."""
    return hash(tuple(_formula_hash(f) for f in context))


def _extract_proof_path(
    node: SearchNode,
) -> list[tuple[str, dict[str, Any]]]:
    """Extract the proof path from a leaf node to the root.

    Traverses parent pointers to reconstruct the sequence of rule
    applications that led to this node.

    Parameters
    ----------
    node:
        Leaf node at the end of a successful proof search.

    Returns
    -------
    list[tuple[str, dict]]
        Ordered list of (action, goal) pairs from root to leaf.
    """
    path: list[tuple[str, dict[str, Any]]] = []
    current: SearchNode | None = node
    while current is not None:
        action = current.action or "root"
        path.append((action, current.goal))
        current = current.parent
    path.reverse()
    return path
