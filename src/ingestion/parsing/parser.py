"""Parsing orchestration for turning local files into ingestion-ready records.

This module uses Docling as the primary parsing backend and only keeps lightweight
normalization logic that is not provided directly by Docling.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .constants import DEFAULT_EXCLUDE_DIRS, DEFAULT_EXTENSIONS
from .docling_adapter import DoclingAdapter
from .models import ChildNode, ParentNode, ParsedDocument, SemanticElement
from .semantic_extractor import SemanticExtractor
from .state import IngestionStateStore

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class ParseRunStats:
    """Counters describing the outcome of a single parse run."""

    discovered_count: int
    parsed_count: int
    skipped_unchanged_count: int
    removed_missing_count: int
    parse_error_count: int
    unparsed_files: tuple[tuple[str, str], ...]


class CorpusParser:
    """Parse a local corpus into normalized records for ingestion.

    Docling is used as the canonical parser for supported formats. A small
    compatibility layer maps Docling items into the repository's semantic schema.
    """

    def __init__(
        self,
        source_dir: str | Path,
        include_extensions: Iterable[str] = DEFAULT_EXTENSIONS,
        exclude_dirs: Iterable[str] = DEFAULT_EXCLUDE_DIRS,
        min_characters: int = 40,
        child_chunk_size: int = 800,
        child_chunk_overlap: int = 120,
        docling_converter: Any | None = None,
        docling_adapter: DoclingAdapter | None = None,
        semantic_extractor: SemanticExtractor | None = None,
    ) -> None:
        """Initialize parser settings and parser run state."""
        self.source_dir = Path(source_dir).expanduser().resolve()
        self.include_extensions = tuple(ext.lower() for ext in include_extensions)
        self.exclude_dirs = set(exclude_dirs)
        self.min_characters = min_characters
        self.child_chunk_size = child_chunk_size
        self.child_chunk_overlap = child_chunk_overlap
        if docling_converter is not None and docling_adapter is not None:
            raise ValueError("Use only one of `docling_converter` or `docling_adapter`.")
        self.docling_adapter = docling_adapter or DoclingAdapter(converter=docling_converter)
        self.semantic_extractor = semantic_extractor or SemanticExtractor(
            docling_adapter=self.docling_adapter
        )
        # Backwards-compatible attribute for integrations/tests that may inspect it.
        self.docling_converter = self.docling_adapter.converter
        self.last_run_stats = ParseRunStats(
            discovered_count=0,
            parsed_count=0,
            skipped_unchanged_count=0,
            removed_missing_count=0,
            parse_error_count=0,
            unparsed_files=(),
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
        unparsed_files: list[tuple[str, str]] = []

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

            doc_id = self._build_doc_id(rel)
            try:
                text, elements = self._extract_with_docling(path=path, doc_id=doc_id)
            except Exception as exc:
                error_message = str(exc)
                LOGGER.error("UNPARSED_FILE relative_path=%s reason=%s", rel_str, error_message)
                parse_error_count += 1
                unparsed_files.append((rel_str, error_message))
                continue

            if len(text) < self.min_characters:
                continue
            if not elements:
                continue

            paper_title, authors, year = self._infer_paper_metadata(elements)
            parent_nodes = self._build_parent_nodes(doc_id, elements, paper_title, authors, year)
            child_nodes = self._build_child_nodes(
                doc_id=doc_id,
                elements=elements,
                parent_nodes=parent_nodes,
                paper_title=paper_title,
                authors=authors,
                year=year,
            )
            metadata = self._build_metadata(
                full_path=path,
                relative_path=rel,
                text=text,
                paper_title=paper_title,
                authors=authors,
                year=year,
                elements=elements,
                parent_nodes=parent_nodes,
                child_nodes=child_nodes,
            )
            documents.append(
                ParsedDocument(
                    doc_id=doc_id,
                    text=text,
                    metadata=metadata,
                    elements=tuple(elements),
                    parent_nodes=tuple(parent_nodes),
                    child_nodes=tuple(child_nodes),
                )
            )

            if state_store and file_fingerprint is not None:
                state_store.record_ingested(
                    relative_path=rel_str,
                    fingerprint=file_fingerprint,
                    doc_id=doc_id,
                    char_count=metadata["char_count"],
                )

        removed_missing_count = 0
        if state_store:
            if max_files is None:
                removed_missing_count = state_store.remove_missing(seen_relative_paths)
            state_store.save()

        self.last_run_stats = ParseRunStats(
            discovered_count=len(discovered_files),
            parsed_count=len(documents),
            skipped_unchanged_count=skipped_unchanged_count,
            removed_missing_count=removed_missing_count,
            parse_error_count=parse_error_count,
            unparsed_files=tuple(unparsed_files),
        )
        return documents

    def export_jsonl(
        self,
        parsed_docs: list[ParsedDocument],
        output_file: str | Path,
        *,
        keep_existing_if_empty: bool = False,
    ) -> None:
        """Write parsed documents as JSONL for traceability and offline inspection."""
        output_path = Path(output_file)
        if keep_existing_if_empty and not parsed_docs and output_path.exists():
            LOGGER.info(
                "Skipping JSONL overwrite because parse result is empty and "
                "keep_existing_if_empty=True. path=%s",
                output_path,
            )
            return
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as handle:
            for doc in parsed_docs:
                row = {
                    "doc_id": doc.doc_id,
                    "text": doc.text,
                    "metadata": doc.metadata,
                    "elements": [self._serialize_element(item) for item in doc.elements],
                    "parent_nodes": [self._serialize_parent(item) for item in doc.parent_nodes],
                    "child_nodes": [self._serialize_child(item) for item in doc.child_nodes],
                }
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    def export_tracking_manifest(
        self,
        parsed_docs: list[ParsedDocument],
        output_file: str | Path,
        preview_characters: int = 240,
    ) -> None:
        """Write a human-readable tracking manifest for parsed documents."""
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        documents = []
        for index, doc in enumerate(parsed_docs, start=1):
            metadata = doc.metadata
            element_counts = self._count_by_type(doc.elements)
            documents.append(
                {
                    "index": index,
                    "doc_id": doc.doc_id,
                    "title": metadata.get("title"),
                    "paper_title": metadata.get("paper_title"),
                    "authors": metadata.get("authors"),
                    "year": metadata.get("year"),
                    "topic": metadata.get("topic"),
                    "file_ext": metadata.get("file_ext"),
                    "char_count": metadata.get("char_count"),
                    "relative_path": metadata.get("relative_path"),
                    "source_path": metadata.get("source_path"),
                    "elements_count": len(doc.elements),
                    "parent_nodes_count": len(doc.parent_nodes),
                    "child_nodes_count": len(doc.child_nodes),
                    "element_type_counts": element_counts,
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

    def _extract_with_docling(self, path: Path, doc_id: str) -> tuple[str, list[SemanticElement]]:
        """Convert a file with Docling and map its structure to semantic elements."""
        result = self.docling_adapter.convert(path)
        if not self.docling_adapter.is_successful_conversion(result.status):
            errors = [str(item) for item in (result.errors or [])]
            raise ValueError(
                f"Docling conversion failed with status={result.status} errors={errors}"
            )

        doc = result.document
        elements = self.semantic_extractor.extract(doc_id=doc_id, doc=doc)
        text = (doc.export_to_text() or "").strip()
        if not text:
            text = "\n".join(item.text for item in elements).strip()
        return text, elements

    def _build_parent_nodes(
        self,
        doc_id: str,
        elements: list[SemanticElement],
        paper_title: str | None,
        authors: list[str],
        year: int | None,
    ) -> list[ParentNode]:
        """Build parent nodes aligned with section/subsection boundaries."""
        parents: list[ParentNode] = []
        current_elements: list[SemanticElement] = []
        current_section: tuple[str, ...] = ("front_matter",)

        def flush_parent() -> None:
            """Persist current parent buffer as one section-aligned parent node."""
            if not current_elements:
                return
            parent_index = len(parents) + 1
            text = "\n".join(item.text for item in current_elements)
            page_start = min(item.page for item in current_elements)
            page_end = max(item.page for item in current_elements)
            section_label = current_section[-1] if current_section else "front_matter"
            parent_id = self._hash_id(
                doc_id, "parent", str(parent_index), ".".join(current_section)
            )
            parents.append(
                ParentNode(
                    parent_id=parent_id,
                    doc_id=doc_id,
                    section_path=current_section,
                    page_start=page_start,
                    page_end=page_end,
                    text=text,
                    metadata={
                        "doc_id": doc_id,
                        "paper_title": paper_title,
                        "authors": authors,
                        "year": year,
                        "section": section_label,
                        "page_start": page_start,
                        "page_end": page_end,
                        "chunk_level": "parent",
                    },
                )
            )

        for element in elements:
            if element.element_type == "section_heading":
                flush_parent()
                current_elements = [element]
                current_section = element.section_path or ("front_matter",)
                continue

            if not current_elements:
                current_elements = [element]
                current_section = element.section_path or ("front_matter",)
                continue

            current_elements.append(element)

        flush_parent()
        return parents

    def _build_child_nodes(
        self,
        doc_id: str,
        elements: list[SemanticElement],
        parent_nodes: list[ParentNode],
        paper_title: str | None,
        authors: list[str],
        year: int | None,
    ) -> list[ChildNode]:
        """Build fine-grained retrieval nodes from parent nodes and special elements."""
        children: list[ChildNode] = []

        for parent in parent_nodes:
            windows = self._token_windows(
                parent.text,
                chunk_size=self.child_chunk_size,
                overlap=self.child_chunk_overlap,
            )
            for chunk_index, chunk_text in enumerate(windows, start=1):
                child_id = self._hash_id(parent.parent_id, "text", str(chunk_index))
                children.append(
                    ChildNode(
                        child_id=child_id,
                        parent_id=parent.parent_id,
                        doc_id=doc_id,
                        chunk_level="child",
                        chunk_type="text",
                        section_path=parent.section_path,
                        page_start=parent.page_start,
                        page_end=parent.page_end,
                        text=chunk_text,
                        metadata={
                            "doc_id": doc_id,
                            "paper_title": paper_title,
                            "authors": authors,
                            "year": year,
                            "section": parent.metadata.get("section"),
                            "page_start": parent.page_start,
                            "page_end": parent.page_end,
                            "chunk_level": "child",
                            "chunk_type": "text",
                            "chunk_index": chunk_index,
                        },
                    )
                )

        for idx, element in enumerate(elements):
            if element.element_type not in {"table", "figure_caption"}:
                continue

            selected_parent = self._parent_for_section(parent_nodes, element.section_path)
            if selected_parent is None and parent_nodes:
                selected_parent = parent_nodes[0]
            if selected_parent is None:
                continue

            chunk_type = "table" if element.element_type == "table" else "figure"
            if chunk_type == "table":
                table_rows = element.metadata.get("rows", [])
                table_text = self._serialize_table_rows(table_rows)
                chunk_text = f"{element.text}\n{table_text}".strip()
                extra_metadata = {"table_rows": table_rows}
            else:
                context = self._figure_context(elements, idx)
                chunk_text = f"{element.text}\n{context}".strip()
                extra_metadata = {"figure_context": context}

            child_id = self._hash_id(selected_parent.parent_id, chunk_type, element.element_id)
            children.append(
                ChildNode(
                    child_id=child_id,
                    parent_id=selected_parent.parent_id,
                    doc_id=doc_id,
                    chunk_level="child",
                    chunk_type=chunk_type,
                    section_path=element.section_path,
                    page_start=element.page,
                    page_end=element.page,
                    text=chunk_text,
                    metadata={
                        "doc_id": doc_id,
                        "paper_title": paper_title,
                        "authors": authors,
                        "year": year,
                        "section": element.section_path[-1]
                        if element.section_path
                        else "front_matter",
                        "page_start": element.page,
                        "page_end": element.page,
                        "chunk_level": "child",
                        "chunk_type": chunk_type,
                        **extra_metadata,
                    },
                )
            )

        return children

    def _parent_for_section(
        self,
        parent_nodes: list[ParentNode],
        section_path: tuple[str, ...],
    ) -> ParentNode | None:
        """Return best matching parent for section path."""
        for parent in parent_nodes:
            if parent.section_path == section_path:
                return parent
        for parent in parent_nodes:
            if section_path and parent.section_path and parent.section_path[-1] == section_path[-1]:
                return parent
        return None

    def _figure_context(self, elements: list[SemanticElement], figure_index: int) -> str:
        """Find nearby explanatory paragraph to enrich figure chunk context."""
        figure = elements[figure_index]
        for item in elements[figure_index + 1 :]:
            if item.page != figure.page:
                break
            if item.section_path != figure.section_path:
                break
            if item.element_type == "paragraph":
                return item.text
        return ""

    def _infer_paper_metadata(
        self,
        elements: list[SemanticElement],
    ) -> tuple[str | None, list[str], int | None]:
        """Infer paper-level metadata such as title, authors, and year."""
        title = None
        for element in elements:
            if element.element_type == "title":
                title = element.text
                break
        authors = self._infer_authors(elements)
        year = self._infer_year(elements)
        return title, authors, year

    def _infer_authors(self, elements: list[SemanticElement]) -> list[str]:
        """Heuristically infer author lines from first-page front matter text."""
        first_page = [item for item in elements if item.page == 1]
        if not first_page:
            return []

        candidates: list[str] = []
        title_seen = False
        for element in first_page:
            if element.element_type == "title":
                title_seen = True
                continue
            if not title_seen:
                continue
            if element.element_type == "section_heading":
                break
            text = element.text.strip()
            if not text or re.search(r"\d{4}", text) or "@" in text:
                continue
            word_count = len(text.split())
            if 2 <= word_count <= 15:
                candidates.append(text)
            if len(candidates) >= 3:
                break
        return candidates

    def _infer_year(self, elements: list[SemanticElement]) -> int | None:
        """Infer publication year from early document content."""
        early_text = "\n".join(item.text for item in elements[:25])
        match = re.search(r"\b(19|20)\d{2}\b", early_text)
        if not match:
            return None
        return int(match.group(0))

    def _build_metadata(
        self,
        full_path: Path,
        relative_path: Path,
        text: str,
        paper_title: str | None,
        authors: list[str],
        year: int | None,
        elements: list[SemanticElement],
        parent_nodes: list[ParentNode],
        child_nodes: list[ChildNode],
    ) -> dict[str, Any]:
        """Build retrieval metadata payload for a parsed source file."""
        topic = relative_path.parts[0] if len(relative_path.parts) > 1 else "root"
        page_start = min((item.page for item in elements), default=1)
        page_end = max((item.page for item in elements), default=1)
        return {
            "source_path": str(full_path),
            "relative_path": str(relative_path),
            "file_name": full_path.name,
            "file_ext": full_path.suffix.lower(),
            "topic": topic,
            "title": paper_title or full_path.stem,
            "paper_title": paper_title or full_path.stem,
            "authors": authors,
            "year": year,
            "char_count": len(text),
            "page_start": page_start,
            "page_end": page_end,
            "elements_count": len(elements),
            "parent_nodes_count": len(parent_nodes),
            "child_nodes_count": len(child_nodes),
        }

    def _token_windows(self, text: str, chunk_size: int, overlap: int) -> list[str]:
        """Split text into overlapping token windows for child retrieval nodes."""
        tokens = text.split()
        if not tokens:
            return []
        if chunk_size <= 0:
            return [" ".join(tokens)]

        step = max(chunk_size - max(overlap, 0), 1)
        windows: list[str] = []
        for start in range(0, len(tokens), step):
            window = tokens[start : start + chunk_size]
            if not window:
                continue
            windows.append(" ".join(window))
            if start + chunk_size >= len(tokens):
                break
        return windows

    def _serialize_table_rows(self, rows: list[list[str]]) -> str:
        """Serialize parsed table rows into a compact stable text representation."""
        if not rows:
            return ""
        return "\n".join(" | ".join(row) for row in rows if row)

    def _build_doc_id(self, relative_path: Path) -> str:
        """Build stable document id from a source-relative path."""
        return hashlib.sha1(str(relative_path).encode("utf-8")).hexdigest()

    @staticmethod
    def _file_fingerprint(path: Path) -> str:
        """Compute SHA-256 fingerprint for file-content change detection."""
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _preview_text(text: str, preview_characters: int) -> str:
        """Create compact single-line preview for tracking manifests."""
        if preview_characters <= 0:
            return ""
        compact = " ".join(text.split())
        if len(compact) <= preview_characters:
            return compact
        return compact[:preview_characters].rstrip() + "..."

    @staticmethod
    def _count_by_type(elements: Iterable[SemanticElement]) -> dict[str, int]:
        """Count elements by semantic type."""
        counts: dict[str, int] = {}
        for item in elements:
            counts[item.element_type] = counts.get(item.element_type, 0) + 1
        return counts

    @staticmethod
    def _hash_id(*parts: str) -> str:
        """Create stable SHA-1 id from parts."""
        raw = "::".join(parts)
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def _serialize_element(self, item: SemanticElement) -> dict[str, Any]:
        """Convert semantic element dataclass into JSON-serializable payload."""
        return {
            "element_id": item.element_id,
            "element_type": item.element_type,
            "text": item.text,
            "page": item.page,
            "order": item.order,
            "section_path": list(item.section_path),
            "metadata": item.metadata,
        }

    def _serialize_parent(self, item: ParentNode) -> dict[str, Any]:
        """Convert parent node dataclass into JSON-serializable payload."""
        return {
            "parent_id": item.parent_id,
            "doc_id": item.doc_id,
            "section_path": list(item.section_path),
            "page_start": item.page_start,
            "page_end": item.page_end,
            "text": item.text,
            "metadata": item.metadata,
        }

    def _serialize_child(self, item: ChildNode) -> dict[str, Any]:
        """Convert child node dataclass into JSON-serializable payload."""
        return {
            "child_id": item.child_id,
            "parent_id": item.parent_id,
            "doc_id": item.doc_id,
            "chunk_level": item.chunk_level,
            "chunk_type": item.chunk_type,
            "section_path": list(item.section_path),
            "page_start": item.page_start,
            "page_end": item.page_end,
            "text": item.text,
            "metadata": item.metadata,
        }
