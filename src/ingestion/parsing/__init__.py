"""Public parsing API for ingestion."""

from __future__ import annotations

from .constants import DEFAULT_EXCLUDE_DIRS, DEFAULT_EXTENSIONS
from .docling_adapter import DoclingAdapter
from .models import ChildNode, ParentNode, ParsedDocument, SemanticElement
from .parser import CorpusParser, ParseRunStats
from .pdf_audit import annotate_pdf_with_chunks
from .semantic_extractor import SemanticExtractor
from .state import IngestionStateStore

__all__ = [
    "CorpusParser",
    "DoclingAdapter",
    "SemanticExtractor",
    "annotate_pdf_with_chunks",
    "ParseRunStats",
    "IngestionStateStore",
    "ParsedDocument",
    "SemanticElement",
    "ParentNode",
    "ChildNode",
    "DEFAULT_EXTENSIONS",
    "DEFAULT_EXCLUDE_DIRS",
]
