import pytest
from leefomgevinglab.connectors.ozon import OzonConnector
from leefomgevinglab.connectors.base import ConnectorError

B = "https://x/ozon/v8"
RD = (139784.0, 442870.0)


def _conn(tmp_path, capture, ret):
    class _O(OzonConnector):
        def post_json(self, url, json_body=None, headers=None):
            capture["url"] = url
            capture["body"] = json_body
            capture["headers"] = headers
            return ret
    return _O(base_url=B, api_key="K", cache_dir=str(tmp_path))


def test_regelingen_op_punt_parst_en_zet_headers(tmp_path):
    cap = {}
    payload = {"_embedded": {"regelingen": [
        {"identificatie": "/akn/nl/act/pv26/2022/ov01", "opschrift": "Omgevingsverordening Utrecht",
         "officieleTitel": "OV Utrecht lang", "type": {"waarde": "Omgevingsverordening"},
         "aangeleverdDoorEen": {"naam": "provincie Utrecht", "bestuurslaag": "provincie"}},
    ]}}
    c = _conn(tmp_path, cap, payload)
    out = c.regelingen_op_punt(RD)
    assert cap["url"] == f"{B}/regelingen/_zoek"
    assert cap["body"] == {"geometrie": {"type": "Point", "coordinates": [139784.0, 442870.0]}}
    assert cap["headers"]["x-api-key"] == "K"
    assert cap["headers"]["Accept"] == "application/hal+json"
    assert cap["headers"]["Content-Crs"] == "http://www.opengis.net/def/crs/EPSG/0/28992"
    assert out == [{"titel": "Omgevingsverordening Utrecht", "type": "Omgevingsverordening",
                    "bevoegd_gezag": "provincie Utrecht", "uri": "_akn_nl_act_pv26_2022_ov01"}]


def test_regelingen_titel_valt_terug_op_officieleTitel(tmp_path):
    cap = {}
    payload = {"_embedded": {"regelingen": [
        {"identificatie": "/akn/x", "officieleTitel": "Alleen officieel", "type": {"waarde": "Omgevingsplan"},
         "aangeleverdDoorEen": {"naam": "gemeente X"}},
    ]}}
    c = _conn(tmp_path, cap, payload)
    assert c.regelingen_op_punt(RD)[0]["titel"] == "Alleen officieel"


def test_regelteksten_op_punt_topM_en_pad(tmp_path):
    cap = {}
    payload = {"_embedded": {"regeltekstannotaties": [
        {"opschrift": "Bouwregels"}, {"opschrift": "Parkeren"}, {"opschrift": "Reclame"}]}}
    c = _conn(tmp_path, cap, payload)
    out = c.regelteksten_op_punt("_akn_nl_act_pv26_2022_ov01", RD, max_m=2)
    assert cap["url"] == f"{B}/regelingen/_akn_nl_act_pv26_2022_ov01/regeltekstannotaties/_zoek"
    assert out == ["Bouwregels", "Parkeren"]


def test_regelteksten_leeg(tmp_path):
    c = _conn(tmp_path, {}, {"_embedded": {}})
    assert c.regelteksten_op_punt("u", RD) == []


def test_zonder_key_raises(tmp_path):
    c = OzonConnector(base_url=B, api_key=None, cache_dir=str(tmp_path))
    with pytest.raises(ConnectorError):
        c.regelingen_op_punt(RD)
    with pytest.raises(ConnectorError):
        c.regelteksten_op_punt("u", RD)
