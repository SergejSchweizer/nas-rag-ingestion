"""Tests for parser PDF audit bbox overlay helpers."""

import json
from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter

from src.ingestion.parsing.pdf_audit import annotate_pdf_with_chunks


def _sample_elements_with_bboxes() -> tuple[dict, ...]:
    return (
        {
            "element_id": "e1",
            "element_type": "paragraph",
            "text": "hello",
            "page": 1,
            "order": 1,
            "section_path": ["Intro"],
            "metadata": {
                "bboxes": [
                    {
                        "page": 1,
                        "l": 100,
                        "t": 120,
                        "r": 200,
                        "b": 170,
                        "origin": "coordorigin.bottomleft",
                    }
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
                    {
                        "page": 2,
                        "l": 0.2,
                        "t": 0.2,
                        "r": 0.5,
                        "b": 0.35,
                        "origin": "coordorigin.topleft",
                    }
                ]
            },
        },
    )


def test_annotate_pdf_with_chunks_creates_red_frame_annotations(tmp_path: Path) -> None:
    source_pdf = tmp_path / "sample.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    writer.add_blank_page(width=595, height=842)
    with source_pdf.open("wb") as handle:
        writer.write(handle)

    output_pdf = tmp_path / "annotated.pdf"
    annotate_pdf_with_chunks(
        source_pdf=source_pdf,
        output_pdf=output_pdf,
        relative_path="topic/sample.pdf",
        elements=_sample_elements_with_bboxes(),
    )

    assert output_pdf.exists()
    out_reader = PdfReader(str(output_pdf))
    annots_page_1 = out_reader.pages[0].get("/Annots")
    annots_page_2 = out_reader.pages[1].get("/Annots")
    assert annots_page_1 is not None
    assert annots_page_2 is not None

    page_1_texts = [str(item.get_object().get("/Contents", "")) for item in annots_page_1]
    page_2_texts = [str(item.get_object().get("/Contents", "")) for item in annots_page_2]

    assert any("Label Colors (Hierarchy)" in text for text in page_1_texts)
    assert any("Label Colors (Hierarchy)" in text for text in page_2_texts)
    assert any("H03 C001:paragraph" in text for text in page_1_texts)
    assert any("prev=none" in text and "next=C002" in text for text in page_1_texts)
    assert any("H04 C002:table" in text for text in page_2_texts)
    assert any("prev=C001" in text and "next=none" in text for text in page_2_texts)


def test_annotate_pdf_with_chunks_requires_bbox_data(tmp_path: Path) -> None:
    source_pdf = tmp_path / "sample.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    with source_pdf.open("wb") as handle:
        writer.write(handle)

    try:
        annotate_pdf_with_chunks(
            source_pdf=source_pdf,
            output_pdf=tmp_path / "annotated.pdf",
            relative_path="topic/no-box.pdf",
            elements=(
                {
                    "element_id": "e1",
                    "element_type": "paragraph",
                    "text": "hello",
                    "page": 1,
                    "order": 1,
                    "section_path": ["Intro"],
                    "metadata": {},
                },
            ),
        )
    except ValueError as exc:
        assert "No bounding boxes found" in str(exc)
    else:
        raise AssertionError("Expected ValueError when bboxes are missing.")


def test_annotate_pdf_with_chunks_marks_equation_like_paragraphs(tmp_path: Path) -> None:
    source_pdf = tmp_path / "sample.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    with source_pdf.open("wb") as handle:
        writer.write(handle)

    output_pdf = tmp_path / "annotated.pdf"
    annotate_pdf_with_chunks(
        source_pdf=source_pdf,
        output_pdf=output_pdf,
        relative_path="topic/equation-like-paragraph.pdf",
        elements=(
            {
                "element_id": "eq1",
                "element_type": "paragraph",
                "text": "Terminal value = 1513/1244 - 1 = 21.62%",
                "page": 1,
                "order": 1,
                "section_path": ["Results"],
                "metadata": {
                    "bboxes": [
                        {
                            "page": 1,
                            "l": 100,
                            "t": 120,
                            "r": 300,
                            "b": 170,
                            "origin": "coordorigin.bottomleft",
                        }
                    ]
                },
            },
        ),
    )

    out_reader = PdfReader(str(output_pdf))
    annots = out_reader.pages[0].get("/Annots")
    assert annots is not None
    texts = [str(item.get_object().get("/Contents", "")) for item in annots]
    assert any("H06 C001:equation" in text for text in texts)


def test_original_pdf_page_5_has_five_equation_labels(tmp_path: Path) -> None:
    parsed_jsonl = Path("data/parsed/parsed_documents.jsonl")
    if not parsed_jsonl.exists():
        pytest.skip(f"Missing parsed dataset: {parsed_jsonl}")

    source_pdf = Path("data/fixtures/pdfs/origin_intro_stocks_and_cryptocurrencies.pdf")
    if not source_pdf.exists():
        pytest.skip(f"Missing source fixture: {source_pdf}")

    row: dict | None = None
    with parsed_jsonl.open("r", encoding="utf-8") as handle:
        for line in handle:
            raw = line.strip()
            if not raw:
                continue
            candidate = json.loads(raw)
            metadata = candidate.get("metadata", {})
            if not isinstance(metadata, dict):
                continue
            if Path(str(metadata.get("source_path", ""))) == source_pdf:
                row = candidate
                break

    if row is None:
        pytest.skip(f"Could not find parsed row for source PDF: {source_pdf}")

    elements = tuple(item for item in row.get("elements", []) if isinstance(item, dict))
    output_pdf = tmp_path / "annotated_from_origin.pdf"
    annotate_pdf_with_chunks(
        source_pdf=source_pdf,
        output_pdf=output_pdf,
        relative_path=str(row.get("metadata", {}).get("relative_path", source_pdf.name)),
        elements=elements,
    )

    reader = PdfReader(str(output_pdf))
    assert len(reader.pages) >= 5, "Expected at least 5 pages in the source PDF."
    annotations = reader.pages[4].get("/Annots")
    texts = (
        [str(item.get_object().get("/Contents", "")) for item in annotations]
        if annotations is not None
        else []
    )
    equation_labels = {text for text in texts if ":equation" in text}
    assert len(equation_labels) == 5
