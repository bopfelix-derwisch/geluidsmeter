# tests/test_afvaldb_ingest.py
import importlib.util
from pathlib import Path
from leefomgevinglab.afvaldb import store

SPEC = Path(__file__).resolve().parents[1] / "scripts" / "12_fetch_afval_bronnen.py"
_spec = importlib.util.spec_from_file_location("ingest_bronnen", SPEC)
ingest = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ingest)

FIX = Path(__file__).parent / "fixtures" / "afval"


def _row(regio, periode, **t):
    return {"Regiokenmerken": regio, "Perioden": periode, **t}


def test_vul_database_is_idempotent(tmp_path):
    con = store.open_db(str(tmp_path / "afval.duckdb"))
    args = dict(clo_csv=str(FIX / "clo_huishoudelijk.csv"),
                afvalfonds_csv=str(FIX / "afvalfonds_recycling.csv"),
                lma_csv=str(FIX / "lma_rws.csv"), opgehaald_op="2026-07-23")
    ingest.vul_database(con, cbs_rows=[_row("PV24    ", "2020JJ00", GFTAfval_6=12)], **args)
    n1 = con.execute("SELECT COUNT(*) FROM afval_feit").fetchone()[0]
    ingest.vul_database(con, cbs_rows=[_row("PV24    ", "2020JJ00", GFTAfval_6=12)], **args)
    n2 = con.execute("SELECT COUNT(*) FROM afval_feit").fetchone()[0]
    assert n1 == n2 and n1 > 0
    # crosswalk niet verdubbeld
    assert con.execute("SELECT COUNT(*) FROM afvalstroom_crosswalk").fetchone()[0] == len(
        __import__("leefomgevinglab.afvaldb.crosswalk", fromlist=["CROSSWALK"]).CROSSWALK)


def test_vul_database_laadt_alle_bronnen(tmp_path):
    con = store.open_db(str(tmp_path / "afval.duckdb"))
    cbs_rows = [_row("PV24    ", "2020JJ00", GFTAfval_6=12)]
    telling = ingest.vul_database(
        con, cbs_rows=cbs_rows,
        clo_csv=str(FIX / "clo_huishoudelijk.csv"),
        afvalfonds_csv=str(FIX / "afvalfonds_recycling.csv"),
        lma_csv=str(FIX / "lma_rws.csv"),
        opgehaald_op="2026-07-23")
    # feiten uit elke bron aanwezig
    assert store.series(con, "PV24", "GFT-afval")            # CBS
    assert store.series(con, "NL", "Totaal huishoudelijk afval", indicator_type="per_inwoner")  # CLO
    bronnen = {r[0] for r in con.execute("SELECT DISTINCT bron_id FROM afval_feit").fetchall()}
    assert {"cbs-83558NED", "clo-nl014437"}.issubset(bronnen)
    assert any(b.startswith("afvalfonds-") for b in bronnen)
    assert any(b.startswith("lma-rws-") for b in bronnen)
    # crosswalk geladen
    assert con.execute("SELECT COUNT(*) FROM afvalstroom_crosswalk").fetchone()[0] > 0
    assert telling["cbs"] >= 1
