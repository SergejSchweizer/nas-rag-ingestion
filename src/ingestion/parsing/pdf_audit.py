"""PDF audit utilities to overlay hierarchy-colored chunk annotations on PDFs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pypdf import PdfReader, PdfWriter
from pypdf.annotations import FreeText

_HIERARCHY_ORDER: tuple[str, ...] = (
    "title",
    "section_heading",
    "paragraph",
    "table",
    "figure_caption",
    "equation",
    "references",
)

_TYPE_COLOR_HEX: dict[str, str] = {
    "title": "b51f1f",
    "section_heading": "c77800",
    "paragraph": "166534",
    "table": "1d4ed8",
    "figure_caption": "7c3aed",
    "equation": "0f766e",
    "references": "6b7280",
    "chunk": "dc2626",
}

_TYPE_FILL_HEX: dict[str, str] = {
    "title": "fde8e8",
    "section_heading": "fff4e5",
    "paragraph": "e8f6ec",
    "table": "e8f0ff",
    "figure_caption": "f2e8ff",
    "equation": "e6f9f7",
    "references": "f3f4f6",
    "chunk": "fee2e2",
}


def annotate_pdf_with_chunks(
    source_pdf: str | Path,
    output_pdf: str | Path,
    *,
    relative_path: str,
    elements: tuple[dict[str, Any], ...],
) -> None:
    """Write annotated PDF with hierarchy-colored chunk frames and per-page legend."""

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

    dependencies = _chunk_dependencies(elements=elements)
    frames_by_page = _frames_by_page(elements=elements)
    legend_items = _legend_items(frames_by_page)
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
            color = _color_for_type(str(frame.get("element_type", "chunk")))
            fill_color = _fill_for_type(str(frame.get("element_type", "chunk")))
            dependency = dependencies.get(int(frame.get("element_index", index)))
            label = _frame_label(frame=frame, index=index, dependency=dependency)
            writer.add_annotation(
                page_number=page_index,
                annotation=FreeText(
                    text=label,
                    rect=rect,
                    font="Courier",
                    font_size="6pt",
                    font_color=color,
                    border_color=color,
                    background_color=fill_color,
                ),
            )
        _add_legend_annotations(
            writer=writer,
            page_index=page_index,
            page=page,
            legend_items=legend_items,
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
            left = _safe_float(bbox.get("l"))
            t = _safe_float(bbox.get("t"))
            r = _safe_float(bbox.get("r"))
            b = _safe_float(bbox.get("b"))
            if None in {left, t, r, b}:
                continue
            grouped.setdefault(page, []).append(
                {
                    "element_index": element_index,
                    "element_id": str(element.get("element_id", "")),
                    "element_type": element_type,
                    "l": left,
                    "t": t,
                    "r": r,
                    "b": b,
                    "origin": str(bbox.get("origin", "unknown")).lower(),
                }
            )
    return grouped


def _chunk_dependencies(
    elements: tuple[dict[str, Any], ...],
) -> dict[int, tuple[int | None, int | None]]:
    """Build simple previous/next dependencies across bbox-backed text chunks."""
    chunk_indexes: list[int] = []
    for element_index, element in enumerate(elements, start=1):
        if not isinstance(element, dict):
            continue
        metadata = element.get("metadata", {})
        if not isinstance(metadata, dict):
            continue
        bboxes = metadata.get("bboxes", [])
        if not isinstance(bboxes, list):
            continue
        if any(isinstance(bbox, dict) for bbox in bboxes):
            chunk_indexes.append(element_index)

    dependencies: dict[int, tuple[int | None, int | None]] = {}
    for idx, element_index in enumerate(chunk_indexes):
        prev_index = chunk_indexes[idx - 1] if idx > 0 else None
        next_index = chunk_indexes[idx + 1] if idx + 1 < len(chunk_indexes) else None
        dependencies[element_index] = (prev_index, next_index)
    return dependencies


def _legend_items(frames_by_page: dict[int, list[dict[str, Any]]]) -> tuple[tuple[str, str], ...]:
    """Build sorted legend entries from observed element types across document pages."""
    seen_types: set[str] = set()
    for frames in frames_by_page.values():
        for frame in frames:
            seen_types.add(str(frame.get("element_type", "chunk")))

    ordered = sorted(seen_types, key=lambda item: (_hierarchy_rank(item), item))
    return tuple((item, _color_for_type(item)) for item in ordered)


def _add_legend_annotations(
    *,
    writer: PdfWriter,
    page_index: int,
    page: Any,
    legend_items: tuple[tuple[str, str], ...],
) -> None:
    """Add top-right legend that describes color and hierarchy for labels."""
    if not legend_items:
        return

    page_width = float(page.mediabox.width)
    page_height = float(page.mediabox.height)
    margin = 12.0
    box_width = min(260.0, max(170.0, page_width * 0.32))
    row_height = 12.0
    title_height = 14.0

    x1 = page_width - margin
    x0 = max(margin, x1 - box_width)
    y_top = page_height - margin

    title_rect = (x0, y_top - title_height, x1, y_top)
    writer.add_annotation(
        page_number=page_index,
        annotation=FreeText(
            text="Label Colors (Hierarchy)",
            rect=title_rect,
            font="Courier",
            font_size="8pt",
            font_color="111827",
            border_color="111827",
            background_color="ffffff",
        ),
    )

    for idx, (element_type, color) in enumerate(legend_items, start=1):
        y1 = y_top - title_height - ((idx - 1) * row_height) - 2
        y0 = y1 - row_height + 2
        rank = _hierarchy_rank(element_type)
        label = f"H{rank:02d} {element_type}"
        writer.add_annotation(
            page_number=page_index,
            annotation=FreeText(
                text=label,
                rect=(x0, y0, x1, y1),
                font="Courier",
                font_size="7pt",
                font_color=color,
                border_color=color,
                background_color="ffffff",
            ),
        )


def _to_pdf_rect(frame: dict[str, Any], page: Any) -> tuple[float, float, float, float]:
    """Convert stored bbox into PDF coordinate rect `(x0, y0, x1, y1)`."""
    page_width = float(page.mediabox.width)
    page_height = float(page.mediabox.height)
    left = float(frame["l"])
    t = float(frame["t"])
    r = float(frame["r"])
    b = float(frame["b"])
    origin = str(frame.get("origin", "unknown"))

    # Normalized coordinates.
    if max(abs(left), abs(t), abs(r), abs(b)) <= 1.0:
        left *= page_width
        r *= page_width
        t *= page_height
        b *= page_height

    x0 = min(left, r)
    x1 = max(left, r)

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


def _frame_label(
    frame: dict[str, Any],
    index: int,
    dependency: tuple[int | None, int | None] | None,
) -> str:
    """Build short colored frame label text with hierarchy and dependencies."""
    element_type = str(frame.get("element_type", "chunk"))
    element_index = int(frame.get("element_index", index))
    rank = _hierarchy_rank(element_type)
    prev_label = "none"
    next_label = "none"
    if dependency is not None:
        prev_index, next_index = dependency
        if prev_index is not None:
            prev_label = f"C{prev_index:03d}"
        if next_index is not None:
            next_label = f"C{next_index:03d}"
    return f"H{rank:02d} C{element_index:03d}:{element_type} prev={prev_label} next={next_label}"


def _hierarchy_rank(element_type: str) -> int:
    """Return 1-based hierarchy rank for an element type."""
    if element_type in _HIERARCHY_ORDER:
        return _HIERARCHY_ORDER.index(element_type) + 1
    return len(_HIERARCHY_ORDER) + 1


def _color_for_type(element_type: str) -> str:
    """Return border/font color for an element type."""
    return _TYPE_COLOR_HEX.get(element_type, _TYPE_COLOR_HEX["chunk"])


def _fill_for_type(element_type: str) -> str:
    """Return light fill color for an element type."""
    return _TYPE_FILL_HEX.get(element_type, _TYPE_FILL_HEX["chunk"])


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
