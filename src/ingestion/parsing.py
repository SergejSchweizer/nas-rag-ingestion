from __future__ import annotations

from abc import ABC, abstractmethod
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


DEFAULT_EXTENSIONS = (".pdf", ".md", ".txt")
DEFAULT_EXCLUDE_DIRS = (".git", ".venv", "node_modules", "__pycache__")


@dataclass(frozen=True)
class ParsedDocument:
    doc_id: str
    text: str
    metadata: dict


class FileTextExtractor(ABC):
    """
    Strategy pattern interface.

    Each concrete extractor handles one file type and can be swapped independently.
    """

    @abstractmethod
    def extract_text(self, path: Path) -> str:
        raise NotImplementedError


class TextFileExtractor(FileTextExtractor):
    """Concrete Strategy for `.txt` and `.md` files."""

    def extract_text(self, path: Path) -> str:
        for encoding in ("utf-8", "latin-1"):
            try:
                return path.read_text(encoding=encoding)
            except UnicodeDecodeError:
                continue
        return ""


class PdfFileExtractor(FileTextExtractor):
    """Concrete Strategy for `.pdf` files."""

    def extract_text(self, path: Path) -> str:
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise ImportError(
                "Parsing PDF files requires `pypdf`. Install it to parse PDF content."
            ) from exc

        reader = PdfReader(str(path))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(pages)


class ExtractorFactory:
    """
    Factory pattern to resolve extractors by extension.

    Keeps extension-to-extractor wiring in one place.
    """

    def __init__(self, extractors: dict[str, FileTextExtractor] | None = None) -> None:
        self.extractors = extractors or {
            ".txt": TextFileExtractor(),
            ".md": TextFileExtractor(),
            ".pdf": PdfFileExtractor(),
        }

    def for_path(self, path: Path) -> FileTextExtractor | None:
        return self.extractors.get(path.suffix.lower())


class CorpusParser:
    """
    Parse a local corpus into normalized records for LlamaIndex.

    Uses dependency injection for `ExtractorFactory` so parser behavior stays testable
    and easy to extend with new file formats later.
    """

    def __init__(
        self,
        source_dir: str | Path,
        include_extensions: Iterable[str] = DEFAULT_EXTENSIONS,
        exclude_dirs: Iterable[str] = DEFAULT_EXCLUDE_DIRS,
        min_characters: int = 40,
        extractor_factory: ExtractorFactory | None = None,
    ) -> None:
        self.source_dir = Path(source_dir).expanduser().resolve()
        self.include_extensions = tuple(ext.lower() for ext in include_extensions)
        self.exclude_dirs = set(exclude_dirs)
        self.min_characters = min_characters
        self.extractor_factory = extractor_factory or ExtractorFactory()

    def discover_files(self) -> list[Path]:
        files: list[Path] = []
        for path in self.source_dir.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in self.include_extensions:
                continue
            if any(part in self.exclude_dirs for part in path.parts):
                continue
            files.append(path)
        return sorted(files)

    def parse(self) -> list[ParsedDocument]:
        documents: list[ParsedDocument] = []
        for path in self.discover_files():
            text = self._extract_text(path).strip()
            if len(text) < self.min_characters:
                continue
            rel = path.relative_to(self.source_dir)
            metadata = self._build_metadata(path, rel, text)
            doc_id = self._build_doc_id(rel)
            documents.append(ParsedDocument(doc_id=doc_id, text=text, metadata=metadata))
        return documents

    def to_llama_documents(self, parsed_docs: list[ParsedDocument]) -> list:
        try:
            from llama_index.core import Document
        except ImportError as exc:
            raise ImportError(
                "llama-index is required to build LlamaIndex Document objects. "
                "Install it with your dependency manager first."
            ) from exc

        return [
            Document(text=doc.text, metadata=doc.metadata, doc_id=doc.doc_id)
            for doc in parsed_docs
        ]

    def export_jsonl(self, parsed_docs: list[ParsedDocument], output_file: str | Path) -> None:
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as handle:
            for doc in parsed_docs:
                row = {"doc_id": doc.doc_id, "text": doc.text, "metadata": doc.metadata}
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    def _extract_text(self, path: Path) -> str:
        extractor = self.extractor_factory.for_path(path)
        if extractor is None:
            return ""
        return extractor.extract_text(path)

    def _build_doc_id(self, relative_path: Path) -> str:
        return hashlib.sha1(str(relative_path).encode("utf-8")).hexdigest()

    def _build_metadata(self, full_path: Path, relative_path: Path, text: str) -> dict:
        first_heading = self._extract_first_heading(text, full_path.suffix.lower())
        topic = relative_path.parts[0] if len(relative_path.parts) > 1 else "root"
        return {
            "source_path": str(full_path),
            "relative_path": str(relative_path),
            "file_name": full_path.name,
            "file_ext": full_path.suffix.lower(),
            "topic": topic,
            "title": first_heading or full_path.stem,
            "char_count": len(text),
        }

    @staticmethod
    def _extract_first_heading(text: str, suffix: str) -> str | None:
        if suffix != ".md":
            return None
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                return stripped.lstrip("#").strip()
        return None
