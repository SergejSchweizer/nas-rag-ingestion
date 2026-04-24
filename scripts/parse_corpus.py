#!/usr/bin/env python3
from __future__ import annotations

"""CLI entrypoint for the ingestion parsing stage.

Parses local files into normalized JSONL records that can be consumed by
subsequent chunking and indexing stages.
"""

import argparse
import logging

from src.ingestion.parsing import CorpusParser
from src.ingestion.runtime_config import load_yaml_config, resolve_parse_runtime_config
from src.logging_utils import configure_weekly_logging


def build_args() -> argparse.Namespace:
    """Define and parse command line arguments for corpus parsing."""
    parser = argparse.ArgumentParser(description="Parse local corpus for LlamaIndex ingestion.")
    parser.add_argument(
        "--config",
        default="config/config.yaml",
        help="Path to runtime configuration YAML.",
    )
    parser.add_argument(
        "--source-dir",
        default=None,
        help="Optional override for source directory path.",
    )
    parser.add_argument(
        "--output-jsonl",
        default=None,
        help="Optional override for parsed JSONL output path.",
    )
    parser.add_argument(
        "--output-manifest",
        default=None,
        help="Optional override for tracking manifest output path.",
    )
    parser.add_argument(
        "--preview-characters",
        type=int,
        default=None,
        help="Character length used for manifest text preview.",
    )
    parser.add_argument(
        "--min-characters",
        type=int,
        default=None,
        help="Optional override for minimum document character count.",
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=None,
        help="Optional limit for number of files to parse per run.",
    )
    parser.add_argument(
        "--state-file",
        default=None,
        help="Optional override for local ingestion state path.",
    )
    parser.add_argument(
        "--no-skip-unchanged",
        action="store_true",
        help="Disable skip-unchanged behavior and ingest all discovered files.",
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
    """Run parse flow and emit parsed JSONL artifact."""
    args = build_args()
    config = load_yaml_config(args.config)
    runtime = resolve_parse_runtime_config(
        config,
        source_dir=args.source_dir,
        output_jsonl=args.output_jsonl,
        output_manifest=args.output_manifest,
        state_file=args.state_file,
        log_dir=args.log_dir,
        log_level=args.log_level,
        preview_characters=args.preview_characters,
        min_characters=args.min_characters,
        max_files=args.max_files,
        no_skip_unchanged=args.no_skip_unchanged,
    )

    log_file_path = configure_weekly_logging(log_dir=runtime.log_dir, level=runtime.log_level)
    logger = logging.getLogger(__name__)
    logger.info("Starting corpus parsing. source_dir=%s max_files=%s", runtime.source_dir, runtime.max_files)
    logger.info("Logging to %s (weekly rotation enabled)", log_file_path)

    parser = CorpusParser(
        source_dir=runtime.source_dir,
        min_characters=runtime.min_characters,
        child_chunk_size=runtime.child_chunk_size,
        child_chunk_overlap=runtime.child_chunk_overlap,
    )
    parsed_docs = parser.parse(
        max_files=runtime.max_files,
        state_file=runtime.state_file,
        skip_unchanged=runtime.skip_unchanged,
    )
    parser.export_jsonl(parsed_docs, runtime.output_jsonl)
    parser.export_tracking_manifest(
        parsed_docs,
        runtime.output_manifest,
        preview_characters=runtime.preview_characters,
    )
    print(f"Parsed {len(parsed_docs)} documents from {runtime.source_dir}")
    print(f"Saved JSONL to {runtime.output_jsonl}")
    print(f"Saved tracking manifest to {runtime.output_manifest}")
    print(f"State file: {runtime.state_file}")
    print(
        "Run stats: "
        f"discovered={parser.last_run_stats.discovered_count}, "
        f"parsed={parser.last_run_stats.parsed_count}, "
        f"skipped_unchanged={parser.last_run_stats.skipped_unchanged_count}, "
        f"removed_missing={parser.last_run_stats.removed_missing_count}, "
        f"parse_errors={parser.last_run_stats.parse_error_count}"
    )
    logger.info(
        "Completed parsing. discovered=%s parsed=%s skipped_unchanged=%s removed_missing=%s parse_errors=%s",
        parser.last_run_stats.discovered_count,
        parser.last_run_stats.parsed_count,
        parser.last_run_stats.skipped_unchanged_count,
        parser.last_run_stats.removed_missing_count,
        parser.last_run_stats.parse_error_count,
    )
    if parser.last_run_stats.unparsed_files:
        logger.info("Unparsed file summary: total=%s", len(parser.last_run_stats.unparsed_files))
        for relative_path, reason in parser.last_run_stats.unparsed_files:
            logger.info("UNPARSED_FILE_SUMMARY relative_path=%s reason=%s", relative_path, reason)


if __name__ == "__main__":
    main()
