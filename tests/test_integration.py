"""
Integration tests for the BimodalHarness cross-repo data pipeline.

Tests cover:
- End-to-end JSONL loading from data/samples/test_formulas.jsonl
- ModelChecker import check (skipped if not installed)
- data/VERSION file format validation
- All formula tags present in sample data
- All label types (VALID, INVALID, TIMEOUT) present in sample data
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from bimodal_harness.data.schema import (
    FormulaTag,
    Label,
    LabeledFormula,
    load_jsonl,
)

# Path to the sample JSONL file (relative to project root, found via this file's location)
TESTS_DIR = Path(__file__).parent
PROJECT_ROOT = TESTS_DIR.parent
SAMPLE_JSONL = PROJECT_ROOT / "data" / "samples" / "test_formulas.jsonl"
DATA_VERSION = PROJECT_ROOT / "data" / "VERSION"


# ---------------------------------------------------------------------------
# JSONL loading tests
# ---------------------------------------------------------------------------

class TestSampleJsonlLoading:
    def test_sample_file_exists(self):
        assert SAMPLE_JSONL.exists(), f"Sample JSONL not found at {SAMPLE_JSONL}"

    def test_loads_all_records(self):
        records = list(load_jsonl(SAMPLE_JSONL))
        assert len(records) > 0, "Sample JSONL must contain at least one record"

    def test_all_records_are_labeled_formulas(self):
        for record in load_jsonl(SAMPLE_JSONL):
            assert isinstance(record, LabeledFormula)

    def test_contains_all_formula_tags(self):
        """All six formula tags must appear in the sample data."""
        seen_tags: set[FormulaTag] = set()

        def collect_tags(node):
            seen_tags.add(node.tag)
            for child in [node.child, node.left, node.right, node.event, node.guard]:
                if child is not None:
                    collect_tags(child)

        for record in load_jsonl(SAMPLE_JSONL):
            collect_tags(record.formula)

        expected_tags = set(FormulaTag)
        missing = expected_tags - seen_tags
        assert not missing, f"Formula tags missing from sample data: {missing}"

    def test_contains_all_label_types(self):
        """VALID, INVALID, and TIMEOUT must all appear in sample data."""
        seen_labels: set[Label] = set()
        for record in load_jsonl(SAMPLE_JSONL):
            seen_labels.add(record.label)

        expected_labels = set(Label)
        missing = expected_labels - seen_labels
        assert not missing, f"Labels missing from sample data: {missing}"

    def test_valid_records_have_proof_trace(self):
        for record in load_jsonl(SAMPLE_JSONL):
            if record.label == Label.VALID:
                assert record.proof_trace is not None, (
                    f"VALID record missing proof_trace: {record.formula.tag}"
                )

    def test_invalid_records_have_countermodel(self):
        for record in load_jsonl(SAMPLE_JSONL):
            if record.label == Label.INVALID:
                assert record.countermodel is not None, (
                    f"INVALID record missing countermodel: {record.formula.tag}"
                )

    def test_timeout_records_have_no_trace_or_countermodel(self):
        for record in load_jsonl(SAMPLE_JSONL):
            if record.label == Label.TIMEOUT:
                assert record.proof_trace is None
                assert record.countermodel is None

    def test_metrics_always_present(self):
        for record in load_jsonl(SAMPLE_JSONL):
            assert record.metrics is not None
            assert record.pattern_key is not None

    def test_round_trip_all_records(self):
        """from_json(to_json(x)).label == x.label for all sample records."""
        for record in load_jsonl(SAMPLE_JSONL):
            as_dict = record.to_json()
            roundtripped = LabeledFormula.from_json(as_dict)
            assert roundtripped.label == record.label
            assert roundtripped.formula.tag == record.formula.tag
            assert roundtripped.metrics.complexity == record.metrics.complexity


# ---------------------------------------------------------------------------
# data/VERSION file tests
# ---------------------------------------------------------------------------

class TestDataVersion:
    def test_version_file_exists(self):
        assert DATA_VERSION.exists(), f"data/VERSION not found at {DATA_VERSION}"

    def test_version_file_has_schema_version(self):
        content = DATA_VERSION.read_text()
        assert "SCHEMA_VERSION=" in content, "data/VERSION must contain SCHEMA_VERSION="

    def test_version_file_has_lean_version(self):
        content = DATA_VERSION.read_text()
        assert "LEAN_VERSION=" in content, "data/VERSION must contain LEAN_VERSION="

    def test_version_file_has_model_checker_version(self):
        content = DATA_VERSION.read_text()
        assert "MODEL_CHECKER_VERSION=" in content, (
            "data/VERSION must contain MODEL_CHECKER_VERSION="
        )


# ---------------------------------------------------------------------------
# ModelChecker import test (skipped if not installed)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    importlib.util.find_spec("model_checker") is None,
    reason="model-checker package not installed",
)
class TestModelCheckerImport:
    def test_bimodal_theory_importable(self):
        """BimodalSemantics must be importable from model_checker.theory_lib.bimodal."""
        from model_checker.theory_lib import bimodal  # type: ignore[import]
        assert hasattr(bimodal, "BimodalSemantics"), (
            "model_checker.theory_lib.bimodal.BimodalSemantics not found"
        )

    def test_bimodal_semantics_instantiable(self):
        """BimodalSemantics must be instantiable (basic smoke test)."""
        from model_checker.theory_lib.bimodal import BimodalSemantics  # type: ignore[import]
        # Just verifying the class exists and is callable; don't pass arguments
        # since the constructor signature may vary between versions
        assert callable(BimodalSemantics)
