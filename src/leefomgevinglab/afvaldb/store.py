"""DuckDB-store voor het canonieke afval-datamodel (CBS↔AMICE) + forecasts."""
import duckdb

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS bron (
    bron_id TEXT PRIMARY KEY, naam TEXT, url TEXT, licentie TEXT, type TEXT, opgehaald_op DATE);
CREATE TABLE IF NOT EXISTS afval_feit (
    bron_id TEXT, regio_code TEXT, jaar INTEGER, afvalstroom_canoniek TEXT,
    euralcode TEXT, verwerking TEXT, indicator_type TEXT, hoeveelheid DOUBLE, eenheid TEXT);
CREATE TABLE IF NOT EXISTS afvalstroom_crosswalk (
    bron_type TEXT, bron_sleutel TEXT, afvalstroom_canoniek TEXT);
CREATE TABLE IF NOT EXISTS forecast (
    regio_code TEXT, afvalstroom_canoniek TEXT, jaar INTEGER,
    verwacht DOUBLE, ondergrens DOUBLE, bovengrens DOUBLE, methode TEXT);
"""

_FEIT_COLS = ["bron_id", "regio_code", "jaar", "afvalstroom_canoniek", "euralcode",
              "verwerking", "indicator_type", "hoeveelheid", "eenheid"]
_FC_COLS = ["regio_code", "afvalstroom_canoniek", "jaar", "verwacht", "ondergrens", "bovengrens", "methode"]


def open_db(path: str) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(path)
    con.execute(SCHEMA_SQL)
    return con


def reset(con) -> None:
    """Leeg de datatabellen zodat een her-ingest de data vervangt i.p.v. verdubbelt."""
    for tbl in ("bron", "afval_feit", "afvalstroom_crosswalk", "forecast"):
        con.execute(f"DELETE FROM {tbl}")


def upsert_bron(con, bron: dict) -> None:
    con.execute("DELETE FROM bron WHERE bron_id = ?", [bron["bron_id"]])
    con.execute("INSERT INTO bron VALUES (?, ?, ?, ?, ?, ?)",
                [bron["bron_id"], bron["naam"], bron["url"], bron["licentie"],
                 bron["type"], bron["opgehaald_op"]])


def insert_feiten(con, records: list[dict]) -> None:
    con.executemany(
        f"INSERT INTO afval_feit VALUES ({', '.join(['?'] * len(_FEIT_COLS))})",
        [[r.get(c) for c in _FEIT_COLS] for r in records])


def insert_crosswalk(con, rows: list[dict]) -> None:
    con.executemany("INSERT INTO afvalstroom_crosswalk VALUES (?, ?, ?)",
                    [[r["bron_type"], r["bron_sleutel"], r["afvalstroom_canoniek"]] for r in rows])


def insert_forecasts(con, rows: list[dict]) -> None:
    con.executemany(
        f"INSERT INTO forecast VALUES ({', '.join(['?'] * len(_FC_COLS))})",
        [[r.get(c) for c in _FC_COLS] for r in rows])


def series(con, regio_code, afvalstroom_canoniek, indicator_type="volume", bron_id=None):
    q = ("SELECT jaar, hoeveelheid FROM afval_feit WHERE regio_code = ? "
         "AND afvalstroom_canoniek = ? AND indicator_type = ?")
    params = [regio_code, afvalstroom_canoniek, indicator_type]
    if bron_id:
        q += " AND bron_id = ?"
        params.append(bron_id)
    q += " ORDER BY jaar"
    return [(int(j), float(h)) for j, h in con.execute(q, params).fetchall()]


def forecast_rows(con, regio_code, afvalstroom_canoniek) -> list[dict]:
    rows = con.execute(
        f"SELECT {', '.join(_FC_COLS)} FROM forecast WHERE regio_code = ? "
        "AND afvalstroom_canoniek = ? ORDER BY jaar", [regio_code, afvalstroom_canoniek]).fetchall()
    return [dict(zip(_FC_COLS, r)) for r in rows]


def open_readonly(db_path: str) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(db_path, read_only=True)


def bronnen(con) -> list[dict]:
    cols = ["bron_id", "naam", "url", "licentie", "type", "opgehaald_op"]
    rows = con.execute(f"SELECT {', '.join(cols)} FROM bron ORDER BY bron_id").fetchall()
    out = []
    for r in rows:
        d = dict(zip(cols, r))
        d["opgehaald_op"] = None if d["opgehaald_op"] is None else str(d["opgehaald_op"])
        out.append(d)
    return out


def run_select(con, sql: str) -> list[dict]:
    cur = con.execute(sql)
    names = [c[0] for c in cur.description]
    return [dict(zip(names, row)) for row in cur.fetchall()]
