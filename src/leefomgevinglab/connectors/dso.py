"""DSO Registratie Toepasbare Regels via de Samengestelde RTR Services.

Live calls vereisen een API-key (DSO_API_KEY in .env). Operatie-pad en
api-key-header zijn config-gedreven; bevestig ze tegen de OpenAPI-spec zodra
de key beschikbaar is. De connector geeft de DSO-respons ongewijzigd door;
veld-mapping gebeurt in Plan 2b.
"""
from .base import BaseConnector, ConnectorError


class DsoConnector(BaseConnector):
    def __init__(self, base_url: str, operation_path: str, api_key: str | None,
                 api_key_header: str = "x-api-key", **kwargs):
        super().__init__(**kwargs)
        self.base_url = base_url.rstrip("/")
        self.operation_path = operation_path.strip("/")
        self.api_key = api_key
        self.api_key_header = api_key_header

    def bepaal_regels(self, activiteit: str, locatie: dict | None = None) -> dict:
        if not self.api_key:
            raise ConnectorError("Geen DSO_API_KEY geconfigureerd")
        url = f"{self.base_url}/{self.operation_path}"
        params = {"activiteit": activiteit}
        if locatie:
            params["lat"] = locatie.get("lat")
            params["lon"] = locatie.get("lon")
        headers = {self.api_key_header: self.api_key}
        return self.get_json(url, params=params, headers=headers)
