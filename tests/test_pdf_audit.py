"""Tests for parser PDF audit bbox overlay helpers."""

from pathlib import Path
import json

from pypdf import PdfReader, PdfWriter

from src.ingestion.parsing.pdf_audit import annotate_pdf_with_chunks, load_parsed_record


def _write_sample_jsonl(path: Path, source_pdf: Path) -> str:
    doc_id = "doc-123"
    row = {
        "doc_id": doc_id,
        "metadata": {
            "source_path": str(source_pdf),
            "relative_path": "topic/sample.pdf",
        },
        "parent_nodes": [],
        "child_nodes": [],
        "elements": [
            {
                "element_id": "e1",
                "element_type": "paragraph",
                "text": "hello",
                "page": 1,
                "order": 1,
                "section_path": ["Intro"],
                "metadata": {
                    "bboxes": [
                        {"page": 1, "l": 100, "t": 120, "r": 200, "b": 170, "origin": "coordorigin.bottomleft"}
                    ]
                },
            },
            {
                "element_id": "e2",
                "element_type": "table",
                "text": "table",
                "page": 2,
                "order": 2,
                "section_path": ["Results"],
                "metadata": {
                    "bboxes": [
                        {"page": 2, "l": 0.2, "t": 0.2, "r": 0.5, "b": 0.35, "origin": "coordorigin.topleft"}
                    ]
                },
            },
        ],
    }
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    return doc_id


def test_load_parsed_record_by_relative_path(tmp_path: Path) -> None:
    source_pdf = tmp_path / "sample.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    with source_pdf.open("wb") as handle:
        writer.write(handle)
    parsed_jsonl = tmp_path / "parsed.jsonl"
    doc_id = _write_sample_jsonl(parsed_jsonl, source_pdf)

    record = load_parsed_record(parsed_jsonl, relative_path="topic/sample.pdf")

    assert record.doc_id == doc_id
    assert record.source_path == str(source_pdf)
    assert len(record.elements) == 2


def test_annotate_pdf_with_chunks_creates_red_frame_annotations(tmp_path: Path) -> None:
    source_pdf = tmp_path / "sample.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    writer.add_blank_page(width=595, height=842)
    with source_pdf.open("wb") as handle:
        writer.write(handle)
    parsed_jsonl = tmp_path / "parsed.jsonl"
    doc_id = _write_sample_jsonl(parsed_jsonl, source_pdf)
    record = load_parsed_record(parsed_jsonl, doc_id=doc_id)

    output_pdf = tmp_path / "annotated.pdf"
    annotate_pdf_with_chunks(
        source_pdf=source_pdf,
        output_pdf=output_pdf,
        relative_path=record.relative_path,
        elements=record.elements,
    )

    assert output_pdf.exists()
    out_reader = PdfReader(str(output_pdf))
    annots_page_1 = out_reader.pages[0].get("/Annots")
    annots_page_2 = out_reader.pages[1].get("/Annots")
    assert annots_page_1 is not None
    assert annots_page_2 is not None


def test_annotate_pdf_with_chunks_requires_bbox_data(tmp_path: Path) -> None:
    source_pdf = tmp_path / "sample.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    with source_pdf.open("wb") as handle:
        writer.write(handle)

    parsed_jsonl = tmp_path / "parsed.jsonl"
    row = {
        "doc_id": "doc-no-box",
        "metadata": {
            "source_path": str(source_pdf),
            "relative_path": "topic/no-box.pdf",
        },
        "parent_nodes": [],
        "child_nodes": [],
        "elements": [
            {
                "element_id": "e1",
                "element_type": "paragraph",
                "text": "hello",
                "page": 1,
                "order": 1,
                "section_path": ["Intro"],
                "metadata": {},
            }
        ],
    }
    parsed_jsonl.write_text(json.dumps(row) + "\n", encoding="utf-8")
    record = load_parsed_record(parsed_jsonl, doc_id="doc-no-box")

    try:
        annotate_pdf_with_chunks(
            source_pdf=source_pdf,
            output_pdf=tmp_path / "annotated.pdf",
            relative_path=record.relative_path,
            elements=record.elements,
        )
    except ValueError as exc:
        assert "No bounding boxes found" in str(exc)
    else:
        raise AssertionError("Expected ValueError when bboxes are missing.")
