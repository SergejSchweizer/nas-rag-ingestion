"""Tests for parsing, idempotency, manifest export, and Docling integration behavior."""

import json
from pathlib import Path

from src.ingestion.parsing import CorpusParser
from src.ingestion.parsing.models import ParsedDocument


def test_discover_files_filters_extensions_and_excluded_dirs(tmp_path: Path) -> None:
    """Parser should include only supported extensions and skip excluded directories."""
    (tmp_path / "papers").mkdir()
    (tmp_path / ".git").mkdir()

    (tmp_path / "papers" / "one.md").write_text("# Paper One\nSome text here.", encoding="utf-8")
    (tmp_path / "papers" / "two.txt").write_text("Useful text content.", encoding="utf-8")
    (tmp_path / "papers" / "three.csv").write_text("a,b", encoding="utf-8")
    (tmp_path / ".git" / "ignored.md").write_text("# Ignored", encoding="utf-8")

    parser = CorpusParser(source_dir=tmp_path, include_extensions=(".md", ".txt"))
    files = parser.discover_files()

    rel_files = {str(path.relative_to(tmp_path)) for path in files}
    assert rel_files == {"papers/one.md", "papers/two.txt"}


def test_parse_extracts_markdown_title_and_topic(tmp_path: Path) -> None:
    """Docling-backed parsing should keep title/topic metadata and semantic hierarchy."""
    doc_dir = tmp_path / "crypto-papers"
    doc_dir.mkdir()
    file_path = doc_dir / "btc.md"
    file_path.write_text("# Bitcoin Whitepaper\nBody text " * 10, encoding="utf-8")

    parser = CorpusParser(source_dir=tmp_path, include_extensions=(".md",), min_characters=20)
    parsed = parser.parse()

    assert len(parsed) == 1
    doc = parsed[0]
    assert doc.metadata["title"] == "Bitcoin Whitepaper"
    assert doc.metadata["topic"] == "crypto-papers"
    assert doc.metadata["relative_path"] == "crypto-papers/btc.md"
    assert doc.metadata["char_count"] >= 20
    assert doc.metadata["paper_title"] == "Bitcoin Whitepaper"
    assert doc.elements
    assert doc.parent_nodes
    assert doc.child_nodes


def test_parse_skips_short_documents(tmp_path: Path) -> None:
    """Parser should drop documents below the configured minimum character threshold."""
    (tmp_path / "notes.txt").write_text("short", encoding="utf-8")
    parser = CorpusParser(source_dir=tmp_path, include_extensions=(".txt",), min_characters=10)
    parsed = parser.parse()
    assert parsed == []


def test_parse_respects_max_files_limit(tmp_path: Path) -> None:
    """`max_files` should limit discovered files in deterministic order."""
    docs_dir = tmp_path / "notes"
    docs_dir.mkdir()
    (docs_dir / "a.txt").write_text("alpha content long enough", encoding="utf-8")
    (docs_dir / "b.txt").write_text("beta content long enough", encoding="utf-8")
    (docs_dir / "c.txt").write_text("gamma content long enough", encoding="utf-8")

    parser = CorpusParser(source_dir=tmp_path, include_extensions=(".txt",), min_characters=5)
    parsed = parser.parse(max_files=2)

    assert len(parsed) == 2
    rel_paths = {doc.metadata["relative_path"] for doc in parsed}
    assert rel_paths == {"notes/a.txt", "notes/b.txt"}


def test_export_tracking_manifest_has_readable_summary(tmp_path: Path) -> None:
    """Tracking manifest should include summary counters and per-document preview."""
    (tmp_path / "paper.md").write_text(
        "# Paper Title\nThis is a long paragraph for preview generation.",
        encoding="utf-8",
    )
    parser = CorpusParser(source_dir=tmp_path, include_extensions=(".md",), min_characters=5)
    parsed = parser.parse()
    manifest_path = tmp_path / "parsed_documents_manifest.json"

    parser.export_tracking_manifest(parsed, manifest_path, preview_characters=20)

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["document_count"] == 1
    assert payload["total_characters"] == parsed[0].metadata["char_count"]
    assert payload["documents"][0]["title"] == "Paper Title"
    assert payload["documents"][0]["text_preview"].endswith("...")


def test_export_jsonl_keeps_existing_file_when_result_is_empty(tmp_path: Path) -> None:
    """JSONL export should preserve existing output when configured to keep empty runs."""
    parser = CorpusParser(source_dir=tmp_path, include_extensions=(".txt",), min_characters=1)
    output_path = tmp_path / "parsed_documents.jsonl"

    seeded = ParsedDocument(
        doc_id="doc-1",
        text="seed text",
        metadata={"char_count": 9},
        elements=(),
        parent_nodes=(),
        child_nodes=(),
    )
    parser.export_jsonl([seeded], output_path)
    before = output_path.read_text(encoding="utf-8")

    parser.export_jsonl([], output_path, keep_existing_if_empty=True)
    after = output_path.read_text(encoding="utf-8")

    assert after == before


def test_parse_with_state_skips_unchanged_files(tmp_path: Path) -> None:
    """Second parse run should skip unchanged files when state tracking is enabled."""
    state_file = tmp_path / "state" / "ingestion_state.json"
    (tmp_path / "paper.txt").write_text("same content for idempotency", encoding="utf-8")
    parser = CorpusParser(source_dir=tmp_path, include_extensions=(".txt",), min_characters=5)

    first_run = parser.parse(state_file=state_file, skip_unchanged=True)
    second_run = parser.parse(state_file=state_file, skip_unchanged=True)

    assert len(first_run) == 1
    assert len(second_run) == 0
    assert parser.last_run_stats.skipped_unchanged_count == 1


def test_parse_with_state_reingests_file_if_content_changes(tmp_path: Path) -> None:
    """File should be re-ingested when fingerprint changes between runs."""
    state_file = tmp_path / "state" / "ingestion_state.json"
    target_file = tmp_path / "paper.txt"
    target_file.write_text("v1 content for parser", encoding="utf-8")
    parser = CorpusParser(source_dir=tmp_path, include_extensions=(".txt",), min_characters=5)

    run_one = parser.parse(state_file=state_file, skip_unchanged=True)
    target_file.write_text("v2 content for parser", encoding="utf-8")
    run_two = parser.parse(state_file=state_file, skip_unchanged=True)

    assert len(run_one) == 1
    assert len(run_two) == 1


def test_parse_continues_when_docling_converter_raises(tmp_path: Path) -> None:
    """Parser should keep running and count parse errors when converter raises."""

    class BrokenConverter:
        """Converter test double that always fails."""

        def convert(self, source: object, raises_on_error: bool = True) -> object:
            """Raise conversion error for path-based conversion."""
            raise ValueError("broken file payload")

        def convert_string(self, content: str, format: object, name: str | None = None) -> object:
            """Raise conversion error for string-based conversion."""
            raise ValueError("broken file payload")

    (tmp_path / "bad.md").write_text("ignored content", encoding="utf-8")
    parser = CorpusParser(
        source_dir=tmp_path,
        include_extensions=(".md",),
        docling_converter=BrokenConverter(),
    )

    parsed = parser.parse()
    assert parsed == []
    assert parser.last_run_stats.parse_error_count == 1
    assert len(parser.last_run_stats.unparsed_files) == 1
    relative_path, reason = parser.last_run_stats.unparsed_files[0]
    assert relative_path == "bad.md"
    assert "broken file payload" in reason


def test_parse_builds_semantic_elements_and_special_chunks(tmp_path: Path) -> None:
    """Parser should build semantic elements, parent nodes, and special child chunks."""
    (tmp_path / "paper.md").write_text(
        "\n".join(
            [
                "# Crypto Market Dynamics",
                "Sergej Schweizer",
                "2024",
                "## Introduction",
                "This paragraph explains the market structure.",
                "Figure 1: BTC volatility regime chart.",
                "This paragraph explains the figure in detail.",
                "## Results",
                "A = B + C",
                "col1 | col2 | col3",
                "v1 | v2 | v3",
                "## References",
                "[1] Satoshi, 2008",
            ]
        ),
        encoding="utf-8",
    )

    parser = CorpusParser(source_dir=tmp_path, include_extensions=(".md",), min_characters=5)
    parsed = parser.parse()

    assert len(parsed) == 1
    doc = parsed[0]

    element_types = {item.element_type for item in doc.elements}
    assert "title" in element_types
    assert "section_heading" in element_types
    assert "paragraph" in element_types
    assert "figure_caption" in element_types
    assert "equation" in element_types
    assert "table" in element_types
    assert "references" in element_types

    assert doc.parent_nodes
    assert doc.child_nodes
    chunk_types = {item.chunk_type for item in doc.child_nodes}
    assert "text" in chunk_types
    assert "table" in chunk_types
    assert "figure" in chunk_types

    first_parent = doc.parent_nodes[0]
    assert first_parent.metadata["chunk_level"] == "parent"
    first_child = doc.child_nodes[0]
    assert first_child.metadata["chunk_level"] == "child"
    assert first_child.metadata["doc_id"] == doc.doc_id
