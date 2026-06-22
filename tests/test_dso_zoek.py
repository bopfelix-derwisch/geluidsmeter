import pytest
from leefomgevinglab.connectors.dso_zoek import ZoekConnector
from leefomgevinglab.connectors.base import ConnectorError


def test_zoek_werkzaamheden_parses_hal(tmp_path):
    captured = {}

    class _Z(ZoekConnector):
        def post_json(self, url, json_body=None, headers=None):
            captured["url"] = url
            captured["body"] = json_body
            captured["headers"] = headers
            return {"_embedded": {"werkzaamheden": [
                {"urn": "DakkapelPlaatsen", "omschrijving": "Dakkapel plaatsen",
                 "functioneleStructuurRef": "http://x/werkzaamheden/id/concept/DakkapelPlaatsen",
                 "trefwoorden": ["dakkapel"]},
                {"urn": "BouwwerkOnderhouden", "omschrijving": "Bouwwerk onderhouden",
                 "functioneleStructuurRef": "http://x/werkzaamheden/id/concept/BouwwerkOnderhouden",
                 "trefwoorden": ["onderhoud"]},
            ]}}

    c = _Z(base_url="https://x/v2/", api_key="K", cache_dir=str(tmp_path))
    out = c.zoek_werkzaamheden("dakkapel")
    assert captured["url"] == "https://x/v2/werkzaamheden/_zoek"
    assert captured["body"] == {"zoekterm": "dakkapel"}
    assert captured["headers"]["x-api-key"] == "K"
    assert out[0]["urn"] == "DakkapelPlaatsen"
    assert out[0]["trefwoorden"] == ["dakkapel"]
    assert len(out) == 2


def test_zoek_respects_max_n(tmp_path):
    class _Z(ZoekConnector):
        def post_json(self, url, json_body=None, headers=None):
            return {"_embedded": {"werkzaamheden": [{"urn": str(i)} for i in range(10)]}}

    c = _Z(base_url="https://x/v2", api_key="K", cache_dir=str(tmp_path))
    assert len(c.zoek_werkzaamheden("x", max_n=3)) == 3


def test_zoek_without_key_raises(tmp_path):
    c = ZoekConnector(base_url="https://x/v2", api_key=None, cache_dir=str(tmp_path))
    with pytest.raises(ConnectorError):
        c.zoek_werkzaamheden("dakkapel")
