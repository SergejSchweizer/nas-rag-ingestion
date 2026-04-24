"""Tests for package metadata consistency."""

import src


def test_package_version_is_defined() -> None:
    """Package should expose non-empty `__version__` string."""
    assert isinstance(src.__version__, str)
    assert src.__version__
