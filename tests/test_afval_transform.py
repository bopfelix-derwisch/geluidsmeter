from leefomgevinglab.usecases.afval import transform as t


def _row(regio, periode, **topics):
    base = {"Regiokenmerken": regio, "Perioden": periode}
    base.update(topics)
    return base


def test_is_provincie_alleen_pv():
    assert t.is_provincie("PV24    ") is True
    assert t.is_provincie("NL01    ") is False
    assert t.is_provincie("LD03") is False


def test_periode_to_jaar():
    assert t.periode_to_jaar("1993JJ00") == 1993
    assert t.periode_to_jaar("2020KW01") is None


def test_tidy_volumes_alleen_provincie_en_jaar_en_nietnull():
    rows = [
        _row("PV24    ", "2020JJ00", TotaalGemeentelijkAfval_1=100, GFTAfval_6=None),
        _row("PV25    ", "2020JJ00", GFTAfval_6=12.5),
        _row("NL01    ", "2020JJ00", TotaalGemeentelijkAfval_1=9999),   # geen provincie
        _row("PV24    ", "2020KW01", TotaalGemeentelijkAfval_1=1),      # geen jaar
    ]
    out = t.tidy_volumes(rows)
    assert {"regio_code": "PV24", "jaar": 2020,
            "afvalstroom": "Totaal gemeentelijk afval", "hoeveelheid_kton": 100.0} in out
    assert {"regio_code": "PV25", "jaar": 2020,
            "afvalstroom": "GFT-afval", "hoeveelheid_kton": 12.5} in out
    assert all(r["regio_code"].startswith("PV") for r in out)
    assert all("KW" not in str(r["jaar"]) for r in out)
    # None-waarde levert geen rij
    assert not any(r["regio_code"] == "PV24" and r["afvalstroom"] == "GFT-afval" for r in out)


def test_circulariteit_pct():
    rows = [_row("PV24    ", "2020JJ00",
                 NuttigeToepassing_174=75, Verbranden_177=20, Storten_178=5)]
    out = t.circulariteit_rows(rows)
    assert len(out) == 1
    r = out[0]
    assert r["regio_code"] == "PV24" and r["jaar"] == 2020
    assert r["nuttige_toepassing_kton"] == 75.0
    assert r["verwijderen_kton"] == 25.0
    assert round(r["circulariteit_pct"], 1) == 75.0


def test_circulariteit_overslaan_bij_ontbrekende_of_nul():
    rows = [
        _row("PV24    ", "2020JJ00", NuttigeToepassing_174=None, Verbranden_177=1, Storten_178=1),
        _row("PV25    ", "2020JJ00", NuttigeToepassing_174=0, Verbranden_177=0, Storten_178=0),
    ]
    assert t.circulariteit_rows(rows) == []
