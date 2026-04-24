from __future__ import annotations

"""Live availability checks for embedding and LLM endpoints from runtime config."""

import json
from pathlib import Path
from urllib import error as urllib_error
from urllib import request as urllib_request

import yaml


def _load_runtime_service_config() -> tuple[str, str, str, str, str, str | None]:
    """Load embedding/LLM/Qdrant endpoint settings from runtime config."""
    config_path = Path("config/config.yaml")
    if not config_path.exists():
        raise AssertionError(f"Required runtime config not found: {config_path}")

    payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise AssertionError("config/config.yaml must contain a top-level mapping.")

    embeddings = payload.get("embeddings", {})
    llm = payload.get("llm", {})
    qdrant = payload.get("qdrant", {})
    if not isinstance(embeddings, dict):
        raise AssertionError("`embeddings` must be a mapping in config/config.yaml.")
    if not isinstance(llm, dict):
        raise AssertionError("`llm` must be a mapping in config/config.yaml.")
    if not isinstance(qdrant, dict):
        raise AssertionError("`qdrant` must be a mapping in config/config.yaml.")

    embedding_endpoint = str(embeddings.get("endpoint", "")).strip()
    embedding_model = str(embeddings.get("model", "")).strip()
    llm_endpoint = str(llm.get("endpoint", "")).strip()
    llm_model = str(llm.get("model", "")).strip()
    qdrant_url = str(qdrant.get("url", "")).strip()
    qdrant_api_key = str(qdrant.get("api_key", "")).strip() or None

    if not embedding_endpoint or not embedding_model:
        raise AssertionError("`embeddings.endpoint` and `embeddings.model` are required in config/config.yaml.")
    if not llm_endpoint or not llm_model:
        raise AssertionError("`llm.endpoint` and `llm.model` are required in config/config.yaml.")
    if not qdrant_url:
        raise AssertionError("`qdrant.url` is required in config/config.yaml.")

    return (
        embedding_endpoint.rstrip("/"),
        embedding_model,
        llm_endpoint.rstrip("/"),
        llm_model,
        qdrant_url.rstrip("/"),
        qdrant_api_key,
    )


def _http_json(
    method: str,
    url: str,
    payload: dict | None = None,
    timeout: float = 20.0,
    headers: dict[str, str] | None = None,
    retries: int = 2,
) -> object:
    """Send JSON HTTP request and parse JSON response."""
    data = None
    request_headers = dict(headers or {})
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    content: str | None = None
    last_error: Exception | None = None
    for _ in range(retries + 1):
        request = urllib_request.Request(url=url, data=data, headers=request_headers, method=method.upper())
        try:
            with urllib_request.urlopen(request, timeout=timeout) as response:
                content = response.read().decode("utf-8")
            break
        except urllib_error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            raise AssertionError(f"HTTP {exc.code} from {url}: {body[:500]}") from exc
        except (urllib_error.URLError, TimeoutError) as exc:
            last_error = exc
            continue
    if content is None:
        raise AssertionError(f"Endpoint unreachable: {url}") from last_error
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise AssertionError(f"Non-JSON response from {url}: {content[:300]}") from exc


def _extract_embedding_vector(payload: object) -> list[float]:
    """Parse common TEI/OpenAI-compatible embedding response shapes."""
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

    if isinstance(payload, list) and payload:
        if isinstance(payload[0], (int, float)):
            return [float(x) for x in payload]
        if isinstance(payload[0], list):
            return [float(x) for x in payload[0]]
    return []


def test_embedding_model_endpoint_available_from_config() -> None:
    """Embedding endpoint from config should return a usable vector."""
    embedding_endpoint, embedding_model, _, _, _, _ = _load_runtime_service_config()

    attempts = (
        (f"{embedding_endpoint}/embed", {"inputs": "health check text"}),
        (f"{embedding_endpoint}/embed", {"inputs": ["health check text"]}),
        (f"{embedding_endpoint}/v1/embeddings", {"input": "health check text", "model": embedding_model}),
        (f"{embedding_endpoint}/embeddings", {"input": "health check text", "model": embedding_model}),
    )

    last_error: AssertionError | None = None
    for url, payload in attempts:
        try:
            response = _http_json("POST", url, payload)
            vector = _extract_embedding_vector(response)
            if vector:
                assert len(vector) > 0
                return
        except AssertionError as exc:
            last_error = exc
            continue

    raise AssertionError(
        "Embedding endpoint did not return a recognized embedding payload. "
        f"endpoint={embedding_endpoint}, model={embedding_model}"
    ) from last_error


def test_llm_model_endpoint_available_from_config() -> None:
    """LLM endpoint from config should expose and run configured model."""
    _, _, llm_endpoint, llm_model, _, _ = _load_runtime_service_config()

    tags = _http_json("GET", f"{llm_endpoint}/api/tags")
    assert isinstance(tags, dict), "Unexpected /api/tags response shape."
    models = tags.get("models", [])
    assert isinstance(models, list), "Unexpected `models` field in /api/tags response."

    available_names: list[str] = []
    for item in models:
        if isinstance(item, dict):
            name = item.get("name")
            if isinstance(name, str):
                available_names.append(name)

    assert any(name == llm_model or name.startswith(f"{llm_model}:") for name in available_names), (
        f"Model `{llm_model}` not found in Ollama tags at {llm_endpoint}. "
        f"Available: {available_names[:20]}"
    )

    generate_response = _http_json(
        "POST",
        f"{llm_endpoint}/api/generate",
        payload={
            "model": llm_model,
            "prompt": "Reply with the single word: ok",
            "stream": False,
        },
        timeout=60.0,
    )
    assert isinstance(generate_response, dict), "Unexpected /api/generate response shape."
    response_text = str(generate_response.get("response", "")).strip().lower()
    assert response_text, "Empty response from Ollama generate."
    assert "ok" in response_text, f"Unexpected response from model `{llm_model}`: {response_text!r}"


def test_qdrant_health_endpoint_available_from_config() -> None:
    """Qdrant endpoint from config should expose a healthy service response."""
    _, _, _, _, qdrant_url, qdrant_api_key = _load_runtime_service_config()
    headers: dict[str, str] = {}
    if qdrant_api_key and qdrant_api_key not in {"REPLACE_ME", "<set-in-local-config>"}:
        headers["api-key"] = qdrant_api_key

    attempts = (
        f"{qdrant_url}/healthz",
        f"{qdrant_url}/readyz",
        f"{qdrant_url}/collections",
    )

    last_error: AssertionError | None = None
    for url in attempts:
        try:
            response = _http_json("GET", url, headers=headers)
            if isinstance(response, dict):
                # /healthz and /readyz can return simple status payloads;
                # /collections returns {"result": {...}, "status": "ok"}.
                status = str(response.get("status", "")).lower()
                if status in {"ok", "healthy", "ready"}:
                    return
                if "result" in response:
                    return
                if response.get("title") == "qdrant - vector search engine":
                    return
            # Some deployments may return plain booleans wrapped in JSON.
            if isinstance(response, bool):
                assert response is True
                return
        except AssertionError as exc:
            last_error = exc
            continue

    raise AssertionError(f"Qdrant health check failed for endpoint={qdrant_url}") from last_error
