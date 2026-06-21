"""Ingest van open linked-data bronnen (IMX-Geo TTL, IMEV vocab-JSON) voor de semantische graaf."""
import json

import httpx

from leefomgevinglab.connectors.base import ConnectorError


def fetch_ttl(url: str, timeout_s: float = 25.0) -> str:
    try:
        resp = httpx.get(url, timeout=timeout_s, follow_redirects=True)
        resp.raise_for_status()
        return resp.text
    except httpx.HTTPError as exc:
        raise ConnectorError(f"TTL niet beschikbaar: {url}") from exc


def fetch_all(urls: list[str], timeout_s: float = 25.0) -> list[str]:
    texts: list[str] = []
    for url in urls:
        try:
            texts.append(fetch_ttl(url, timeout_s))
        except ConnectorError:
            continue
    return texts


def fetch_all_json(urls: list[str], timeout_s: float = 25.0) -> list:
    """Haal vocab-JSON-bronnen op en parse ze; sla mislukte/onleesbare over."""
    docs: list = []
    for url in urls:
        try:
            docs.append(json.loads(fetch_ttl(url, timeout_s)))
        except (ConnectorError, ValueError):
            continue
    return docs
