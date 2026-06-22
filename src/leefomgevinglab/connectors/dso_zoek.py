"""DSO ZoekInterface: vrije-tekst zoeken naar werkzaamheden (resolver-bron).

POST /werkzaamheden/_zoek met body {"zoekterm": "<vrije tekst>"} (leeg = alle).
Geeft HAL-respons _embedded.werkzaamheden[] gerankt op relevantie.
"""
from .base import BaseConnector, ConnectorError


class ZoekConnector(BaseConnector):
    def __init__(self, base_url: str, api_key: str | None,
                 api_key_header: str = "x-api-key", **kwargs):
        super().__init__(**kwargs)
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.api_key_header = api_key_header

    def zoek_werkzaamheden(self, tekst: str, max_n: int = 5) -> list[dict]:
        if not self.api_key:
            raise ConnectorError("Geen DSO_API_KEY geconfigureerd")
        url = f"{self.base_url}/werkzaamheden/_zoek"
        headers = {self.api_key_header: self.api_key}
        data = self.post_json(url, json_body={"zoekterm": tekst}, headers=headers)
        items = (data.get("_embedded") or {}).get("werkzaamheden") or []
        out = []
        for w in items[:max_n]:
            out.append({
                "urn": w.get("urn"),
                "omschrijving": w.get("omschrijving"),
                "functioneleStructuurRef": w.get("functioneleStructuurRef"),
                "trefwoorden": w.get("trefwoorden") or [],
            })
        return out
