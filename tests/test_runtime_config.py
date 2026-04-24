from __future__ import annotations

from src.ingestion.runtime_config import resolve_parse_runtime_config


def test_resolve_parse_runtime_config_uses_config_paths() -> None:
    cfg = {
        "paths": {
            "source_dir": "/volume1/RAG/crypto",
            "output_jsonl": "data/parsed/parsed_documents.jsonl",
            "output_manifest": "data/parsed/parsed_documents_manifest.json",
            "state_file": "data/state/ingestion_state.json",
            "log_dir": "/volume1/Temp/logs",
        },
        "parsing": {
            "min_characters": 60,
            "preview_characters": 300,
            "max_files": 25,
            "skip_unchanged": True,
            "log_level": "INFO",
        },
    }

    resolved = resolve_parse_runtime_config(cfg)
    assert resolved.source_dir == "/volume1/RAG/crypto"
    assert resolved.output_jsonl.endswith("parsed_documents.jsonl")
    assert resolved.output_manifest.endswith("parsed_documents_manifest.json")
    assert resolved.state_file.endswith("ingestion_state.json")
    assert resolved.log_dir == "/volume1/Temp/logs"
    assert resolved.min_characters == 60
    assert resolved.preview_characters == 300
    assert resolved.max_files == 25
    assert resolved.skip_unchanged is True


def test_resolve_parse_runtime_config_cli_overrides_config() -> None:
    cfg = {
        "paths": {
            "source_dir": "/a",
            "output_jsonl": "/b",
            "output_manifest": "/c",
            "state_file": "/d",
            "log_dir": "/e",
        },
        "parsing": {
            "min_characters": 40,
            "preview_characters": 240,
            "max_files": None,
            "skip_unchanged": True,
            "log_level": "INFO",
        },
    }

    resolved = resolve_parse_runtime_config(
        cfg,
        source_dir="/override/source",
        output_jsonl="/override/out.jsonl",
        output_manifest="/override/out.json",
        state_file="/override/state.json",
        log_dir="/override/logs",
        log_level="DEBUG",
        preview_characters=123,
        min_characters=10,
        max_files=5,
        no_skip_unchanged=True,
    )

    assert resolved.source_dir == "/override/source"
    assert resolved.output_jsonl == "/override/out.jsonl"
    assert resolved.output_manifest == "/override/out.json"
    assert resolved.state_file == "/override/state.json"
    assert resolved.log_dir == "/override/logs"
    assert resolved.log_level == "DEBUG"
    assert resolved.preview_characters == 123
    assert resolved.min_characters == 10
    assert resolved.max_files == 5
    assert resolved.skip_unchanged is False

