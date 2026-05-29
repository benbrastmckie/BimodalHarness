"""Unit tests for synthetic proof step data generator."""

from __future__ import annotations

import pytest

from bimodal_harness.data.synthetic_policy_data import generate_synthetic_proof_steps
from bimodal_harness.schema.actions import FRAME_CLASS_MASKS
from bimodal_harness.schema.records import ProofStepRecord


class TestGenerateSyntheticProofSteps:
    def test_returns_list_of_records(self):
        records = generate_synthetic_proof_steps(n_steps=100, seed=0)
        assert isinstance(records, list)
        assert len(records) > 0
        for r in records:
            assert isinstance(r, ProofStepRecord)

    def test_augmented_size_larger_than_input(self):
        # n_steps=100 base; augmented should be > 100
        records = generate_synthetic_proof_steps(n_steps=100, seed=0)
        assert len(records) > 100

    def test_records_have_valid_frame_class_base(self):
        records = generate_synthetic_proof_steps(n_steps=200, seed=1, frame_class="Base")
        for r in records:
            assert r.frame_class == "Base"

    def test_records_have_valid_frame_class_discrete(self):
        records = generate_synthetic_proof_steps(n_steps=200, seed=1, frame_class="Discrete")
        for r in records:
            assert r.frame_class == "Discrete"

    def test_records_have_valid_frame_class_dense(self):
        records = generate_synthetic_proof_steps(n_steps=200, seed=1, frame_class="Dense")
        for r in records:
            assert r.frame_class == "Dense"

    def test_all_base_valid_action_indices_covered(self):
        from bimodal_harness.schema.actions import ACTION_TO_INDEX
        # Generate enough records to cover all valid Base actions
        records = generate_synthetic_proof_steps(n_steps=1000, seed=42, frame_class="Base")
        found_indices = set(r.action_index for r in records)
        base_mask = FRAME_CLASS_MASKS["Base"]
        valid_indices = {i for i, v in enumerate(base_mask) if v}
        # Index 42 ("axiom" rule) is valid in mask but unreachable via step_to_action_index
        # (axiom rule records use specific axiom constructor indices 0-41 instead).
        # Exclude it from the coverage check.
        reachable_valid = valid_indices - {ACTION_TO_INDEX["axiom"]}
        missing = reachable_valid - found_indices
        assert len(missing) == 0, f"Missing action indices: {missing}"

    def test_discrete_only_axioms_not_in_base(self):
        records = generate_synthetic_proof_steps(n_steps=500, seed=0, frame_class="Base")
        base_mask = FRAME_CLASS_MASKS["Base"]
        for r in records:
            assert base_mask[r.action_index], (
                f"Invalid action {r.action_index} for Base frame class"
            )

    def test_discrete_axioms_present_for_discrete(self):
        from bimodal_harness.schema.actions import ACTION_TO_INDEX
        records = generate_synthetic_proof_steps(n_steps=500, seed=0, frame_class="Discrete")
        found_indices = set(r.action_index for r in records)
        # prior_UZ (index 37) and prior_SZ (index 38) should appear
        assert ACTION_TO_INDEX["prior_UZ"] in found_indices
        assert ACTION_TO_INDEX["prior_SZ"] in found_indices

    def test_dense_axioms_present_for_dense(self):
        from bimodal_harness.schema.actions import ACTION_TO_INDEX
        records = generate_synthetic_proof_steps(n_steps=500, seed=0, frame_class="Dense")
        found_indices = set(r.action_index for r in records)
        assert ACTION_TO_INDEX["density"] in found_indices
        assert ACTION_TO_INDEX["dense_indicator"] in found_indices

    def test_records_pass_dataclass_validation(self):
        # ProofStepRecord has __post_init__ validation; if records are created
        # successfully the validation passed.
        records = generate_synthetic_proof_steps(n_steps=200, seed=42)
        # Check basic field types
        for r in records:
            assert isinstance(r.step_id, str)
            assert isinstance(r.action_index, int)
            assert 0 <= r.action_index <= 48
            assert r.depth >= 0
            assert r.proof_height >= 0

    def test_reproducible_with_same_seed(self):
        records1 = generate_synthetic_proof_steps(n_steps=100, seed=7)
        records2 = generate_synthetic_proof_steps(n_steps=100, seed=7)
        assert len(records1) == len(records2)
        # Check action indices match (same order)
        indices1 = [r.action_index for r in records1]
        indices2 = [r.action_index for r in records2]
        assert indices1 == indices2

    def test_goal_json_has_valid_tag(self):
        from bimodal_harness.schema.constants import VALID_FORMULA_TAGS
        records = generate_synthetic_proof_steps(n_steps=200, seed=0)
        for r in records:
            assert r.goal_json.get("tag") in VALID_FORMULA_TAGS

    def test_all_rule_actions_covered(self):
        from bimodal_harness.schema.actions import RULE_ACTIONS, ACTION_TO_INDEX
        records = generate_synthetic_proof_steps(n_steps=500, seed=42)
        found_indices = set(r.action_index for r in records)
        # "axiom" rule (index 42) is covered by axiom constructor records (indices 0-41).
        # Check all other inference rules are present.
        for rule in RULE_ACTIONS:
            if rule == "axiom":
                continue
            idx = ACTION_TO_INDEX[rule]
            assert idx in found_indices, f"Rule action '{rule}' (index {idx}) not found"
