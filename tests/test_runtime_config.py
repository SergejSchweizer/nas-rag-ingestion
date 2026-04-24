from __future__ import annotations

"""Tests for config loading and CLI override precedence resolution."""

from src.ingestion.runtime_config import resolve_index_runtime_config, resolve_parse_runtime_config


def test_resolve_parse_runtime_config_uses_config_paths() -> None:
    """Resolver should map config values directly when no CLI overrides are provided."""
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
    assert resolved.child_chunk_size == 800
    assert resolved.child_chunk_overlap == 120


def test_resolve_parse_runtime_config_cli_overrides_config() -> None:
    """CLI override values should take precedence over file-based config values."""
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
    assert resolved.child_chunk_size == 800
    assert resolved.child_chunk_overlap == 120


def test_resolve_parse_runtime_config_preserves_zero_cli_overrides() -> None:
    """Integer CLI overrides should preserve explicit zero values."""
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
            "skip_unchanged": True,
            "log_level": "INFO",
        },
    }

    resolved = resolve_parse_runtime_config(
        cfg,
        preview_characters=0,
        min_characters=0,
    )

    assert resolved.preview_characters == 0
    assert resolved.min_characters == 0


def test_resolve_index_runtime_config_uses_config_values() -> None:
    """Index config resolver should map values from file config by default."""
    cfg = {
        "paths": {
            "output_jsonl": "data/parsed/parsed_documents.jsonl",
            "log_dir": "/volume1/Temp/logs",
        },
        "parsing": {
            "log_level": "INFO",
        },
        "qdrant": {
            "url": "http://localhost:6333",
            "api_key": "secret",
            "collection": "nas_docs",
            "vector_size": 1024,
            "distance": "Cosine",
        },
        "embeddings": {
            "provider": "local",
            "model": "bge-m3",
            "endpoint": "http://localhost:11434",
        },
    }

    resolved = resolve_index_runtime_config(cfg)
    assert resolved.input_jsonl.endswith("parsed_documents.jsonl")
    assert resolved.index_state_file.endswith("indexing_state.json")
    assert resolved.qdrant_url == "http://localhost:6333"
    assert resolved.qdrant_api_key == "secret"
    assert resolved.qdrant_collection == "nas_docs"
    assert resolved.qdrant_vector_size == 1024
    assert resolved.qdrant_distance == "Cosine"
    assert resolved.embedding_model == "bge-m3"
    assert resolved.embedding_provider == "local"
    assert resolved.embedding_endpoint == "http://localhost:11434"
    assert resolved.log_dir == "/volume1/Temp/logs"
    assert resolved.log_level == "INFO"
    assert resolved.recreate_collection is False
    assert resolved.batch_size == 128


def test_resolve_index_runtime_config_cli_overrides_config() -> None:
    """CLI overrides should take precedence for index runtime config."""
    cfg = {
        "paths": {
            "output_jsonl": "data/parsed/parsed_documents.jsonl",
            "log_dir": "/volume1/Temp/logs",
        },
        "parsing": {
            "log_level": "INFO",
        },
        "qdrant": {
            "url": "http://localhost:6333",
            "api_key": "secret",
            "collection": "nas_docs",
            "vector_size": 1024,
            "distance": "Cosine",
        },
        "embeddings": {
            "provider": "local",
            "model": "bge-m3",
            "endpoint": "http://localhost:11434",
        },
    }

    resolved = resolve_index_runtime_config(
        cfg,
        input_jsonl="/tmp/parsed.jsonl",
        index_state_file="/tmp/indexing_state.json",
        qdrant_url="http://10.10.10.10:6333",
        qdrant_api_key="override-key",
        qdrant_collection="override_docs",
        embedding_model="qwen3:0.6b",
        embedding_provider="ollama",
        embedding_endpoint="http://10.10.10.10:11434",
        log_dir="/tmp/logs",
        log_level="DEBUG",
        recreate_collection=True,
        batch_size=32,
    )

    assert resolved.input_jsonl == "/tmp/parsed.jsonl"
    assert resolved.index_state_file == "/tmp/indexing_state.json"
    assert resolved.qdrant_url == "http://10.10.10.10:6333"
    assert resolved.qdrant_api_key == "override-key"
    assert resolved.qdrant_collection == "override_docs"
    assert resolved.embedding_model == "qwen3:0.6b"
    assert resolved.embedding_provider == "ollama"
    assert resolved.embedding_endpoint == "http://10.10.10.10:11434"
    assert resolved.log_dir == "/tmp/logs"
    assert resolved.log_level == "DEBUG"
    assert resolved.recreate_collection is True
    assert resolved.batch_size == 32
