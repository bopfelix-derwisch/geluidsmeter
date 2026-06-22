"""DSO Toepasbare Regels via het echte POST-protocol (pre-productie).

Twee services:
- Samengestelde RTR v2: _bepaalRegelbeheerobjectTyperingen (welke regelbeheerobjecten gelden).
- Uitvoeren v3: indieningsvereisten/_bepaal (best-effort diepere inhoud; Content-Crs EPSG:28992).

Geometrie in RD/EPSG:28992 als GeoJSON Point [x, y]. Refs zijn werkzaamheid-concept-URI's.
Live geverifieerd 2026-06-22; zie docs/superpowers/specs/2026-06-22-dso-regels-resolver-design.md.
"""
from .base import BaseConnector, ConnectorError


def _geo_point(geo_rd: tuple[float, float]) -> dict:
    return {"intersects": {"type": "Point", "coordinates": [geo_rd[0], geo_rd[1]]}}


class DsoConnector(BaseConnector):
    def __init__(self, rtr_base_url: str, uitvoeren_base_url: str, api_key: str | None,
                 api_key_header: str = "x-api-key", **kwargs):
        super().__init__(**kwargs)
        self.rtr_base_url = rtr_base_url.rstrip("/")
        self.uitvoeren_base_url = uitvoeren_base_url.rstrip("/")
        self.api_key = api_key
        self.api_key_header = api_key_header

    def _headers(self, extra: dict | None = None) -> dict:
        h = {self.api_key_header: self.api_key}
        if extra:
            h.update(extra)
        return h

    def bepaal_typeringen(self, refs: list[str], geo_rd: tuple[float, float],
                          datum: str | None = None) -> list[dict]:
        if not self.api_key:
            raise ConnectorError("Geen DSO_API_KEY geconfigureerd")
        url = f"{self.rtr_base_url}/werkzaamheden/_bepaalRegelbeheerobjectTyperingen"
        body = {"functioneleStructuurRefs": list(refs), "_geo": _geo_point(geo_rd)}
        if datum:
            body["datum"] = datum
        return self.post_json(url, json_body=body, headers=self._headers())

    def bepaal_indieningsvereisten(self, refs: list[str], geo_rd: tuple[float, float],
                                   datum: str | None = None) -> list[dict]:
        if not self.api_key:
            raise ConnectorError("Geen DSO_API_KEY geconfigureerd")
        url = f"{self.uitvoeren_base_url}/indieningsvereisten/_bepaal"
        body = {
            "functioneleStructuurRefs": [{"functioneleStructuurRef": r, "antwoorden": []} for r in refs],
            "_geo": _geo_point(geo_rd),
        }
        if datum:
            body["datum"] = datum
        return self.post_json(url, json_body=body, headers=self._headers({"Content-Crs": "EPSG:28992"}))
