from leefomgevinglab.afvaldb import crosswalk as cw


def test_cbs_topic_naar_canoniek():
    assert cw.canoniek("cbs_topic", "GFTAfval_6") == "GFT-afval"
    assert cw.canoniek("cbs_topic", "Verpakkingsglas_9") == "Verpakkingsglas"


def test_afvalfonds_materiaal_naar_canoniek():
    assert cw.canoniek("afvalfonds_materiaal", "Glas") == "Verpakkingsglas"
    assert cw.canoniek("afvalfonds_materiaal", "Papier en karton") == "Oud papier en karton"


def test_euralcode_naar_canoniek():
    assert cw.canoniek("euralcode", "200108") == "GFT-afval"


def test_onbekende_sleutel_is_none():
    assert cw.canoniek("cbs_topic", "BestaatNiet_999") is None


def test_crosswalk_rows_hebben_verplichte_kolommen():
    for row in cw.CROSSWALK:
        assert set(row) == {"bron_type", "bron_sleutel", "afvalstroom_canoniek"}
