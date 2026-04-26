"""Runtime configuration loading for ingestion CLI flows."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class ParseRuntimeConfig:
    """Resolved runtime settings for the parsing CLI execution."""

    source_dir: str
    output_jsonl: str
    output_manifest: str
    state_file: str
    log_dir: str
    log_level: str
    preview_characters: int
    min_characters: int
    max_files: int | None
    skip_unchanged: bool
    child_chunk_size: int
    child_chunk_overlap: int


@dataclass(frozen=True)
class IndexRuntimeConfig:
    """Resolved runtime settings for the indexing CLI execution."""

    input_jsonl: str
    index_state_file: str
    qdrant_url: str
    qdrant_api_key: str | None
    qdrant_collection: str
    qdrant_vector_size: int
    qdrant_distance: str
    embedding_model: str
    embedding_provider: str
    embedding_endpoint: str | None
    log_dir: str
    log_level: str
    recreate_collection: bool
    batch_size: int


def load_yaml_config(path: str | Path) -> dict[str, Any]:
    """Load YAML config file and validate top-level mapping shape."""
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    with config_path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Config must be a mapping at top-level: {config_path}")
    return payload


def resolve_parse_runtime_config(
    config: dict[str, Any],
    *,
    source_dir: str | None = None,
    output_jsonl: str | None = None,
    output_manifest: str | None = None,
    state_file: str | None = None,
    log_dir: str | None = None,
    log_level: str | None = None,
    preview_characters: int | None = None,
    min_characters: int | None = None,
    max_files: int | None = None,
    no_skip_unchanged: bool = False,
) -> ParseRuntimeConfig:
    """Resolve parse runtime configuration from file config and CLI overrides."""
    paths_cfg = config.get("paths", {})
    parsing_cfg = config.get("parsing", {})
    chunking_cfg = config.get("chunking", {})
    if not isinstance(paths_cfg, dict):
        raise ValueError("`paths` must be a mapping in config.")
    if not isinstance(parsing_cfg, dict):
        raise ValueError("`parsing` must be a mapping in config.")
    if not isinstance(chunking_cfg, dict):
        raise ValueError("`chunking` must be a mapping in config.")

    resolved_source_dir = source_dir or _required_str(paths_cfg, "source_dir")
    resolved_output_jsonl = output_jsonl or _required_str(paths_cfg, "output_jsonl")
    resolved_output_manifest = output_manifest or _required_str(paths_cfg, "output_manifest")
    resolved_state_file = state_file or _required_str(paths_cfg, "state_file")
    resolved_log_dir = log_dir or _required_str(paths_cfg, "log_dir")

    resolved_log_level = log_level or str(parsing_cfg.get("log_level", "INFO"))
    resolved_preview_characters = (
        preview_characters
        if preview_characters is not None
        else int(parsing_cfg.get("preview_characters", 240))
    )
    resolved_min_characters = (
        min_characters if min_characters is not None else int(parsing_cfg.get("min_characters", 40))
    )
    resolved_max_files = (
        max_files if max_files is not None else _optional_int(parsing_cfg.get("max_files"))
    )
    default_skip_unchanged = bool(parsing_cfg.get("skip_unchanged", True))
    resolved_skip_unchanged = False if no_skip_unchanged else default_skip_unchanged
    resolved_child_chunk_size = int(chunking_cfg.get("chunk_size", 800))
    resolved_child_chunk_overlap = int(chunking_cfg.get("chunk_overlap", 120))

    return ParseRuntimeConfig(
        source_dir=resolved_source_dir,
        output_jsonl=resolved_output_jsonl,
        output_manifest=resolved_output_manifest,
        state_file=resolved_state_file,
        log_dir=resolved_log_dir,
        log_level=resolved_log_level,
        preview_characters=resolved_preview_characters,
        min_characters=resolved_min_characters,
        max_files=resolved_max_files,
        skip_unchanged=resolved_skip_unchanged,
        child_chunk_size=resolved_child_chunk_size,
        child_chunk_overlap=resolved_child_chunk_overlap,
    )


def resolve_index_runtime_config(
    config: dict[str, Any],
    *,
    input_jsonl: str | None = None,
    index_state_file: str | None = None,
    qdrant_url: str | None = None,
    qdrant_api_key: str | None = None,
    qdrant_collection: str | None = None,
    embedding_model: str | None = None,
    embedding_provider: str | None = None,
    embedding_endpoint: str | None = None,
    log_dir: str | None = None,
    log_level: str | None = None,
    recreate_collection: bool = False,
    batch_size: int | None = None,
) -> IndexRuntimeConfig:
    """Resolve indexing runtime configuration from file config and CLI overrides."""
    paths_cfg = config.get("paths", {})
    parsing_cfg = config.get("parsing", {})
    qdrant_cfg = config.get("qdrant", {})
    embeddings_cfg = config.get("embeddings", {})
    if not isinstance(paths_cfg, dict):
        raise ValueError("`paths` must be a mapping in config.")
    if not isinstance(parsing_cfg, dict):
        raise ValueError("`parsing` must be a mapping in config.")
    if not isinstance(qdrant_cfg, dict):
        raise ValueError("`qdrant` must be a mapping in config.")
    if not isinstance(embeddings_cfg, dict):
        raise ValueError("`embeddings` must be a mapping in config.")

    resolved_input_jsonl = input_jsonl or _required_str(paths_cfg, "output_jsonl")
    resolved_index_state_file = index_state_file or str(
        paths_cfg.get("index_state_file", "data/state/indexing_state.json")
    )
    resolved_qdrant_url = qdrant_url or _required_str(qdrant_cfg, "url", section="qdrant")
    resolved_qdrant_api_key = (
        qdrant_api_key if qdrant_api_key is not None else _optional_str(qdrant_cfg.get("api_key"))
    )
    resolved_qdrant_collection = qdrant_collection or _required_str(
        qdrant_cfg,
        "collection",
        section="qdrant",
    )
    resolved_qdrant_vector_size = int(qdrant_cfg.get("vector_size", 1024))
    resolved_qdrant_distance = str(qdrant_cfg.get("distance", "Cosine"))
    resolved_embedding_model = embedding_model or _required_str(
        embeddings_cfg,
        "model",
        section="embeddings",
    )
    resolved_embedding_provider = embedding_provider or str(embeddings_cfg.get("provider", "tei"))
    resolved_embedding_endpoint = (
        embedding_endpoint
        if embedding_endpoint is not None
        else _optional_str(embeddings_cfg.get("endpoint"))
    )
    resolved_log_dir = log_dir or _required_str(paths_cfg, "log_dir")
    resolved_log_level = log_level or str(parsing_cfg.get("log_level", "INFO"))
    resolved_batch_size = (
        batch_size
        if batch_size is not None
        else int(config.get("indexing", {}).get("batch_size", 128))
    )

    return IndexRuntimeConfig(
        input_jsonl=resolved_input_jsonl,
        index_state_file=resolved_index_state_file,
        qdrant_url=resolved_qdrant_url,
        qdrant_api_key=resolved_qdrant_api_key,
        qdrant_collection=resolved_qdrant_collection,
        qdrant_vector_size=resolved_qdrant_vector_size,
        qdrant_distance=resolved_qdrant_distance,
        embedding_model=resolved_embedding_model,
        embedding_provider=resolved_embedding_provider,
        embedding_endpoint=resolved_embedding_endpoint,
        log_dir=resolved_log_dir,
        log_level=resolved_log_level,
        recreate_collection=recreate_collection,
        batch_size=resolved_batch_size,
    )


def _required_str(mapping: dict[str, Any], key: str, *, section: str = "paths") -> str:
    """Return required string value from mapping or raise configuration error."""
    value = mapping.get(key)
    if not value or not isinstance(value, str):
        raise ValueError(f"Missing required config key: {section}.{key}")
    return value


def _optional_int(value: Any) -> int | None:
    """Return integer representation or `None` when value is not provided."""
    if value is None:
        return None
    return int(value)


def _optional_str(value: Any) -> str | None:
    """Return string when non-empty string is provided, otherwise `None`."""
    if value is None:
        return None
    if isinstance(value, str) and value.strip():
        return value
    return None
