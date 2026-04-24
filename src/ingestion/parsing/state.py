from __future__ import annotations

"""Local ingestion state tracking for idempotent parsing runs."""

import json
from datetime import datetime, timezone
from pathlib import Path


class IngestionStateStore:
    """Persist and query per-file ingestion fingerprints."""

    VERSION = 1

    def __init__(self, state_file: str | Path) -> None:
        """Initialize state store and load existing state payload if available."""
        self.state_file = Path(state_file)
        self.payload = self._load()

    def should_ingest(self, relative_path: str, fingerprint: str) -> bool:
        """Return true when file should be ingested based on stored fingerprint."""
        existing = self.payload["files"].get(relative_path)
        if not existing:
            return True
        return existing.get("fingerprint") != fingerprint

    def record_ingested(
        self,
        relative_path: str,
        fingerprint: str,
        doc_id: str,
        char_count: int,
    ) -> None:
        """Record successful ingestion metadata for a file."""
        self.payload["files"][relative_path] = {
            "fingerprint": fingerprint,
            "doc_id": doc_id,
            "char_count": char_count,
            "last_ingested_at_utc": self._now_utc(),
        }

    def remove_missing(self, seen_relative_paths: set[str]) -> int:
        """Remove state entries for files that are no longer present."""
        tracked = set(self.payload["files"].keys())
        missing = tracked - seen_relative_paths
        for rel_path in missing:
            del self.payload["files"][rel_path]
        return len(missing)

    def save(self) -> None:
        """Persist current state payload to disk."""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.payload["updated_at_utc"] = self._now_utc()
        self.state_file.write_text(
            json.dumps(self.payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _load(self) -> dict:
        """Load state payload from disk, falling back to defaults on corruption."""
        if not self.state_file.exists():
            return self._default_payload()

        try:
            raw = json.loads(self.state_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return self._default_payload()

        files = raw.get("files")
        if not isinstance(files, dict):
            return self._default_payload()

        return {
            "version": self.VERSION,
            "updated_at_utc": raw.get("updated_at_utc"),
            "files": files,
        }

    @classmethod
    def _default_payload(cls) -> dict:
        """Return initial empty state payload."""
        return {
            "version": cls.VERSION,
            "updated_at_utc": None,
            "files": {},
        }

    @staticmethod
    def _now_utc() -> str:
        """Return current UTC timestamp in ISO-8601 format."""
        return datetime.now(timezone.utc).isoformat()
