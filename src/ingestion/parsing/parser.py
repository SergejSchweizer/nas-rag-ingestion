from __future__ import annotations

"""Parsing orchestration for turning local files into ingestion-ready records."""

import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import dataclass
import logging
from typing import Iterable

from .constants import DEFAULT_EXCLUDE_DIRS, DEFAULT_EXTENSIONS
from .extractors import ExtractorFactory
from .models import ParsedDocument
from .state import IngestionStateStore

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class ParseRunStats:
    discovered_count: int
    parsed_count: int
    skipped_unchanged_count: int
    removed_missing_count: int
    parse_error_count: int


class CorpusParser:
    """Parse a local corpus into normalized records for LlamaIndex."""

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
        self.last_run_stats = ParseRunStats(
            discovered_count=0,
            parsed_count=0,
            skipped_unchanged_count=0,
            removed_missing_count=0,
            parse_error_count=0,
        )

    def discover_files(self) -> list[Path]:
        """Discover source files respecting extension and directory filters."""
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

    def parse(
        self,
        max_files: int | None = None,
        state_file: str | Path | None = None,
        skip_unchanged: bool = True,
    ) -> list[ParsedDocument]:
        """Parse discovered files into normalized `ParsedDocument` records."""
        if max_files is not None and max_files <= 0:
            raise ValueError("max_files must be greater than 0 when provided.")

        documents: list[ParsedDocument] = []
        discovered_files = self.discover_files()
        if max_files is not None:
            discovered_files = discovered_files[:max_files]

        state_store = IngestionStateStore(state_file) if state_file else None
        seen_relative_paths: set[str] = set()
        skipped_unchanged_count = 0
        parse_error_count = 0

        for path in discovered_files:
            rel = path.relative_to(self.source_dir)
            rel_str = str(rel)
            seen_relative_paths.add(rel_str)

            file_fingerprint = self._file_fingerprint(path) if state_store else None
            if (
                state_store
                and skip_unchanged
                and file_fingerprint is not None
                and not state_store.should_ingest(rel_str, file_fingerprint)
            ):
                skipped_unchanged_count += 1
                continue

            try:
                text = self._extract_text(path).strip()
            except Exception as exc:
                LOGGER.warning("Failed to parse %s: %s", path, exc)
                parse_error_count += 1
                continue
            if len(text) < self.min_characters:
                continue
            metadata = self._build_metadata(path, rel, text)
            doc_id = self._build_doc_id(rel)
            documents.append(ParsedDocument(doc_id=doc_id, text=text, metadata=metadata))

            if state_store and file_fingerprint is not None:
                state_store.record_ingested(
                    relative_path=rel_str,
                    fingerprint=file_fingerprint,
                    doc_id=doc_id,
                    char_count=metadata["char_count"],
                )

        removed_missing_count = 0
        if state_store:
            # Avoid deleting tracked files during a limited run.
            if max_files is None:
                removed_missing_count = state_store.remove_missing(seen_relative_paths)
            state_store.save()

        self.last_run_stats = ParseRunStats(
            discovered_count=len(discovered_files),
            parsed_count=len(documents),
            skipped_unchanged_count=skipped_unchanged_count,
            removed_missing_count=removed_missing_count,
            parse_error_count=parse_error_count,
        )
        return documents

    def to_llama_documents(self, parsed_docs: list[ParsedDocument]) -> list:
        """Convert parsed records into LlamaIndex `Document` objects."""
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
        """Write parsed documents as JSONL for traceability and offline inspection."""
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as handle:
            for doc in parsed_docs:
                row = {"doc_id": doc.doc_id, "text": doc.text, "metadata": doc.metadata}
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    def export_tracking_manifest(
        self,
        parsed_docs: list[ParsedDocument],
        output_file: str | Path,
        preview_characters: int = 240,
    ) -> None:
        """Write a human-readable tracking manifest for parsed documents.

        The JSONL export is useful for pipelines, while this manifest is optimized
        for operational tracking and quick inspection.
        """
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        documents = []
        for index, doc in enumerate(parsed_docs, start=1):
            metadata = doc.metadata
            documents.append(
                {
                    "index": index,
                    "doc_id": doc.doc_id,
                    "title": metadata.get("title"),
                    "topic": metadata.get("topic"),
                    "file_ext": metadata.get("file_ext"),
                    "char_count": metadata.get("char_count"),
                    "relative_path": metadata.get("relative_path"),
                    "source_path": metadata.get("source_path"),
                    "text_preview": self._preview_text(doc.text, preview_characters),
                }
            )

        manifest = {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "source_dir": str(self.source_dir),
            "document_count": len(parsed_docs),
            "total_characters": sum(doc.metadata.get("char_count", 0) for doc in parsed_docs),
            "documents": documents,
        }
        output_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    def _extract_text(self, path: Path) -> str:
        extractor = self.extractor_factory.for_path(path)
        if extractor is None:
            return ""
        return extractor.extract_text(path)

    def _build_doc_id(self, relative_path: Path) -> str:
        return hashlib.sha1(str(relative_path).encode("utf-8")).hexdigest()

    @staticmethod
    def _file_fingerprint(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

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

    @staticmethod
    def _preview_text(text: str, preview_characters: int) -> str:
        if preview_characters <= 0:
            return ""
        compact = " ".join(text.split())
        if len(compact) <= preview_characters:
            return compact
        return compact[:preview_characters].rstrip() + "..."
