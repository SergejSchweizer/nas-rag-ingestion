from __future__ import annotations

"""PDF audit utilities to overlay red labeled frames at parsed chunk coordinates."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pypdf import PdfReader, PdfWriter
from pypdf.annotations import FreeText


@dataclass(frozen=True)
class ParsedRecord:
    """Minimal parsed record shape needed for PDF chunk audit rendering."""

    doc_id: str
    source_path: str
    relative_path: str
    elements: tuple[dict[str, Any], ...]


def load_parsed_record(
    parsed_jsonl: str | Path,
    *,
    doc_id: str | None = None,
    relative_path: str | None = None,
    source_pdf: str | Path | None = None,
) -> ParsedRecord:
    """Load one parsed record from JSONL using one selector."""
    if sum(value is not None for value in (doc_id, relative_path, source_pdf)) != 1:
        raise ValueError("Provide exactly one selector: doc_id, relative_path, or source_pdf.")

    source_pdf_norm = str(Path(source_pdf).resolve()) if source_pdf is not None else None
    path = Path(parsed_jsonl)
    if not path.exists():
        raise FileNotFoundError(f"Parsed JSONL not found: {path}")

    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            raw = line.strip()
            if not raw:
                continue
            row = json.loads(raw)
            if not isinstance(row, dict):
                continue
            metadata = row.get("metadata", {})
            if not isinstance(metadata, dict):
                metadata = {}

            if doc_id is not None and str(row.get("doc_id", "")) != doc_id:
                continue
            if relative_path is not None and str(metadata.get("relative_path", "")) != relative_path:
                continue
            if source_pdf_norm is not None:
                current_source = str(Path(str(metadata.get("source_path", ""))).resolve())
                if current_source != source_pdf_norm:
                    continue

            elements = row.get("elements", [])
            if not isinstance(elements, list):
                elements = []
            return ParsedRecord(
                doc_id=str(row.get("doc_id", "")),
                source_path=str(metadata.get("source_path", "")),
                relative_path=str(metadata.get("relative_path", "")),
                elements=tuple(item for item in elements if isinstance(item, dict)),
            )

    selector = (
        f"doc_id={doc_id!r}"
        if doc_id is not None
        else f"relative_path={relative_path!r}"
        if relative_path is not None
        else f"source_pdf={str(source_pdf)!r}"
    )
    raise ValueError(f"No parsed record matched selector: {selector} in {parsed_jsonl}")


def annotate_pdf_with_chunks(
    source_pdf: str | Path,
    output_pdf: str | Path,
    *,
    relative_path: str,
    elements: tuple[dict[str, Any], ...],
) -> None:
    """Write annotated PDF with red labeled frames around chunk bounding boxes."""

    src = Path(source_pdf)
    if not src.exists():
        raise FileNotFoundError(f"Source PDF not found: {src}")
    if src.suffix.lower() != ".pdf":
        raise ValueError(f"Source is not a PDF: {src}")
    dst = Path(output_pdf)
    dst.parent.mkdir(parents=True, exist_ok=True)

    reader = PdfReader(str(src))
    writer = PdfWriter()
    writer.add_outline_item(title=f"Parser Audit: {relative_path}", page_number=0, bold=True)

    frames_by_page = _frames_by_page(elements=elements)
    if not any(frames_by_page.values()):
        raise ValueError(
            "No bounding boxes found in parsed elements metadata. "
            "Re-run parse_corpus.py so element metadata includes `bboxes`."
        )

    for page_index, page in enumerate(reader.pages):
        writer.add_page(page)
        page_number = page_index + 1
        page_frames = frames_by_page.get(page_number, [])
        for index, frame in enumerate(page_frames, start=1):
            rect = _to_pdf_rect(frame=frame, page=page)
            label = _frame_label(frame=frame, index=index)
            writer.add_annotation(
                page_number=page_index,
                annotation=FreeText(
                    text=label,
                    rect=rect,
                    font="Courier",
                    font_size="6pt",
                    font_color="ff0000",
                    border_color="ff0000",
                    background_color=None,
                ),
            )

    with dst.open("wb") as handle:
        writer.write(handle)


def _frames_by_page(elements: tuple[dict[str, Any], ...]) -> dict[int, list[dict[str, Any]]]:
    """Collect frame descriptors grouped by 1-based page number."""
    grouped: dict[int, list[dict[str, Any]]] = {}
    element_index = 0
    for element in elements:
        element_index += 1
        element_type = str(element.get("element_type", "chunk"))
        metadata = element.get("metadata", {})
        if not isinstance(metadata, dict):
            continue
        bboxes = metadata.get("bboxes", [])
        if not isinstance(bboxes, list):
            continue
        for bbox in bboxes:
            if not isinstance(bbox, dict):
                continue
            page = _safe_int(bbox.get("page"), default=1)
            l = _safe_float(bbox.get("l"))
            t = _safe_float(bbox.get("t"))
            r = _safe_float(bbox.get("r"))
            b = _safe_float(bbox.get("b"))
            if None in {l, t, r, b}:
                continue
            grouped.setdefault(page, []).append(
                {
                    "element_index": element_index,
                    "element_type": element_type,
                    "l": l,
                    "t": t,
                    "r": r,
                    "b": b,
                    "origin": str(bbox.get("origin", "unknown")).lower(),
                }
            )
    return grouped


def _to_pdf_rect(frame: dict[str, Any], page: Any) -> tuple[float, float, float, float]:
    """Convert stored bbox into PDF coordinate rect `(x0, y0, x1, y1)`."""
    page_width = float(page.mediabox.width)
    page_height = float(page.mediabox.height)
    l = float(frame["l"])
    t = float(frame["t"])
    r = float(frame["r"])
    b = float(frame["b"])
    origin = str(frame.get("origin", "unknown"))

    # Normalized coordinates.
    if max(abs(l), abs(t), abs(r), abs(b)) <= 1.0:
        l *= page_width
        r *= page_width
        t *= page_height
        b *= page_height

    x0 = min(l, r)
    x1 = max(l, r)

    if "top" in origin:
        y0 = page_height - max(t, b)
        y1 = page_height - min(t, b)
    else:
        y0 = min(t, b)
        y1 = max(t, b)

    x0 = _clamp(x0, 0.0, page_width)
    x1 = _clamp(x1, 0.0, page_width)
    y0 = _clamp(y0, 0.0, page_height)
    y1 = _clamp(y1, 0.0, page_height)

    if x1 <= x0:
        x1 = min(page_width, x0 + 1.0)
    if y1 <= y0:
        y1 = min(page_height, y0 + 1.0)
    return (x0, y0, x1, y1)


def _frame_label(frame: dict[str, Any], index: int) -> str:
    """Build short red-frame label text."""
    element_type = str(frame.get("element_type", "chunk"))
    element_index = int(frame.get("element_index", index))
    return f"C{element_index:03d}:{element_type}"


def _safe_int(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
