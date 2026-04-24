from __future__ import annotations

"""Runtime configuration loading for ingestion CLI flows."""

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
        preview_characters if preview_characters is not None else int(parsing_cfg.get("preview_characters", 240))
    )
    resolved_min_characters = (
        min_characters if min_characters is not None else int(parsing_cfg.get("min_characters", 40))
    )
    resolved_max_files = max_files if max_files is not None else _optional_int(parsing_cfg.get("max_files"))
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


def _required_str(mapping: dict[str, Any], key: str) -> str:
    """Return required string value from mapping or raise configuration error."""
    value = mapping.get(key)
    if not value or not isinstance(value, str):
        raise ValueError(f"Missing required config key: paths.{key}")
    return value


def _optional_int(value: Any) -> int | None:
    """Return integer representation or `None` when value is not provided."""
    if value is None:
        return None
    return int(value)
