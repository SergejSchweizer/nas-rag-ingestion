from __future__ import annotations

"""Data models for ingestion parsing."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ParsedDocument:
    """Canonical parsed record used across ingestion stages."""

    doc_id: str
    text: str
    metadata: dict

