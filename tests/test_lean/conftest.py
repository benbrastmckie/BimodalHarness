"""Lean-specific pytest fixtures and configuration.

All tests in this package require:
1. ``lean-interact`` to be installed (``pip install 'bimodal-harness[lean]'``)
2. A valid BimodalLogic project path (set via ``BIMODAL_LOGIC_PATH`` or use
   the default ``~/Projects/BimodalLogic``)
3. The BimodalLogic ``.lake/build/`` cache to be present (run ``lake build``
   in the BimodalLogic project if not)

Tests are automatically skipped when either condition is not met.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bimodal_harness.lean.bridge import lean_interact_available


def _bimodal_logic_path() -> Path:
    """Return the configured BimodalLogic project path."""
    from bimodal_harness.config import BIMODAL_LOGIC_PATH

    return Path(BIMODAL_LOGIC_PATH)


def _bimodal_logic_valid() -> bool:
    """Return True if the BimodalLogic project exists and has a lake build."""
    path = _bimodal_logic_path()
    return (path / "lakefile.lean").exists() and (path / ".lake" / "build").exists()


# ---------------------------------------------------------------------------
# Skip conditions
# ---------------------------------------------------------------------------

#: Skip marker applied when lean-interact is not importable.
skip_no_lean_interact = pytest.mark.skipif(
    not lean_interact_available(),
    reason="lean-interact not installed; run: pip install 'bimodal-harness[lean]'",
)

#: Skip marker applied when BimodalLogic project is absent or unbuilt.
skip_no_bimodal_logic = pytest.mark.skipif(
    not _bimodal_logic_valid(),
    reason=(
        f"BimodalLogic not found or not built at {_bimodal_logic_path()}; "
        "run 'lake build' in BimodalLogic project"
    ),
)


# ---------------------------------------------------------------------------
# Session-scoped bridge fixture
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def lean_bridge():
    """Session-scoped LeanBridge.

    Skipped automatically when lean-interact is not installed or BimodalLogic
    is not available.  All tests that receive this fixture inherit those
    skip conditions.
    """
    if not lean_interact_available():
        pytest.skip("lean-interact not installed")
    if not _bimodal_logic_valid():
        pytest.skip(
            f"BimodalLogic not built at {_bimodal_logic_path()}; "
            "run 'lake build' first"
        )

    from bimodal_harness.lean import LeanBridge

    with LeanBridge() as bridge:
        yield bridge


@pytest.fixture(scope="session")
def bimodal_logic_path() -> Path:
    """Return the BimodalLogic project path as a Path object."""
    return _bimodal_logic_path()
