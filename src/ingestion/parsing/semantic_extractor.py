"""Semantic extraction from Docling documents."""

from __future__ import annotations

import hashlib
import re
from typing import Any

from .docling_adapter import DoclingAdapter
from .models import SemanticElement


class SemanticExtractor:
    """Convert Docling document items into normalized semantic elements."""

    def __init__(self, docling_adapter: DoclingAdapter) -> None:
        """Initialize extractor with a Docling adapter dependency."""
        self.docling_adapter = docling_adapter

    def extract(self, doc_id: str, doc: Any) -> list[SemanticElement]:
        """Map Docling document items to ordered semantic elements."""
        types = self.docling_adapter.item_types()
        SectionHeaderItem = types["SectionHeaderItem"]
        TitleItem = types["TitleItem"]
        FormulaItem = types["FormulaItem"]
        TableItem = types["TableItem"]
        PictureItem = types["PictureItem"]

        elements: list[SemanticElement] = []
        section_path: list[str] = []
        in_references = False
        order = 0

        for item, _level in doc.iterate_items(with_groups=False, traverse_pictures=True):
            text = self.docling_adapter.extract_item_text(item=item, doc=doc).strip()
            if not text:
                continue

            page = self.docling_adapter.item_page(item=item)
            metadata: dict[str, Any] = {"bboxes": self.docling_adapter.item_bboxes(item=item)}

            if isinstance(item, TitleItem):
                element_type = "title"
            elif isinstance(item, SectionHeaderItem):
                heading_level = int(getattr(item, "level", 1) or 1)
                section_path = self._update_section_path(section_path, heading_level, text)
                in_references = text.lower().startswith("references")
                element_type = "section_heading"
            elif isinstance(item, FormulaItem):
                element_type = "equation"
            elif isinstance(item, TableItem):
                element_type = "table"
                metadata["rows"] = self.docling_adapter.table_rows(item=item, doc=doc)
            elif isinstance(item, PictureItem):
                element_type = "figure_caption"
            else:
                element_type, extra_metadata = self._classify_text_block(
                    text=text, in_references=in_references
                )
                metadata.update(extra_metadata)

            order += 1
            elements.append(
                SemanticElement(
                    element_id=self._build_element_id(doc_id, order),
                    element_type=element_type,
                    text=text,
                    page=page,
                    order=order,
                    section_path=tuple(section_path),
                    metadata=metadata,
                )
            )

        return self._merge_adjacent_elements(doc_id=doc_id, elements=elements)

    def _classify_text_block(self, text: str, in_references: bool) -> tuple[str, dict[str, Any]]:
        """Classify free-text blocks that are not explicitly typed by Docling."""
        if in_references:
            return "references", {}
        if self._looks_like_figure_caption(text):
            return "figure_caption", {}
        if self._looks_like_equation(text):
            return "equation", {}
        if self._looks_like_table(text):
            return "table", {"rows": self._rows_from_table_text(text)}
        return "paragraph", {}

    def _merge_adjacent_elements(
        self, doc_id: str, elements: list[SemanticElement]
    ) -> list[SemanticElement]:
        """Merge adjacent compatible semantic elements into richer blocks."""
        if not elements:
            return []

        merged: list[SemanticElement] = []
        order = 0
        idx = 0
        joinable = {"paragraph", "references", "table"}

        while idx < len(elements):
            current = elements[idx]
            if current.element_type not in joinable:
                order += 1
                merged.append(
                    SemanticElement(
                        element_id=self._build_element_id(doc_id, order),
                        element_type=current.element_type,
                        text=current.text,
                        page=current.page,
                        order=order,
                        section_path=current.section_path,
                        metadata=dict(current.metadata),
                    )
                )
                idx += 1
                continue

            parts = [current.text]
            rows = list(current.metadata.get("rows", []))
            bboxes = list(current.metadata.get("bboxes", []))
            page = current.page
            section_path = current.section_path
            j = idx + 1
            while j < len(elements):
                nxt = elements[j]
                if (
                    nxt.element_type == current.element_type
                    and nxt.page == page
                    and nxt.section_path == section_path
                    and nxt.order == elements[j - 1].order + 1
                ):
                    parts.append(nxt.text)
                    if nxt.element_type == "table":
                        rows.extend(nxt.metadata.get("rows", []))
                    bboxes.extend(nxt.metadata.get("bboxes", []))
                    j += 1
                    continue
                break

            metadata = dict(current.metadata)
            if current.element_type == "table":
                metadata["rows"] = rows
            metadata["bboxes"] = bboxes

            order += 1
            merged.append(
                SemanticElement(
                    element_id=self._build_element_id(doc_id, order),
                    element_type=current.element_type,
                    text="\n".join(parts),
                    page=page,
                    order=order,
                    section_path=section_path,
                    metadata=metadata,
                )
            )
            idx = j

        return merged

    def _update_section_path(
        self,
        section_path: list[str],
        level: int,
        heading_text: str,
    ) -> list[str]:
        """Update section path based on heading level and text."""
        if level <= 0:
            return section_path
        updated = list(section_path)
        if level <= len(updated):
            updated = updated[: level - 1]
        while len(updated) < level - 1:
            updated.append("section")
        updated.append(heading_text)
        return updated

    def _rows_from_table_text(self, text: str) -> list[list[str]]:
        """Parse textual table notation into a row/column matrix."""
        rows: list[list[str]] = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if re.fullmatch(r"[\-:|\s]+", stripped):
                continue
            if "|" in stripped:
                cols = [col.strip() for col in stripped.split("|") if col.strip()]
            elif "\t" in stripped:
                cols = [col.strip() for col in stripped.split("\t") if col.strip()]
            else:
                cols = [col.strip() for col in re.split(r"\s{2,}", stripped) if col.strip()]
            if cols:
                rows.append(cols)
        return rows

    def _looks_like_table(self, text: str) -> bool:
        """Detect table-like markdown or columnar text blocks."""
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return False
        if any(line.count("|") >= 2 for line in lines):
            return True
        if sum(1 for line in lines if "|" in line) >= 2:
            return True
        return any("\t" in line for line in lines)

    def _looks_like_equation(self, text: str) -> bool:
        """Detect equation-like text blocks."""
        if "=" not in text:
            return False
        math_tokens = {"+", "-", "*", "/", "^", "∑", "∏", "∫", "λ", "σ"}
        return any(token in text for token in math_tokens)

    def _looks_like_figure_caption(self, text: str) -> bool:
        """Detect figure caption text using common paper caption prefixes."""
        return re.match(r"^(figure|fig\.)\s*\d+", text.strip().lower()) is not None

    def _build_element_id(self, doc_id: str, order: int) -> str:
        """Build stable semantic element id."""
        return self._hash_id(doc_id, "element", str(order))

    @staticmethod
    def _hash_id(*parts: str) -> str:
        """Create stable SHA-1 id from parts."""
        raw = "::".join(parts)
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()
