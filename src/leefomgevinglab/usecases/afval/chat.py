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
