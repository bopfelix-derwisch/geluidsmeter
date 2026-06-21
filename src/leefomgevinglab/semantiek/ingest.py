"""Ingest van open linked-data TTL-bronnen (IMX-Geo) voor de semantische graaf."""
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
