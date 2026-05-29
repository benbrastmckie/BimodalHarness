"""Synthetic proof step data generator for policy network bootstrap training.

Generates labeled ProofStepRecord objects covering all 49 actions (42 axiom
constructors + 7 inference rules) with formula structures matching each action's
applicability schema.

Public API
----------
- generate_synthetic_proof_steps(n_steps, seed, frame_class) -> list[ProofStepRecord]
"""

from __future__ import annotations

import random
import uuid
from typing import Any

from bimodal_harness.data.augmentation import augment_all
from bimodal_harness.schema.actions import (
    AXIOM_ACTIONS,
    FRAME_CLASS_MASKS,
    RULE_ACTIONS,
    step_to_action_index,
)
from bimodal_harness.schema.records import ProofStepRecord

# ---------------------------------------------------------------------------
# Formula JSON helpers
# ---------------------------------------------------------------------------


def _atom(name: str) -> dict[str, Any]:
    return {"tag": "atom", "name": name}


def _bot() -> dict[str, Any]:
    return {"tag": "bot"}


def _imp(left: dict, right: dict) -> dict[str, Any]:
    return {"tag": "imp", "left": left, "right": right}


def _box(child: dict) -> dict[str, Any]:
    return {"tag": "box", "child": child}


def _untl(event: dict, guard: dict) -> dict[str, Any]:
    return {"tag": "untl", "event": event, "guard": guard}


def _snce(event: dict, guard: dict) -> dict[str, Any]:
    return {"tag": "snce", "event": event, "guard": guard}


# Atom names used in formula generation
_ATOMS = ["p", "q", "r", "s", "t"]


def _formula_pretty(f: dict[str, Any]) -> str:
    """Generate a simple human-readable string for a formula JSON."""
    tag = f.get("tag", "")
    if tag == "atom":
        return f["name"]
    if tag == "bot":
        return "⊥"
    if tag == "imp":
        return f"({_formula_pretty(f['left'])} → {_formula_pretty(f['right'])})"
    if tag == "box":
        return f"□({_formula_pretty(f['child'])})"
    if tag == "untl":
        return f"U({_formula_pretty(f['event'])}, {_formula_pretty(f['guard'])})"
    if tag == "snce":
        return f"S({_formula_pretty(f['event'])}, {_formula_pretty(f['guard'])})"
    return "?"


# ---------------------------------------------------------------------------
# Goal formula schemas for each of the 42 axioms
# ---------------------------------------------------------------------------

# Each entry is a callable(rng) -> goal_json
# We define exact schemas reflecting each axiom's formula pattern.

def _make_axiom_goal_generators() -> dict[str, list]:
    """Build a dict mapping axiom_name -> list of goal formula generators."""
    gens: dict[str, list] = {}

    # Layer 1: Propositional axioms
    def prop_k(rng):
        p, q, r = rng.sample(_ATOMS, 3)
        phi, psi, chi = _atom(p), _atom(q), _atom(r)
        # (phi→(psi→chi))→((phi→psi)→(phi→chi))
        return _imp(_imp(phi, _imp(psi, chi)), _imp(_imp(phi, psi), _imp(phi, chi)))

    def prop_s(rng):
        p, q = rng.sample(_ATOMS, 2)
        phi, psi = _atom(p), _atom(q)
        # phi→(psi→phi)
        return _imp(phi, _imp(psi, phi))

    def ex_falso(rng):
        p = rng.choice(_ATOMS)
        # ⊥→phi
        return _imp(_bot(), _atom(p))

    def peirce(rng):
        p, q = rng.sample(_ATOMS, 2)
        phi, psi = _atom(p), _atom(q)
        # ((phi→psi)→phi)→phi
        return _imp(_imp(_imp(phi, psi), phi), phi)

    gens["prop_k"] = [prop_k]
    gens["prop_s"] = [prop_s]
    gens["ex_falso"] = [ex_falso]
    gens["peirce"] = [peirce]

    # Layer 2: S5 Modal axioms
    def modal_t(rng):
        p = rng.choice(_ATOMS)
        # □phi→phi
        return _imp(_box(_atom(p)), _atom(p))

    def modal_4(rng):
        p = rng.choice(_ATOMS)
        # □phi→□□phi
        return _imp(_box(_atom(p)), _box(_box(_atom(p))))

    def modal_b(rng):
        p = rng.choice(_ATOMS)
        # phi→□◇phi  (◇phi = ¬□¬phi ≈ imp(box(imp(phi,bot)), bot) but simplified)
        # For our purposes: phi → box(imp(box(imp(phi, bot)), bot))
        phi = _atom(p)
        neg_phi = _imp(phi, _bot())
        box_neg_phi = _box(neg_phi)
        neg_box_neg_phi = _imp(box_neg_phi, _bot())
        box_neg_box_neg_phi = _box(neg_box_neg_phi)
        return _imp(phi, box_neg_box_neg_phi)

    def modal_5_collapse(rng):
        p = rng.choice(_ATOMS)
        # ◇□phi→□phi  ≈  imp(imp(box(imp(box(phi), bot)), bot), box(phi))
        phi = _atom(p)
        box_phi = _box(phi)
        neg_box_phi = _imp(box_phi, _bot())
        box_neg_box_phi = _box(neg_box_phi)
        neg_box_neg_box_phi = _imp(box_neg_box_phi, _bot())
        return _imp(neg_box_neg_box_phi, box_phi)

    def modal_k_dist(rng):
        p, q = rng.sample(_ATOMS, 2)
        phi, psi = _atom(p), _atom(q)
        # □(phi→psi)→(□phi→□psi)
        return _imp(_box(_imp(phi, psi)), _imp(_box(phi), _box(psi)))

    gens["modal_t"] = [modal_t]
    gens["modal_4"] = [modal_4]
    gens["modal_b"] = [modal_b]
    gens["modal_5_collapse"] = [modal_5_collapse]
    gens["modal_k_dist"] = [modal_k_dist]

    # Layer 3: BX Temporal axioms (22 axioms)
    def serial_future(rng):
        # ⊤→F(⊤) but we use imp(p, untl(p, bot)) as a simplified version
        # Actually serial_future: ⊤ → U(⊤, ⊤) -- there exists a future moment
        p = rng.choice(_ATOMS)
        return _imp(_atom(p), _untl(_atom(p), _atom(p)))

    def serial_past(rng):
        p = rng.choice(_ATOMS)
        return _imp(_atom(p), _snce(_atom(p), _atom(p)))

    def left_mono_until_G(rng):
        p, q, r = rng.sample(_ATOMS, 3)
        phi, chi, psi = _atom(p), _atom(q), _atom(r)
        # G(phi→chi)→(psi U phi → psi U chi)
        g_phi_chi = _box(_imp(phi, chi))  # □ approximates G here
        return _imp(g_phi_chi, _imp(_untl(psi, phi), _untl(psi, chi)))

    def left_mono_since_H(rng):
        p, q, r = rng.sample(_ATOMS, 3)
        phi, chi, psi = _atom(p), _atom(q), _atom(r)
        h_phi_chi = _box(_imp(phi, chi))
        return _imp(h_phi_chi, _imp(_snce(psi, phi), _snce(psi, chi)))

    def right_mono_until(rng):
        p, q, r = rng.sample(_ATOMS, 3)
        phi, psi, chi = _atom(p), _atom(q), _atom(r)
        # G(phi→psi)→(phi U chi → psi U chi)
        g_phi_psi = _box(_imp(phi, psi))
        return _imp(g_phi_psi, _imp(_untl(phi, chi), _untl(psi, chi)))

    def right_mono_since(rng):
        p, q, r = rng.sample(_ATOMS, 3)
        phi, psi, chi = _atom(p), _atom(q), _atom(r)
        h_phi_psi = _box(_imp(phi, psi))
        return _imp(h_phi_psi, _imp(_snce(phi, chi), _snce(psi, chi)))

    def connect_future(rng):
        p = rng.choice(_ATOMS)
        phi = _atom(p)
        # phi → G(P(phi)) : simplified as phi → box(snce(phi, phi))
        return _imp(phi, _box(_snce(phi, phi)))

    def connect_past(rng):
        p = rng.choice(_ATOMS)
        phi = _atom(p)
        # phi → H(F(phi)) : simplified as phi → box(untl(phi, phi))
        return _imp(phi, _box(_untl(phi, phi)))

    def enrichment_until(rng):
        p, q, r = rng.sample(_ATOMS, 3)
        phi, psi, chi = _atom(p), _atom(q), _atom(r)
        # p ∧ U(psi,phi) → U(psi ∧ S(p,phi), phi) - simplified
        lhs = _untl(psi, phi)
        rhs = _untl(_imp(psi, _snce(chi, phi)), phi)
        return _imp(lhs, rhs)

    def enrichment_since(rng):
        p, q, r = rng.sample(_ATOMS, 3)
        phi, psi, chi = _atom(p), _atom(q), _atom(r)
        lhs = _snce(psi, phi)
        rhs = _snce(_imp(psi, _untl(chi, phi)), phi)
        return _imp(lhs, rhs)

    def self_accum_until(rng):
        p, q = rng.sample(_ATOMS, 2)
        psi, phi = _atom(p), _atom(q)
        # U(psi,phi) → U(psi, phi ∧ U(psi,phi)) - simplified
        return _imp(_untl(psi, phi), _untl(psi, _imp(phi, _untl(psi, phi))))

    def self_accum_since(rng):
        p, q = rng.sample(_ATOMS, 2)
        psi, phi = _atom(p), _atom(q)
        return _imp(_snce(psi, phi), _snce(psi, _imp(phi, _snce(psi, phi))))

    def absorb_until(rng):
        p, q = rng.sample(_ATOMS, 2)
        phi, psi = _atom(p), _atom(q)
        return _imp(_untl(_imp(phi, _untl(psi, phi)), phi), _untl(psi, phi))

    def absorb_since(rng):
        p, q = rng.sample(_ATOMS, 2)
        phi, psi = _atom(p), _atom(q)
        return _imp(_snce(_imp(phi, _snce(psi, phi)), phi), _snce(psi, phi))

    def linear_until(rng):
        p, q, r, s = rng.sample(_ATOMS, 4)
        psi, phi, theta, chi = _atom(p), _atom(q), _atom(r), _atom(s)
        # U(psi,phi) ∧ U(theta,chi) → ... simplified to just Until formulas
        lhs = _imp(_untl(psi, phi), _untl(theta, chi))
        rhs = _untl(psi, phi)
        return _imp(lhs, rhs)

    def linear_since(rng):
        p, q, r, s = rng.sample(_ATOMS, 4)
        psi, phi, theta, chi = _atom(p), _atom(q), _atom(r), _atom(s)
        lhs = _imp(_snce(psi, phi), _snce(theta, chi))
        rhs = _snce(psi, phi)
        return _imp(lhs, rhs)

    def until_F(rng):
        p, q = rng.sample(_ATOMS, 2)
        psi, phi = _atom(p), _atom(q)
        # U(psi,phi) → F(psi) ; F(psi) = U(psi, ⊤) ≈ U(psi, psi)
        return _imp(_untl(psi, phi), _untl(psi, psi))

    def since_P(rng):
        p, q = rng.sample(_ATOMS, 2)
        psi, phi = _atom(p), _atom(q)
        return _imp(_snce(psi, phi), _snce(psi, psi))

    def temp_linearity(rng):
        p, q = rng.sample(_ATOMS, 2)
        phi, psi = _atom(p), _atom(q)
        return _imp(_untl(phi, phi), _imp(_untl(psi, psi), _untl(phi, psi)))

    def temp_linearity_past(rng):
        p, q = rng.sample(_ATOMS, 2)
        phi, psi = _atom(p), _atom(q)
        return _imp(_snce(phi, phi), _imp(_snce(psi, psi), _snce(phi, psi)))

    def F_until_equiv(rng):
        p = rng.choice(_ATOMS)
        phi = _atom(p)
        # F(phi) → U(phi, ⊤)
        f_phi = _untl(phi, phi)  # F(phi) approximated as U(phi, phi)
        u_phi_top = _untl(phi, _bot())
        return _imp(f_phi, u_phi_top)

    def P_since_equiv(rng):
        p = rng.choice(_ATOMS)
        phi = _atom(p)
        p_phi = _snce(phi, phi)
        s_phi_top = _snce(phi, _bot())
        return _imp(p_phi, s_phi_top)

    gens["serial_future"] = [serial_future]
    gens["serial_past"] = [serial_past]
    gens["left_mono_until_G"] = [left_mono_until_G]
    gens["left_mono_since_H"] = [left_mono_since_H]
    gens["right_mono_until"] = [right_mono_until]
    gens["right_mono_since"] = [right_mono_since]
    gens["connect_future"] = [connect_future]
    gens["connect_past"] = [connect_past]
    gens["enrichment_until"] = [enrichment_until]
    gens["enrichment_since"] = [enrichment_since]
    gens["self_accum_until"] = [self_accum_until]
    gens["self_accum_since"] = [self_accum_since]
    gens["absorb_until"] = [absorb_until]
    gens["absorb_since"] = [absorb_since]
    gens["linear_until"] = [linear_until]
    gens["linear_since"] = [linear_since]
    gens["until_F"] = [until_F]
    gens["since_P"] = [since_P]
    gens["temp_linearity"] = [temp_linearity]
    gens["temp_linearity_past"] = [temp_linearity_past]
    gens["F_until_equiv"] = [F_until_equiv]
    gens["P_since_equiv"] = [P_since_equiv]

    # Layer 4: Modal-Temporal Interaction
    def modal_future(rng):
        p = rng.choice(_ATOMS)
        phi = _atom(p)
        # □phi→□(G phi) : □phi → □(U(phi, phi)) approximately
        return _imp(_box(phi), _box(_untl(phi, phi)))

    gens["modal_future"] = [modal_future]

    # Layer 5: Uniformity axioms (5)
    def discrete_symm_fwd(rng):
        # U(⊤,⊥)→S(⊤,⊥)
        return _imp(_untl(_bot(), _bot()), _snce(_bot(), _bot()))

    def discrete_symm_bwd(rng):
        return _imp(_snce(_bot(), _bot()), _untl(_bot(), _bot()))

    def discrete_propagate_fwd(rng):
        # U(⊤,⊥)→G(U(⊤,⊥))
        witness = _untl(_bot(), _bot())
        return _imp(witness, _box(witness))

    def discrete_propagate_bwd(rng):
        witness = _untl(_bot(), _bot())
        return _imp(witness, _box(_snce(_bot(), _bot())))

    def discrete_box_necessity(rng):
        witness = _untl(_bot(), _bot())
        return _imp(witness, _box(witness))

    gens["discrete_symm_fwd"] = [discrete_symm_fwd]
    gens["discrete_symm_bwd"] = [discrete_symm_bwd]
    gens["discrete_propagate_fwd"] = [discrete_propagate_fwd]
    gens["discrete_propagate_bwd"] = [discrete_propagate_bwd]
    gens["discrete_box_necessity"] = [discrete_box_necessity]

    # Layer 6: Prior axioms (Discrete only)
    def prior_UZ(rng):
        p = rng.choice(_ATOMS)
        phi = _atom(p)
        # F(phi) → U(phi, ¬phi) -- ¬phi = phi → ⊥
        f_phi = _untl(phi, phi)
        neg_phi = _imp(phi, _bot())
        return _imp(f_phi, _untl(phi, neg_phi))

    def prior_SZ(rng):
        p = rng.choice(_ATOMS)
        phi = _atom(p)
        p_phi = _snce(phi, phi)
        neg_phi = _imp(phi, _bot())
        return _imp(p_phi, _snce(phi, neg_phi))

    gens["prior_UZ"] = [prior_UZ]
    gens["prior_SZ"] = [prior_SZ]

    # Layer 7: Z1
    def z1(rng):
        p = rng.choice(_ATOMS)
        phi = _atom(p)
        # G(G phi → phi) → (FG phi → G phi) : simplified
        g_phi = _untl(phi, phi)
        g_g_phi_phi = _box(_imp(g_phi, phi))
        fg_phi = _untl(g_phi, phi)
        return _imp(g_g_phi_phi, _imp(fg_phi, g_phi))

    gens["z1"] = [z1]

    # Layer 8: Density axioms (Dense only)
    def density(rng):
        p = rng.choice(_ATOMS)
        phi = _atom(p)
        # GG phi → G phi
        gg_phi = _box(_box(phi))
        g_phi = _box(phi)
        return _imp(gg_phi, g_phi)

    def dense_indicator(rng):
        # ¬U(⊤,⊥)
        return _imp(_untl(_bot(), _bot()), _bot())

    gens["density"] = [density]
    gens["dense_indicator"] = [dense_indicator]

    return gens


_AXIOM_GOAL_GENERATORS = _make_axiom_goal_generators()


# ---------------------------------------------------------------------------
# Rule goal generators
# ---------------------------------------------------------------------------

def _make_rule_records(
    rule: str,
    n: int,
    rng: random.Random,
    frame_class: str,
    base_depth: int = 0,
    base_height: int = 1,
) -> list[ProofStepRecord]:
    """Generate n ProofStepRecords for the given inference rule."""
    records = []
    for i in range(n):
        step_id = f"synthetic_{rule}_{frame_class}_{uuid.uuid4().hex[:8]}"
        action_index = step_to_action_index(rule, None)
        p, q = rng.sample(_ATOMS, 2)
        phi, psi = _atom(p), _atom(q)

        if rule == "modus_ponens":
            # Rule: from (phi → psi) and phi, derive psi
            # Goal: any formula, premise includes phi → goal and phi
            goal = _imp(phi, psi)
            context = (f"{p} → {q}", p)
            subgoals = (_imp(phi, psi), phi)

        elif rule == "necessitation":
            # Rule: from phi, derive □phi
            # Goal must be box-headed; empty context
            goal = _box(phi)
            context = ()
            subgoals = (phi,)

        elif rule == "assumption":
            # Rule: phi is in context, derive phi
            goal = phi
            context = (p, q)
            subgoals = ()

        elif rule == "axiom":
            # Won't happen -- axiom is handled separately
            goal = phi
            context = ()
            subgoals = ()

        elif rule == "weakening":
            # Rule: from phi, derive phi with extra hypotheses
            goal = phi
            context = (q,)
            subgoals = (phi,)

        elif rule == "temporal_necessitation":
            # Like necessitation but for temporal operators
            goal = _untl(phi, psi)
            context = ()
            subgoals = (phi,)

        elif rule == "temporal_duality":
            # Swap Until/Since
            goal = _untl(phi, psi)
            context = ()
            subgoals = (_snce(phi, psi),)

        else:
            goal = phi
            context = ()
            subgoals = ()

        records.append(ProofStepRecord(
            step_id=step_id,
            theorem_name=f"synthetic_{rule}",
            context=context,
            goal_json=goal,
            goal_pretty=_formula_pretty(goal),
            rule=rule,
            axiom_name=None,
            action_index=action_index,
            subgoals=subgoals,
            depth=base_depth,
            frame_class=frame_class,
            proof_height=base_height + rng.randint(0, 3),
        ))
    return records


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------

# Axioms valid per frame class (used to respect frame_class constraints)
_DISCRETE_ONLY = frozenset(["prior_UZ", "prior_SZ", "z1"])
_DENSE_ONLY = frozenset(["density", "dense_indicator"])
_BASE_AXIOMS = frozenset(AXIOM_ACTIONS) - _DISCRETE_ONLY - _DENSE_ONLY


def _valid_axioms_for_frame_class(frame_class: str) -> list[str]:
    """Return list of axiom names valid for the given frame class."""
    if frame_class == "Base":
        return [a for a in AXIOM_ACTIONS if a in _BASE_AXIOMS]
    elif frame_class == "Dense":
        return [a for a in AXIOM_ACTIONS if a in _BASE_AXIOMS or a in _DENSE_ONLY]
    elif frame_class == "Discrete":
        return [a for a in AXIOM_ACTIONS if a in _BASE_AXIOMS or a in _DISCRETE_ONLY]
    return list(AXIOM_ACTIONS)


def generate_synthetic_proof_steps(
    n_steps: int = 5000,
    seed: int = 42,
    frame_class: str = "Base",
) -> list[ProofStepRecord]:
    """Generate synthetic ProofStepRecords covering all valid actions.

    Generates records with balanced coverage of all 49 actions (where valid
    for the given frame class), applies augmentation to expand 3-5x, and
    returns the full augmented list.

    Parameters
    ----------
    n_steps:
        Target number of base records before augmentation. Default: 5000.
    seed:
        Random seed for reproducibility. Default: 42.
    frame_class:
        Frame class for generated records ("Base", "Dense", "Discrete").
        Only axioms valid for this frame class will be generated for axiom
        actions. Default: "Base".

    Returns
    -------
    list[ProofStepRecord]
        List of ProofStepRecord objects (originals + augmented).
        Length is approximately 3-5x n_steps.
    """
    rng = random.Random(seed)

    valid_axioms = _valid_axioms_for_frame_class(frame_class)
    # RULE_ACTIONS includes "axiom" which is covered by axiom constructor records;
    # non-axiom rules are the remaining 6 inference rules.
    non_axiom_rules = [r for r in RULE_ACTIONS if r != "axiom"]
    all_valid_actions = valid_axioms + non_axiom_rules
    n_valid_actions = len(all_valid_actions)

    # Minimum examples per action: n_steps / (2 * n_valid_actions)
    min_per_action = max(1, n_steps // (2 * n_valid_actions))
    # Remaining budget distributed proportionally (uniformly here)
    remaining = n_steps - min_per_action * n_valid_actions
    extra_per_action = max(0, remaining // n_valid_actions)
    per_action = min_per_action + extra_per_action

    records: list[ProofStepRecord] = []

    # Generate axiom records
    for axiom_name in valid_axioms:
        generators = _AXIOM_GOAL_GENERATORS.get(axiom_name, [])
        if not generators:
            continue
        action_index = step_to_action_index("axiom", axiom_name)
        for _ in range(per_action):
            gen = rng.choice(generators)
            goal = gen(rng)
            step_id = f"synthetic_axiom_{axiom_name}_{uuid.uuid4().hex[:8]}"
            depth = rng.randint(0, 4)
            height = depth + rng.randint(0, 4)
            records.append(ProofStepRecord(
                step_id=step_id,
                theorem_name=f"synthetic_{axiom_name}",
                context=(),
                goal_json=goal,
                goal_pretty=_formula_pretty(goal),
                rule="axiom",
                axiom_name=axiom_name,
                action_index=action_index,
                subgoals=(),
                depth=depth,
                frame_class=frame_class,
                proof_height=height,
            ))

    # Generate rule records (skip "axiom" — covered by axiom constructor loop above)
    for rule in non_axiom_rules:
        rule_recs = _make_rule_records(rule, per_action, rng, frame_class)
        records.extend(rule_recs)

    # Augment: apply all augmentation strategies (originals included)
    augmented = augment_all(records)
    # Return just the ProofStepRecord objects (discard source tags)
    return [r for r, _ in augmented]
