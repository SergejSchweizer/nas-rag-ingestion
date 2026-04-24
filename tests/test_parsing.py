from pathlib import Path
import json

from src.ingestion.parsing import CorpusParser, ExtractorFactory, FileTextExtractor


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


def test_parse_respects_max_files_limit(tmp_path: Path) -> None:
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


def test_parser_supports_custom_extractor_via_dependency_injection(tmp_path: Path) -> None:
    class UpperExtractor(FileTextExtractor):
        def extract_text(self, path: Path) -> str:
            return path.read_text(encoding="utf-8").upper()

    (tmp_path / "notes.txt").write_text("alpha beta gamma", encoding="utf-8")
    factory = ExtractorFactory(extractors={".txt": UpperExtractor()})
    parser = CorpusParser(
        source_dir=tmp_path,
        include_extensions=(".txt",),
        min_characters=5,
        extractor_factory=factory,
    )
    parsed = parser.parse()

    assert len(parsed) == 1
    assert parsed[0].text == "ALPHA BETA GAMMA"


def test_export_tracking_manifest_has_readable_summary(tmp_path: Path) -> None:
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


def test_parse_with_state_skips_unchanged_files(tmp_path: Path) -> None:
    state_file = tmp_path / "state" / "ingestion_state.json"
    (tmp_path / "paper.txt").write_text("same content for idempotency", encoding="utf-8")
    parser = CorpusParser(source_dir=tmp_path, include_extensions=(".txt",), min_characters=5)

    first_run = parser.parse(state_file=state_file, skip_unchanged=True)
    second_run = parser.parse(state_file=state_file, skip_unchanged=True)

    assert len(first_run) == 1
    assert len(second_run) == 0
    assert parser.last_run_stats.skipped_unchanged_count == 1


def test_parse_with_state_reingests_file_if_content_changes(tmp_path: Path) -> None:
    state_file = tmp_path / "state" / "ingestion_state.json"
    target_file = tmp_path / "paper.txt"
    target_file.write_text("v1 content for parser", encoding="utf-8")
    parser = CorpusParser(source_dir=tmp_path, include_extensions=(".txt",), min_characters=5)

    run_one = parser.parse(state_file=state_file, skip_unchanged=True)
    target_file.write_text("v2 content for parser", encoding="utf-8")
    run_two = parser.parse(state_file=state_file, skip_unchanged=True)

    assert len(run_one) == 1
    assert len(run_two) == 1


def test_parse_continues_when_extractor_raises(tmp_path: Path) -> None:
    class BrokenExtractor(FileTextExtractor):
        def extract_text(self, path: Path) -> str:
            raise ValueError("broken file payload")

    (tmp_path / "bad.txt").write_text("ignored content", encoding="utf-8")
    parser = CorpusParser(
        source_dir=tmp_path,
        include_extensions=(".txt",),
        extractor_factory=ExtractorFactory(extractors={".txt": BrokenExtractor()}),
    )

    parsed = parser.parse()
    assert parsed == []
    assert parser.last_run_stats.parse_error_count == 1
