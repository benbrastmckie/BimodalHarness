"""Integration tests for the proof step ingestion pipeline.

Tests ``load_proof_steps``, ``get_frame_class_mask``,
``proof_step_statistics``, and ``print_proof_step_statistics`` from
``bimodal_harness.data.ingestion``.

These tests use a fixture JSONL file (``tests/fixtures/proof_steps_fixture.jsonl``)
that contains synthetic proof steps with known field values, avoiding any
dependency on the Lean build environment.
"""

from __future__ import annotations

import json
import textwrap
from io import StringIO
from pathlib import Path

import pytest

from bimodal_harness.data.ingestion import (
    get_frame_class_mask,
    load_proof_steps,
    print_proof_step_statistics,
    proof_step_statistics,
)
from bimodal_harness.schema.actions import (
    ACTION_TO_INDEX,
    ALL_ACTIONS,
    AXIOM_ACTIONS,
    RULE_ACTIONS,
)
from bimodal_harness.schema.records import ProofStepRecord

# ---------------------------------------------------------------------------
# Fixture paths
# ---------------------------------------------------------------------------

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures"
PROOF_STEPS_FIXTURE = FIXTURE_DIR / "proof_steps_fixture.jsonl"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_step_dict(**kwargs) -> dict:
    """Build a valid proof step dict with sensible defaults, overriding with kwargs."""
    defaults = {
        "step_id": "t/0",
        "theorem_name": "t",
        "context": [],
        "goal_json": {"tag": "bot"},
        "goal_pretty": "⊥",
        "rule": "axiom",
        "axiom_name": "ex_falso",
        "action_index": ACTION_TO_INDEX["ex_falso"],
        "subgoals": [],
        "depth": 0,
        "frame_class": "Base",
        "proof_height": 0,
    }
    defaults.update(kwargs)
    return defaults


# ---------------------------------------------------------------------------
# Tests for load_proof_steps with fixture file
# ---------------------------------------------------------------------------


class TestLoadProofStepsFixture:
    """Test load_proof_steps against the synthetic fixture JSONL."""

    def test_fixture_file_exists(self):
        assert PROOF_STEPS_FIXTURE.exists(), (
            f"Fixture file not found: {PROOF_STEPS_FIXTURE}"
        )

    def test_loads_expected_record_count(self):
        """Fixture has 10 proof step records."""
        records = load_proof_steps(PROOF_STEPS_FIXTURE)
        assert len(records) == 10

    def test_all_records_are_proof_step_records(self):
        records = load_proof_steps(PROOF_STEPS_FIXTURE)
        for r in records:
            assert isinstance(r, ProofStepRecord)

    def test_action_indices_in_valid_range(self):
        """All action_index values must be in [0, 48]."""
        records = load_proof_steps(PROOF_STEPS_FIXTURE)
        for r in records:
            assert 0 <= r.action_index <= 48, (
                f"Step {r.step_id!r}: action_index={r.action_index} out of range"
            )

    def test_all_rules_are_valid(self):
        """All rule names must be in RULE_ACTIONS."""
        records = load_proof_steps(PROOF_STEPS_FIXTURE)
        for r in records:
            assert r.rule in RULE_ACTIONS, (
                f"Step {r.step_id!r}: invalid rule {r.rule!r}"
            )

    def test_axiom_name_present_iff_rule_is_axiom(self):
        """axiom_name is non-None iff rule == 'axiom'."""
        records = load_proof_steps(PROOF_STEPS_FIXTURE)
        for r in records:
            if r.rule == "axiom":
                assert r.axiom_name is not None, (
                    f"Step {r.step_id!r}: axiom_name is None for rule='axiom'"
                )
            else:
                assert r.axiom_name is None, (
                    f"Step {r.step_id!r}: axiom_name={r.axiom_name!r} for rule={r.rule!r}"
                )

    def test_action_index_consistent_with_rule_and_axiom_name(self):
        """With validate_action_index=True, no validation errors should occur."""
        # This implicitly tests that the fixture's action_index values are
        # consistent with step_to_action_index.
        records = load_proof_steps(PROOF_STEPS_FIXTURE, validate_action_index=True)
        assert len(records) == 10

    def test_distinct_theorems(self):
        """Fixture has 3 distinct theorems."""
        records = load_proof_steps(PROOF_STEPS_FIXTURE)
        theorems = set(r.theorem_name for r in records)
        assert len(theorems) == 4, f"Expected 4 theorems, got {sorted(theorems)}"

    def test_first_record_fields(self):
        """Spot-check the first record's fields."""
        records = load_proof_steps(PROOF_STEPS_FIXTURE)
        r = records[0]
        assert r.step_id == "prop_k_inst/0"
        assert r.theorem_name == "prop_k_inst"
        assert r.rule == "axiom"
        assert r.axiom_name == "prop_s"
        assert r.action_index == ACTION_TO_INDEX["prop_s"]
        assert r.context == ()
        assert r.subgoals == ()
        assert r.depth == 0
        assert r.proof_height == 0
        assert r.frame_class == "Base"

    def test_modus_ponens_step_has_subgoals(self):
        """The modus_ponens step (step_id='mp_example/0') should have 2 subgoals."""
        records = load_proof_steps(PROOF_STEPS_FIXTURE)
        mp_steps = [r for r in records if r.step_id == "mp_example/0"]
        assert len(mp_steps) == 1
        mp = mp_steps[0]
        assert mp.rule == "modus_ponens"
        assert len(mp.subgoals) == 2
        assert mp.action_index == 44

    def test_context_non_empty_step(self):
        """nec_example/3 has a non-empty context."""
        records = load_proof_steps(PROOF_STEPS_FIXTURE)
        ctx_steps = [r for r in records if r.step_id == "nec_example/3"]
        assert len(ctx_steps) == 1
        r = ctx_steps[0]
        assert len(r.context) == 1
        assert "p → (p → p)" in r.context


# ---------------------------------------------------------------------------
# Tests for load_proof_steps with temporary files
# ---------------------------------------------------------------------------


class TestLoadProofStepsTempFiles:
    """Test load_proof_steps with dynamically created JSONL files."""

    def test_file_not_found_raises(self, tmp_path):
        missing = tmp_path / "nonexistent.jsonl"
        with pytest.raises(FileNotFoundError):
            load_proof_steps(missing)

    def test_empty_file_returns_empty_list(self, tmp_path):
        empty = tmp_path / "empty.jsonl"
        empty.write_text("")
        records = load_proof_steps(empty)
        assert records == []

    def test_comment_lines_skipped(self, tmp_path):
        """Lines starting with '#' are treated as comments."""
        f = tmp_path / "commented.jsonl"
        line = json.dumps(make_step_dict())
        f.write_text(f"# This is a comment\n{line}\n")
        records = load_proof_steps(f)
        assert len(records) == 1

    def test_blank_lines_skipped(self, tmp_path):
        """Blank lines are skipped without error."""
        f = tmp_path / "blank_lines.jsonl"
        line = json.dumps(make_step_dict())
        f.write_text(f"\n{line}\n\n{line}\n")
        records = load_proof_steps(f, validate_action_index=False)
        assert len(records) == 2

    def test_valid_single_record(self, tmp_path):
        f = tmp_path / "single.jsonl"
        d = make_step_dict()
        f.write_text(json.dumps(d) + "\n")
        records = load_proof_steps(f)
        assert len(records) == 1
        assert records[0].step_id == "t/0"

    def test_multiple_records(self, tmp_path):
        f = tmp_path / "multi.jsonl"
        lines = [
            json.dumps(make_step_dict(step_id=f"t/{i}", theorem_name="t"))
            for i in range(5)
        ]
        f.write_text("\n".join(lines) + "\n")
        records = load_proof_steps(f, validate_action_index=False)
        assert len(records) == 5

    def test_action_index_mismatch_raises(self, tmp_path):
        """A record with wrong action_index should raise ValueError."""
        f = tmp_path / "bad.jsonl"
        # prop_k is at index 0, but we'll claim index 5
        d = make_step_dict(
            rule="axiom",
            axiom_name="prop_k",
            action_index=5,  # wrong: should be 0
        )
        f.write_text(json.dumps(d) + "\n")
        with pytest.raises(ValueError, match="action_index mismatch"):
            load_proof_steps(f, validate_action_index=True)

    def test_action_index_mismatch_ignored_when_validation_disabled(self, tmp_path):
        """Validation can be disabled to allow mismatched action_index."""
        f = tmp_path / "bad.jsonl"
        d = make_step_dict(
            rule="axiom",
            axiom_name="prop_k",
            action_index=5,  # wrong
        )
        f.write_text(json.dumps(d) + "\n")
        records = load_proof_steps(f, validate_action_index=False)
        assert len(records) == 1
        assert records[0].action_index == 5  # preserved as-is

    def test_records_have_correct_types(self, tmp_path):
        """context and subgoals should be tuples after loading."""
        f = tmp_path / "types.jsonl"
        d = make_step_dict(context=["φ", "ψ"], subgoals=[{"tag": "bot"}])
        f.write_text(json.dumps(d) + "\n")
        records = load_proof_steps(f, validate_action_index=False)
        r = records[0]
        assert isinstance(r.context, tuple)
        assert isinstance(r.subgoals, tuple)

    def test_modus_ponens_record(self, tmp_path):
        """A modus_ponens step with valid action_index passes validation."""
        f = tmp_path / "mp.jsonl"
        d = make_step_dict(
            rule="modus_ponens",
            axiom_name=None,
            action_index=ACTION_TO_INDEX["modus_ponens"],
            subgoals=[{"tag": "bot"}, {"tag": "atom", "name": "p"}],
            depth=1,
            proof_height=3,
        )
        f.write_text(json.dumps(d) + "\n")
        records = load_proof_steps(f)
        assert records[0].rule == "modus_ponens"
        assert records[0].action_index == 44

    def test_all_valid_rules_load_correctly(self, tmp_path):
        """One record per rule should all load without errors."""
        f = tmp_path / "all_rules.jsonl"
        lines = []
        for rule in RULE_ACTIONS:
            if rule == "axiom":
                d = make_step_dict(rule="axiom", axiom_name="prop_k", action_index=0)
            else:
                d = make_step_dict(
                    rule=rule,
                    axiom_name=None,
                    action_index=ACTION_TO_INDEX[rule],
                )
            lines.append(json.dumps(d))
        f.write_text("\n".join(lines) + "\n")
        records = load_proof_steps(f)
        assert len(records) == len(RULE_ACTIONS)


# ---------------------------------------------------------------------------
# Tests for get_frame_class_mask
# ---------------------------------------------------------------------------


class TestGetFrameClassMask:
    """Test get_frame_class_mask returns the correct boolean masks."""

    def test_base_mask_length(self):
        record = ProofStepRecord(**{**make_step_dict(), "context": (), "subgoals": ()})
        mask = get_frame_class_mask(record)
        assert len(mask) == 49

    def test_base_mask_true_count(self):
        record = ProofStepRecord(**{**make_step_dict(), "context": (), "subgoals": ()})
        mask = get_frame_class_mask(record)
        # Base: 37 base axioms + 7 rules = 44 True values
        assert sum(mask) == 44

    def test_dense_mask_true_count(self):
        record = ProofStepRecord(
            **{
                **make_step_dict(frame_class="Dense"),
                "context": (),
                "subgoals": (),
            }
        )
        mask = get_frame_class_mask(record)
        # Dense: 39 axioms + 7 rules = 46 True values
        assert sum(mask) == 46

    def test_discrete_mask_true_count(self):
        record = ProofStepRecord(
            **{
                **make_step_dict(frame_class="Discrete"),
                "context": (),
                "subgoals": (),
            }
        )
        mask = get_frame_class_mask(record)
        # Discrete: 40 axioms + 7 rules = 47 True values
        assert sum(mask) == 47

    def test_mask_is_list_of_bools(self):
        record = ProofStepRecord(**{**make_step_dict(), "context": (), "subgoals": ()})
        mask = get_frame_class_mask(record)
        assert isinstance(mask, list)
        assert all(isinstance(v, bool) for v in mask)


# ---------------------------------------------------------------------------
# Tests for proof_step_statistics
# ---------------------------------------------------------------------------


class TestProofStepStatistics:
    """Test proof_step_statistics summary computation."""

    def test_empty_returns_zero_stats(self):
        stats = proof_step_statistics([])
        assert stats["total_steps"] == 0
        assert stats["theorem_count"] == 0
        assert stats["depth_min"] is None
        assert stats["depth_max"] is None
        assert stats["depth_mean"] is None
        assert stats["rule_distribution"] == {}
        assert stats["axiom_distribution"] == {}
        assert stats["action_index_coverage"] == 0

    def test_total_steps_from_fixture(self):
        records = load_proof_steps(PROOF_STEPS_FIXTURE)
        stats = proof_step_statistics(records)
        assert stats["total_steps"] == 10

    def test_theorem_count_from_fixture(self):
        records = load_proof_steps(PROOF_STEPS_FIXTURE)
        stats = proof_step_statistics(records)
        assert stats["theorem_count"] == 4

    def test_depth_range_from_fixture(self):
        records = load_proof_steps(PROOF_STEPS_FIXTURE)
        stats = proof_step_statistics(records)
        assert stats["depth_min"] == 0
        assert stats["depth_max"] == 3

    def test_depth_mean_from_fixture(self):
        records = load_proof_steps(PROOF_STEPS_FIXTURE)
        stats = proof_step_statistics(records)
        depths = [r.depth for r in records]
        expected_mean = sum(depths) / len(depths)
        assert abs(stats["depth_mean"] - expected_mean) < 1e-9

    def test_rule_distribution_contains_expected_rules(self):
        records = load_proof_steps(PROOF_STEPS_FIXTURE)
        stats = proof_step_statistics(records)
        rd = stats["rule_distribution"]
        assert "axiom" in rd
        assert "modus_ponens" in rd
        assert "assumption" in rd
        assert "necessitation" in rd
        assert "weakening" in rd

    def test_axiom_distribution_only_for_axiom_rule(self):
        records = load_proof_steps(PROOF_STEPS_FIXTURE)
        stats = proof_step_statistics(records)
        # Only axiom-rule steps contribute to axiom_distribution
        ad = stats["axiom_distribution"]
        axiom_steps = [r for r in records if r.rule == "axiom"]
        total_from_dist = sum(ad.values())
        assert total_from_dist == len(axiom_steps)

    def test_action_index_coverage_positive(self):
        records = load_proof_steps(PROOF_STEPS_FIXTURE)
        stats = proof_step_statistics(records)
        # We use axiom and rule steps, so coverage should be > 0
        assert stats["action_index_coverage"] > 0

    def test_action_index_coverage_at_most_49(self):
        records = load_proof_steps(PROOF_STEPS_FIXTURE)
        stats = proof_step_statistics(records)
        assert stats["action_index_coverage"] <= 49

    def test_rule_distribution_counts_sum_to_total(self):
        records = load_proof_steps(PROOF_STEPS_FIXTURE)
        stats = proof_step_statistics(records)
        total = sum(stats["rule_distribution"].values())
        assert total == stats["total_steps"]

    def test_single_record_stats(self, tmp_path):
        """Statistics for a single record should be well-defined."""
        f = tmp_path / "single.jsonl"
        f.write_text(json.dumps(make_step_dict()) + "\n")
        records = load_proof_steps(f)
        stats = proof_step_statistics(records)
        assert stats["total_steps"] == 1
        assert stats["theorem_count"] == 1
        assert stats["depth_min"] == 0
        assert stats["depth_max"] == 0
        assert stats["depth_mean"] == 0.0
        assert stats["action_index_coverage"] == 1


# ---------------------------------------------------------------------------
# Tests for print_proof_step_statistics
# ---------------------------------------------------------------------------


class TestPrintProofStepStatistics:
    """Test that print_proof_step_statistics produces sensible output."""

    def test_prints_without_error(self, capsys):
        records = load_proof_steps(PROOF_STEPS_FIXTURE)
        print_proof_step_statistics(records)
        captured = capsys.readouterr()
        assert "Total steps" in captured.out

    def test_prints_theorem_count(self, capsys):
        records = load_proof_steps(PROOF_STEPS_FIXTURE)
        print_proof_step_statistics(records)
        captured = capsys.readouterr()
        assert "Distinct theorems" in captured.out

    def test_prints_rule_distribution(self, capsys):
        records = load_proof_steps(PROOF_STEPS_FIXTURE)
        print_proof_step_statistics(records)
        captured = capsys.readouterr()
        assert "Rule distribution" in captured.out
        assert "axiom" in captured.out

    def test_prints_axiom_distribution_when_present(self, capsys):
        records = load_proof_steps(PROOF_STEPS_FIXTURE)
        print_proof_step_statistics(records)
        captured = capsys.readouterr()
        assert "Axiom distribution" in captured.out

    def test_empty_records_prints_without_error(self, capsys):
        print_proof_step_statistics([])
        captured = capsys.readouterr()
        assert "Total steps" in captured.out
        assert "0" in captured.out
