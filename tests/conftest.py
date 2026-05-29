"""Shared pytest fixtures, markers, and configuration for BimodalHarness tests."""

from __future__ import annotations

import warnings

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers and suppress known third-party warnings."""
    config.addinivalue_line(
        "markers",
        "gpu: tests requiring GPU hardware (skip in CPU-only CI)",
    )
    config.addinivalue_line(
        "markers",
        "lean: tests requiring Lean 4 toolchain (skip if not installed)",
    )
    config.addinivalue_line(
        "markers",
        "slow: slow tests (run with --run-slow flag)",
    )
    # Suppress pkg_resources deprecation warnings from z3-solver packaging
    warnings.filterwarnings(
        "ignore",
        category=DeprecationWarning,
        message=".*pkg_resources.*",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Auto-skip gpu and lean tests unless explicitly requested."""
    skip_gpu = pytest.mark.skip(reason="GPU not available; use -m gpu to run")
    skip_lean = pytest.mark.skip(reason="Lean toolchain not installed; use -m lean to run")

    for item in items:
        if "gpu" in item.keywords:
            item.add_marker(skip_gpu)
        if "lean" in item.keywords:
            item.add_marker(skip_lean)
