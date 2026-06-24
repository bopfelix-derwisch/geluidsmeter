from leefomgevinglab.connectors.externe_veiligheid import ExterneVeiligheidConnector

WFS = "https://x/geoserver/wfs"
RD = (151658.2, 418729.5)


def _conn(tmp_path, capture, ret):
    class _C(ExterneVeiligheidConnector):
        def get_json(self, url, params=None, headers=None):
            capture["url"] = url
            capture["params"] = params
            return ret
    return _C(wfs_url=WFS, cache_dir=str(tmp_path))


def test_bouwt_wfs_params_met_rd_punt(tmp_path):
    cap = {}
    payload = {"features": [
        {"properties": {"bedrijfsnaam": "Autobedrijf Mekes", "maatgevende_stof": "propaan"}},
    ]}
    c = _conn(tmp_path, cap, payload)
    out = c.aandachtsgebieden_op_punt("rev_public:ev_explosieaandachtsgebieden", RD)
    assert cap["url"] == WFS
    p = cap["params"]
    assert p["request"] == "GetFeature"
    assert p["typeNames"] == "rev_public:ev_explosieaandachtsgebieden"
    assert p["outputFormat"] == "application/json"
    assert p["cql_filter"] == "INTERSECTS(geometrie, POINT(151658.2 418729.5))"
    assert p["service"] == "WFS"
    assert p["version"] == "2.0.0"
    assert p["srsName"] == "EPSG:4326"
    assert p["count"] == 5
    assert out == [{"bron": "Autobedrijf Mekes", "maatgevende_stof": "propaan"}]


def test_bron_valt_terug_op_naamexploitant_en_bronhouder(tmp_path):
    # buisleiding (naamexploitant) en basisnet (bronhouder) hebben geen bedrijfsnaam
    c1 = _conn(tmp_path, {}, {"features": [{"properties": {"naamexploitant": "Gasunie", "maatgevende_stof": "aardgas"}}]})
    assert c1.aandachtsgebieden_op_punt("rev_public:bl_explosieaandachtsgebieden", RD)[0]["bron"] == "Gasunie"
    c2 = _conn(tmp_path, {}, {"features": [{"properties": {"bronhouder": "Rijkswaterstaat", "maatgevende_stof": "LPG"}}]})
    assert c2.aandachtsgebieden_op_punt("rev_public:bn_explosieaandachtsgebieden", RD)[0]["bron"] == "Rijkswaterstaat"


def test_maatgevende_stof_genest_object_pakt_chemischeNaam(tmp_path):
    props = {"bedrijfsnaam": "Bungalowpark Hessenheem",
             "maatgevende_stof": {"categorieNaam": "klasse 2.1: Brandbaar gas", "chemischeNaam": "propaan"}}
    c = _conn(tmp_path, {}, {"features": [{"properties": props}]})
    out = c.aandachtsgebieden_op_punt("rev_public:ev_explosieaandachtsgebieden", RD)
    assert out[0]["maatgevende_stof"] == "propaan"


def test_lege_featurecollection_geen_treffer(tmp_path):
    c = _conn(tmp_path, {}, {"features": []})
    assert c.aandachtsgebieden_op_punt("rev_public:ev_explosieaandachtsgebieden", RD) == []


def test_respecteert_max_n(tmp_path):
    payload = {"features": [{"properties": {"bedrijfsnaam": str(i)}} for i in range(10)]}
    c = _conn(tmp_path, {}, payload)
    assert len(c.aandachtsgebieden_op_punt("laag", RD, max_n=3)) == 3


def test_maatgevende_stof_json_string_pakt_chemischeNaam(tmp_path):
    payload = {"features": [{"properties": {
        "bedrijfsnaam": "Bungalowpark Hessenheem",
        "maatgevende_stof": '{"categorieNaam": "klasse 2.1: Brandbaar gas", "chemischeNaam": "propaan"}'}}]}
    c = _conn(tmp_path, {}, payload)
    assert c.aandachtsgebieden_op_punt("rev_public:ev_explosieaandachtsgebieden", RD)[0]["maatgevende_stof"] == "propaan"


def test_maatgevende_stof_plain_en_kapot_blijft_string(tmp_path):
    c1 = _conn(tmp_path, {}, {"features": [{"properties": {"bedrijfsnaam": "Test", "maatgevende_stof": "propaan"}}]})
    assert c1.aandachtsgebieden_op_punt("laag", RD)[0]["maatgevende_stof"] == "propaan"
    c2 = _conn(tmp_path, {}, {"features": [{"properties": {"bedrijfsnaam": "Test", "maatgevende_stof": "{kapot json"}}]})
    assert c2.aandachtsgebieden_op_punt("laag", RD)[0]["maatgevende_stof"] == "{kapot json"
