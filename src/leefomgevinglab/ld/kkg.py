"""Connector naar de Kadaster Knowledge Graph (KKG) via SPARQL."""
import httpx

from leefomgevinglab.connectors.base import ConnectorError


def sparql(query: str, endpoint: str, timeout_s: float = 30.0) -> list[dict]:
    try:
        resp = httpx.post(
            endpoint,
            data={"query": query},
            headers={"Accept": "application/sparql-results+json"},
            timeout=timeout_s,
        )
        resp.raise_for_status()
        bindings = resp.json()["results"]["bindings"]
    except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
        raise ConnectorError("KKG SPARQL niet beschikbaar") from exc
    return [{k: v.get("value") for k, v in row.items()} for row in bindings]
