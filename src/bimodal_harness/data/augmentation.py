"""Data augmentation strategies for supervised proof step training data.

Provides two augmentation strategies that expand raw proof step triples extracted
from BimodalLogic theorem DerivationTrees:

1. **Temporal dual augmentation**: For each step whose goal formula contains a
   ``untl`` (Until) or ``snce`` (Since) node, generate the temporally dual step
   by swapping ``untl`` <-> ``snce`` throughout the formula JSON.  The dual of
   an Until-formula is a Since-formula and vice versa, reflecting the past/future
   symmetry of the BX axiom system.  Axiom names are also swapped where they
   come in future/past pairs (e.g. ``serial_future`` <-> ``serial_past``).

2. **Context variation augmentation**: For steps with an empty context
   (``[] |- phi``), generate variants ``[psi1, ..., psik] |- phi`` by adding
   synthetic context formulas and assigning the ``weakening`` rule (action index
   48).  Up to ``max_context_additions`` additional formulas are added per step,
   drawn from a small set of propositionally simple formulas.

Both strategies produce new ``ProofStepRecord`` objects with fresh ``step_id``
values (UUID4) and an extra ``augmentation_source`` field tracked via a
parallel list rather than modifying the frozen dataclass.

Public API
----------
- temporal_dual_augmentation(records) -> list[tuple[ProofStepRecord, str]]
- context_variation_augmentation(records, ...) -> list[tuple[ProofStepRecord, str]]
- augment_all(records, ...) -> list[tuple[ProofStepRecord, str]]
- split_dataset(records, train_frac, val_frac, ...) -> tuple[list, list, list]
- augmented_statistics(augmented_records) -> dict
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from bimodal_harness.schema.actions import ACTION_TO_INDEX, step_to_action_index
from bimodal_harness.schema.records import ProofStepRecord

# ---------------------------------------------------------------------------
# Temporal dual axiom mapping
# ---------------------------------------------------------------------------

# Pairs of (future_axiom, past_axiom) from the BX temporal axioms (Layer 3).
# When swapping untl <-> snce in a goal formula, if the step's axiom_name is
# a future axiom it becomes the corresponding past axiom, and vice versa.
_TEMPORAL_AXIOM_DUALS: dict[str, str] = {
    "serial_future": "serial_past",
    "serial_past": "serial_future",
    "left_mono_until_G": "left_mono_since_H",
    "left_mono_since_H": "left_mono_until_G",
    "right_mono_until": "right_mono_since",
    "right_mono_since": "right_mono_until",
    "connect_future": "connect_past",
    "connect_past": "connect_future",
    "enrichment_until": "enrichment_since",
    "enrichment_since": "enrichment_until",
    "self_accum_until": "self_accum_since",
    "self_accum_since": "self_accum_until",
    "absorb_until": "absorb_since",
    "absorb_since": "absorb_until",
    "linear_until": "linear_since",
    "linear_since": "linear_until",
    "until_F": "since_P",
    "since_P": "until_F",
    "temp_linearity": "temp_linearity_past",
    "temp_linearity_past": "temp_linearity",
    "F_until_equiv": "P_since_equiv",
    "P_since_equiv": "F_until_equiv",
    # Uniformity: discrete symmetry swaps fwd <-> bwd (future <-> past direction)
    "discrete_symm_fwd": "discrete_symm_bwd",
    "discrete_symm_bwd": "discrete_symm_fwd",
    "discrete_propagate_fwd": "discrete_propagate_bwd",
    "discrete_propagate_bwd": "discrete_propagate_fwd",
}


def _box_child(formula: dict[str, Any]) -> dict[str, Any]:
    """Return the child formula of a box node.

    Handles both ``"child"`` (canonical DataExport.lean format) and ``"arg"``
    (legacy/fixture format) field names for the box constructor.

    Raises
    ------
    KeyError
        If neither ``"child"`` nor ``"arg"`` key is present.
    """
    if "child" in formula:
        return formula["child"]
    return formula["arg"]


def _formula_has_temporal(formula: dict[str, Any]) -> bool:
    """Return True if the formula JSON contains any 'untl' or 'snce' node."""
    tag = formula.get("tag", "")
    if tag in ("untl", "snce"):
        return True
    if tag == "imp":
        return _formula_has_temporal(formula["left"]) or _formula_has_temporal(formula["right"])
    if tag == "box":
        return _formula_has_temporal(_box_child(formula))
    if tag in ("atom", "bot"):
        return False
    # Unknown tag: conservative return True to avoid missing temporal nodes
    return False


def _swap_temporal(formula: dict[str, Any]) -> dict[str, Any]:
    """Recursively swap all ``untl`` <-> ``snce`` tags in a formula JSON tree.

    Preserves all other fields (``event``, ``guard``, ``left``, ``right``,
    ``child``, ``name``) intact.  Creates new dict objects so the original
    formula is not modified.

    Parameters
    ----------
    formula:
        A formula JSON dict (DataExport.lean Formula.toJson format).

    Returns
    -------
    dict[str, Any]
        A new formula JSON dict with all temporal operators swapped.
    """
    tag = formula.get("tag", "")
    if tag == "atom":
        return dict(formula)
    if tag == "bot":
        return {"tag": "bot"}
    if tag == "imp":
        return {
            "tag": "imp",
            "left": _swap_temporal(formula["left"]),
            "right": _swap_temporal(formula["right"]),
        }
    if tag == "box":
        # Preserve the original field name ("child" or "arg") for compatibility.
        child_key = "child" if "child" in formula else "arg"
        return {"tag": "box", child_key: _swap_temporal(formula[child_key])}
    if tag == "untl":
        return {
            "tag": "snce",
            "event": _swap_temporal(formula["event"]),
            "guard": _swap_temporal(formula["guard"]),
        }
    if tag == "snce":
        return {
            "tag": "untl",
            "event": _swap_temporal(formula["event"]),
            "guard": _swap_temporal(formula["guard"]),
        }
    # Pass through unknown tags unchanged
    return dict(formula)


def _dual_axiom_name(axiom_name: str | None) -> str | None:
    """Return the dual axiom name, or the same name if no dual exists."""
    if axiom_name is None:
        return None
    return _TEMPORAL_AXIOM_DUALS.get(axiom_name, axiom_name)


def _dual_pretty(goal_pretty: str) -> str:
    """Generate a simple dual-annotated pretty string.

    Since regenerating a true pretty-print from the swapped formula JSON
    requires the full formula printer, we annotate with a ``[dual]`` suffix
    to indicate this string is derived.  The neural network primarily uses
    goal_json; goal_pretty is for human inspection.
    """
    return goal_pretty + " [dual]"


# ---------------------------------------------------------------------------
# Context formula bank for context variation augmentation
# ---------------------------------------------------------------------------

# Simple propositional formulas used as synthetic context additions.
# These are kept intentionally simple (atom, bot, imp of atoms) to avoid
# introducing deeply nested formula trees that might confuse the model.
_CONTEXT_FORMULA_BANK: list[tuple[str, str]] = [
    # (goal_pretty, goal_json as dict)
    ("p", "p"),
    ("q", "q"),
    ("r", "r"),
    ("⊥", "⊥"),
    ("p → q", "p → q"),
    ("q → p", "q → p"),
    ("p → p", "p → p"),
]

# Pre-built formula strings for context injection (pretty-print form only,
# since context is stored as tuple[str, ...]).
_CONTEXT_STRINGS: list[str] = [
    "p",
    "q",
    "r",
    "p → q",
    "q → p",
    "p → p",
]


# ---------------------------------------------------------------------------
# Augmentation functions
# ---------------------------------------------------------------------------


def temporal_dual_augmentation(
    records: list[ProofStepRecord],
) -> list[tuple[ProofStepRecord, str]]:
    """Generate temporal dual steps for all steps containing temporal operators.

    For each record whose ``goal_json`` contains at least one ``untl`` or
    ``snce`` node, creates a new ``ProofStepRecord`` with:

    - A fresh UUID4 ``step_id`` (format: ``"<orig_step_id>__dual"``)
    - ``goal_json`` with all ``untl`` <-> ``snce`` nodes swapped
    - ``goal_pretty`` annotated with ``[dual]`` suffix
    - ``axiom_name`` swapped to its temporal dual (when applicable)
    - ``action_index`` recomputed from the dual (rule, axiom_name) pair
    - All other fields copied from the original record

    Parameters
    ----------
    records:
        Source proof step records (e.g. from ``load_proof_steps``).

    Returns
    -------
    list[tuple[ProofStepRecord, str]]
        List of (augmented_record, augmentation_source) pairs.
        ``augmentation_source`` is ``"temporal_dual:<orig_step_id>"``.
    """
    result: list[tuple[ProofStepRecord, str]] = []

    for record in records:
        if not _formula_has_temporal(record.goal_json):
            continue

        dual_goal_json = _swap_temporal(record.goal_json)
        dual_goal_pretty = _dual_pretty(record.goal_pretty)

        # Swap axiom name and recompute action_index.
        dual_axiom_name = _dual_axiom_name(record.axiom_name)
        try:
            dual_action_index = step_to_action_index(record.rule, dual_axiom_name)
        except (KeyError, ValueError):
            # If the dual axiom isn't in the action space (shouldn't happen),
            # keep the original action_index to avoid creating an invalid record.
            dual_action_index = record.action_index
            dual_axiom_name = record.axiom_name

        # Swap temporal in all subgoals too.
        dual_subgoals = tuple(
            _swap_temporal(sg) for sg in record.subgoals
        )

        # Build new step_id: append __dual to original step_id.
        new_step_id = f"{record.step_id}__dual"

        augmented = ProofStepRecord(
            step_id=new_step_id,
            theorem_name=record.theorem_name,
            context=record.context,
            goal_json=dual_goal_json,
            goal_pretty=dual_goal_pretty,
            rule=record.rule,
            axiom_name=dual_axiom_name,
            action_index=dual_action_index,
            subgoals=dual_subgoals,
            depth=record.depth,
            frame_class=record.frame_class,
            proof_height=record.proof_height,
        )
        source = f"temporal_dual:{record.step_id}"
        result.append((augmented, source))

    return result


def context_variation_augmentation(
    records: list[ProofStepRecord],
    *,
    max_context_additions: int = 3,
) -> list[tuple[ProofStepRecord, str]]:
    """Generate context variation steps via the weakening rule.

    For each record with an empty context (``context == ()``), generates
    variants with 1 to ``max_context_additions`` additional context formulas
    added from ``_CONTEXT_STRINGS``.  Each variant uses the ``weakening``
    rule (action index 48) and produces a new step at the same ``depth`` as
    the original but with a non-empty context.

    The ``subgoals`` of the new weakening step is the original goal formula,
    modeling that weakening produces a subgoal of the same formula in a
    context-free sequent.

    Parameters
    ----------
    records:
        Source proof step records.
    max_context_additions:
        Maximum number of context formulas to add per source record.
        Must be in [1, len(_CONTEXT_STRINGS)].

    Returns
    -------
    list[tuple[ProofStepRecord, str]]
        List of (augmented_record, augmentation_source) pairs.
        ``augmentation_source`` is ``"context_variation:<orig_step_id>:<k>ctx"``.
    """
    if max_context_additions < 1:
        raise ValueError(
            f"max_context_additions must be >= 1, got {max_context_additions}"
        )
    max_context_additions = min(max_context_additions, len(_CONTEXT_STRINGS))

    weakening_index = ACTION_TO_INDEX["weakening"]
    result: list[tuple[ProofStepRecord, str]] = []

    for record in records:
        # Only augment steps that originally have an empty context.
        if record.context:
            continue

        for k in range(1, max_context_additions + 1):
            # Take the first k context formulas from the bank.
            added_ctx = tuple(_CONTEXT_STRINGS[:k])

            new_step_id = f"{record.step_id}__ctx{k}"
            new_context = added_ctx

            # The weakening step's subgoal is the original goal (same formula,
            # now to be proved without the added context hypotheses).
            new_subgoals = (record.goal_json,)

            augmented = ProofStepRecord(
                step_id=new_step_id,
                theorem_name=record.theorem_name,
                context=new_context,
                goal_json=record.goal_json,
                goal_pretty=record.goal_pretty,
                rule="weakening",
                axiom_name=None,
                action_index=weakening_index,
                subgoals=new_subgoals,
                depth=record.depth,
                frame_class=record.frame_class,
                proof_height=record.proof_height,
            )
            source = f"context_variation:{record.step_id}:{k}ctx"
            result.append((augmented, source))

    return result


def augment_all(
    records: list[ProofStepRecord],
    *,
    max_context_additions: int = 3,
    include_originals: bool = True,
) -> list[tuple[ProofStepRecord, str]]:
    """Apply all augmentation strategies and combine with original records.

    Combines:
    1. Original records (tagged ``"original"``), if ``include_originals=True``.
    2. Temporal dual augmented records (tagged ``"temporal_dual:..."``).
    3. Context variation augmented records (tagged ``"context_variation:..."``).

    Parameters
    ----------
    records:
        Source proof step records (from ``load_proof_steps``).
    max_context_additions:
        Maximum context formulas added per step in context variation.
        Passed through to ``context_variation_augmentation``.
    include_originals:
        If True (default), include original records tagged as ``"original"``.

    Returns
    -------
    list[tuple[ProofStepRecord, str]]
        Combined list of (record, augmentation_source) tuples.
        Originals come first (if included), then temporal duals, then
        context variations.
    """
    combined: list[tuple[ProofStepRecord, str]] = []

    if include_originals:
        combined.extend((r, "original") for r in records)

    temporal_duals = temporal_dual_augmentation(records)
    combined.extend(temporal_duals)

    ctx_variations = context_variation_augmentation(
        records, max_context_additions=max_context_additions
    )
    combined.extend(ctx_variations)

    return combined


def augmented_statistics(
    augmented_records: list[tuple[ProofStepRecord, str]],
) -> dict:
    """Compute summary statistics for an augmented dataset.

    Parameters
    ----------
    augmented_records:
        List of (ProofStepRecord, augmentation_source) pairs as returned by
        ``augment_all``, ``temporal_dual_augmentation``, or
        ``context_variation_augmentation``.

    Returns
    -------
    dict
        Statistics dictionary with keys:
        - ``total_steps``: total number of records (int)
        - ``augmentation_source_counts``: Counter of source strings
        - ``unique_step_ids``: count of distinct step_id values (int)
        - ``duplicate_step_ids``: count of duplicate step_ids (int)
        - ``action_index_coverage``: number of distinct action indices (int)
        - ``proof_height_distribution``: dict mapping height -> count
        - ``rule_distribution``: dict mapping rule name -> count
    """
    if not augmented_records:
        return {
            "total_steps": 0,
            "augmentation_source_counts": {},
            "unique_step_ids": 0,
            "duplicate_step_ids": 0,
            "action_index_coverage": 0,
            "proof_height_distribution": {},
            "rule_distribution": {},
        }

    records = [r for r, _ in augmented_records]
    sources = [s for _, s in augmented_records]

    step_ids = [r.step_id for r in records]
    unique_ids = set(step_ids)
    duplicate_count = len(step_ids) - len(unique_ids)

    action_indices = set(r.action_index for r in records)

    height_dist: dict[int, int] = {}
    for r in records:
        height_dist[r.proof_height] = height_dist.get(r.proof_height, 0) + 1

    rule_dist: dict[str, int] = {}
    for r in records:
        rule_dist[r.rule] = rule_dist.get(r.rule, 0) + 1

    # Normalize source labels to top-level category for readability.
    source_categories = Counter(
        s.split(":")[0] if ":" in s else s for s in sources
    )

    return {
        "total_steps": len(records),
        "augmentation_source_counts": dict(source_categories),
        "unique_step_ids": len(unique_ids),
        "duplicate_step_ids": duplicate_count,
        "action_index_coverage": len(action_indices),
        "proof_height_distribution": dict(sorted(height_dist.items())),
        "rule_distribution": dict(sorted(rule_dist.items())),
    }


# ---------------------------------------------------------------------------
# Dataset split utility
# ---------------------------------------------------------------------------


def split_dataset(
    records: list[tuple[ProofStepRecord, str]],
    *,
    train_frac: float = 0.8,
    val_frac: float = 0.1,
    seed: int = 42,
    stratify_by_height: bool = True,
) -> tuple[
    list[tuple[ProofStepRecord, str]],
    list[tuple[ProofStepRecord, str]],
    list[tuple[ProofStepRecord, str]],
]:
    """Split augmented records into train, val, and test sets.

    Performs an 80/10/10 split (by default) stratified by proof height when
    ``stratify_by_height=True``.  Within each stratum, records are shuffled
    using ``seed`` for reproducibility.

    The test fraction is derived as ``1 - train_frac - val_frac``.

    Parameters
    ----------
    records:
        List of (ProofStepRecord, augmentation_source) pairs to split.
    train_frac:
        Fraction of records assigned to the training split (default 0.8).
    val_frac:
        Fraction of records assigned to the validation split (default 0.1).
    seed:
        Random seed for shuffling within each stratum (default 42).
    stratify_by_height:
        If True (default), split is stratified by ``proof_height`` field of
        each ``ProofStepRecord``.  If False, a simple random split is used.

    Returns
    -------
    tuple[list, list, list]
        ``(train, val, test)`` splits.

    Raises
    ------
    ValueError
        If ``train_frac + val_frac >= 1.0`` or fractions are out of (0, 1).
    """
    if train_frac <= 0 or train_frac >= 1:
        raise ValueError(f"train_frac must be in (0, 1), got {train_frac}")
    if val_frac <= 0 or val_frac >= 1:
        raise ValueError(f"val_frac must be in (0, 1), got {val_frac}")
    if train_frac + val_frac >= 1.0:
        raise ValueError(
            f"train_frac + val_frac must be < 1.0, got {train_frac + val_frac}"
        )

    import random

    rng = random.Random(seed)

    train: list[tuple[ProofStepRecord, str]] = []
    val: list[tuple[ProofStepRecord, str]] = []
    test: list[tuple[ProofStepRecord, str]] = []

    if stratify_by_height and records:
        # Group by proof_height.
        from collections import defaultdict

        strata: dict[int, list[tuple[ProofStepRecord, str]]] = defaultdict(list)
        for item in records:
            strata[item[0].proof_height].append(item)

        for height in sorted(strata):
            stratum = strata[height]
            rng.shuffle(stratum)
            n = len(stratum)
            n_train = max(1, round(n * train_frac)) if n >= 3 else n
            n_val = max(0, round(n * val_frac)) if n >= 3 else 0
            # Adjust n_train to ensure n_val + n_test > 0 for large strata.
            if n_train + n_val > n:
                n_val = max(0, n - n_train)

            train.extend(stratum[:n_train])
            val.extend(stratum[n_train : n_train + n_val])
            test.extend(stratum[n_train + n_val :])
    else:
        shuffled = list(records)
        rng.shuffle(shuffled)
        n = len(shuffled)
        n_train = round(n * train_frac)
        n_val = round(n * val_frac)
        train = shuffled[:n_train]
        val = shuffled[n_train : n_train + n_val]
        test = shuffled[n_train + n_val :]

    return train, val, test
