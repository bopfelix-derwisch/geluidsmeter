"""Embedding-client voor de RAG-pijplijn via llama.cpp /v1/embeddings."""
import httpx

from leefomgevinglab.connectors.base import ConnectorError


def embed_texts(texts: list[str], base_url: str, model: str, timeout_s: float = 60.0) -> list[list[float]]:
    try:
        resp = httpx.post(
            f"{base_url.rstrip('/')}/embeddings",
            json={"model": model, "input": texts},
            timeout=timeout_s,
        )
        resp.raise_for_status()
        data = resp.json()["data"]
        return [row["embedding"] for row in data]
    except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
        raise ConnectorError("Embedding-service niet beschikbaar") from exc
