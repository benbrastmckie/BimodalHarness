"""Action space enumeration for the BimodalHarness AlphaZero proof search system.

Defines the canonical ordered lists of axiom and inference rule actions used as
output actions for the policy network.  Constructor names match the Lean
Axiom inductive type in Bimodal.ProofSystem.Axioms and the DerivationTree
inductive type in Bimodal.ProofSystem.Derivation exactly.

Summary:
- AXIOM_ACTIONS: 42 axiom constructor names (8 layers)
- RULE_ACTIONS:   7 inference rule names
- ALL_ACTIONS:   49 total actions (policy network output dimension)

Frame-class masks (boolean arrays over ALL_ACTIONS):
- BASE_MASK:     True for actions valid on Base frame class  (37 axioms + 7 rules = 44)
- DENSE_MASK:    True for actions valid on Dense frame class (39 axioms + 7 rules = 46)
- DISCRETE_MASK: True for actions valid on Discrete frame class (40 axioms + 7 rules = 47)

All rules are valid on all frame classes (hence +7 in all masks).

Lean correspondence:
- Axiom constructors: Bimodal.ProofSystem.Axioms.Axiom (42 constructors)
- Rule names: Bimodal.ProofSystem.Derivation.DerivationTree (7 constructors)
- minFrameClass: Bimodal.ProofSystem.Axioms.Axiom.minFrameClass
"""

from __future__ import annotations

from enum import Enum


class FrameClass(str, Enum):
    """Frame class classification matching Lean FrameClass in Axioms.lean.

    Partial order: Base <= Dense and Base <= Discrete; Dense and Discrete
    are incomparable (density contradicts discreteness).
    """

    BASE = "Base"
    DENSE = "Dense"
    DISCRETE = "Discrete"


# ---------------------------------------------------------------------------
# Layer 1: Propositional axioms (4)
# Valid on: Base (and all classes)
# ---------------------------------------------------------------------------
_LAYER_1_PROPOSITIONAL = [
    "prop_k",       # (φ→(ψ→χ))→((φ→ψ)→(φ→χ))
    "prop_s",       # φ→(ψ→φ)  (weakening)
    "ex_falso",     # ⊥→φ
    "peirce",       # ((φ→ψ)→φ)→φ
]

# ---------------------------------------------------------------------------
# Layer 2: S5 Modal axioms (5)
# Valid on: Base (and all classes)
# ---------------------------------------------------------------------------
_LAYER_2_S5_MODAL = [
    "modal_t",          # □φ→φ                  (reflexivity / T)
    "modal_4",          # □φ→□□φ                (transitivity / 4)
    "modal_b",          # φ→□◇φ                 (symmetry / B)
    "modal_5_collapse", # ◇□φ→□φ                (S5 characteristic)
    "modal_k_dist",     # □(φ→ψ)→(□φ→□ψ)       (K distribution)
]

# ---------------------------------------------------------------------------
# Layer 3: BX Temporal axioms (22 = 11 pairs of future/past duals)
# Valid on: Base (and all classes)
# Burgess-Xu axiom system for Until/Since on linear temporal orders.
# ---------------------------------------------------------------------------
_LAYER_3_BX_TEMPORAL = [
    # BX1/BX1': Seriality
    "serial_future",          # ⊤→F(⊤)
    "serial_past",            # ⊤→P(⊤)
    # BX2G/BX2H: Guard monotonicity under G/H
    "left_mono_until_G",      # G(φ→χ)→(ψUφ→ψUχ)
    "left_mono_since_H",      # H(φ→χ)→(ψSφ→ψSχ)
    # BX3/BX3': Event monotonicity
    "right_mono_until",       # G(φ→ψ)→(φUχ→ψUχ)
    "right_mono_since",       # H(φ→ψ)→(φSχ→ψSχ)
    # BX4/BX4': Temporal connectedness
    "connect_future",         # φ→G(P(φ))
    "connect_past",           # φ→H(F(φ))
    # BX13/BX13': Until-Since / Since-Until enrichment
    "enrichment_until",       # p∧U(ψ,φ)→U(ψ∧S(p,φ),φ)
    "enrichment_since",       # p∧S(ψ,φ)→S(ψ∧U(p,φ),φ)
    # BX5/BX5': Self-accumulation
    "self_accum_until",       # U(ψ,φ)→U(ψ,φ∧U(ψ,φ))
    "self_accum_since",       # S(ψ,φ)→S(ψ,φ∧S(ψ,φ))
    # BX6/BX6': Absorption
    "absorb_until",           # U(φ∧U(ψ,φ),φ)→U(ψ,φ)
    "absorb_since",           # S(φ∧S(ψ,φ),φ)→S(ψ,φ)
    # BX7/BX7': Linearity
    "linear_until",           # U(ψ,φ)∧U(θ,χ)→U(ψ∧θ,φ∧χ)∨U(ψ∧χ,φ∧χ)∨U(φ∧θ,φ∧χ)
    "linear_since",           # S(ψ,φ)∧S(θ,χ)→... (past dual)
    # BX10/BX10': Eventuality extraction
    "until_F",                # U(ψ,φ)→F(ψ)
    "since_P",                # S(ψ,φ)→P(ψ)
    # BX11/BX11': F/P linearity
    "temp_linearity",         # F(φ)∧F(ψ)→F(φ∧ψ)∨F(φ∧F(ψ))∨F(F(φ)∧ψ)
    "temp_linearity_past",    # P(φ)∧P(ψ)→... (past dual)
    # BX12/BX12': F-Until / P-Since bridge
    "F_until_equiv",          # F(φ)→U(φ,⊤)
    "P_since_equiv",          # P(φ)→S(φ,⊤)
]

# ---------------------------------------------------------------------------
# Layer 4: Modal-Temporal Interaction (1)
# Valid on: Base (and all classes)
# Note: TF (□φ→G□φ) is derived; only MF is primitive.
# ---------------------------------------------------------------------------
_LAYER_4_INTERACTION = [
    "modal_future",   # □φ→□(Gφ)
]

# ---------------------------------------------------------------------------
# Layer 5: Uniformity axioms (5)
# Valid on: Base (and all classes)
# Encode translation-invariance of discreteness witness U(⊤,⊥).
# ---------------------------------------------------------------------------
_LAYER_5_UNIFORMITY = [
    "discrete_symm_fwd",        # U(⊤,⊥)→S(⊤,⊥)
    "discrete_symm_bwd",        # S(⊤,⊥)→U(⊤,⊥)
    "discrete_propagate_fwd",   # U(⊤,⊥)→G(U(⊤,⊥))
    "discrete_propagate_bwd",   # U(⊤,⊥)→H(U(⊤,⊥))
    "discrete_box_necessity",   # U(⊤,⊥)→□(U(⊤,⊥))
]

# ---------------------------------------------------------------------------
# Layer 6: Prior axioms for integers (2)
# Valid on: Discrete frame class only.
# ---------------------------------------------------------------------------
_LAYER_6_PRIOR = [
    "prior_UZ",   # F(φ)→U(φ,¬φ)
    "prior_SZ",   # P(φ)→S(φ,¬φ)
]

# ---------------------------------------------------------------------------
# Layer 7: Z1 IsSuccArchimedean characteristic axiom (1)
# Valid on: Discrete frame class only.
# ---------------------------------------------------------------------------
_LAYER_7_Z1 = [
    "z1",   # G(Gφ→φ)→(FGφ→Gφ)
]

# ---------------------------------------------------------------------------
# Layer 8: Density axioms (2)
# Valid on: Dense frame class only.
# ---------------------------------------------------------------------------
_LAYER_8_DENSITY = [
    "density",         # GGφ→Gφ
    "dense_indicator", # ¬U(⊤,⊥)
]

# ---------------------------------------------------------------------------
# Canonical ordered action lists
# ---------------------------------------------------------------------------

AXIOM_ACTIONS: list[str] = (
    _LAYER_1_PROPOSITIONAL
    + _LAYER_2_S5_MODAL
    + _LAYER_3_BX_TEMPORAL
    + _LAYER_4_INTERACTION
    + _LAYER_5_UNIFORMITY
    + _LAYER_6_PRIOR
    + _LAYER_7_Z1
    + _LAYER_8_DENSITY
)
"""Canonical ordered list of 42 axiom constructor names.

The ordering matches the layer-by-layer structure in Axioms.lean:
Layer 1 (indices 0-3):   Propositional (4)
Layer 2 (indices 4-8):   S5 Modal (5)
Layer 3 (indices 9-30):  BX Temporal (22)
Layer 4 (index 31):      Modal-Temporal Interaction (1)
Layer 5 (indices 32-36): Uniformity (5)
Layer 6 (indices 37-38): Prior (2)
Layer 7 (index 39):      Z1 (1)
Layer 8 (indices 40-41): Density (2)
"""

RULE_ACTIONS: list[str] = [
    "axiom",                    # DerivationTree.axiom
    "assumption",               # DerivationTree.assumption
    "modus_ponens",             # DerivationTree.modus_ponens
    "necessitation",            # DerivationTree.necessitation
    "temporal_necessitation",   # DerivationTree.temporal_necessitation
    "temporal_duality",         # DerivationTree.temporal_duality
    "weakening",                # DerivationTree.weakening
]
"""Canonical ordered list of 7 inference rule names from DerivationTree."""

ALL_ACTIONS: list[str] = AXIOM_ACTIONS + RULE_ACTIONS
"""Combined list of 49 actions: 42 axioms + 7 inference rules.

This is the output dimension of the policy network.
"""

# ---------------------------------------------------------------------------
# Index mappings (bijective)
# ---------------------------------------------------------------------------

ACTION_TO_INDEX: dict[str, int] = {action: idx for idx, action in enumerate(ALL_ACTIONS)}
"""Map from action name to zero-based index in ALL_ACTIONS (0..48)."""

INDEX_TO_ACTION: dict[int, str] = {idx: action for idx, action in enumerate(ALL_ACTIONS)}
"""Map from zero-based index to action name."""

# ---------------------------------------------------------------------------
# Frame-class masks
# ---------------------------------------------------------------------------

# Axioms that are ONLY valid on the Dense frame class (not Base, not Discrete).
_DENSE_ONLY_AXIOMS: frozenset[str] = frozenset(_LAYER_8_DENSITY)

# Axioms that are ONLY valid on the Discrete frame class (not Base, not Dense).
_DISCRETE_ONLY_AXIOMS: frozenset[str] = frozenset(_LAYER_6_PRIOR + _LAYER_7_Z1)

# Base frame class: all axioms EXCEPT dense-only and discrete-only.
_BASE_AXIOMS: frozenset[str] = frozenset(AXIOM_ACTIONS) - _DENSE_ONLY_AXIOMS - _DISCRETE_ONLY_AXIOMS

def _build_mask(allowed_axioms: frozenset[str]) -> list[bool]:
    """Build a boolean mask over ALL_ACTIONS.

    Parameters
    ----------
    allowed_axioms:
        Set of axiom names that are valid for this frame class.
        All rule actions are always included (True).

    Returns
    -------
    list[bool]
        Boolean mask of length 49 (len(ALL_ACTIONS)).
    """
    mask = []
    for action in ALL_ACTIONS:
        if action in RULE_ACTIONS:
            mask.append(True)  # Rules are always valid
        else:
            mask.append(action in allowed_axioms)
    return mask


BASE_MASK: list[bool] = _build_mask(_BASE_AXIOMS)
"""Boolean mask over ALL_ACTIONS for the Base frame class.

True for Base axioms (37) and all rules (7) = 44 True values.
"""

DENSE_MASK: list[bool] = _build_mask(_BASE_AXIOMS | _DENSE_ONLY_AXIOMS)
"""Boolean mask over ALL_ACTIONS for the Dense frame class.

True for Base axioms (37) + density axioms (2) + all rules (7) = 46 True values.
"""

DISCRETE_MASK: list[bool] = _build_mask(_BASE_AXIOMS | _DISCRETE_ONLY_AXIOMS)
"""Boolean mask over ALL_ACTIONS for the Discrete frame class.

True for Base axioms (37) + discrete axioms (3) + all rules (7) = 47 True values.
"""

FRAME_CLASS_MASKS: dict[str, list[bool]] = {
    "Base": BASE_MASK,
    "Dense": DENSE_MASK,
    "Discrete": DISCRETE_MASK,
}
"""Mapping from frame class name to its boolean action mask."""


def get_mask_for_frame_class(frame_class: str | FrameClass) -> list[bool]:
    """Return the boolean action mask for a given frame class.

    Parameters
    ----------
    frame_class:
        A FrameClass enum value or its string name ("Base", "Dense", "Discrete").

    Returns
    -------
    list[bool]
        Boolean mask of length 49.

    Raises
    ------
    KeyError
        If frame_class is not a valid frame class name.
    """
    if isinstance(frame_class, FrameClass):
        frame_class = frame_class.value
    return FRAME_CLASS_MASKS[frame_class]
