from __future__ import annotations

"""Extractor strategies and factory for file-type specific text extraction."""

from abc import ABC, abstractmethod
import logging
from pathlib import Path

logging.getLogger("pypdf").setLevel(logging.ERROR)
LOGGER = logging.getLogger(__name__)


class FileTextExtractor(ABC):
    """Strategy interface for extracting text from a file."""

    @abstractmethod
    def extract_text(self, path: Path) -> str:
        """Extract plain text from the provided file path."""
        raise NotImplementedError


class TextFileExtractor(FileTextExtractor):
    """Concrete Strategy for `.txt` and `.md` files."""

    def extract_text(self, path: Path) -> str:
        """Read text content using fallback encodings for robustness."""
        for encoding in ("utf-8", "latin-1"):
            try:
                return path.read_text(encoding=encoding)
            except UnicodeDecodeError:
                continue
        return ""


class PdfFileExtractor(FileTextExtractor):
    """Concrete Strategy for `.pdf` files."""

    def extract_text(self, path: Path) -> str:
        """Extract text from PDF pages, tolerating malformed page objects."""
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise ImportError(
                "Parsing PDF files requires `pypdf`. Install it to parse PDF content."
            ) from exc

        reader = PdfReader(str(path), strict=False)
        pages: list[str] = []
        for page_index, page in enumerate(reader.pages):
            try:
                pages.append(page.extract_text() or "")
            except Exception as exc:
                LOGGER.warning(
                    "Skipping unreadable PDF page %s from %s: %s",
                    page_index,
                    path,
                    exc,
                )
                pages.append("")
        return "\n".join(pages)


class ExtractorFactory:
    """Factory that resolves extractors by file extension."""

    def __init__(self, extractors: dict[str, FileTextExtractor] | None = None) -> None:
        """Create extension-to-extractor mapping with sane defaults."""
        self.extractors = extractors or {
            ".txt": TextFileExtractor(),
            ".md": TextFileExtractor(),
            ".pdf": PdfFileExtractor(),
        }

    def for_path(self, path: Path) -> FileTextExtractor | None:
        """Return extractor for `path` extension, or `None` if unsupported."""
        return self.extractors.get(path.suffix.lower())
