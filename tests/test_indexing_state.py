"""Tests for incremental indexing state persistence."""

from __future__ import annotations

from pathlib import Path

from src.ingestion.indexing.state import IndexingStateStore


def test_indexing_state_roundtrip_chunks(tmp_path: Path) -> None:
    """State store should persist and load per-doc chunk hash maps."""
    state_path = tmp_path / "state" / "indexing_state.json"
    store = IndexingStateStore(state_path)
    assert store.get_doc_chunks("doc-1") == {}

    store.set_doc_chunks(
        "doc-1",
        {
            "point-1": "hash-a",
            "point-2": "hash-b",
        },
    )
    store.save()

    reloaded = IndexingStateStore(state_path)
    assert reloaded.get_doc_chunks("doc-1") == {
        "point-1": "hash-a",
        "point-2": "hash-b",
    }
