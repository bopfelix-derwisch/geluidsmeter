import pytest
from leefomgevinglab.connectors.dso import DsoConnector
from leefomgevinglab.connectors.base import ConnectorError


def test_bepaal_regels_builds_request_with_key(tmp_path):
    captured = {}

    class _Dso(DsoConnector):
        def get_json(self, url, params=None, headers=None):
            captured["url"] = url
            captured["params"] = params
            captured["headers"] = headers
            return {"resultaat": "ok"}

    c = _Dso(base_url="https://service.omgevingswet.overheid.nl/x/v2/",
             operation_path="_bepaalToepasbareRegels",
             api_key="SECRET", api_key_header="x-api-key", cache_dir=str(tmp_path))
    out = c.bepaal_regels("kappen van een boom", {"lat": 52.0, "lon": 4.0})

    assert captured["url"] == "https://service.omgevingswet.overheid.nl/x/v2/_bepaalToepasbareRegels"
    assert captured["headers"]["x-api-key"] == "SECRET"
    assert captured["params"]["activiteit"] == "kappen van een boom"
    assert out == {"resultaat": "ok"}


def test_bepaal_regels_without_key_raises(tmp_path):
    c = DsoConnector(base_url="https://x/v2/", operation_path="op",
                     api_key=None, cache_dir=str(tmp_path))
    with pytest.raises(ConnectorError):
        c.bepaal_regels("activiteit X")
