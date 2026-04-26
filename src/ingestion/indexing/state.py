"""State tracking for incremental vector indexing."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


class IndexingStateStore:
    """Persist and query per-document indexed chunk hashes."""

    VERSION = 1

    def __init__(self, state_file: str | Path) -> None:
        """Initialize state store and load existing payload."""
        self.state_file = Path(state_file)
        self.payload = self._load()

    def get_doc_chunks(self, doc_id: str) -> dict[str, str]:
        """Return mapping of point_id -> content_hash for one doc."""
        docs = self.payload.get("docs", {})
        doc_entry = docs.get(doc_id, {})
        chunks = doc_entry.get("chunks", {})
        if isinstance(chunks, dict):
            return {str(key): str(value) for key, value in chunks.items()}
        return {}

    def set_doc_chunks(self, doc_id: str, chunks: dict[str, str]) -> None:
        """Replace stored chunk map for one doc."""
        self.payload.setdefault("docs", {})
        self.payload["docs"][doc_id] = {
            "chunks": dict(chunks),
            "updated_at_utc": self._now_utc(),
        }

    def save(self) -> None:
        """Persist current state payload to disk."""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.payload["updated_at_utc"] = self._now_utc()
        self.state_file.write_text(
            json.dumps(self.payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _load(self) -> dict:
        """Load state payload from disk, falling back to defaults on corruption."""
        if not self.state_file.exists():
            return self._default_payload()
        try:
            raw = json.loads(self.state_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return self._default_payload()

        docs = raw.get("docs")
        if not isinstance(docs, dict):
            return self._default_payload()
        return {
            "version": self.VERSION,
            "updated_at_utc": raw.get("updated_at_utc"),
            "docs": docs,
        }

    @classmethod
    def _default_payload(cls) -> dict:
        """Return initial empty state payload."""
        return {
            "version": cls.VERSION,
            "updated_at_utc": None,
            "docs": {},
        }

    @staticmethod
    def _now_utc() -> str:
        """Return current UTC timestamp in ISO-8601 format."""
        return datetime.now(timezone.utc).isoformat()
