"""Afval data-chatbot: NL-vraag -> read-only DuckDB SELECT -> samenvatting.

Conservatief contract (spiegelt usecases/datavraag). Read-only + SQL-guard.
"""
import re

_VERBODEN = ("insert", "update", "delete", "drop", "alter", "create",
             "attach", "copy", "pragma", "install")
_MAX_LIMIT = 200


class OngeldigeSQL(Exception):
    """De gegenereerde SQL is leeg, geen enkele SELECT, of bevat verboden constructies."""


def valideer_sql(sql: str) -> str:
    s = (sql or "").strip()
    while s.endswith(";"):
        s = s[:-1].strip()
    if not s:
        raise OngeldigeSQL("lege query")
    if ";" in s:
        raise OngeldigeSQL("meerdere statements niet toegestaan")
    low = s.lower()
    if not (low.startswith("select") or low.startswith("with")):
        raise OngeldigeSQL("alleen SELECT/WITH toegestaan")
    for kw in _VERBODEN:
        if re.search(rf"\b{kw}\b", low):
            raise OngeldigeSQL(f"verboden trefwoord: {kw}")
    m = re.search(r"\blimit\s+(\d+)\b", low)
    if m:
        if int(m.group(1)) > _MAX_LIMIT:
            s = re.sub(r"\blimit\s+\d+\b", f"LIMIT {_MAX_LIMIT}", s, flags=re.IGNORECASE)
    else:
        s = f"{s} LIMIT {_MAX_LIMIT}"
    return s


PROVINCIE_NAMEN = {
    "PV20": "Groningen", "PV21": "Fryslân", "PV22": "Drenthe", "PV23": "Overijssel",
    "PV24": "Flevoland", "PV25": "Gelderland", "PV26": "Utrecht", "PV27": "Noord-Holland",
    "PV28": "Zuid-Holland", "PV29": "Zeeland", "PV30": "Noord-Brabant", "PV31": "Limburg",
}


def bouw_grounding(con) -> str:
    def distinct(kolom):
        return [r[0] for r in con.execute(
            f"SELECT DISTINCT {kolom} FROM afval_feit ORDER BY 1").fetchall()]
    stromen = distinct("afvalstroom_canoniek")
    regios = distinct("regio_code")
    indicatoren = distinct("indicator_type")
    bron_ids = distinct("bron_id")
    jmin, jmax = con.execute("SELECT MIN(jaar), MAX(jaar) FROM afval_feit").fetchone()
    prov = ", ".join(f"{c}={n}" for c, n in PROVINCIE_NAMEN.items())
    return (
        "Je genereert precies één DuckDB SQL SELECT over onderstaande database.\n"
        "Tabel afval_feit(bron_id, regio_code, jaar, afvalstroom_canoniek, euralcode, "
        "verwerking, indicator_type, hoeveelheid, eenheid).\n"
        "Tabel forecast(regio_code, afvalstroom_canoniek, jaar, verwacht, ondergrens, "
        "bovengrens, methode).\n"
        f"regio_code is 'NL' of een provinciecode. Provincies: {prov}.\n"
        f"afvalstroom_canoniek in: {stromen}.\n"
        f"regio_code-waarden aanwezig: {regios}.\n"
        f"indicator_type in: {indicatoren} (volume in kton of ton; recyclingpercentage in "
        "pct; per_inwoner in kg per inwoner).\n"
        f"bron_id in: {bron_ids}. jaar loopt van {jmin} t/m {jmax}.\n"
        "Geef UITSLUITEND de SELECT-query terug: geen uitleg, geen puntkomma, geen ```-fences."
    )
