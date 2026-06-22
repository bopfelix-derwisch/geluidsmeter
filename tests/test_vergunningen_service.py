from leefomgevinglab.connectors.base import ConnectorError
from leefomgevinglab.usecases.vergunningen import service

LOC = {"lat": 52.0, "lon": 5.0}
LLM = {"llm_base_url": "http://llm/v1", "model": "qwen", "timeout_s": 5}
KAND = [
    {"urn": "DakkapelPlaatsen", "omschrijving": "Dakkapel plaatsen", "trefwoorden": ["dakkapel"],
     "functioneleStructuurRef": "http://x/DakkapelPlaatsen"},
    {"urn": "BouwwerkOnderhouden", "omschrijving": "Bouwwerk onderhouden", "trefwoorden": ["onderhoud"],
     "functioneleStructuurRef": "http://x/BouwwerkOnderhouden"},
]


class _Zoek:
    def __init__(self, kand=None, error=False):
        self._kand, self._error = kand, error

    def zoek_werkzaamheden(self, tekst, max_n=5):
        if self._error:
            raise ConnectorError("down")
        return self._kand


class _Dso:
    def __init__(self, typ=None, iv=None, typ_err=False, iv_err=False):
        self._typ, self._iv = typ, iv
        self._typ_err, self._iv_err = typ_err, iv_err

    def bepaal_typeringen(self, refs, geo_rd, datum=None):
        if self._typ_err:
            raise ConnectorError("down")
        return self._typ

    def bepaal_indieningsvereisten(self, refs, geo_rd, datum=None):
        if self._iv_err:
            raise ConnectorError("down")
        return self._iv


def _patch_resolver(monkeypatch, gekozen_idx=0):
    monkeypatch.setattr(service.resolver, "wgs84_naar_rd", lambda lat, lon: (155000.0, 463000.0))
    monkeypatch.setattr(service.resolver, "kies_werkzaamheid",
                        lambda vraag, kand, **cfg: {"gekozen": kand[gekozen_idx],
                                                    "match_onderbouwing": "test", "zekerheid_match": "hoog"})


def test_happy_alle_lagen(monkeypatch):
    _patch_resolver(monkeypatch)
    zoek = _Zoek(kand=KAND)
    dso = _Dso(typ=[{"regelbeheerobjecten": ["Conclusie", "Indieningsvereisten"]}],
               iv=[{"naam": "Tekening"}])
    out = service.regels_opzoeken("dakkapel", LOC, zoek, dso, LLM)
    assert out["beschikbaar"] is True
    assert out["gekozen_werkzaamheid"]["urn"] == "DakkapelPlaatsen"
    assert out["alternatieven"] == [{"urn": "BouwwerkOnderhouden", "omschrijving": "Bouwwerk onderhouden"}]
    assert out["typeringen"] == ["Conclusie", "Indieningsvereisten"]
    assert out["indieningsvereisten"] == [{"naam": "Tekening"}]
    assert out["indieningsvereisten_status"] == "beschikbaar"
    assert out["locatie_rd"] == [155000.0, 463000.0]
    assert out["onzekerheid"] is True
    assert "bevoegd gezag" in out["vangnet"]
    assert out["disclaimer"] == service.DISCLAIMER


def test_geen_kandidaten_degradeert(monkeypatch):
    out = service.regels_opzoeken("onzin", LOC, _Zoek(kand=[]), _Dso(), LLM)
    assert out["beschikbaar"] is False
    assert out["gekozen_werkzaamheid"] is None
    assert out["disclaimer"] == service.DISCLAIMER
    assert "bevoegd gezag" in out["vangnet"]


def test_zoekbron_down_degradeert():
    out = service.regels_opzoeken("dakkapel", LOC, _Zoek(error=True), _Dso(), LLM)
    assert out["beschikbaar"] is False
    assert out["gekozen_werkzaamheid"] is None
    assert out["onzekerheid"] is True
    assert out["disclaimer"] == service.DISCLAIMER


def test_iv_leeg_status_niet_beschikbaar_op_locatie(monkeypatch):
    _patch_resolver(monkeypatch)
    dso = _Dso(typ=[{"regelbeheerobjecten": ["Conclusie"]}], iv=[])
    out = service.regels_opzoeken("dakkapel", LOC, _Zoek(kand=KAND), dso, LLM)
    assert out["beschikbaar"] is True
    assert out["typeringen"] == ["Conclusie"]
    assert out["indieningsvereisten"] is None
    assert out["indieningsvereisten_status"] == "niet_beschikbaar_op_locatie"


def test_iv_bron_down_degradeert_alleen_laag5(monkeypatch):
    _patch_resolver(monkeypatch)
    dso = _Dso(typ=[{"regelbeheerobjecten": ["Conclusie"]}], iv_err=True)
    out = service.regels_opzoeken("dakkapel", LOC, _Zoek(kand=KAND), dso, LLM)
    assert out["beschikbaar"] is True                       # laag 1-4 blijven staan
    assert out["typeringen"] == ["Conclusie"]
    assert out["indieningsvereisten_status"] == "bron_tijdelijk_niet_beschikbaar"


def test_typeringen_down_degradeert_alleen_laag4(monkeypatch):
    _patch_resolver(monkeypatch)
    dso = _Dso(typ_err=True, iv=[])
    out = service.regels_opzoeken("dakkapel", LOC, _Zoek(kand=KAND), dso, LLM)
    assert out["beschikbaar"] is True
    assert out["typeringen"] is None


def test_kies_geen_match_degradeert(monkeypatch):
    monkeypatch.setattr(service.resolver, "wgs84_naar_rd", lambda lat, lon: (155000.0, 463000.0))
    monkeypatch.setattr(service.resolver, "kies_werkzaamheid",
                        lambda vraag, kand, **cfg: {"gekozen": None, "match_onderbouwing": "",
                                                    "zekerheid_match": "laag"})
    out = service.regels_opzoeken("dakkapel", LOC, _Zoek(kand=KAND), _Dso(), LLM)
    assert out["beschikbaar"] is False
    assert out["gekozen_werkzaamheid"] is None
    assert out["disclaimer"] == service.DISCLAIMER


def test_locatie_transform_faalt_degradeert(monkeypatch):
    monkeypatch.setattr(service.resolver, "kies_werkzaamheid",
                        lambda vraag, kand, **cfg: {"gekozen": kand[0], "match_onderbouwing": "t",
                                                    "zekerheid_match": "hoog"})

    def _boom(lat, lon):
        raise ValueError("buiten NL")

    monkeypatch.setattr(service.resolver, "wgs84_naar_rd", _boom)
    out = service.regels_opzoeken("dakkapel", LOC, _Zoek(kand=KAND), _Dso(), LLM)
    assert out["beschikbaar"] is False
    assert out["onzekerheid"] is True
    assert out["disclaimer"] == service.DISCLAIMER
