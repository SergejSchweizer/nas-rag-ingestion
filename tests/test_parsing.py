from pathlib import Path

from src.ingestion.parsing import CorpusParser


def test_discover_files_filters_extensions_and_excluded_dirs(tmp_path: Path) -> None:
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


def test_parse_skips_short_documents(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("short", encoding="utf-8")
    parser = CorpusParser(source_dir=tmp_path, include_extensions=(".txt",), min_characters=10)
    parsed = parser.parse()
    assert parsed == []


def test_to_llama_documents_requires_llama_index(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("Enough characters for parsing.", encoding="utf-8")
    parser = CorpusParser(source_dir=tmp_path, include_extensions=(".txt",), min_characters=5)
    parsed = parser.parse()
    assert len(parsed) == 1

    try:
        import llama_index  # noqa: F401
    except ImportError:
        try:
            parser.to_llama_documents(parsed)
            raised = False
        except ImportError:
            raised = True
        assert raised is True

