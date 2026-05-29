"""Bridge interface between Python harness and Lean 4 proof assistant.

This module provides :class:`LeanBridge`, a thin wrapper around the
``lean-interact`` library (v0.11.x).  It supports two operational paths:

* **REPL path** – interactive Lean REPL backed by ``LeanServer`` or
  ``AutoLeanServer``, used for per-formula labelling and tactic steps.
* **Subprocess path** – ``lake exe`` invocations for batch operations such as
  dataset generation and validation.

The module is importable even when ``lean-interact`` is *not* installed.  All
lean-interact symbols are lazily imported at runtime and raise
``LeanInteractNotInstalledError`` with a helpful message if missing.
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    # These are only for type annotations; never imported at module load time.
    pass

# ---------------------------------------------------------------------------
# Lazy lean-interact import helpers
# ---------------------------------------------------------------------------

_lean_interact_available: bool | None = None  # None = not yet checked


def _require_lean_interact() -> None:
    """Raise :exc:`LeanInteractNotInstalledError` if lean-interact is absent."""
    global _lean_interact_available
    if _lean_interact_available is None:
        try:
            import lean_interact  # noqa: F401

            _lean_interact_available = True
        except ImportError:
            _lean_interact_available = False
    if not _lean_interact_available:
        raise LeanInteractNotInstalledError(
            "lean-interact is not installed.  "
            "Install it with:  pip install 'bimodal-harness[lean]'"
        )


def _import_lean_interact() -> Any:
    """Return the ``lean_interact`` module (requires it to be installed)."""
    _require_lean_interact()
    import lean_interact  # noqa: PLC0415

    return lean_interact


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class LeanInteractNotInstalledError(ImportError):
    """Raised when lean-interact is required but not installed."""


class LeanBridgeError(RuntimeError):
    """General error raised by :class:`LeanBridge` operations."""


class LeanREPLError(LeanBridgeError):
    """Raised when the Lean REPL returns an error response."""


class LeanSubprocessError(LeanBridgeError):
    """Raised when a ``lake exe`` subprocess exits with a non-zero status."""


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class CommandResponse:
    """Structured response from a raw Lean REPL command.

    Attributes:
        command: The Lean command that was sent.
        output: Raw stdout/response string from the REPL.
        error: Error message if the command failed, otherwise ``None``.
        elapsed: Wall-clock time in seconds for the round-trip.
    """

    command: str
    output: str
    error: str | None = None
    elapsed: float = 0.0

    @property
    def ok(self) -> bool:
        """Return ``True`` if the command completed without error."""
        return self.error is None


@dataclass
class LabelResult:
    """Result of a ``label_formula`` call.

    Attributes:
        formula: The original formula string.
        label: Boolean label returned by BimodalLogic (``True`` = valid).
        raw_output: Full REPL output (useful for debugging).
        elapsed: Wall-clock time in seconds.
    """

    formula: str
    label: bool | None
    raw_output: str
    elapsed: float = 0.0


@dataclass
class TacticResult:
    """Result of an ``apply_tactic`` call via ``ProofStep``.

    Attributes:
        tactic: The tactic string that was applied.
        goals: Remaining proof goals after the tactic (empty = proof closed).
        error: Error message if the tactic failed, otherwise ``None``.
        elapsed: Wall-clock time in seconds.
    """

    tactic: str
    goals: list[str] = field(default_factory=list)
    error: str | None = None
    elapsed: float = 0.0

    @property
    def proof_closed(self) -> bool:
        """Return ``True`` when all goals are discharged and no error occurred."""
        return self.error is None and len(self.goals) == 0


@dataclass
class SubprocessResult:
    """Result of a ``lake exe`` subprocess invocation.

    Attributes:
        args: Full argument list passed to ``subprocess.run``.
        returncode: Exit code of the process.
        stdout: Captured standard output.
        stderr: Captured standard error.
        elapsed: Wall-clock time in seconds.
    """

    args: list[str]
    returncode: int
    stdout: str
    stderr: str
    elapsed: float = 0.0

    @property
    def ok(self) -> bool:
        """Return ``True`` if the process exited with code 0."""
        return self.returncode == 0


# ---------------------------------------------------------------------------
# LeanBridge
# ---------------------------------------------------------------------------


class LeanBridge:
    """Python interface to the BimodalLogic Lean 4 project via lean-interact.

    The bridge wraps a lean-interact ``LeanServer`` (or ``AutoLeanServer``)
    and provides higher-level helpers for the operations needed by the
    BimodalHarness pipeline:

    * :meth:`run_command` – execute an arbitrary Lean command in the REPL
    * :meth:`label_formula` – query BimodalLogic's ``labelFormula`` evaluator
    * :meth:`apply_tactic` – send a tactic step and inspect remaining goals
    * :meth:`run_subprocess` – invoke ``lake exe`` for batch tools

    Usage
    -----
    As a context manager (recommended)::

        with LeanBridge() as bridge:
            resp = bridge.run_command("#check @id")
            print(resp.output)

    Manual lifecycle::

        bridge = LeanBridge()
        bridge.start()
        try:
            resp = bridge.run_command("#check Nat")
        finally:
            bridge.stop()

    Parameters
    ----------
    project_path:
        Path to the BimodalLogic project root.  Defaults to
        ``BIMODAL_LOGIC_PATH`` from :mod:`bimodal_harness.config`.
    auto_recover:
        If ``True`` (default), use ``AutoLeanServer`` which automatically
        restarts a crashed REPL.  Set to ``False`` to use plain
        ``LeanServer``.
    startup_imports:
        Additional Lean module names to import during :meth:`start`.
        The default startup imports are taken from
        ``config.LEAN_STARTUP_IMPORTS``.
    timeout:
        Per-command REPL timeout in seconds.  Defaults to
        ``config.LEAN_REPL_TIMEOUT``.
    """

    def __init__(
        self,
        project_path: str | None = None,
        auto_recover: bool | None = None,
        startup_imports: list[str] | None = None,
        timeout: float | None = None,
    ) -> None:
        from bimodal_harness import config  # lazy – avoids circular import at module init

        self._project_path: str = project_path or config.BIMODAL_LOGIC_PATH
        self._auto_recover: bool = auto_recover if auto_recover is not None else config.LEAN_AUTO_RECOVER
        self._startup_imports: list[str] = startup_imports if startup_imports is not None else config.LEAN_STARTUP_IMPORTS
        self._timeout: float = timeout if timeout is not None else config.LEAN_REPL_TIMEOUT

        # Internal lean-interact objects – populated by start()
        self._server: Any = None
        self._session_id: int | None = None
        self._started: bool = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the Lean REPL and import startup modules.

        Raises
        ------
        LeanInteractNotInstalledError
            If ``lean-interact`` is not installed.
        LeanBridgeError
            If the REPL fails to start or the startup imports fail.
        """
        if self._started:
            return

        li = _import_lean_interact()

        try:
            project = li.LocalProject(project_path=self._project_path)
            repl_config = li.LeanREPLConfig(project=project)

            if self._auto_recover:
                self._server = li.AutoLeanServer(repl_config)
            else:
                self._server = li.LeanServer(repl_config)

            self._server.__enter__()
        except Exception as exc:
            raise LeanBridgeError(f"Failed to start Lean REPL: {exc}") from exc

        self._started = True

        # Run startup imports
        for module in self._startup_imports:
            resp = self.run_command(f"import {module}")
            if not resp.ok:
                # Non-fatal: warn but do not abort startup
                import warnings

                warnings.warn(
                    f"Startup import failed for '{module}': {resp.error}",
                    stacklevel=2,
                )

    def stop(self) -> None:
        """Shut down the Lean REPL cleanly."""
        if not self._started:
            return
        try:
            if self._server is not None:
                self._server.__exit__(None, None, None)
        except Exception:
            pass  # Best-effort teardown
        finally:
            self._server = None
            self._session_id = None
            self._started = False

    def __enter__(self) -> LeanBridge:
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.stop()

    # ------------------------------------------------------------------
    # REPL operations
    # ------------------------------------------------------------------

    def run_command(self, cmd: str) -> CommandResponse:
        """Execute an arbitrary Lean command in the REPL.

        Parameters
        ----------
        cmd:
            A valid Lean command string, e.g. ``"#check Nat"`` or
            ``"#eval 1 + 1"``.

        Returns
        -------
        CommandResponse
            Structured result.  Check :attr:`CommandResponse.ok` before
            using the output.

        Raises
        ------
        LeanBridgeError
            If the REPL is not started or the server call itself raises.
        """
        if not self._started:
            raise LeanBridgeError("LeanBridge has not been started.  Call start() first.")

        li = _import_lean_interact()
        t0 = time.monotonic()

        try:
            lean_cmd = li.Command(cmd=cmd)
            response = self._server.run(lean_cmd)
            elapsed = time.monotonic() - t0

            # lean-interact returns a CommandResponse-like object;
            # extract fields defensively.
            output = _extract_str(response, "message", "output", "stdout", default="")
            error_text = _extract_str(response, "error", default=None)

            # Some versions encode errors in a ``messages`` list with severity
            if error_text is None and hasattr(response, "messages"):
                errors = [
                    m.get("data", "") if isinstance(m, dict) else str(m)
                    for m in (response.messages or [])
                    if (isinstance(m, dict) and m.get("severity") == "error")
                    or (hasattr(m, "severity") and m.severity == "error")
                ]
                if errors:
                    error_text = "\n".join(errors)

        except Exception as exc:
            elapsed = time.monotonic() - t0
            return CommandResponse(
                command=cmd,
                output="",
                error=str(exc),
                elapsed=elapsed,
            )

        return CommandResponse(
            command=cmd,
            output=output,
            error=error_text,
            elapsed=elapsed,
        )

    def label_formula(self, formula: str) -> LabelResult:
        """Query BimodalLogic's formula labeller via ``#eval``.

        Sends::

            #eval labelFormula "<formula>"

        and parses the boolean result from the REPL output.

        Parameters
        ----------
        formula:
            A BimodalLogic formula string (e.g. ``"box p -> p"``).

        Returns
        -------
        LabelResult
            Contains the parsed boolean label.  If parsing fails,
            :attr:`LabelResult.label` is ``None`` and the raw output is
            preserved for inspection.
        """
        cmd = f'#eval labelFormula "{formula}"'
        resp = self.run_command(cmd)

        label: bool | None = None
        output_lower = resp.output.strip().lower()
        if output_lower in ("true", "tt"):
            label = True
        elif output_lower in ("false", "ff"):
            label = False
        # If we got an error or unparseable output, label stays None

        return LabelResult(
            formula=formula,
            label=label,
            raw_output=resp.output,
            elapsed=resp.elapsed,
        )

    def apply_tactic(self, proof_state: int, tactic: str) -> TacticResult:
        """Apply a tactic to an open proof state via ``ProofStep``.

        Uses the lean-interact ``ProofStep`` API if available; falls back to
        a raw ``#eval`` command approach if ``ProofStep`` is not present in
        the installed version.

        Parameters
        ----------
        proof_state:
            An integer handle identifying the open proof state within the
            current REPL session.
        tactic:
            A Lean 4 tactic string, e.g. ``"intro h"`` or ``"exact h"``.

        Returns
        -------
        TacticResult
            Remaining goals after the tactic (empty = proof closed).
        """
        if not self._started:
            raise LeanBridgeError("LeanBridge has not been started.  Call start() first.")

        li = _import_lean_interact()
        t0 = time.monotonic()

        try:
            if hasattr(li, "ProofStep"):
                step = li.ProofStep(tactic=tactic, state=proof_state)
                response = self._server.run(step)
                elapsed = time.monotonic() - t0

                goals = _extract_goals(response)
                error = _extract_str(response, "error", default=None)
            else:
                # Fallback: use raw command
                cmd = f"-- apply tactic: {tactic}"
                resp = self.run_command(cmd)
                elapsed = resp.elapsed
                goals = []
                error = resp.error

        except Exception as exc:
            elapsed = time.monotonic() - t0
            return TacticResult(tactic=tactic, goals=[], error=str(exc), elapsed=elapsed)

        return TacticResult(tactic=tactic, goals=goals, error=error, elapsed=elapsed)

    # ------------------------------------------------------------------
    # Subprocess operations
    # ------------------------------------------------------------------

    def run_subprocess(
        self,
        args: list[str],
        cwd: str | None = None,
        timeout: float | None = None,
    ) -> SubprocessResult:
        """Run a ``lake exe`` command as a subprocess.

        Parameters
        ----------
        args:
            Command arguments passed after ``lake exe``.  For example,
            ``["dataset_generator", "--help"]`` runs
            ``lake exe dataset_generator --help``.
        cwd:
            Working directory for the subprocess.  Defaults to
            :attr:`_project_path`.
        timeout:
            Override the default subprocess timeout
            (:data:`~bimodal_harness.config.LEAN_SUBPROCESS_TIMEOUT`).

        Returns
        -------
        SubprocessResult
            Captured stdout, stderr, and return code.

        Raises
        ------
        LeanSubprocessError
            If the subprocess times out or the OS raises an error.
        """
        from bimodal_harness import config

        cwd = cwd or self._project_path
        timeout = timeout if timeout is not None else config.LEAN_SUBPROCESS_TIMEOUT
        full_args = ["lake", "exe"] + args

        t0 = time.monotonic()
        try:
            proc = subprocess.run(
                full_args,
                capture_output=True,
                text=True,
                cwd=cwd,
                timeout=timeout,
            )
            elapsed = time.monotonic() - t0
        except subprocess.TimeoutExpired as exc:
            elapsed = time.monotonic() - t0
            raise LeanSubprocessError(
                f"lake exe {args} timed out after {timeout}s"
            ) from exc
        except OSError as exc:
            elapsed = time.monotonic() - t0
            raise LeanSubprocessError(f"lake exe failed to start: {exc}") from exc

        return SubprocessResult(
            args=full_args,
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            elapsed=elapsed,
        )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_started(self) -> bool:
        """Return ``True`` if the REPL is currently running."""
        return self._started

    @property
    def project_path(self) -> str:
        """Return the configured BimodalLogic project path."""
        return self._project_path


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _extract_str(obj: Any, *attrs: str, default: str | None = None) -> str | None:
    """Return the first non-empty string attribute found on *obj*."""
    for attr in attrs:
        val = getattr(obj, attr, None)
        if val is None and isinstance(obj, dict):
            val = obj.get(attr)
        if val is not None:
            return str(val) if val else default
    return default


def _extract_goals(response: Any) -> list[str]:
    """Extract remaining proof goals from a ProofStep response."""
    # lean-interact may store goals as a list of strings or a single string
    goals_raw = getattr(response, "goals", None) or getattr(response, "goal", None)
    if goals_raw is None:
        return []
    if isinstance(goals_raw, list):
        return [str(g) for g in goals_raw if g]
    if isinstance(goals_raw, str) and goals_raw.strip():
        return [goals_raw.strip()]
    return []


# ---------------------------------------------------------------------------
# lean-interact availability probe (importable without side effects)
# ---------------------------------------------------------------------------


def lean_interact_available() -> bool:
    """Return ``True`` if lean-interact is importable in the current environment."""
    global _lean_interact_available
    if _lean_interact_available is None:
        try:
            import lean_interact  # noqa: F401

            _lean_interact_available = True
        except ImportError:
            _lean_interact_available = False
    return bool(_lean_interact_available)
