from __future__ import annotations

"""Index parsed corpus artifacts into Qdrant using LlamaIndex."""

from dataclasses import dataclass
import hashlib
import json
import logging
from pathlib import Path
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request
import uuid
import warnings

from llama_index.core.base.embeddings.base import BaseEmbedding
from pydantic import PrivateAttr

from .state import IndexingStateStore

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class IndexingStats:
    """Counters describing one indexing run."""

    loaded_documents: int
    indexed_nodes: int
    skipped_nodes: int
    deleted_nodes: int


class LlamaIndexIndexer:
    """Build LlamaIndex nodes from parsed JSONL and upsert them into Qdrant."""

    def __init__(
        self,
        *,
        qdrant_url: str,
        qdrant_collection: str,
        embedding_model: str,
        qdrant_api_key: str | None = None,
        qdrant_vector_size: int = 1024,
        qdrant_distance: str = "Cosine",
        embedding_provider: str = "tei",
        embedding_endpoint: str | None = None,
        recreate_collection: bool = False,
        batch_size: int = 128,
    ) -> None:
        """Initialize indexing dependencies and runtime parameters."""
        self.qdrant_url = qdrant_url
        self.qdrant_collection = qdrant_collection
        self.qdrant_api_key = qdrant_api_key
        self.qdrant_vector_size = qdrant_vector_size
        self.qdrant_distance = qdrant_distance
        self.embedding_model = embedding_model
        self.embedding_provider = embedding_provider
        self.embedding_endpoint = embedding_endpoint
        self.recreate_collection = recreate_collection
        self.batch_size = max(1, batch_size)

    def index_from_jsonl(self, input_jsonl: str | Path, state_file: str | Path | None = None) -> IndexingStats:
        """Load parsed JSONL, build LlamaIndex nodes, and upsert into Qdrant."""
        records = self._load_parsed_jsonl(input_jsonl)
        state_store = IndexingStateStore(state_file) if state_file else None
        nodes, skipped_nodes, doc_snapshots, stale_point_ids = self._build_nodes(records, state_store=state_store)
        if not nodes:
            deleted_nodes = self._delete_points(stale_point_ids) if stale_point_ids else 0
            if state_store:
                for doc_id, chunks in doc_snapshots.items():
                    state_store.set_doc_chunks(doc_id, chunks)
                state_store.save()
            return IndexingStats(
                loaded_documents=len(records),
                indexed_nodes=0,
                skipped_nodes=skipped_nodes,
                deleted_nodes=deleted_nodes,
            )

        embed_model = self._build_embed_model()
        vector_store = self._build_vector_store()
        self._ensure_qdrant_collection()

        from llama_index.core import StorageContext, VectorStoreIndex

        storage_context = StorageContext.from_defaults(vector_store=vector_store)
        index = VectorStoreIndex(nodes=[], storage_context=storage_context, embed_model=embed_model)

        for start in range(0, len(nodes), self.batch_size):
            batch = nodes[start : start + self.batch_size]
            index.insert_nodes(batch)

        deleted_nodes = self._delete_points(stale_point_ids) if stale_point_ids else 0
        if state_store:
            for doc_id, chunks in doc_snapshots.items():
                state_store.set_doc_chunks(doc_id, chunks)
            state_store.save()

        return IndexingStats(
            loaded_documents=len(records),
            indexed_nodes=len(nodes),
            skipped_nodes=skipped_nodes,
            deleted_nodes=deleted_nodes,
        )

    @staticmethod
    def _load_parsed_jsonl(input_jsonl: str | Path) -> list[dict[str, Any]]:
        """Load parsed-document JSONL artifact rows into dictionaries."""
        path = Path(input_jsonl)
        if not path.exists():
            raise FileNotFoundError(f"Parsed JSONL not found: {path}")

        records: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, start=1):
                content = line.strip()
                if not content:
                    continue
                try:
                    row = json.loads(content)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid JSONL row at line {line_no} in {path}") from exc
                if not isinstance(row, dict):
                    raise ValueError(f"JSONL row at line {line_no} must be an object.")
                records.append(row)
        return records

    def _build_nodes(
        self,
        records: list[dict[str, Any]],
        *,
        state_store: IndexingStateStore | None,
    ) -> tuple[list[Any], int, dict[str, dict[str, str]], list[str]]:
        """Convert parsed child chunks into LlamaIndex TextNode objects with incremental diffing."""
        from llama_index.core.schema import TextNode

        nodes: list[Any] = []
        skipped = 0
        doc_snapshots: dict[str, dict[str, str]] = {}
        stale_point_ids: list[str] = []
        for row in records:
            doc_id = str(row.get("doc_id", ""))
            doc_metadata = row.get("metadata", {})
            if not isinstance(doc_metadata, dict):
                doc_metadata = {}
            child_nodes = row.get("child_nodes", [])
            if not isinstance(child_nodes, list):
                continue
            previous_chunks = state_store.get_doc_chunks(doc_id) if state_store else {}
            current_chunks: dict[str, str] = {}

            for child in child_nodes:
                if not isinstance(child, dict):
                    skipped += 1
                    continue
                text = str(child.get("text", "")).strip()
                if not text:
                    skipped += 1
                    continue
                child_id = str(child.get("child_id", ""))
                child_metadata = child.get("metadata", {})
                if not isinstance(child_metadata, dict):
                    child_metadata = {}

                metadata = {
                    "doc_id": doc_id,
                    "parent_id": child.get("parent_id"),
                    "chunk_type": child.get("chunk_type"),
                    "chunk_level": child.get("chunk_level"),
                    "page_start": child.get("page_start"),
                    "page_end": child.get("page_end"),
                    "section_path": child.get("section_path"),
                    "relative_path": doc_metadata.get("relative_path"),
                    "title": doc_metadata.get("title"),
                    "topic": doc_metadata.get("topic"),
                    **child_metadata,
                }
                raw_id = child_id or self._fallback_child_id(doc_id, metadata, text)
                point_id = self._to_valid_point_id(raw_id)
                content_hash = self._content_hash(text=text, metadata=metadata)
                current_chunks[point_id] = content_hash
                if previous_chunks.get(point_id) == content_hash:
                    skipped += 1
                    continue
                node_kwargs: dict[str, Any] = {"text": text, "metadata": metadata, "id_": point_id}
                nodes.append(TextNode(**node_kwargs))
            if state_store:
                stale_point_ids.extend(sorted(set(previous_chunks.keys()) - set(current_chunks.keys())))
            doc_snapshots[doc_id] = current_chunks
        return nodes, skipped, doc_snapshots, stale_point_ids

    def _build_embed_model(self) -> Any:
        """Build embedding model adapter for LlamaIndex."""
        provider = self.embedding_provider.lower()

        if provider == "ollama":
            try:
                from llama_index.embeddings.ollama import OllamaEmbedding
            except ImportError as exc:
                raise ImportError(
                    "Ollama embeddings provider requested but `llama-index-embeddings-ollama` is not installed."
                ) from exc
            if not self.embedding_endpoint:
                raise ValueError("`embedding_endpoint` is required when `embedding_provider` is `ollama`.")
            return OllamaEmbedding(
                model_name=self.embedding_model,
                base_url=self.embedding_endpoint,
            )

        if provider in {"tei", "http", "remote", "openai_compatible"}:
            if not self.embedding_endpoint:
                raise ValueError("`embedding_endpoint` is required for remote embedding providers.")
            return RemoteHTTPEmbedding(
                model_name=self.embedding_model,
                endpoint=self.embedding_endpoint,
            )

        raise ValueError(
            f"Unsupported embedding provider: {self.embedding_provider}. Supported values: `tei`, `ollama`."
        )

    def _build_vector_store(self) -> Any:
        """Build Qdrant vector store adapter."""
        from llama_index.vector_stores.qdrant import QdrantVectorStore

        client = self._build_qdrant_client()
        return QdrantVectorStore(client=client, collection_name=self.qdrant_collection)

    def _ensure_qdrant_collection(self) -> None:
        """Create or recreate Qdrant collection with configured vector parameters."""
        from qdrant_client.http.models import Distance, VectorParams

        client = self._build_qdrant_client()
        distance = self._distance_enum(self.qdrant_distance, Distance)
        vectors_config = VectorParams(size=self.qdrant_vector_size, distance=distance)

        if self.recreate_collection:
            LOGGER.warning("Recreating Qdrant collection: %s", self.qdrant_collection)
            client.recreate_collection(collection_name=self.qdrant_collection, vectors_config=vectors_config)
            return

        exists = self._collection_exists(client, self.qdrant_collection)
        if not exists:
            client.create_collection(collection_name=self.qdrant_collection, vectors_config=vectors_config)

    @staticmethod
    def _collection_exists(client: Any, collection_name: str) -> bool:
        """Check collection existence with compatibility across qdrant-client versions."""
        if hasattr(client, "collection_exists"):
            return bool(client.collection_exists(collection_name=collection_name))
        try:
            client.get_collection(collection_name=collection_name)
            return True
        except Exception:
            return False

    @staticmethod
    def _distance_enum(distance_name: str, distance_enum_cls: Any) -> Any:
        """Map config distance string into Qdrant Distance enum."""
        normalized = distance_name.strip().lower()
        mapping = {
            "cosine": distance_enum_cls.COSINE,
            "dot": distance_enum_cls.DOT,
            "euclid": distance_enum_cls.EUCLID,
            "manhattan": distance_enum_cls.MANHATTAN,
        }
        if normalized not in mapping:
            raise ValueError(f"Unsupported Qdrant distance: {distance_name}")
        return mapping[normalized]

    def _build_qdrant_client(self) -> Any:
        """Create Qdrant client while suppressing insecure-api-key warning on HTTP URLs."""
        from qdrant_client import QdrantClient

        api_key = self.qdrant_api_key
        if api_key in {None, "", "REPLACE_ME", "<set-in-local-config>"}:
            api_key = None

        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message=r"Api key is used with an insecure connection.*",
                category=UserWarning,
            )
            return QdrantClient(url=self.qdrant_url, api_key=api_key)

    def _delete_points(self, point_ids: list[str]) -> int:
        """Delete stale point ids from Qdrant collection."""
        if not point_ids:
            return 0
        from qdrant_client.http.models import PointIdsList

        client = self._build_qdrant_client()
        client.delete(
            collection_name=self.qdrant_collection,
            points_selector=PointIdsList(points=point_ids),
            wait=True,
        )
        return len(point_ids)

    @staticmethod
    def _to_valid_point_id(raw_id: str) -> str:
        """Convert arbitrary stable id into a Qdrant-valid UUID string."""
        try:
            return str(uuid.UUID(raw_id))
        except ValueError:
            # Deterministic conversion to keep idempotent upserts stable across runs.
            return str(uuid.uuid5(uuid.NAMESPACE_URL, raw_id))

    @staticmethod
    def _fallback_child_id(doc_id: str, metadata: dict[str, Any], text: str) -> str:
        """Build stable fallback id when child_id is missing."""
        base = json.dumps(
            {
                "doc_id": doc_id,
                "section_path": metadata.get("section_path"),
                "chunk_type": metadata.get("chunk_type"),
                "page_start": metadata.get("page_start"),
                "page_end": metadata.get("page_end"),
                "text": text,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        return hashlib.sha1(base.encode("utf-8")).hexdigest()

    @staticmethod
    def _content_hash(text: str, metadata: dict[str, Any]) -> str:
        """Build stable content hash for incremental skip detection."""
        payload = {
            "text": text,
            "metadata": metadata,
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class RemoteHTTPEmbedding(BaseEmbedding):
    """Embedding adapter for TEI/OpenAI-compatible HTTP embedding endpoints."""

    _endpoint: str = PrivateAttr()
    _timeout_seconds: float = PrivateAttr()

    def __init__(self, *, model_name: str, endpoint: str, timeout_seconds: float = 30.0) -> None:
        super().__init__(model_name=model_name)
        self._endpoint = endpoint.rstrip("/")
        self._timeout_seconds = timeout_seconds

    def _get_query_embedding(self, query: str) -> list[float]:
        return self._embed(query)

    def _get_text_embedding(self, text: str) -> list[float]:
        return self._embed(text)

    async def _aget_query_embedding(self, query: str) -> list[float]:
        return self._embed(query)

    def _embed(self, text: str) -> list[float]:
        attempts = (
            ("/embed", {"inputs": text}),
            ("/embed", {"inputs": [text]}),
            ("/v1/embeddings", {"input": text, "model": self.model_name}),
            ("/embeddings", {"input": text, "model": self.model_name}),
        )
        last_error: Exception | None = None
        for path, payload in attempts:
            try:
                response = self._post_json(path=path, payload=payload)
                vector = self._extract_embedding(response)
                if vector:
                    return vector
            except Exception as exc:
                last_error = exc
                continue
        raise RuntimeError(
            f"Failed to embed text via endpoint={self._endpoint}. "
            f"Tried /embed and /v1/embeddings-style payloads."
        ) from last_error

    def _post_json(self, path: str, payload: dict[str, Any]) -> Any:
        url = self._endpoint + path
        body = json.dumps(payload).encode("utf-8")
        request = urllib_request.Request(
            url=url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib_request.urlopen(request, timeout=self._timeout_seconds) as response:
                content = response.read().decode("utf-8")
        except urllib_error.HTTPError as exc:
            message = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Embedding HTTP {exc.code} from {url}: {message[:500]}") from exc
        except urllib_error.URLError as exc:
            raise RuntimeError(f"Embedding endpoint unreachable: {url}") from exc
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Embedding endpoint returned non-JSON response from {url}") from exc

    @staticmethod
    def _extract_embedding(payload: Any) -> list[float]:
        # OpenAI-compatible: {"data":[{"embedding":[...]}]}
        if isinstance(payload, dict):
            if "data" in payload and isinstance(payload["data"], list) and payload["data"]:
                first = payload["data"][0]
                if isinstance(first, dict) and isinstance(first.get("embedding"), list):
                    return [float(x) for x in first["embedding"]]
            if isinstance(payload.get("embedding"), list):
                return [float(x) for x in payload["embedding"]]
            if "embeddings" in payload and isinstance(payload["embeddings"], list) and payload["embeddings"]:
                first = payload["embeddings"][0]
                if isinstance(first, list):
                    return [float(x) for x in first]

        # TEI can return [..] or [[..]]
        if isinstance(payload, list) and payload:
            if isinstance(payload[0], (int, float)):
                return [float(x) for x in payload]
            if isinstance(payload[0], list):
                return [float(x) for x in payload[0]]

        raise ValueError("Embedding payload shape not recognized.")
