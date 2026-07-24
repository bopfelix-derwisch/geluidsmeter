from leefomgevinglab.afvaldb import store
from leefomgevinglab.usecases.afval import chat


def _db(tmp_path):
    p = str(tmp_path / "afval.duckdb")
    con = store.open_db(p)
    store.insert_feiten(con, [
        {"bron_id": "cbs-83558NED", "regio_code": "PV24", "jaar": 2020,
         "afvalstroom_canoniek": "GFT-afval", "euralcode": None, "verwerking": "onbekend",
         "indicator_type": "volume", "hoeveelheid": 12.0, "eenheid": "kton"}])
    con.close()
    return p


def test_beantwoord_happy(tmp_path, monkeypatch):
    p = _db(tmp_path)
    monkeypatch.setattr(chat, "genereer_sql",
                        lambda vraag, grounding, **kw: "SELECT hoeveelheid FROM afval_feit")
    monkeypatch.setattr(chat, "vat_samen",
                        lambda vraag, rijen, **kw: "In 2020 was het 12 kton.")
    out = chat.beantwoord("hoeveel GFT in Flevoland 2020?", p,
                          llm_base_url="x", model="m")
    assert out["beschikbaar"] is True
    assert out["rijen"] == [{"hoeveelheid": 12.0}]
    assert out["antwoord"] == "In 2020 was het 12 kton."
    assert "limit 200" in out["sql"].lower()   # LIMIT afgedwongen
    assert "disclaimer" in out and "bron" in out


def test_beantwoord_gevaarlijke_sql_niet_uitgevoerd(tmp_path, monkeypatch):
    p = _db(tmp_path)
    monkeypatch.setattr(chat, "genereer_sql",
                        lambda vraag, grounding, **kw: "DROP TABLE afval_feit")
    out = chat.beantwoord("verwijder alles", p, llm_base_url="x", model="m")
    assert out["beschikbaar"] is False
    assert out["rijen"] == []
    # DB is intact
    con = store.open_db(p)
    assert con.execute("SELECT COUNT(*) FROM afval_feit").fetchone()[0] == 1


def test_beantwoord_lege_resultaten(tmp_path, monkeypatch):
    p = _db(tmp_path)
    monkeypatch.setattr(chat, "genereer_sql",
                        lambda vraag, grounding, **kw: "SELECT * FROM afval_feit WHERE jaar=1900")
    out = chat.beantwoord("iets", p, llm_base_url="x", model="m")
    assert out["beschikbaar"] is True and out["rijen"] == []
    assert "geen resultaten" in out["antwoord"].lower()


def test_beantwoord_db_afwezig(tmp_path):
    out = chat.beantwoord("iets", str(tmp_path / "bestaat_niet.duckdb"),
                          llm_base_url="x", model="m")
    assert out["beschikbaar"] is False
    assert out["antwoord"] is None


def test_beantwoord_bestandsfunctie_faalt_veilig(tmp_path, monkeypatch):
    p = _db(tmp_path)
    monkeypatch.setattr(chat, "genereer_sql",
                        lambda vraag, grounding, **kw: "SELECT content FROM read_text('/etc/hostname')")
    out = chat.beantwoord("lees /etc/hostname", p, llm_base_url="x", model="m")
    assert out["beschikbaar"] is False
    assert out["rijen"] == []


def test_beantwoord_grounding_fout_degradeert(tmp_path, monkeypatch):
    p = _db(tmp_path)
    def boom(con):
        raise RuntimeError("schema kapot")
    monkeypatch.setattr(chat, "bouw_grounding", boom)
    out = chat.beantwoord("iets", p, llm_base_url="x", model="m")
    assert out["beschikbaar"] is False
    assert out["rijen"] == []
