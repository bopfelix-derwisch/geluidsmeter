from leefomgevinglab.usecases.datavraag import nabijheid as NB


def test_scholen_parse(monkeypatch):
    fake_rows = [{"naam": "School A", "g": "POINT(4.30 51.90)"}]
    gebied = "POLYGON((4.0 51.6,4.6 51.6,4.6 52.1,4.0 52.1,4.0 51.6))"
    out = NB.scholen_in_gebied(gebied, "http://x", sparql_fn=lambda q, ep, **k: fake_rows)
    assert out == [("School A", 4.30, 51.90)]


def test_provincie_polygon(monkeypatch):
    rows = [{"wkt": "POLYGON((4 51,5 51,5 52,4 52,4 51))"}]
    wkt = NB.provincie_polygon("Zuid-Holland", "http://x", sparql_fn=lambda q, ep, **k: rows)
    assert wkt.startswith("POLYGON")
    assert NB.provincie_polygon("X", "http://x", sparql_fn=lambda q, ep, **k: []) is None


def test_nabij_meters():
    # school op (4.30, 51.90); object ~30 m ernaast vs object ~5 km verderop
    scholen = [("S", 4.30, 51.90)]
    dichtbij = "POINT(4.3004 51.9000)"     # ~27 m
    verweg = "POINT(4.40 51.90)"           # ~6-7 km
    res = NB.nabij([dichtbij, verweg], scholen, straal_m=200)
    assert dichtbij in res and verweg not in res
