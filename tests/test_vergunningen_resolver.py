import httpx
from leefomgevinglab.usecases.vergunningen import resolver

K1 = {"urn": "DakkapelPlaatsen", "omschrijving": "Dakkapel plaatsen", "trefwoorden": ["dakkapel"],
      "functioneleStructuurRef": "http://x/DakkapelPlaatsen"}
K2 = {"urn": "BouwwerkOnderhouden", "omschrijving": "Bouwwerk onderhouden", "trefwoorden": ["onderhoud"],
      "functioneleStructuurRef": "http://x/BouwwerkOnderhouden"}


def test_wgs84_naar_rd_amersfoort_referentiepunt():
    # OLV-toren Amersfoort = definitiepunt RD (155000, 463000)
    x, y = resolver.wgs84_naar_rd(52.15517440, 5.38720621)
    assert abs(x - 155000) < 1.0
    assert abs(y - 463000) < 1.0


def test_kies_geen_kandidaten():
    out = resolver.kies_werkzaamheid("iets", [], "http://llm/v1", "qwen")
    assert out["gekozen"] is None
    assert out["zekerheid_match"] == "laag"


def test_kies_een_kandidaat_zonder_llm(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("LLM mag niet aangeroepen worden bij 1 kandidaat")

    monkeypatch.setattr(httpx, "post", boom)
    out = resolver.kies_werkzaamheid("dakkapel", [K1], "http://llm/v1", "qwen")
    assert out["gekozen"]["urn"] == "DakkapelPlaatsen"


def test_kies_meer_kandidaten_qwen(monkeypatch):
    def fake_post(url, json=None, headers=None, timeout=None):
        return httpx.Response(200, json={"choices": [{"message": {
            "content": '{"index": 1, "onderbouwing": "onderhoud past beter", "zekerheid": "hoog"}'}}]})

    monkeypatch.setattr(httpx, "post", fake_post)
    out = resolver.kies_werkzaamheid("onderhoud plegen", [K1, K2], "http://llm/v1", "qwen")
    assert out["gekozen"]["urn"] == "BouwwerkOnderhouden"
    assert out["zekerheid_match"] == "hoog"
    assert "onderhoud" in out["match_onderbouwing"]


def test_kies_valt_terug_bij_llm_fout(monkeypatch):
    def boom(*a, **k):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx, "post", boom)
    out = resolver.kies_werkzaamheid("x", [K1, K2], "http://llm/v1", "qwen")
    assert out["gekozen"]["urn"] == "DakkapelPlaatsen"   # hoogst gerankt
    assert out["zekerheid_match"] == "laag"


def test_extract_activiteit_haalt_kale_woordgroep(monkeypatch):
    def fake_post(url, json=None, timeout=None):
        return httpx.Response(200, json={"choices": [{"message": {"content": "dakkapel plaatsen"}}]})

    monkeypatch.setattr(httpx, "post", fake_post)
    out = resolver.extract_activiteit("mag ik een dakkapel plaatsen in mijn tuin?", "http://llm/v1", "qwen")
    assert out == "dakkapel plaatsen"


def test_extract_activiteit_valt_terug_op_vraag_bij_fout(monkeypatch):
    def boom(*a, **k):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx, "post", boom)
    vraag = "mag ik een dakkapel plaatsen?"
    assert resolver.extract_activiteit(vraag, "http://llm/v1", "qwen") == vraag


def test_extract_activiteit_lege_output_valt_terug(monkeypatch):
    def fake_post(url, json=None, timeout=None):
        return httpx.Response(200, json={"choices": [{"message": {"content": "   "}}]})

    monkeypatch.setattr(httpx, "post", fake_post)
    vraag = "iets vaags"
    assert resolver.extract_activiteit(vraag, "http://llm/v1", "qwen") == vraag
