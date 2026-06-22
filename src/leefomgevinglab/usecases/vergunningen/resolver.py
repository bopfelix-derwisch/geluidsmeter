"""Resolver: vrije tekst -> werkzaamheid (Qwen-keuze) + WGS84 -> RD (EPSG:28992)."""
import json

import httpx
from pyproj import Transformer

# always_xy=True => transform(lon, lat) -> (x, y)
_TRANSFORMER = Transformer.from_crs("EPSG:4326", "EPSG:28992", always_xy=True)


def wgs84_naar_rd(lat: float, lon: float) -> tuple[float, float]:
    x, y = _TRANSFORMER.transform(lon, lat)
    return (round(x, 1), round(y, 1))


def _top_hit(kandidaten: list[dict], onderbouwing: str, zekerheid: str) -> dict:
    return {"gekozen": kandidaten[0], "match_onderbouwing": onderbouwing, "zekerheid_match": zekerheid}


def kies_werkzaamheid(vraag: str, kandidaten: list[dict], llm_base_url: str, model: str,
                      timeout_s: float = 60.0) -> dict:
    if not kandidaten:
        return {"gekozen": None, "match_onderbouwing": "Geen werkzaamheid gevonden",
                "zekerheid_match": "laag"}
    if len(kandidaten) == 1:
        return _top_hit(kandidaten, "Enige kandidaat", "midden")

    opties = "\n".join(
        f"{i}. {k.get('omschrijving')} (trefwoorden: {', '.join(k.get('trefwoorden') or [])})"
        for i, k in enumerate(kandidaten)
    )
    prompt = (
        "Je bent een feitelijke assistent voor de Omgevingswet. Kies welke werkzaamheid het "
        "beste past bij de vraag van de burger. Verzin niets; kies uit de gegeven lijst.\n\n"
        f"Vraag: {vraag}\n\nWerkzaamheden:\n{opties}\n\n"
        'Antwoord UITSLUITEND als JSON: {"index": <nummer>, "onderbouwing": "<kort>", '
        '"zekerheid": "hoog|midden|laag"}'
    )
    try:
        resp = httpx.post(
            f"{llm_base_url.rstrip('/')}/chat/completions",
            json={"model": model, "messages": [{"role": "user", "content": prompt}],
                  "temperature": 0.1},
            timeout=timeout_s,
        )
        if resp.status_code >= 400:
            raise httpx.HTTPStatusError(f"HTTP {resp.status_code}", request=None, response=resp)
        text = resp.json()["choices"][0]["message"]["content"].strip()
        parsed = json.loads(text)
        idx = int(parsed["index"])
        if not 0 <= idx < len(kandidaten):
            raise ValueError("index buiten bereik")
        zekerheid = parsed.get("zekerheid", "midden")
        if zekerheid not in ("hoog", "midden", "laag"):
            zekerheid = "midden"
        return {"gekozen": kandidaten[idx],
                "match_onderbouwing": parsed.get("onderbouwing", ""),
                "zekerheid_match": zekerheid}
    except (httpx.HTTPError, KeyError, ValueError, IndexError, TypeError):
        return _top_hit(kandidaten, "LLM niet beschikbaar; hoogst gerankte gekozen", "laag")
