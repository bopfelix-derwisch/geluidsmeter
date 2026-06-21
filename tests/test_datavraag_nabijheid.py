from leefomgevinglab.usecases.datavraag import nabijheid as NB


def test_scholen_parse(monkeypatch):
    fake_rows = [{"label": "School A", "lon": "4.30", "lat": "51.90"}]
    out = NB.scholen_in_provincie("Zuid-Holland", "http://x", sparql_fn=lambda q, ep, **k: fake_rows)
    assert out == [("School A", 4.30, 51.90)]


def test_nabij_meters():
    # school op (4.30, 51.90); object ~30 m ernaast vs object ~5 km verderop
    scholen = [("S", 4.30, 51.90)]
    dichtbij = "POINT(4.3004 51.9000)"     # ~27 m
    verweg = "POINT(4.40 51.90)"           # ~6-7 km
    res = NB.nabij([dichtbij, verweg], scholen, straal_m=200)
    assert dichtbij in res and verweg not in res
