"""Tests for random parser-audit PDF batch script helpers."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from pypdf import PdfWriter


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


def test_has_bbox_chunks_detects_bbox_presence() -> None:
    """Rows should be considered eligible only when they contain bbox-backed elements."""
    module = _load_module()
    row_with_bbox: dict[str, object] = {
        "elements": [
            {
                "metadata": {
                    "bboxes": [
                        {"page": 1, "l": 10, "t": 10, "r": 30, "b": 20},
                    ]
                }
            }
        ]
    }
    row_without_bbox: dict[str, object] = {"elements": [{"metadata": {}}]}

    assert module._has_bbox_chunks(row_with_bbox) is True
    assert module._has_bbox_chunks(row_without_bbox) is False


def test_load_pdf_rows_keeps_only_pdf_with_existing_source_and_bboxes(tmp_path: Path) -> None:
    """Loader should keep only rows that can be annotated into parser-audit PDFs."""
    module = _load_module()

    source_pdf = tmp_path / "source.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    with source_pdf.open("wb") as handle:
        writer.write(handle)

    rows = [
        {
            "metadata": {
                "file_ext": ".pdf",
                "source_path": str(source_pdf),
            },
            "elements": [
                {
                    "metadata": {
                        "bboxes": [
                            {"page": 1, "l": 0.1, "t": 0.1, "r": 0.3, "b": 0.2},
                        ]
                    }
                }
            ],
        },
        {
            "metadata": {
                "file_ext": ".pdf",
                "source_path": str(source_pdf),
            },
            "elements": [{"metadata": {}}],
        },
        {
            "metadata": {
                "file_ext": ".md",
                "source_path": str(source_pdf),
            },
            "elements": [
                {
                    "metadata": {
                        "bboxes": [
                            {"page": 1, "l": 0.1, "t": 0.1, "r": 0.3, "b": 0.2},
                        ]
                    }
                }
            ],
        },
    ]
    jsonl_path = tmp_path / "parsed.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    loaded = module.load_pdf_rows(jsonl_path)
    assert len(loaded) == 1
