"""Tests for random parser-audit PDF batch script helpers."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_module():
    """Load random parser-audit script module from file path."""
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "annotate_random_parsed_pdfs.py"
    spec = importlib.util.spec_from_file_location("annotate_random_parsed_pdfs", script_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Failed to load module from {script_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_output_path_uses_numeric_pdf_names(tmp_path: Path) -> None:
    """Output path should use numbered file names like `1.pdf` and `2.pdf`."""
    module = _load_module()

    assert module.output_path(tmp_path, 1) == tmp_path / "1.pdf"
    assert module.output_path(tmp_path, 2) == tmp_path / "2.pdf"


def test_output_path_rejects_non_positive_ordinal(tmp_path: Path) -> None:
    """Output path helper should reject non-positive ordinals."""
    module = _load_module()

    try:
        module.output_path(tmp_path, 0)
    except ValueError as exc:
        assert "greater than 0" in str(exc)
    else:
        raise AssertionError("Expected ValueError for ordinal=0.")
