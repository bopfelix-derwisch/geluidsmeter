from leefomgevinglab.afvaldb.loaders import cbs


def _row(regio, periode, **topics):
    return {"Regiokenmerken": regio, "Perioden": periode, **topics}


def test_parse_provincie_en_nl_volumes():
    rows = [
        _row("PV24    ", "2020JJ00", GFTAfval_6=12, TotaalGemeentelijkAfval_1=100),
        _row("NL01    ", "2020JJ00", GFTAfval_6=800),
        _row("LD03", "2020JJ00", GFTAfval_6=1),   # landsdeel: overslaan
        _row("PV24    ", "2020KW01", GFTAfval_6=3),  # geen jaar: overslaan
    ]
    recs = cbs.parse(rows)
    pv = [r for r in recs if r["regio_code"] == "PV24" and r["afvalstroom_canoniek"] == "GFT-afval"]
    nl = [r for r in recs if r["regio_code"] == "NL" and r["afvalstroom_canoniek"] == "GFT-afval"]
    assert pv and pv[0]["hoeveelheid"] == 12.0 and pv[0]["jaar"] == 2020
    assert pv[0]["indicator_type"] == "volume" and pv[0]["eenheid"] == "kton"
    assert pv[0]["bron_id"] == "cbs-83558NED" and pv[0]["verwerking"] == "onbekend"
    assert nl and nl[0]["hoeveelheid"] == 800.0
    # geen landsdeel/kwartaal
    assert not any(r["regio_code"].startswith("LD") for r in recs)
    assert all(r["jaar"] == 2020 for r in recs)
