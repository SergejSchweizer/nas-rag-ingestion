"""Tests for parser PDF audit bbox overlay helpers."""

from pathlib import Path

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
                "bboxes": [{"page": 1, "l": 100, "t": 120, "r": 200, "b": 170, "origin": "coordorigin.bottomleft"}]
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
                "bboxes": [{"page": 2, "l": 0.2, "t": 0.2, "r": 0.5, "b": 0.35, "origin": "coordorigin.topleft"}]
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
