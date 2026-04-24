from __future__ import annotations

"""Public parsing API for ingestion."""

from .constants import DEFAULT_EXCLUDE_DIRS, DEFAULT_EXTENSIONS
from .extractors import ExtractorFactory, FileTextExtractor, PdfFileExtractor, TextFileExtractor
from .models import ParsedDocument
from .parser import CorpusParser, ParseRunStats
from .state import IngestionStateStore

__all__ = [
    "CorpusParser",
    "ParseRunStats",
    "IngestionStateStore",
    "ParsedDocument",
    "FileTextExtractor",
    "TextFileExtractor",
    "PdfFileExtractor",
    "ExtractorFactory",
    "DEFAULT_EXTENSIONS",
    "DEFAULT_EXCLUDE_DIRS",
]
