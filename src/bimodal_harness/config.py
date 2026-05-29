"""Global configuration and settings for BimodalHarness."""

from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# BimodalLogic project paths
# ---------------------------------------------------------------------------

#: Default path to the BimodalLogic Lean 4 project.
#: Override by setting the ``BIMODAL_LOGIC_PATH`` environment variable.
BIMODAL_LOGIC_PATH: str = os.environ.get(
    "BIMODAL_LOGIC_PATH",
    str(Path.home() / "Projects" / "BimodalLogic"),
)

# ---------------------------------------------------------------------------
# Lean bridge configuration
# ---------------------------------------------------------------------------

#: Timeout in seconds for a single Lean REPL command.
LEAN_REPL_TIMEOUT: float = float(os.environ.get("LEAN_REPL_TIMEOUT", "30.0"))

#: Timeout in seconds for a full subprocess invocation (e.g. ``lake exe``).
LEAN_SUBPROCESS_TIMEOUT: float = float(os.environ.get("LEAN_SUBPROCESS_TIMEOUT", "300.0"))

#: Whether to use ``AutoLeanServer`` (crash-recovering) by default.
LEAN_AUTO_RECOVER: bool = os.environ.get("LEAN_AUTO_RECOVER", "1").strip() not in ("0", "false", "no")

#: Lean modules that should be imported when a LeanBridge session starts.
LEAN_STARTUP_IMPORTS: list[str] = [
    "Bimodal.Syntax.Formula",
    "Bimodal.Syntax.Atom",
]
