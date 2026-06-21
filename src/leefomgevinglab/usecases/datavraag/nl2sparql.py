"""NL-vraag -> SPARQL via Qwen, met een veilige fallback-query."""
import re

import httpx
from rdflib.plugins.sparql import prepareQuery

from leefomgevinglab.connectors.base import ConnectorError

FALLBACK_SPARQL = (
    "PREFIX ll: <https://leefomgevinglab.local/rev/> "
    "SELECT (COUNT(?s) AS ?n) WHERE { ?s a ll:REVProductiefaciliteit }"
)


def is_geldige_sparql(query: str) -> bool:
    try:
        prepareQuery(query)
        return True
    except Exception:
        return False


def _strip_codeblok(tekst: str) -> str:
    m = re.search(r"```(?:sparql)?\s*(.+?)```", tekst, re.DOTALL | re.IGNORECASE)
    return (m.group(1) if m else tekst).strip()


def genereer_sparql(vraag: str, grounding: str, llm_base_url: str, model: str, timeout_s: float = 60.0) -> str:
    prompt = (
        "Schrijf één SPARQL-query (alleen de query, geen uitleg) die de vraag beantwoordt, "
        "uitsluitend met de gegeven prefixes/klassen.\n\n"
        f"{grounding}\n\nVraag: {vraag}"
    )
    try:
        resp = httpx.post(
            f"{llm_base_url.rstrip('/')}/chat/completions",
            json={"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.1},
            timeout=timeout_s,
        )
        resp.raise_for_status()
        return _strip_codeblok(resp.json()["choices"][0]["message"]["content"])
    except (httpx.HTTPError, KeyError, ValueError, IndexError) as exc:
        raise ConnectorError("LLM niet beschikbaar voor SPARQL-generatie") from exc


def kies_sparql(vraag: str, grounding: str, llm_base_url: str, model: str, timeout_s: float = 60.0) -> tuple[str, str]:
    try:
        q = genereer_sparql(vraag, grounding, llm_base_url, model, timeout_s)
        if is_geldige_sparql(q):
            return q, "llm"
    except ConnectorError:
        pass
    return FALLBACK_SPARQL, "fallback"
