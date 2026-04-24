#!/usr/bin/env python3
from __future__ import annotations

"""CLI entrypoint for indexing parsed corpus artifacts into Qdrant via LlamaIndex."""

import argparse
import logging
import os
from pathlib import Path
import sys

# Support running the script directly from the repository root without
# requiring editable installation first.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.ingestion.indexing import LlamaIndexIndexer
from src.ingestion.runtime_config import load_yaml_config, resolve_index_runtime_config
from src.logging_utils import configure_weekly_logging


def build_args() -> argparse.Namespace:
    """Define and parse command line arguments for corpus indexing."""
    parser = argparse.ArgumentParser(description="Index parsed corpus JSONL to Qdrant using LlamaIndex.")
    parser.add_argument(
        "--config",
        default="config/config.yaml",
        help="Path to runtime configuration YAML.",
    )
    parser.add_argument(
        "--input-jsonl",
        default=None,
        help="Optional override for parsed JSONL input path.",
    )
    parser.add_argument(
        "--index-state-file",
        default=None,
        help="Optional override for incremental indexing state file path.",
    )
    parser.add_argument(
        "--qdrant-url",
        default=None,
        help="Optional override for Qdrant URL.",
    )
    parser.add_argument(
        "--qdrant-api-key",
        default=None,
        help="Optional override for Qdrant API key.",
    )
    parser.add_argument(
        "--qdrant-collection",
        default=None,
        help="Optional override for Qdrant collection name.",
    )
    parser.add_argument(
        "--embedding-model",
        default=None,
        help="Optional override for embedding model name.",
    )
    parser.add_argument(
        "--embedding-provider",
        default=None,
        help="Optional override for embedding provider (for example: tei, ollama).",
    )
    parser.add_argument(
        "--embedding-endpoint",
        default=None,
        help="Optional override for embedding provider endpoint.",
    )
    parser.add_argument(
        "--recreate-collection",
        action="store_true",
        help="Recreate target Qdrant collection before indexing.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="Optional upsert batch size.",
    )
    parser.add_argument(
        "--log-dir",
        default=None,
        help="Optional override for weekly rotating log directory path.",
    )
    parser.add_argument(
        "--log-level",
        default=None,
        help="Optional override for log level (for example: DEBUG, INFO, WARNING, ERROR).",
    )
    return parser.parse_args()


def main() -> None:
    """Run indexing flow for parsed JSONL -> LlamaIndex -> Qdrant."""
    args = build_args()
    config = load_yaml_config(args.config)
    runtime = resolve_index_runtime_config(
        config,
        input_jsonl=args.input_jsonl,
        index_state_file=args.index_state_file,
        qdrant_url=args.qdrant_url,
        qdrant_api_key=args.qdrant_api_key,
        qdrant_collection=args.qdrant_collection,
        embedding_model=args.embedding_model,
        embedding_provider=args.embedding_provider,
        embedding_endpoint=args.embedding_endpoint,
        log_dir=args.log_dir,
        log_level=args.log_level,
        recreate_collection=args.recreate_collection,
        batch_size=args.batch_size,
    )

    if runtime.embedding_endpoint:
        # Useful for local Ollama-based embedding backends.
        os.environ.setdefault("OLLAMA_BASE_URL", runtime.embedding_endpoint)

    log_file_path = configure_weekly_logging(log_dir=runtime.log_dir, level=runtime.log_level)
    logger = logging.getLogger(__name__)
    logger.info(
        "Starting indexing. input_jsonl=%s collection=%s embedding_model=%s",
        runtime.input_jsonl,
        runtime.qdrant_collection,
        runtime.embedding_model,
    )
    logger.info("Logging to %s (weekly rotation enabled)", log_file_path)

    indexer = LlamaIndexIndexer(
        qdrant_url=runtime.qdrant_url,
        qdrant_api_key=runtime.qdrant_api_key,
        qdrant_collection=runtime.qdrant_collection,
        qdrant_vector_size=runtime.qdrant_vector_size,
        qdrant_distance=runtime.qdrant_distance,
        embedding_model=runtime.embedding_model,
        embedding_provider=runtime.embedding_provider,
        embedding_endpoint=runtime.embedding_endpoint,
        recreate_collection=runtime.recreate_collection,
        batch_size=runtime.batch_size,
    )
    stats = indexer.index_from_jsonl(runtime.input_jsonl, state_file=runtime.index_state_file)

    print(f"Indexed {stats.indexed_nodes} nodes into collection `{runtime.qdrant_collection}`")
    print(f"Loaded documents: {stats.loaded_documents}")
    print(f"Skipped nodes: {stats.skipped_nodes}")
    print(f"Deleted stale nodes: {stats.deleted_nodes}")
    print(f"Input JSONL: {runtime.input_jsonl}")
    print(f"Index state file: {runtime.index_state_file}")
    logger.info(
        "Completed indexing. loaded_documents=%s indexed_nodes=%s skipped_nodes=%s deleted_nodes=%s",
        stats.loaded_documents,
        stats.indexed_nodes,
        stats.skipped_nodes,
        stats.deleted_nodes,
    )


if __name__ == "__main__":
    main()
