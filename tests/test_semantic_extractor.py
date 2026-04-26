"""Tests for semantic extraction metadata preservation behavior."""

from __future__ import annotations

from typing import Any

from src.ingestion.parsing.semantic_extractor import SemanticExtractor


class _TitleItem:
    def __init__(self, text: str) -> None:
        self.text = text


class _SectionHeaderItem:
    def __init__(self, text: str, level: int = 1) -> None:
        self.text = text
        self.level = level


class _TextItem:
    def __init__(self, text: str) -> None:
        self.text = text


class _FormulaItem:
    def __init__(self, text: str) -> None:
        self.text = text


class _TableItem:
    def __init__(self, text: str) -> None:
        self.text = text


class _PictureItem:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeDoc:
    def __init__(self, items: list[Any]) -> None:
        self.items = items

    def iterate_items(self, with_groups: bool, traverse_pictures: bool) -> list[tuple[Any, int]]:
        assert with_groups is False
        assert traverse_pictures is True
        return [(item, 0) for item in self.items]


class _FakeAdapter:
    def item_types(self) -> dict[str, Any]:
        return {
            "SectionHeaderItem": _SectionHeaderItem,
            "TitleItem": _TitleItem,
            "TextItem": _TextItem,
            "FormulaItem": _FormulaItem,
            "TableItem": _TableItem,
            "PictureItem": _PictureItem,
        }

    def extract_item_text(self, item: Any, doc: Any) -> str:
        _ = doc
        return str(getattr(item, "text", ""))

    def item_page(self, item: Any) -> int:
        _ = item
        return 1

    def item_bboxes(self, item: Any) -> list[dict[str, Any]]:
        _ = item
        return [
            {"page": 1, "l": 0.1, "t": 0.1, "r": 0.2, "b": 0.2, "origin": "coordorigin.topleft"}
        ]

    def table_rows(self, item: Any, doc: Any) -> list[list[str]]:
        _ = item
        _ = doc
        return [["a", "b"], ["c", "d"]]


def test_extract_preserves_bboxes_for_text_classification() -> None:
    """Text-item classification should keep bbox metadata."""
    adapter = _FakeAdapter()
    extractor = SemanticExtractor(docling_adapter=adapter)  # type: ignore[arg-type]
    doc = _FakeDoc(items=[_TextItem("plain paragraph text")])

    elements = extractor.extract(doc_id="doc", doc=doc)
    assert len(elements) == 1
    element = elements[0]
    assert element.element_type == "paragraph"
    assert "bboxes" in element.metadata
    assert element.metadata["bboxes"]


def test_extract_preserves_bboxes_for_table_like_text() -> None:
    """Heuristic table text should keep both parsed rows and bbox metadata."""
    adapter = _FakeAdapter()
    extractor = SemanticExtractor(docling_adapter=adapter)  # type: ignore[arg-type]
    doc = _FakeDoc(items=[_TextItem("col1 | col2\nv1 | v2")])

    elements = extractor.extract(doc_id="doc", doc=doc)
    assert len(elements) == 1
    element = elements[0]
    assert element.element_type == "table"
    assert "rows" in element.metadata
    assert element.metadata["rows"]
    assert "bboxes" in element.metadata
    assert element.metadata["bboxes"]


def test_extract_keeps_empty_formula_items_as_equations() -> None:
    """Formula items with empty extracted text should still be preserved."""
    adapter = _FakeAdapter()
    extractor = SemanticExtractor(docling_adapter=adapter)  # type: ignore[arg-type]
    doc = _FakeDoc(items=[_FormulaItem("")])

    elements = extractor.extract(doc_id="doc", doc=doc)
    assert len(elements) == 1
    element = elements[0]
    assert element.element_type == "equation"
    assert element.text == "[equation]"
    assert "bboxes" in element.metadata
    assert element.metadata["bboxes"]
