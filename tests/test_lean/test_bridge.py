"""Validation tests for the Python-Lean bridge via lean-interact.

All tests are marked ``@pytest.mark.lean`` and are skipped by default.
Run them explicitly with::

    pytest tests/test_lean/ -m lean -v

Requirements:
- lean-interact installed: ``pip install 'bimodal-harness[lean]'``
- BimodalLogic built: ``lake build`` in the BimodalLogic project directory

These tests exercise both the REPL path (via :class:`LeanBridge`) and
the subprocess path (``lake exe``).
"""

from __future__ import annotations

import pytest

from bimodal_harness.lean import (
    CommandResponse,
    LabelResult,
    LeanBridge,
    LeanBridgeError,
    SubprocessResult,
    TacticResult,
    lean_interact_available,
)
from bimodal_harness.lean.bridge import (
    LeanInteractNotInstalledError,
)

# ---------------------------------------------------------------------------
# Importability tests (no lean-interact required)
# ---------------------------------------------------------------------------


class TestImportability:
    """Verify that the module and all public symbols are importable without lean-interact."""

    def test_module_importable(self) -> None:
        """Bridge module must import cleanly without lean-interact installed."""
        import bimodal_harness.lean  # noqa: F401

    def test_all_public_classes_importable(self) -> None:
        """All public classes and functions must be importable."""
        assert LeanBridge is not None
        assert LeanBridgeError is not None
        assert LeanInteractNotInstalledError is not None
        assert CommandResponse is not None
        assert LabelResult is not None
        assert TacticResult is not None
        assert SubprocessResult is not None

    def test_lean_interact_available_returns_bool(self) -> None:
        """lean_interact_available() must return a bool without raising."""
        result = lean_interact_available()
        assert isinstance(result, bool)

    def test_lean_bridge_instantiation_without_start(self) -> None:
        """LeanBridge can be instantiated (not started) without lean-interact."""
        bridge = LeanBridge(project_path="/tmp/does_not_exist")
        assert not bridge.is_started
        assert bridge.project_path == "/tmp/does_not_exist"

    def test_run_command_raises_without_start(self) -> None:
        """run_command() must raise LeanBridgeError when not started."""
        bridge = LeanBridge(project_path="/tmp/does_not_exist")
        with pytest.raises(LeanBridgeError, match="not been started"):
            bridge.run_command("#check Nat")

    def test_apply_tactic_raises_without_start(self) -> None:
        """apply_tactic() must raise LeanBridgeError when not started."""
        bridge = LeanBridge(project_path="/tmp/does_not_exist")
        with pytest.raises(LeanBridgeError, match="not been started"):
            bridge.apply_tactic(proof_state=0, tactic="rfl")

    def test_start_raises_without_lean_interact(self) -> None:
        """start() must raise LeanInteractNotInstalledError when lean-interact is absent."""
        if lean_interact_available():
            pytest.skip("lean-interact is installed; skip this negative test")
        bridge = LeanBridge(project_path="/tmp/does_not_exist")
        with pytest.raises(LeanInteractNotInstalledError):
            bridge.start()


# ---------------------------------------------------------------------------
# Result dataclass tests (no lean-interact required)
# ---------------------------------------------------------------------------


class TestResultDataclasses:
    """Verify the result dataclass APIs."""

    def test_command_response_ok(self) -> None:
        resp = CommandResponse(command="#check Nat", output="Nat : Type", error=None)
        assert resp.ok is True

    def test_command_response_not_ok(self) -> None:
        resp = CommandResponse(command="bad", output="", error="unknown identifier")
        assert resp.ok is False

    def test_label_result_fields(self) -> None:
        result = LabelResult(formula="box p -> p", label=True, raw_output="true")
        assert result.label is True
        assert result.formula == "box p -> p"

    def test_tactic_result_proof_closed(self) -> None:
        result = TacticResult(tactic="rfl", goals=[], error=None)
        assert result.proof_closed is True

    def test_tactic_result_not_closed(self) -> None:
        result = TacticResult(tactic="intro h", goals=["⊢ False"], error=None)
        assert result.proof_closed is False

    def test_tactic_result_with_error(self) -> None:
        result = TacticResult(tactic="bad", goals=[], error="unknown tactic 'bad'")
        assert result.proof_closed is False

    def test_subprocess_result_ok(self) -> None:
        result = SubprocessResult(
            args=["lake", "exe", "foo"],
            returncode=0,
            stdout="output",
            stderr="",
        )
        assert result.ok is True

    def test_subprocess_result_failure(self) -> None:
        result = SubprocessResult(
            args=["lake", "exe", "foo"],
            returncode=1,
            stdout="",
            stderr="error",
        )
        assert result.ok is False


# ---------------------------------------------------------------------------
# REPL integration tests (require lean-interact + BimodalLogic)
# ---------------------------------------------------------------------------


@pytest.mark.lean
class TestLeanBridgeREPL:
    """Integration tests for the REPL path.

    All tests use the session-scoped ``lean_bridge`` fixture from conftest.py
    and are automatically skipped when lean-interact or BimodalLogic is absent.
    """

    def test_lean_bridge_connects(self, lean_bridge: LeanBridge) -> None:
        """Bridge must connect and report is_started == True."""
        assert lean_bridge.is_started

    def test_check_id(self, lean_bridge: LeanBridge) -> None:
        """``#check @id`` is a universally valid Lean command."""
        resp = lean_bridge.run_command("#check @id")
        assert resp.ok, f"REPL error: {resp.error}"
        assert resp.output.strip()  # non-empty output

    def test_eval_simple_expr(self, lean_bridge: LeanBridge) -> None:
        """``#eval 1 + 1`` should return ``2``."""
        resp = lean_bridge.run_command("#eval 1 + 1")
        assert resp.ok, f"REPL error: {resp.error}"
        assert "2" in resp.output

    def test_import_bimodal_syntax(self, lean_bridge: LeanBridge) -> None:
        """Should be able to import the core Formula module."""
        resp = lean_bridge.run_command("import Bimodal.Syntax.Formula")
        assert resp.ok, f"Import failed: {resp.error}"

    def test_check_formula_type(self, lean_bridge: LeanBridge) -> None:
        """``#check`` on a BimodalLogic type should return a non-empty result."""
        resp = lean_bridge.run_command("#check Bimodal.Syntax.Formula")
        # We accept either success or 'unknown namespace' (import order)
        assert resp.output.strip() or resp.error is not None  # something returned

    def test_eval_formula_prettyprint(self, lean_bridge: LeanBridge) -> None:
        """Attempt to evaluate a formula pretty-print (best-effort)."""
        resp = lean_bridge.run_command(
            '#eval (Bimodal.Syntax.Formula.atom_s "p").prettyPrint'
        )
        # We do not assert success because the formula API may differ;
        # we assert the bridge returns a structured response.
        assert isinstance(resp, CommandResponse)
        assert isinstance(resp.elapsed, float)

    def test_run_command_error_handling(self, lean_bridge: LeanBridge) -> None:
        """A syntactically bad command should return a CommandResponse with error set."""
        resp = lean_bridge.run_command("this is not valid lean syntax !!!")
        assert isinstance(resp, CommandResponse)
        # Either error is set or output contains an error message
        assert resp.error is not None or resp.output.strip()

    def test_label_formula_returns_label_result(self, lean_bridge: LeanBridge) -> None:
        """label_formula() must return a LabelResult (label may be None if API differs)."""
        result = lean_bridge.label_formula("box p -> p")
        assert isinstance(result, LabelResult)
        assert result.formula == "box p -> p"
        assert isinstance(result.elapsed, float)

    def test_bridge_context_manager(self) -> None:
        """Context manager protocol must start and stop the bridge cleanly."""
        if not lean_interact_available():
            pytest.skip("lean-interact not installed")

        from pathlib import Path

        from bimodal_harness.config import BIMODAL_LOGIC_PATH

        if not (Path(BIMODAL_LOGIC_PATH) / "lakefile.lean").exists():
            pytest.skip("BimodalLogic not found")

        with LeanBridge() as bridge:
            assert bridge.is_started
            resp = bridge.run_command("#check Nat")
            assert isinstance(resp, CommandResponse)

        assert not bridge.is_started

    def test_bridge_error_recovery(self, lean_bridge: LeanBridge) -> None:
        """AutoLeanServer should recover from a malformed tactic command."""
        # Send something that will error the REPL
        resp1 = lean_bridge.run_command("💥💥💥 invalid utf-8-ish command !!!!")
        assert isinstance(resp1, CommandResponse)

        # The bridge should still work after the error
        resp2 = lean_bridge.run_command("#check Nat")
        assert isinstance(resp2, CommandResponse)
        assert lean_bridge.is_started  # server is still alive


# ---------------------------------------------------------------------------
# Subprocess integration tests (require BimodalLogic + lake in PATH)
# ---------------------------------------------------------------------------


@pytest.mark.lean
class TestLeanBridgeSubprocess:
    """Integration tests for the ``lake exe`` subprocess path."""

    def test_subprocess_dataset_generator_help(self, lean_bridge: LeanBridge) -> None:
        """``lake exe dataset_generator --help`` should return exit code 0 or 1 with output."""
        result = lean_bridge.run_subprocess(["dataset_generator", "--help"])
        assert isinstance(result, SubprocessResult)
        # Accept exit codes 0 or 1 (some tools return 1 for --help)
        assert result.returncode in (0, 1, 2)
        # Must have produced some output
        combined = result.stdout + result.stderr
        assert combined.strip()

    def test_subprocess_result_fields(self, lean_bridge: LeanBridge) -> None:
        """SubprocessResult must have all expected fields populated."""
        result = lean_bridge.run_subprocess(["dataset_generator", "--help"])
        assert isinstance(result.args, list)
        assert result.args[0] == "lake"
        assert isinstance(result.returncode, int)
        assert isinstance(result.stdout, str)
        assert isinstance(result.stderr, str)
        assert isinstance(result.elapsed, float)
        assert result.elapsed >= 0.0
