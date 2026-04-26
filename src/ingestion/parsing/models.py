"""Data models for ingestion parsing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ParsedDocument:
    """Canonical parsed record used across ingestion and retrieval stages."""

    doc_id: str
    text: str
    metadata: dict
    elements: tuple["SemanticElement", ...]
    parent_nodes: tuple["ParentNode", ...]
    child_nodes: tuple["ChildNode", ...]


@dataclass(frozen=True)
class SemanticElement:
    """Single semantic unit extracted from source document text."""

    element_id: str
    element_type: str
    text: str
    page: int
    order: int
    section_path: tuple[str, ...]
    metadata: dict[str, Any]


@dataclass(frozen=True)
class ParentNode:
    """Section-aligned parent retrieval node."""

    parent_id: str
    doc_id: str
    section_path: tuple[str, ...]
    page_start: int
    page_end: int
    text: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class ChildNode:
    """Fine-grained child retrieval node linked to a parent node."""

    child_id: str
    parent_id: str
    doc_id: str
    chunk_level: str
    chunk_type: str
    section_path: tuple[str, ...]
    page_start: int
    page_end: int
    text: str
    metadata: dict[str, Any]
