#!/usr/bin/env python3
from __future__ import annotations

import argparse

from src.ingestion.parsing import CorpusParser


def build_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Parse local corpus for LlamaIndex ingestion.")
    parser.add_argument(
        "--source-dir",
        default="/volume1/RAG/crypto",
        help="Path to source documents directory.",
    )
    parser.add_argument(
        "--output-jsonl",
        default="data/parsed/parsed_documents.jsonl",
        help="Path to write parsed documents as JSONL.",
    )
    parser.add_argument(
        "--min-characters",
        type=int,
        default=40,
        help="Drop documents shorter than this limit.",
    )
    return parser.parse_args()


def main() -> None:
    args = build_args()
    parser = CorpusParser(source_dir=args.source_dir, min_characters=args.min_characters)
    parsed_docs = parser.parse()
    parser.export_jsonl(parsed_docs, args.output_jsonl)
    print(f"Parsed {len(parsed_docs)} documents from {args.source_dir}")
    print(f"Saved JSONL to {args.output_jsonl}")


if __name__ == "__main__":
    main()

