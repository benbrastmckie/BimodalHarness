"""Training record dataclasses for BimodalHarness.

Defines the Python dataclasses that mirror the Lean types exported by
Bimodal.Automation.DataExport.  The primary type is TrainingRecord, which
combines a labelled formula with proof or countermodel evidence and
structural features.

Lean correspondence:
- TrainingRecord: mirrors LabeledFormula from DataExport.lean (conceptual)
- PatternKey: mirrors PatternKey struct in Bimodal.Automation.SuccessPatterns
- RuleProfile: mirrors RuleProfile struct in Bimodal.Automation.DataExport
- ProofTrace: derived from DerivationTree metrics (height, RuleProfile)
- SimpleCountermodel: mirrors Bimodal.Metalogic.Decidability.SimpleCountermodel
- DifficultyMetrics: aggregated from multiple proof/search statistics
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from bimodal_harness.schema.constants import (
    SCHEMA_VERSION,
    VALID_DIFFICULTY_TIERS,
    VALID_FRAME_CLASSES,
    VALID_LABELS,
    VALID_TOP_OPERATORS,
)


@dataclass(frozen=True, slots=True)
class PatternKey:
    """Feature vector for formula pattern matching.

    Lean correspondence:
    - PatternKey struct in Bimodal.Automation.SuccessPatterns
    - Created by PatternKey.fromFormula

    All non-negative integers.  complexity >= 1 (minimum is 1 for atom/bot).
    """

    modal_depth: int
    """Modal nesting depth (number of □ operators on the deepest path)."""

    temporal_depth: int
    """Temporal nesting depth (number of U/S operators on the deepest path)."""

    imp_count: int
    """Number of implication operators in the formula."""

    complexity: int
    """Structural complexity = total connective count + 1 (always >= 1)."""

    top_operator: str
    """Top-level GoalCategory name.  One of VALID_TOP_OPERATORS."""

    def __post_init__(self) -> None:
        if self.modal_depth < 0:
            raise ValueError(f"modal_depth must be >= 0, got {self.modal_depth}")
        if self.temporal_depth < 0:
            raise ValueError(f"temporal_depth must be >= 0, got {self.temporal_depth}")
        if self.imp_count < 0:
            raise ValueError(f"imp_count must be >= 0, got {self.imp_count}")
        if self.complexity < 1:
            raise ValueError(f"complexity must be >= 1, got {self.complexity}")
        if self.top_operator not in VALID_TOP_OPERATORS:
            raise ValueError(
                f"top_operator must be one of {VALID_TOP_OPERATORS}, got {self.top_operator!r}"
            )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a flat dictionary matching DataExport.lean PatternKey.toJson fields."""
        return {
            "modalDepth": self.modal_depth,
            "temporalDepth": self.temporal_depth,
            "impCount": self.imp_count,
            "complexity": self.complexity,
            "topOperator": self.top_operator,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PatternKey:
        """Deserialize from DataExport.lean PatternKey.toJson format (camelCase keys)."""
        return cls(
            modal_depth=int(data["modalDepth"]),
            temporal_depth=int(data["temporalDepth"]),
            imp_count=int(data["impCount"]),
            complexity=int(data["complexity"]),
            top_operator=str(data["topOperator"]),
        )


@dataclass(frozen=True, slots=True)
class RuleProfile:
    """Counts of each inference rule in a derivation tree.

    Lean correspondence:
    - RuleProfile struct in Bimodal.Automation.DataExport
    - Computed by walkDerivationTree

    7 fields, one per DerivationTree constructor.
    """

    axiom_count: int = 0
    assumption_count: int = 0
    mp_count: int = 0
    necessitation_count: int = 0
    temporal_necessitation_count: int = 0
    temporal_duality_count: int = 0
    weakening_count: int = 0

    def to_dict(self) -> dict[str, int]:
        """Serialize to DataExport.lean RuleProfile.toJson format."""
        return {
            "axiom": self.axiom_count,
            "assumption": self.assumption_count,
            "modus_ponens": self.mp_count,
            "necessitation": self.necessitation_count,
            "temporal_necessitation": self.temporal_necessitation_count,
            "temporal_duality": self.temporal_duality_count,
            "weakening": self.weakening_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RuleProfile:
        """Deserialize from DataExport.lean RuleProfile.toJson format."""
        return cls(
            axiom_count=int(data.get("axiom", 0)),
            assumption_count=int(data.get("assumption", 0)),
            mp_count=int(data.get("modus_ponens", 0)),
            necessitation_count=int(data.get("necessitation", 0)),
            temporal_necessitation_count=int(data.get("temporal_necessitation", 0)),
            temporal_duality_count=int(data.get("temporal_duality", 0)),
            weakening_count=int(data.get("weakening", 0)),
        )


@dataclass(frozen=True, slots=True)
class ProofTrace:
    """Summary of a successful derivation tree.

    Combines the tree height (from DerivationTree.height) with a RuleProfile
    (from walkDerivationTree) and a list of axiom constructor names used.
    """

    height: int
    """Derivation tree height (= 0 for axiom/assumption leaves)."""

    rule_profile: RuleProfile
    """Counts of each inference rule applied."""

    axioms_used: tuple[str, ...]
    """Ordered list of axiom constructor names appearing in the proof.

    Names match AXIOM_ACTIONS exactly.  May contain duplicates if an axiom
    schema is instantiated multiple times.
    """

    def __post_init__(self) -> None:
        if self.height < 0:
            raise ValueError(f"height must be >= 0, got {self.height}")

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a flat dictionary."""
        return {
            "height": self.height,
            "rules": self.rule_profile.to_dict(),
            "axioms_used": list(self.axioms_used),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProofTrace:
        """Deserialize from serialized dict."""
        return cls(
            height=int(data["height"]),
            rule_profile=RuleProfile.from_dict(data.get("rules", {})),
            axioms_used=tuple(data.get("axioms_used", [])),
        )


@dataclass(frozen=True, slots=True)
class SimpleCountermodel:
    """A simple countermodel for an invalid formula.

    Lean correspondence:
    - SimpleCountermodel in Bimodal.Metalogic.Decidability.CountermodelExtraction
    - Serialized by SimpleCountermodel.toJson in DataExport.lean

    In the JSON export, trueAtoms and falseAtoms are lists of Atom JSON objects.
    Here we store only the base names for simplicity.
    """

    true_atoms: tuple[str, ...]
    """Atom base names set to true in the countermodel."""

    false_atoms: tuple[str, ...]
    """Atom base names set to false in the countermodel."""

    formula_json: dict[str, Any]
    """The formula that this countermodel refutes (as JSON tree)."""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to DataExport.lean SimpleCountermodel.toJson format."""
        return {
            "trueAtoms": [{"base": a, "fresh_index": None} for a in self.true_atoms],
            "falseAtoms": [{"base": a, "fresh_index": None} for a in self.false_atoms],
            "formula": self.formula_json,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SimpleCountermodel:
        """Deserialize from DataExport.lean SimpleCountermodel.toJson format."""
        true_atoms = tuple(
            a["base"] if isinstance(a, dict) else str(a)
            for a in data.get("trueAtoms", [])
        )
        false_atoms = tuple(
            a["base"] if isinstance(a, dict) else str(a)
            for a in data.get("falseAtoms", [])
        )
        return cls(
            true_atoms=true_atoms,
            false_atoms=false_atoms,
            formula_json=data.get("formula", {}),
        )


@dataclass(frozen=True, slots=True)
class DifficultyMetrics:
    """Aggregated difficulty metrics for a training record.

    Combines structural formula features with search statistics.
    """

    atom_count: int
    """Number of distinct atoms in the formula."""

    modal_depth: int
    """Modal operator nesting depth (from PatternKey)."""

    temporal_depth: int
    """Temporal operator nesting depth (from PatternKey)."""

    complexity: int
    """Formula structural complexity (from PatternKey)."""

    decision_time_ms: int
    """Wall-clock time taken by the Lean prover/checker in milliseconds."""

    search_depth: int
    """Depth in the proof search tree at which the decision was made."""

    difficulty_tier: str
    """Human-readable difficulty category.  One of VALID_DIFFICULTY_TIERS."""

    def __post_init__(self) -> None:
        if self.difficulty_tier not in VALID_DIFFICULTY_TIERS:
            raise ValueError(
                f"difficulty_tier must be one of {VALID_DIFFICULTY_TIERS}, "
                f"got {self.difficulty_tier!r}"
            )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a flat dictionary."""
        return {
            "atom_count": self.atom_count,
            "modal_depth": self.modal_depth,
            "temporal_depth": self.temporal_depth,
            "complexity": self.complexity,
            "decision_time_ms": self.decision_time_ms,
            "search_depth": self.search_depth,
            "difficulty_tier": self.difficulty_tier,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DifficultyMetrics:
        """Deserialize from a flat dictionary."""
        return cls(
            atom_count=int(data["atom_count"]),
            modal_depth=int(data["modal_depth"]),
            temporal_depth=int(data["temporal_depth"]),
            complexity=int(data["complexity"]),
            decision_time_ms=int(data["decision_time_ms"]),
            search_depth=int(data["search_depth"]),
            difficulty_tier=str(data["difficulty_tier"]),
        )


@dataclass(slots=True)
class TrainingRecord:
    """A single labelled training example for the AlphaZero proof search system.

    Mirrors the LabeledFormula concept exported by Bimodal.Automation.DataExport,
    augmented with Python-side metadata for ML training.

    Required fields (always present):
    - record_id, formula_json, formula_pretty, label
    - pattern_key, difficulty_metrics
    - schema_version, frame_class, source, logic_system

    Conditional fields:
    - proof_trace: present iff label == "valid"
    - countermodel: present iff label == "invalid"
    """

    # Core identity
    record_id: str
    """Unique identifier for this training record (UUID4 string)."""

    formula_json: dict[str, Any]
    """Formula serialized as JSON tree (DataExport.lean Formula.toJson format)."""

    formula_pretty: str
    """Human-readable formula string (DataExport.lean Formula.prettyPrint format)."""

    label: str
    """Classification label.  Must be "valid" or "invalid"."""

    # Structural features
    pattern_key: PatternKey
    """Formula structural features for pattern matching."""

    difficulty_metrics: DifficultyMetrics
    """Difficulty classification and search statistics."""

    # Evidence (label-conditional)
    proof_trace: ProofTrace | None
    """Derivation tree summary.  Required when label == "valid", None otherwise."""

    countermodel: SimpleCountermodel | None
    """Countermodel evidence.  Required when label == "invalid", None otherwise."""

    # Metadata
    schema_version: str = field(default=SCHEMA_VERSION)
    """Schema version string (semver).  Must equal SCHEMA_VERSION on ingest."""

    frame_class: str = field(default="Base")
    """Frame class used for this derivation.  One of VALID_FRAME_CLASSES."""

    source: str = field(default="lean_export")
    """Data source identifier."""

    logic_system: str = field(default="TM_BX")
    """Logic system identifier.  "TM_BX" for BimodalLogic under the BX axiom system."""

    def __post_init__(self) -> None:
        if self.label not in VALID_LABELS:
            raise ValueError(f"label must be one of {VALID_LABELS}, got {self.label!r}")
        if self.frame_class not in VALID_FRAME_CLASSES:
            raise ValueError(
                f"frame_class must be one of {VALID_FRAME_CLASSES}, got {self.frame_class!r}"
            )

    @classmethod
    def make_id(cls) -> str:
        """Generate a fresh UUID4 record ID."""
        return str(uuid.uuid4())
