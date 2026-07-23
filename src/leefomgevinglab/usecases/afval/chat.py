"""Afval data-chatbot: NL-vraag -> read-only DuckDB SELECT -> samenvatting.

Conservatief contract (spiegelt usecases/datavraag). Read-only + SQL-guard.
"""
import re
from pathlib import Path

import httpx

from leefomgevinglab.connectors.base import ConnectorError
from leefomgevinglab.afvaldb import store

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


DISCLAIMER = ("Indicatief; open cijfers als proxy voor het gesloten LMA/AMICE, geen officieel cijfer.")
VANGNET = "Raadpleeg de bronhouder (CBS, Afvalfonds, RWS/LMA) voor officiele cijfers."
BRON = "Afvaldatabase: CBS 83558NED, CLO, Afvalfonds, LMA/RWS (open bronnen)."


def _chat(prompt: str, llm_base_url: str, model: str, timeout_s: float) -> str:
    try:
        resp = httpx.post(
            f"{llm_base_url.rstrip('/')}/chat/completions",
            json={"model": model, "messages": [{"role": "user", "content": prompt}],
                  "temperature": 0.0},
            timeout=timeout_s,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except (httpx.HTTPError, KeyError, ValueError, IndexError) as exc:
        raise ConnectorError("AI tijdelijk niet beschikbaar") from exc


def genereer_sql(vraag: str, grounding: str, llm_base_url: str, model: str,
                 timeout_s: float = 60.0) -> str:
    tekst = _chat(f"{grounding}\n\nVraag: {vraag}\nSQL:", llm_base_url, model, timeout_s)
    tekst = tekst.strip()
    if tekst.startswith("```"):
        tekst = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", tekst).strip()
    return tekst


def vat_samen(vraag: str, rijen: list[dict], llm_base_url: str, model: str,
              timeout_s: float = 60.0) -> str:
    prompt = (
        "Je bent een feitelijke data-assistent. Beantwoord de vraag in 2-3 zinnen op basis van "
        "UITSLUITEND de gegeven queryresultaten. Verzin niets; noem concrete getallen. Geen beleidsoordeel.\n\n"
        f"Vraag: {vraag}\nResultaten (JSON): {rijen}"
    )
    return _chat(prompt, llm_base_url, model, timeout_s)


def beantwoord(vraag: str, db_path: str, llm_base_url: str, model: str,
               timeout_s: float = 60.0) -> dict:
    base = {"vraag": vraag, "disclaimer": DISCLAIMER, "vangnet": VANGNET, "bron": BRON}
    if not Path(db_path).exists():
        return {**base, "antwoord": None, "sql": None, "rijen": [], "beschikbaar": False}
    con = store.open_readonly(db_path)
    try:
        grounding = bouw_grounding(con)
        try:
            ruwe = genereer_sql(vraag, grounding, llm_base_url=llm_base_url, model=model, timeout_s=timeout_s)
        except ConnectorError:
            return {**base, "antwoord": "AI tijdelijk niet beschikbaar.", "sql": None, "rijen": [], "beschikbaar": False}
        try:
            sql = valideer_sql(ruwe)
        except OngeldigeSQL:
            return {**base, "antwoord": "Deze vraag kon niet veilig naar een query worden vertaald.",
                    "sql": ruwe, "rijen": [], "beschikbaar": False}
        try:
            rijen = store.run_select(con, sql)
        except Exception:
            return {**base, "antwoord": "De query kon niet worden uitgevoerd.", "sql": sql,
                    "rijen": [], "beschikbaar": False}
    finally:
        con.close()
    if not rijen:
        return {**base, "antwoord": "Geen resultaten voor deze vraag.", "sql": sql, "rijen": [], "beschikbaar": True}
    try:
        antwoord = vat_samen(vraag, rijen, llm_base_url=llm_base_url, model=model, timeout_s=timeout_s)
    except ConnectorError:
        antwoord = f"{len(rijen)} resultaten (AI-samenvatting tijdelijk niet beschikbaar)."
    return {**base, "antwoord": antwoord, "sql": sql, "rijen": rijen, "beschikbaar": True}
