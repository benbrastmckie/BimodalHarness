"""
Data schema definitions for BimodalHarness.

.. deprecated::
    This module (``bimodal_harness.data.schema``) is **deprecated** and will be
    removed in a future release.  It was the initial attempt to mirror the Lean 4
    JSON export format but has several mismatches with the actual Lean output:

    - ``Label`` uses uppercase values (``"VALID"``, ``"INVALID"``, ``"TIMEOUT"``)
      but Lean emits lowercase (``"valid"``, ``"invalid"``, ``"timeout"``)
    - ``PatternKey.from_json`` reads snake_case keys but Lean emits camelCase
    - ``DifficultyMetrics.difficulty_tier`` is an integer (1-5) but Lean emits
      a string (``"easy"``, ``"medium"``, ``"hard"``, ``"very_hard"``)
    - ``RuleProfile`` field names (``imp_left``, ``box_right`` etc.) do not match
      the actual Lean ``RuleProfile`` fields
    - ``box`` AST nodes require an ``event`` field that Lean does not emit

    **Migration guide**:
    - Use ``bimodal_harness.schema.records.TrainingRecord`` for ML-pipeline code
    - Use ``bimodal_harness.data.ingestion.ingest_jsonl`` to load JSONL files
    - Use ``bimodal_harness.data.ingestion.lean_export_to_training_record`` for
      direct Lean JSONL dict translation

This module defines Python dataclasses that exactly mirror the Lean 4 JSON export
format produced by BimodalLogic's DatasetGenerator.lean. The schema covers:

- FormulaNode: Recursive AST for bimodal temporal logic formulas
- LabeledFormula: Top-level training record with provenance metadata
- PatternKey: Structural fingerprint for formula categorization
- SimpleCountermodel: Kripke counterexample for INVALID formulas
- ProofTrace: Proof structure metadata for VALID formulas
- DifficultyMetrics: Complexity indicators for curriculum learning
- RuleProfile: Rule application statistics from the tableau prover

JSON tag to Lean constructor mapping:
  "atom" -> .atom (String name)
  "bot"  -> .bot  (nullary)
  "imp"  -> .imp  (left, right subtrees)
  "box"  -> .box  (child, event subtree - S4 modal)
  "untl" -> .untl (guard, child subtrees - Until temporal)
  "snce" -> .snce (guard, child subtrees - Since temporal)

Version: 1 (matches BimodalLogic schema as of Lean v4.27.0-rc1)
"""

from __future__ import annotations

import warnings as _warnings

_warnings.warn(
    "bimodal_harness.data.schema is deprecated and will be removed in a future release. "
    "Use bimodal_harness.schema.records.TrainingRecord for ML-pipeline code "
    "and bimodal_harness.data.ingestion for loading JSONL files. "
    "See the module docstring for migration details.",
    DeprecationWarning,
    stacklevel=2,
)

import json
from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class FormulaTag(StrEnum):
    """Formula constructor tags as serialized by BimodalLogic's DataExport.lean."""

    ATOM = "atom"
    BOT = "bot"
    IMP = "imp"
    BOX = "box"
    UNTL = "untl"
    SNCE = "snce"


class Label(StrEnum):
    """Validity classification produced by the BimodalLogic tableau prover."""

    VALID = "VALID"
    INVALID = "INVALID"
    TIMEOUT = "TIMEOUT"


# ---------------------------------------------------------------------------
# FormulaNode: recursive AST
# ---------------------------------------------------------------------------


@dataclass
class FormulaNode:
    """
    Recursive AST node for a bimodal temporal logic formula.

    Fields present depend on the tag:
      atom: name (str) is set
      bot:  no children
      imp:  left and right are set
      box:  child and event are set (S4 modal operator)
      untl: guard and child are set (Until: p U q)
      snce: guard and child are set (Since: p S q)
    """

    tag: FormulaTag
    name: str | None = None  # atom only
    child: FormulaNode | None = None  # box, untl, snce
    left: FormulaNode | None = None  # imp
    right: FormulaNode | None = None  # imp
    event: FormulaNode | None = None  # box (event modality)
    guard: FormulaNode | None = None  # untl, snce (guard formula)

    @classmethod
    def from_json(cls, data: dict) -> FormulaNode:
        """
        Deserialize a FormulaNode from its JSON dict representation.

        Handles recursive nesting for compound operators.

        Args:
            data: Dict with at least a "tag" key matching FormulaTag values.

        Returns:
            FormulaNode instance with all applicable children populated.

        Raises:
            KeyError: If required fields for a tag are missing.
            ValueError: If the tag string is not a valid FormulaTag.
        """
        tag = FormulaTag(data["tag"])

        if tag == FormulaTag.ATOM:
            return cls(tag=tag, name=data["name"])

        if tag == FormulaTag.BOT:
            return cls(tag=tag)

        if tag == FormulaTag.IMP:
            return cls(
                tag=tag,
                left=cls.from_json(data["left"]),
                right=cls.from_json(data["right"]),
            )

        if tag == FormulaTag.BOX:
            return cls(
                tag=tag,
                child=cls.from_json(data["child"]),
                event=cls.from_json(data["event"]),
            )

        if tag in (FormulaTag.UNTL, FormulaTag.SNCE):
            return cls(
                tag=tag,
                guard=cls.from_json(data["guard"]),
                child=cls.from_json(data["child"]),
            )

        raise ValueError(f"Unrecognized FormulaTag: {tag!r}")

    def to_json(self) -> dict:
        """
        Serialize a FormulaNode back to its JSON dict representation.

        Mirrors the inverse of from_json for round-trip testing.
        """
        d: dict = {"tag": self.tag.value}
        if self.tag == FormulaTag.ATOM:
            d["name"] = self.name
        elif self.tag == FormulaTag.IMP:
            d["left"] = self.left.to_json()  # type: ignore[union-attr]
            d["right"] = self.right.to_json()  # type: ignore[union-attr]
        elif self.tag == FormulaTag.BOX:
            d["child"] = self.child.to_json()  # type: ignore[union-attr]
            d["event"] = self.event.to_json()  # type: ignore[union-attr]
        elif self.tag in (FormulaTag.UNTL, FormulaTag.SNCE):
            d["guard"] = self.guard.to_json()  # type: ignore[union-attr]
            d["child"] = self.child.to_json()  # type: ignore[union-attr]
        return d


# ---------------------------------------------------------------------------
# PatternKey: structural fingerprint
# ---------------------------------------------------------------------------


@dataclass
class PatternKey:
    """
    Structural fingerprint for formula categorization and dataset stratification.

    Maps to PatternKey in BimodalLogic's DataExport.lean.
    """

    modal_depth: int
    temporal_depth: int
    imp_count: int
    complexity: int
    top_operator: str  # e.g. "imp", "box", "untl", "atom", "bot"

    @classmethod
    def from_json(cls, data: dict) -> PatternKey:
        return cls(
            modal_depth=data["modal_depth"],
            temporal_depth=data["temporal_depth"],
            imp_count=data["imp_count"],
            complexity=data["complexity"],
            top_operator=data["top_operator"],
        )

    def to_json(self) -> dict:
        return {
            "modal_depth": self.modal_depth,
            "temporal_depth": self.temporal_depth,
            "imp_count": self.imp_count,
            "complexity": self.complexity,
            "top_operator": self.top_operator,
        }


# ---------------------------------------------------------------------------
# SimpleCountermodel: Kripke counterexample
# ---------------------------------------------------------------------------


@dataclass
class SimpleCountermodel:
    """
    Minimal Kripke countermodel witnessing invalidity.

    true_atoms:  propositional atoms that hold at the evaluation world
    false_atoms: propositional atoms that do not hold at the evaluation world
    formula:     the formula being refuted (string representation)

    Maps to SimpleCountermodel in BimodalLogic's DataExport.lean.
    """

    true_atoms: list[str]
    false_atoms: list[str]
    formula: str

    @classmethod
    def from_json(cls, data: dict) -> SimpleCountermodel:
        return cls(
            true_atoms=list(data["true_atoms"]),
            false_atoms=list(data["false_atoms"]),
            formula=data["formula"],
        )

    def to_json(self) -> dict:
        return {
            "true_atoms": self.true_atoms,
            "false_atoms": self.false_atoms,
            "formula": self.formula,
        }


# ---------------------------------------------------------------------------
# RuleProfile: tableau rule application statistics
# ---------------------------------------------------------------------------


@dataclass
class RuleProfile:
    """
    Rule application count statistics from the BimodalLogic tableau prover.

    Each field counts how many times the corresponding rule was applied
    during proof search. Zero counts are valid.

    Maps to RuleProfile in BimodalLogic's DataExport.lean.
    """

    imp_left: int = 0
    imp_right: int = 0
    box_left: int = 0
    box_right: int = 0
    untl_left: int = 0
    untl_right: int = 0
    snce_left: int = 0

    @classmethod
    def from_json(cls, data: dict) -> RuleProfile:
        return cls(
            imp_left=data.get("imp_left", 0),
            imp_right=data.get("imp_right", 0),
            box_left=data.get("box_left", 0),
            box_right=data.get("box_right", 0),
            untl_left=data.get("untl_left", 0),
            untl_right=data.get("untl_right", 0),
            snce_left=data.get("snce_left", 0),
        )

    def to_json(self) -> dict:
        return {
            "imp_left": self.imp_left,
            "imp_right": self.imp_right,
            "box_left": self.box_left,
            "box_right": self.box_right,
            "untl_left": self.untl_left,
            "untl_right": self.untl_right,
            "snce_left": self.snce_left,
        }


# ---------------------------------------------------------------------------
# ProofTrace: proof structure metadata
# ---------------------------------------------------------------------------


@dataclass
class ProofTrace:
    """
    Proof structure metadata for VALID formulas.

    height:       depth of the proof tree
    axioms_used:  list of axiom names applied (e.g. "id", "bot")
    rules_applied: detailed rule application statistics

    Maps to ProofTrace in BimodalLogic's DataExport.lean.
    """

    height: int
    axioms_used: list[str]
    rules_applied: RuleProfile

    @classmethod
    def from_json(cls, data: dict) -> ProofTrace:
        return cls(
            height=data["height"],
            axioms_used=list(data.get("axioms_used", [])),
            rules_applied=RuleProfile.from_json(data.get("rules_applied", {})),
        )

    def to_json(self) -> dict:
        return {
            "height": self.height,
            "axioms_used": self.axioms_used,
            "rules_applied": self.rules_applied.to_json(),
        }


# ---------------------------------------------------------------------------
# DifficultyMetrics: curriculum learning indicators
# ---------------------------------------------------------------------------


@dataclass
class DifficultyMetrics:
    """
    Complexity indicators for curriculum learning and dataset stratification.

    Maps to DifficultyMetrics in BimodalLogic's DataExport.lean.
    """

    complexity: int
    modal_depth: int
    temporal_depth: int
    imp_count: int
    atom_count: int
    decision_time_ms: float
    difficulty_tier: int  # 1 (easy) through 5 (hard)

    @classmethod
    def from_json(cls, data: dict) -> DifficultyMetrics:
        return cls(
            complexity=data["complexity"],
            modal_depth=data["modal_depth"],
            temporal_depth=data["temporal_depth"],
            imp_count=data["imp_count"],
            atom_count=data["atom_count"],
            decision_time_ms=float(data["decision_time_ms"]),
            difficulty_tier=data["difficulty_tier"],
        )

    def to_json(self) -> dict:
        return {
            "complexity": self.complexity,
            "modal_depth": self.modal_depth,
            "temporal_depth": self.temporal_depth,
            "imp_count": self.imp_count,
            "atom_count": self.atom_count,
            "decision_time_ms": self.decision_time_ms,
            "difficulty_tier": self.difficulty_tier,
        }


# ---------------------------------------------------------------------------
# LabeledFormula: top-level training record
# ---------------------------------------------------------------------------


@dataclass
class LabeledFormula:
    """
    Top-level training record exported by BimodalLogic.

    This is the primary data type for BimodalHarness. Each JSONL line from
    BimodalLogic decodes to one LabeledFormula.

    Fields:
        formula:      The bimodal formula AST
        label:        VALID | INVALID | TIMEOUT
        proof_trace:  Present for VALID formulas; None otherwise
        countermodel: Present for INVALID formulas; None otherwise
        metrics:      Complexity and timing metrics (always present)
        pattern_key:  Structural fingerprint (always present)

    Maps to LabeledFormula in BimodalLogic's DataExport.lean.
    """

    formula: FormulaNode
    label: Label
    metrics: DifficultyMetrics
    pattern_key: PatternKey
    proof_trace: ProofTrace | None = None
    countermodel: SimpleCountermodel | None = None

    @classmethod
    def from_json(cls, data: dict) -> LabeledFormula:
        """
        Deserialize a LabeledFormula from its JSON dict representation.

        Handles optional proof_trace and countermodel based on label value.

        Args:
            data: Dict matching the BimodalLogic export schema.

        Returns:
            LabeledFormula with all applicable fields populated.
        """
        label = Label(data["label"])

        proof_trace: ProofTrace | None = None
        countermodel: SimpleCountermodel | None = None

        if data.get("proof_trace") is not None:
            proof_trace = ProofTrace.from_json(data["proof_trace"])
        if data.get("countermodel") is not None:
            countermodel = SimpleCountermodel.from_json(data["countermodel"])

        return cls(
            formula=FormulaNode.from_json(data["formula"]),
            label=label,
            proof_trace=proof_trace,
            countermodel=countermodel,
            metrics=DifficultyMetrics.from_json(data["metrics"]),
            pattern_key=PatternKey.from_json(data["pattern_key"]),
        )

    def to_json(self) -> dict:
        """Serialize a LabeledFormula back to its JSON dict representation."""
        d: dict = {
            "formula": self.formula.to_json(),
            "label": self.label.value,
            "metrics": self.metrics.to_json(),
            "pattern_key": self.pattern_key.to_json(),
        }
        if self.proof_trace is not None:
            d["proof_trace"] = self.proof_trace.to_json()
        if self.countermodel is not None:
            d["countermodel"] = self.countermodel.to_json()
        return d


# ---------------------------------------------------------------------------
# JSONL I/O utilities
# ---------------------------------------------------------------------------


def load_jsonl(path: Any) -> Iterator[LabeledFormula]:
    """
    Lazily load a JSONL file of LabeledFormula records.

    Each line must be a valid JSON object matching the LabeledFormula schema.
    Empty lines and comment lines (starting with '#') are skipped.

    Args:
        path: Path-like or str pointing to a .jsonl file.

    Yields:
        LabeledFormula instances in file order.

    Raises:
        FileNotFoundError: If path does not exist.
        json.JSONDecodeError: If a line is not valid JSON.
        ValueError: If a JSON object does not match the LabeledFormula schema.
    """
    p = Path(path)
    with p.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            try:
                data = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise json.JSONDecodeError(
                    f"Line {line_no} in {p}: {exc.msg}", exc.doc, exc.pos
                ) from exc
            yield LabeledFormula.from_json(data)
