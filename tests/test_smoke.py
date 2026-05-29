"""Smoke tests: verify the package is importable and structurally correct."""

from __future__ import annotations


def test_package_importable() -> None:
    """Package root is importable without errors."""
    import bimodal_harness  # noqa: F401


def test_version_string_exists() -> None:
    """Package exposes a non-empty __version__ string."""
    import bimodal_harness

    assert hasattr(bimodal_harness, "__version__")
    assert isinstance(bimodal_harness.__version__, str)
    assert len(bimodal_harness.__version__) > 0


def test_subpackage_data_importable() -> None:
    """data subpackage is importable."""
    import bimodal_harness.data  # noqa: F401


def test_subpackage_models_importable() -> None:
    """models subpackage is importable."""
    import bimodal_harness.models  # noqa: F401


def test_subpackage_search_importable() -> None:
    """search subpackage is importable."""
    import bimodal_harness.search  # noqa: F401


def test_subpackage_training_importable() -> None:
    """training subpackage is importable."""
    import bimodal_harness.training  # noqa: F401


def test_subpackage_evaluation_importable() -> None:
    """evaluation subpackage is importable."""
    import bimodal_harness.evaluation  # noqa: F401


def test_subpackage_lean_importable() -> None:
    """lean subpackage is importable."""
    import bimodal_harness.lean  # noqa: F401


def test_subpackage_z3_importable() -> None:
    """z3 subpackage is importable."""
    import bimodal_harness.z3  # noqa: F401
