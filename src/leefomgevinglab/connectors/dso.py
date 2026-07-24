"""DSO Toepasbare Regels via het echte POST-protocol.

Twee services, elk met een eigen omgeving (pre of prod) en dus een eigen API-key:
- Samengestelde RTR v2: _bepaalRegelbeheerobjectTyperingen (welke regelbeheerobjecten gelden).
- Uitvoeren v3: indieningsvereisten/_bepaal (best-effort diepere inhoud; Content-Crs EPSG:28992).

De omgeving per service wordt in de config gekozen (dso.rtr_env / dso.uitvoeren_env);
de bijbehorende key komt uit .env (DSO_API_KEY voor pre, DSO_API_KEY_PROD voor prod).

Geometrie in RD/EPSG:28992 als GeoJSON Point [x, y]. Refs zijn werkzaamheid-concept-URI's.
Zie docs/superpowers/specs/2026-06-22-dso-regels-resolver-design.md.
"""
from .base import BaseConnector, ConnectorError


def _geo_point(geo_rd: tuple[float, float]) -> dict:
    return {"intersects": {"type": "Point", "coordinates": [geo_rd[0], geo_rd[1]]}}


class DsoConnector(BaseConnector):
    def __init__(self, rtr_base_url: str, uitvoeren_base_url: str,
                 rtr_api_key: str | None, uitvoeren_api_key: str | None,
                 api_key_header: str = "x-api-key", **kwargs):
        super().__init__(**kwargs)
        self.rtr_base_url = rtr_base_url.rstrip("/")
        self.uitvoeren_base_url = uitvoeren_base_url.rstrip("/")
        self.rtr_api_key = rtr_api_key
        self.uitvoeren_api_key = uitvoeren_api_key
        self.api_key_header = api_key_header

    def _headers(self, api_key: str | None, extra: dict | None = None) -> dict:
        if not api_key:
            raise ConnectorError("Geen DSO-API-key geconfigureerd (controleer .env)")
        h = {self.api_key_header: api_key}
        if extra:
            h.update(extra)
        return h

    def bepaal_typeringen(self, refs: list[str], geo_rd: tuple[float, float],
                          datum: str | None = None) -> list[dict]:
        url = f"{self.rtr_base_url}/werkzaamheden/_bepaalRegelbeheerobjectTyperingen"
        body = {"functioneleStructuurRefs": list(refs), "_geo": _geo_point(geo_rd)}
        if datum:
            body["datum"] = datum
        return self.post_json(url, json_body=body, headers=self._headers(self.rtr_api_key))

    def bepaal_indieningsvereisten(self, refs: list[str], geo_rd: tuple[float, float],
                                   datum: str | None = None) -> list[dict]:
        url = f"{self.uitvoeren_base_url}/indieningsvereisten/_bepaal"
        body = {
            "functioneleStructuurRefs": [{"functioneleStructuurRef": r, "antwoorden": []} for r in refs],
            "_geo": _geo_point(geo_rd),
        }
        if datum:
            body["datum"] = datum
        return self.post_json(url, json_body=body,
                              headers=self._headers(self.uitvoeren_api_key, {"Content-Crs": "EPSG:28992"}))
