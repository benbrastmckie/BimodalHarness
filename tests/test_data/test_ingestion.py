"""Tests for data ingestion pipeline: translation, entry points, and cache.

Covers:
- Box formula validation fix (schema/formula.py)
- labeled_formula_to_training_record() translation function
- ingest_jsonl() and ingest_directory() pipeline entry points
- ingest_and_cache() / load_cached() Parquet cache round-trip
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bimodal_harness.data.ingestion import (
    DIFFICULTY_TIER_MAP,
    TOP_OPERATOR_MAP,
    ingest_and_cache,
    ingest_directory,
    ingest_jsonl,
    is_cache_fresh,
    labeled_formula_to_training_record,
    load_cached,
)
from bimodal_harness.data.schema import (
    DifficultyMetrics,
    FormulaNode,
    FormulaTag,
    Label,
    LabeledFormula,
    PatternKey,
    ProofTrace,
    RuleProfile,
    SimpleCountermodel,
)
from bimodal_harness.schema.formula import validate_formula_json
from bimodal_harness.schema.records import TrainingRecord

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

SAMPLE_JSONL = Path(__file__).parent.parent.parent / "data" / "samples" / "test_formulas.jsonl"


def _make_labeled_formula(
    *,
    tag: str = "atom",
    label: str = "VALID",
    difficulty_tier: int = 1,
    top_operator: str = "atom",
    with_proof: bool = True,
    with_countermodel: bool = False,
) -> LabeledFormula:
    """Construct a minimal LabeledFormula for testing."""
    if tag == "atom":
        formula = FormulaNode(tag=FormulaTag.ATOM, name="p")
    elif tag == "bot":
        formula = FormulaNode(tag=FormulaTag.BOT)
    elif tag == "imp":
        formula = FormulaNode(
            tag=FormulaTag.IMP,
            left=FormulaNode(tag=FormulaTag.ATOM, name="p"),
            right=FormulaNode(tag=FormulaTag.ATOM, name="q"),
        )
    elif tag == "box":
        formula = FormulaNode(
            tag=FormulaTag.BOX,
            child=FormulaNode(tag=FormulaTag.ATOM, name="p"),
            event=FormulaNode(tag=FormulaTag.ATOM, name="e"),
        )
    elif tag == "untl":
        formula = FormulaNode(
            tag=FormulaTag.UNTL,
            guard=FormulaNode(tag=FormulaTag.ATOM, name="p"),
            child=FormulaNode(tag=FormulaTag.ATOM, name="q"),
        )
    elif tag == "snce":
        formula = FormulaNode(
            tag=FormulaTag.SNCE,
            guard=FormulaNode(tag=FormulaTag.ATOM, name="r"),
            child=FormulaNode(tag=FormulaTag.ATOM, name="p"),
        )
    else:
        formula = FormulaNode(tag=FormulaTag.ATOM, name="p")

    metrics = DifficultyMetrics(
        complexity=3,
        modal_depth=0,
        temporal_depth=0,
        imp_count=0,
        atom_count=1,
        decision_time_ms=1.0,
        difficulty_tier=difficulty_tier,
    )
    pattern_key = PatternKey(
        modal_depth=0,
        temporal_depth=0,
        imp_count=0,
        complexity=3,
        top_operator=top_operator,
    )
    proof_trace = None
    if with_proof:
        proof_trace = ProofTrace(
            height=2,
            axioms_used=["id"],
            rules_applied=RuleProfile(),
        )
    countermodel_obj = None
    if with_countermodel:
        countermodel_obj = SimpleCountermodel(
            true_atoms=["p"],
            false_atoms=["q"],
            formula="p",
        )

    return LabeledFormula(
        formula=formula,
        label=Label(label),
        metrics=metrics,
        pattern_key=pattern_key,
        proof_trace=proof_trace,
        countermodel=countermodel_obj,
    )


# ---------------------------------------------------------------------------
# Box formula validation tests (Phase 1: bug fix)
# ---------------------------------------------------------------------------


class TestBoxFormulaValidation:
    """Box formula validation -- schema/formula.py requires only 'child'.

    The bimodal JSONL format includes {'child', 'event'} for box nodes.
    The validate_formula_json() function only requires 'child' (extra fields are
    silently ignored), so both formats are accepted.
    """

    def test_box_with_child_only_is_valid(self):
        """Box with only child is valid per schema/formula.py validation."""
        formula = {"tag": "box", "child": {"tag": "atom", "name": "p"}}
        assert validate_formula_json(formula) is True

    def test_box_with_child_and_event_is_valid(self):
        """Box with both child and event (JSONL format) also passes validation."""
        formula = {
            "tag": "box",
            "child": {"tag": "atom", "name": "p"},
            "event": {"tag": "atom", "name": "e"},
        }
        assert validate_formula_json(formula) is True

    def test_box_with_nested_child_is_valid(self):
        """Box with nested child formula tree is valid."""
        formula = {
            "tag": "box",
            "child": {"tag": "imp", "left": {"tag": "atom", "name": "p"}, "right": {"tag": "bot"}},
            "event": {"tag": "untl", "guard": {"tag": "bot"}, "child": {"tag": "bot"}},
        }
        assert validate_formula_json(formula) is True

    def test_box_missing_child_is_invalid(self):
        """Box without child field is invalid (child is required)."""
        formula = {"tag": "box"}
        assert validate_formula_json(formula) is False

    def test_box_with_invalid_child_is_invalid(self):
        """Box with invalid child formula tree must fail."""
        formula = {
            "tag": "box",
            "child": {"tag": "unknown_tag"},
        }
        assert validate_formula_json(formula) is False


# ---------------------------------------------------------------------------
# Translation function tests (Phase 1)
# ---------------------------------------------------------------------------


class TestLabeledFormulaToTrainingRecord:
    def test_timeout_returns_none(self):
        lf = _make_labeled_formula(label="TIMEOUT", with_proof=False)
        assert labeled_formula_to_training_record(lf) is None

    def test_valid_record_label(self):
        lf = _make_labeled_formula(label="VALID", tag="bot", top_operator="bot")
        record = labeled_formula_to_training_record(lf)
        assert record is not None
        assert record.label == "valid"

    def test_invalid_record_label(self):
        lf = _make_labeled_formula(
            label="INVALID", tag="atom", with_proof=False, with_countermodel=True
        )
        record = labeled_formula_to_training_record(lf)
        assert record is not None
        assert record.label == "invalid"

    def test_record_id_is_generated(self):
        lf = _make_labeled_formula(label="VALID", tag="bot", top_operator="bot")
        r1 = labeled_formula_to_training_record(lf)
        r2 = labeled_formula_to_training_record(lf)
        assert r1 is not None and r2 is not None
        # Each call generates a unique UUID
        assert r1.record_id != r2.record_id

    def test_record_id_is_uuid_format(self):
        import uuid

        lf = _make_labeled_formula(label="VALID", tag="bot", top_operator="bot")
        record = labeled_formula_to_training_record(lf)
        assert record is not None
        uuid.UUID(record.record_id)  # raises if not valid UUID

    def test_formula_pretty_derived(self):
        lf = _make_labeled_formula(label="VALID", tag="bot", top_operator="bot")
        record = labeled_formula_to_training_record(lf)
        assert record is not None
        assert record.formula_pretty == "⊥"

    def test_formula_json_round_trip(self):
        lf = _make_labeled_formula(label="VALID", tag="atom", top_operator="atom")
        record = labeled_formula_to_training_record(lf)
        assert record is not None
        assert record.formula_json == {"tag": "atom", "name": "p"}

    # Difficulty tier mappings
    # Note: tier 1 maps to "easy" (not "trivial") -- VALID_DIFFICULTY_TIERS
    # does not include "trivial". Tiers 1 and 2 both collapse to "easy".
    @pytest.mark.parametrize(
        ("tier_int", "tier_str"),
        [
            (1, "easy"),
            (2, "easy"),
            (3, "medium"),
            (4, "hard"),
            (5, "very_hard"),
        ],
    )
    def test_difficulty_tier_mapping(self, tier_int: int, tier_str: str):
        lf = _make_labeled_formula(
            label="VALID", tag="bot", top_operator="bot", difficulty_tier=tier_int
        )
        record = labeled_formula_to_training_record(lf)
        assert record is not None
        assert record.difficulty_metrics.difficulty_tier == tier_str

    def test_unknown_difficulty_tier_raises(self):
        lf = _make_labeled_formula(label="VALID", tag="bot", top_operator="bot")
        lf.metrics.difficulty_tier = 99  # type: ignore[attr-defined]  # force bad value
        with pytest.raises((KeyError, AttributeError)):
            labeled_formula_to_training_record(lf)

    # Top operator mappings
    @pytest.mark.parametrize(
        ("raw_op", "pascal_op"),
        [
            ("atom", "Atom"),
            ("bot", "Bottom"),
            ("imp", "Implication"),
            ("box", "Box"),
            ("untl", "Until"),
            ("snce", "Since"),
        ],
    )
    def test_top_operator_mapping(self, raw_op: str, pascal_op: str):
        # Build a formula matching the operator
        tag_map = {
            "atom": "atom",
            "bot": "bot",
            "imp": "imp",
            "box": "box",
            "untl": "untl",
            "snce": "snce",
        }
        tag = tag_map[raw_op]
        lf = _make_labeled_formula(label="VALID", tag=tag, top_operator=raw_op)
        record = labeled_formula_to_training_record(lf)
        assert record is not None
        assert record.pattern_key.top_operator == pascal_op

    def test_proof_trace_preserved_for_valid(self):
        lf = _make_labeled_formula(label="VALID", tag="bot", top_operator="bot", with_proof=True)
        record = labeled_formula_to_training_record(lf)
        assert record is not None
        assert record.proof_trace is not None
        assert record.proof_trace.height == 2
        assert record.proof_trace.axioms_used == ("id",)

    def test_countermodel_preserved_for_invalid(self):
        lf = _make_labeled_formula(
            label="INVALID",
            tag="atom",
            with_proof=False,
            with_countermodel=True,
        )
        record = labeled_formula_to_training_record(lf)
        assert record is not None
        assert record.countermodel is not None
        assert record.countermodel.true_atoms == ("p",)
        assert record.countermodel.false_atoms == ("q",)

    def test_search_depth_from_proof_height(self):
        lf = _make_labeled_formula(label="VALID", tag="bot", top_operator="bot", with_proof=True)
        record = labeled_formula_to_training_record(lf)
        assert record is not None
        assert record.difficulty_metrics.search_depth == 2  # from proof_trace.height

    def test_search_depth_defaults_zero_for_invalid(self):
        lf = _make_labeled_formula(
            label="INVALID",
            tag="atom",
            with_proof=False,
            with_countermodel=True,
        )
        record = labeled_formula_to_training_record(lf)
        assert record is not None
        assert record.difficulty_metrics.search_depth == 0

    def test_default_frame_class(self):
        lf = _make_labeled_formula(label="VALID", tag="bot", top_operator="bot")
        record = labeled_formula_to_training_record(lf)
        assert record is not None
        assert record.frame_class == "Base"

    def test_result_is_training_record_instance(self):
        lf = _make_labeled_formula(label="VALID", tag="bot", top_operator="bot")
        record = labeled_formula_to_training_record(lf)
        assert isinstance(record, TrainingRecord)


# ---------------------------------------------------------------------------
# ingest_jsonl tests (Phase 2)
# ---------------------------------------------------------------------------


class TestIngestJsonl:
    def test_sample_file_loads(self):
        records = ingest_jsonl(SAMPLE_JSONL)
        assert len(records) > 0

    def test_timeout_records_skipped(self):
        # The sample file has 1 TIMEOUT record; all others should be loaded
        records = ingest_jsonl(SAMPLE_JSONL)
        assert all(r.label in ("valid", "invalid") for r in records)

    def test_returns_training_records(self):
        records = ingest_jsonl(SAMPLE_JSONL)
        assert all(isinstance(r, TrainingRecord) for r in records)

    def test_correct_record_count(self):
        # Sample file: 8 records total, 1 TIMEOUT -> 7 training records
        records = ingest_jsonl(SAMPLE_JSONL)
        assert len(records) == 7

    def test_skip_timeout_false_raises(self):
        """skip_timeout=False raises when TIMEOUT is encountered."""
        with pytest.raises(ValueError, match="TIMEOUT"):
            ingest_jsonl(SAMPLE_JSONL, skip_timeout=False)

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            ingest_jsonl(Path("/nonexistent/path.jsonl"))

    def test_field_values_on_valid_record(self):
        """Verify bot formula translates correctly."""
        records = ingest_jsonl(SAMPLE_JSONL)
        # Second record in sample is VALID bot formula
        bot_records = [r for r in records if r.formula_json == {"tag": "bot"}]
        assert len(bot_records) == 1
        bot = bot_records[0]
        assert bot.label == "valid"
        assert bot.formula_pretty == "⊥"
        assert bot.pattern_key.top_operator == "Bottom"
        # Sample bot has difficulty_tier=1 -> "easy" (tier 1 and 2 both map to "easy")
        assert bot.difficulty_metrics.difficulty_tier == "easy"

    def test_box_formula_translates(self):
        """Box formula with event field loads without error."""
        records = ingest_jsonl(SAMPLE_JSONL)
        box_records = [r for r in records if r.formula_json.get("tag") == "box"]
        assert len(box_records) == 1
        box = box_records[0]
        assert box.pattern_key.top_operator == "Box"
        assert box.difficulty_metrics.difficulty_tier == "easy"  # tier 2 -> "easy"


# ---------------------------------------------------------------------------
# ingest_directory tests (Phase 2)
# ---------------------------------------------------------------------------


class TestIngestDirectory:
    def test_single_jsonl_file(self, tmp_path: Path):
        """A directory with one JSONL file produces correct records."""
        # Copy sample to temp dir
        src = SAMPLE_JSONL.read_text()
        dest = tmp_path / "test.jsonl"
        dest.write_text(src)

        records = ingest_directory(tmp_path)
        assert len(records) == 7  # same as ingest_jsonl result

    def test_multiple_jsonl_files(self, tmp_path: Path):
        """Records from multiple files are concatenated."""
        src = SAMPLE_JSONL.read_text()
        (tmp_path / "a.jsonl").write_text(src)
        (tmp_path / "b.jsonl").write_text(src)

        records = ingest_directory(tmp_path)
        assert len(records) == 14  # 7 * 2 files

    def test_empty_directory(self, tmp_path: Path):
        """Empty directory returns empty list."""
        records = ingest_directory(tmp_path)
        assert records == []

    def test_only_timeout_records(self, tmp_path: Path):
        """File containing only TIMEOUT records produces empty list."""
        timeout_line = json.dumps(
            {
                "formula": {
                    "tag": "imp",
                    "left": {
                        "tag": "box",
                        "child": {"tag": "atom", "name": "p"},
                        "event": {"tag": "atom", "name": "e"},
                    },
                    "right": {"tag": "bot"},
                },
                "label": "TIMEOUT",
                "metrics": {
                    "complexity": 5,
                    "modal_depth": 1,
                    "temporal_depth": 0,
                    "imp_count": 1,
                    "atom_count": 2,
                    "decision_time_ms": 5000.0,
                    "difficulty_tier": 5,
                },
                "pattern_key": {
                    "modal_depth": 1,
                    "temporal_depth": 0,
                    "imp_count": 1,
                    "complexity": 5,
                    "top_operator": "imp",
                },
            }
        )
        (tmp_path / "timeouts.jsonl").write_text(timeout_line + "\n")
        records = ingest_directory(tmp_path)
        assert records == []

    def test_nonexistent_directory_raises(self):
        with pytest.raises(FileNotFoundError):
            ingest_directory(Path("/nonexistent/dir"))

    def test_custom_glob_pattern(self, tmp_path: Path):
        """Only files matching glob pattern are loaded."""
        src = SAMPLE_JSONL.read_text()
        (tmp_path / "data.jsonl").write_text(src)
        (tmp_path / "ignored.txt").write_text("not jsonl")

        records = ingest_directory(tmp_path, glob="*.jsonl")
        assert len(records) == 7


# ---------------------------------------------------------------------------
# Parquet cache tests (Phase 4)
# ---------------------------------------------------------------------------


class TestParquetCache:
    def test_ingest_and_cache_creates_file(self, tmp_path: Path):
        src = SAMPLE_JSONL.read_text()
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "sample.jsonl").write_text(src)
        cache = tmp_path / "cache.parquet"

        ingest_and_cache(data_dir, cache)
        assert cache.exists()

    def test_load_cached_returns_records(self, tmp_path: Path):
        src = SAMPLE_JSONL.read_text()
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "sample.jsonl").write_text(src)
        cache = tmp_path / "cache.parquet"

        ingest_and_cache(data_dir, cache)
        records = load_cached(cache)
        assert len(records) == 7

    def test_cache_round_trip_preserves_label(self, tmp_path: Path):
        src = SAMPLE_JSONL.read_text()
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "sample.jsonl").write_text(src)
        cache = tmp_path / "cache.parquet"

        original = ingest_and_cache(data_dir, cache)
        loaded = load_cached(cache)

        orig_labels = sorted(r.label for r in original)
        load_labels = sorted(r.label for r in loaded)
        assert orig_labels == load_labels

    def test_cache_round_trip_preserves_formula_pretty(self, tmp_path: Path):
        src = SAMPLE_JSONL.read_text()
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "sample.jsonl").write_text(src)
        cache = tmp_path / "cache.parquet"

        original = ingest_and_cache(data_dir, cache)
        loaded = load_cached(cache)

        orig_pretty = sorted(r.formula_pretty for r in original)
        load_pretty = sorted(r.formula_pretty for r in loaded)
        assert orig_pretty == load_pretty

    def test_cache_round_trip_preserves_difficulty_tier(self, tmp_path: Path):
        src = SAMPLE_JSONL.read_text()
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "sample.jsonl").write_text(src)
        cache = tmp_path / "cache.parquet"

        original = ingest_and_cache(data_dir, cache)
        loaded = load_cached(cache)

        orig_tiers = sorted(r.difficulty_metrics.difficulty_tier for r in original)
        load_tiers = sorted(r.difficulty_metrics.difficulty_tier for r in loaded)
        assert orig_tiers == load_tiers

    def test_load_cached_not_found_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            load_cached(tmp_path / "nonexistent.parquet")

    def test_is_cache_fresh_no_cache(self, tmp_path: Path):
        """Returns False if cache doesn't exist."""
        assert is_cache_fresh(tmp_path, tmp_path / "cache.parquet") is False

    def test_is_cache_fresh_stale(self, tmp_path: Path):
        """Returns False if cache is older than source files."""
        import time

        data_dir = tmp_path / "data"
        data_dir.mkdir()
        src = SAMPLE_JSONL.read_text()
        cache = tmp_path / "cache.parquet"

        # Write cache first (older)
        cache.write_bytes(b"fake")
        time.sleep(0.05)
        # Write source after (newer)
        (data_dir / "sample.jsonl").write_text(src)

        assert is_cache_fresh(data_dir, cache) is False

    def test_is_cache_fresh_fresh(self, tmp_path: Path):
        """Returns True if cache is newer than all source files."""
        import time

        data_dir = tmp_path / "data"
        data_dir.mkdir()
        src = SAMPLE_JSONL.read_text()

        # Write source first (older)
        (data_dir / "sample.jsonl").write_text(src)
        time.sleep(0.05)
        # Write cache after (newer)
        cache = tmp_path / "cache.parquet"
        cache.write_bytes(b"fake")

        assert is_cache_fresh(data_dir, cache) is True


# ---------------------------------------------------------------------------
# Constant coverage tests
# ---------------------------------------------------------------------------


class TestTranslationConstants:
    def test_difficulty_tier_map_has_all_tiers(self):
        assert set(DIFFICULTY_TIER_MAP.keys()) == {1, 2, 3, 4, 5}
        # "trivial" is not in VALID_DIFFICULTY_TIERS; tiers 1 and 2 both map to "easy"
        assert set(DIFFICULTY_TIER_MAP.values()) == {
            "easy",
            "medium",
            "hard",
            "very_hard",
        }

    def test_top_operator_map_has_all_operators(self):
        assert set(TOP_OPERATOR_MAP.keys()) == {"atom", "bot", "imp", "box", "untl", "snce"}
        assert set(TOP_OPERATOR_MAP.values()) == {
            "Atom",
            "Bottom",
            "Implication",
            "Box",
            "Until",
            "Since",
        }
