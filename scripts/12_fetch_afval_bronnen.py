"""Ingest: vult de DuckDB-afvaldatabase uit alle open bronnen en bouwt de Holt-forecast.

CBS live via OData; CLO/Afvalfonds/LMA via gebundelde snapshot (pdfplumber of curated CSV).
Bron: open/CC-BY — proxy-context naast het gesloten LMA/AMICE.
"""
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from leefomgevinglab.afvaldb import store, forecast
from leefomgevinglab.afvaldb.crosswalk import CROSSWALK
from leefomgevinglab.afvaldb.loaders import cbs, clo, afvalfonds, lma_rws
from leefomgevinglab.connectors.cbs_afval import CbsAfvalConnector

_ROOT = Path(__file__).resolve().parents[1]
_FIX = _ROOT / "tests" / "fixtures" / "afval"


def vul_database(con, cbs_rows, clo_csv, afvalfonds_csv, lma_csv, opgehaald_op,
                 afvalfonds_jaar=2023, lma_jaar=2022):
    store.reset(con)
    store.insert_crosswalk(con, CROSSWALK)
    telling = {}

    cbs_recs = cbs.parse(cbs_rows)
    store.upsert_bron(con, {**cbs.BRON, "opgehaald_op": opgehaald_op})
    store.insert_feiten(con, cbs_recs)
    telling["cbs"] = len(cbs_recs)

    clo_recs = clo.parse_csv(clo_csv)
    store.upsert_bron(con, {**clo.BRON, "opgehaald_op": opgehaald_op})
    store.insert_feiten(con, clo_recs)
    telling["clo"] = len(clo_recs)

    af_recs = afvalfonds.parse_csv(afvalfonds_csv, jaar=afvalfonds_jaar)
    store.upsert_bron(con, {**afvalfonds.bron(afvalfonds_jaar), "opgehaald_op": opgehaald_op})
    store.insert_feiten(con, af_recs)
    telling["afvalfonds"] = len(af_recs)

    lma_recs = lma_rws.parse_csv(lma_csv, jaar=lma_jaar)
    store.upsert_bron(con, {**lma_rws.bron(lma_jaar), "opgehaald_op": opgehaald_op})
    store.insert_feiten(con, lma_recs)
    telling["lma"] = len(lma_recs)

    return telling


def main():
    from datetime import date
    cfg = yaml.safe_load(open(_ROOT / "core" / "config.yaml"))
    ll = cfg["leefomgevinglab"]
    db = ll["afvaldb"]
    afval = ll["afval"]
    Path(db["db_path"]).parent.mkdir(parents=True, exist_ok=True)
    con = store.open_db(db["db_path"])
    today = date.today().isoformat()

    print("CBS 83558NED ophalen...")
    conn = CbsAfvalConnector(base_url=afval["odata_base_url"], table_id=afval["table_id"],
                             cache_dir=ll.get("cache_dir", "/tmp/llab_cache"), timeout=30.0)
    cbs_rows = conn.typed_dataset()

    # Rapport-snapshots: PDF indien geconfigureerd, anders curated CSV-fallback.
    af_pdf, lma_pdf = db.get("afvalfonds_pdf", ""), db.get("lma_pdf", "")
    af_csv, lma_csv = str(_FIX / "afvalfonds_recycling.csv"), str(_FIX / "lma_rws.csv")
    snap = Path(db["snapshots_dir"]); snap.mkdir(parents=True, exist_ok=True)
    if af_pdf:
        rows = afvalfonds.extract_pdf(af_pdf)
        (snap / "afvalfonds_recycling.csv").write_text(
            "materiaal,recycling_pct\n" + "\n".join(f"{r['materiaal']},{r['recycling_pct']}" for r in rows))
        af_csv = str(snap / "afvalfonds_recycling.csv")
    if lma_pdf:
        rows = lma_rws.extract_pdf(lma_pdf)
        (snap / "lma_rws.csv").write_text(
            "euralcode,verwerking,ton\n" + "\n".join(f"{r['euralcode']},{r['verwerking']},{r['ton']}" for r in rows))
        lma_csv = str(snap / "lma_rws.csv")

    telling = vul_database(con, cbs_rows=cbs_rows,
                           clo_csv=str(_FIX / "clo_huishoudelijk.csv"),
                           afvalfonds_csv=af_csv, lma_csv=lma_csv, opgehaald_op=today,
                           afvalfonds_jaar=db.get("afvalfonds_jaar", 2023),
                           lma_jaar=db.get("lma_jaar", 2022))
    print("Feiten per bron:", telling)
    n = forecast.bouw_forecasts(con, tot_jaar=db.get("forecast_tot_jaar", 2035))
    print(f"Forecast gebouwd voor {n} reeksen -> {db['db_path']}")


if __name__ == "__main__":
    main()
