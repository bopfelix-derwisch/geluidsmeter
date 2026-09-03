"""Datakwaliteit-scan op een (REV) WFS — over álle lagen, filterbaar per bronhouder/activiteit.

Per laag: exact totaal via resultType=hits (met een optioneel CQL-filter voor bronhouder/activiteit)
plus een sample (GetFeature/GeoJSON) waaruit we geometrie-validiteit, lege bron-/stofvelden,
verlopen objecten, ruwe duplicaten en de bronhouders/activiteiten afleiden. Read-only; per-laag
degradatie (een laag-fout — bv. een filter op een veld dat de laag niet heeft — blokkeert de rest niet).

De WFS is een presentatielaag; kwaliteitsissues ontstaan bij de aanlevering door de bronhouder.
Live geverifieerd tegen rev-portaal.nl 2026-07-04.
"""
import json
import re
from datetime import datetime, timezone

import httpx
from shapely.geometry import shape

_SRC_FIELDS = ("bedrijfsnaam", "naamexploitant", "bronhouder")

# waarden die de REV gebruikt om "geen bruikbare waarde" uit te drukken (IMEV-nilReason-achtig)
_GEEN_WAARDE = {"onbekend", "waardeonbekend", "nietvantoepassing", "geenwaarde"}


def _stof_waarde(v):
    """Normaliseer maatgevende_stof naar een bruikbare stofnaam, of None.

    De WFS levert dit als genest object óf als JSON-string:
    {"categorieNaam": ..., "chemischeNaam": "propaan"} / {"geenWaardeReden": "nietVanToepassing"}.
    Zelfde afhandeling als connectors/externe_veiligheid.py.
    """
    if isinstance(v, str) and v.startswith("{"):
        try:
            v = json.loads(v)
        except ValueError:
            pass
    if isinstance(v, dict):
        if v.get("geenWaardeReden"):
            return None
        v = v.get("chemischeNaam") or v.get("categorieNaam")
    if not v or str(v).strip().lower() in _GEEN_WAARDE:
        return None
    return v

# IMEV 3.0.2: verplichte attributen van elk ExterneVeiligheidsobject, gemapt op de WFS-veldnamen.
# 'bevoegdgezag' (bevoegdGezagCode) is óók IMEV-verplicht en wordt alleen geëvalueerd op lagen die
# het ontsluiten (bv. ev_activiteiten); waar het veld niet in het schema zit, gaat het naar niet_in_schema.
IMEV_VERPLICHTE_VELDEN = ("identificatie", "bronhoudercode", "bevoegdgezag",
                          "begin_geldigheid", "tijdstip_registratie")


def _parse_dt(v):
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _cql_literal(v: str) -> str:
    return "'" + str(v).replace("'", "''") + "'"


def bouw_cql(bronhouder: str | None = None, activiteit: str | None = None) -> str | None:
    """Combineer optionele filters tot één CQL-expressie (of None)."""
    parts = []
    if bronhouder:
        parts.append("bronhouder=" + _cql_literal(bronhouder))
    if activiteit:
        parts.append("evactiviteit=" + _cql_literal(activiteit))
    return " AND ".join(parts) or None


def _check(r: httpx.Response) -> httpx.Response:
    # status-code-check i.p.v. raise_for_status: consistent met de rest van de codebase.
    if r.status_code >= 400:
        raise httpx.HTTPError(f"HTTP {r.status_code}")
    return r


def lagen_uit_capabilities(wfs_url: str, namespace: str = "rev_public:", timeout_s: float = 30.0) -> list[str]:
    """Ontdek alle FeatureType-namen (binnen het namespace) via GetCapabilities."""
    with httpx.Client(timeout=timeout_s) as client:
        r = _check(client.get(wfs_url, params={"service": "WFS", "version": "2.0.0",
                                               "request": "GetCapabilities"}))
    namen = re.findall(r"<Name>(" + re.escape(namespace) + r"[^<]+)</Name>", r.text)
    # dedupe met behoud van volgorde
    seen, out = set(), []
    for n in namen:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def _hits(client, wfs_url, laag, cql=None):
    p = {"service": "WFS", "version": "2.0.0", "request": "GetFeature",
         "typeNames": laag, "resultType": "hits"}
    if cql:
        p["cql_filter"] = cql
    r = _check(client.get(wfs_url, params=p))
    m = re.search(r'numberMatched="(\d+)"', r.text)
    return int(m.group(1)) if m else None


def _sample(client, wfs_url, laag, n, cql=None):
    p = {"service": "WFS", "version": "2.0.0", "request": "GetFeature", "typeNames": laag,
         "outputFormat": "application/json", "srsName": "EPSG:4326", "count": n}
    if cql:
        p["cql_filter"] = cql
    r = _check(client.get(wfs_url, params=p))
    return (r.json() or {}).get("features") or []


def _metrics_uit_sample(features: list, nu: datetime, bronhouders: set, activiteiten: set,
                        imev_velden=IMEV_VERPLICHTE_VELDEN, geometrie_verplicht: bool = True) -> dict:
    src_null = stof_null = verlopen = 0
    eind_gevuld = 0                              # features met een gevulde eind_geldigheid
    geom_valid = geom_invalid = geom_empty = geom_null = 0
    seen = set()
    dup = 0
    laag_bronh = set()
    # IMEV: bepaal welke verplichte velden de laag écht ontsluit (aanwezig in >=1 feature).
    # Alleen die tellen we per feature als 'leeg'; velden die de laag niet ontsluit gaan
    # naar niet_in_schema (structureel), zodat we een veld alleen evalueren waar het bestaat.
    schema_velden = set()
    for f in features:
        schema_velden.update((f.get("properties") or {}).keys())
    imev_in_schema = [v for v in imev_velden if v in schema_velden]
    imev_niet_in_schema = [v for v in imev_velden if schema_velden and v not in schema_velden]
    imev_ontbrekend = 0                          # totaal ontbrekende verplichte veldwaarden (leeg-maar-aanwezig)
    imev_incompleet = 0                          # features met >=1 ontbrekend verplicht veld
    imev_veld_null = {v: 0 for v in imev_in_schema}
    for f in features:
        p = f.get("properties") or {}
        mist = 0
        for v in imev_in_schema:
            if not p.get(v):
                imev_veld_null[v] += 1
                mist += 1
        if geometrie_verplicht and not f.get("geometry"):
            mist += 1
        imev_ontbrekend += mist
        if mist:
            imev_incompleet += 1
        if not any(p.get(k) for k in _SRC_FIELDS):
            src_null += 1
        if "maatgevende_stof" in p and _stof_waarde(p.get("maatgevende_stof")) is None:
            stof_null += 1
        bh = p.get("bronhouder")
        if bh:
            laag_bronh.add(bh)
            bronhouders.add(bh)
        act = p.get("evactiviteit")
        if act:
            activiteiten.add(act)
        eg = _parse_dt(p.get("eind_geldigheid"))
        if eg:
            eind_gevuld += 1
            if eg < nu:
                verlopen += 1
        g = f.get("geometry")
        if not g:
            geom_null += 1
        else:
            try:
                geom = shape(g)
                if geom.is_empty:
                    geom_empty += 1
                elif geom.is_valid:
                    geom_valid += 1
                else:
                    geom_invalid += 1
            except Exception:
                geom_invalid += 1
        key = (p.get("identificatie"), json.dumps(g, sort_keys=True) if g else None)
        if key in seen:
            dup += 1
        seen.add(key)
    n = len(features)
    return {
        # verlopen is alleen meetbaar als de laag überhaupt een eind_geldigheid vult;
        # anders None (= '–' in de UI) i.p.v. een 0 die "geen probleem" suggereert.
        "sample": n, "bron_null": src_null, "stof_null": stof_null,
        "verlopen": verlopen if eind_gevuld else None,
        "geom_valid": geom_valid, "geom_invalid": geom_invalid, "geom_empty": geom_empty,
        "geom_null": geom_null, "duplicaten": dup, "n_bronhouders": len(laag_bronh),
        "geom_invalid_pct": round(100 * geom_invalid / n, 1) if n else None,
        # IMEV 3.0.2 conformiteit
        "imev_ontbrekend": imev_ontbrekend,
        "imev_incompleet": imev_incompleet,
        "imev_incompleet_pct": round(100 * imev_incompleet / n, 1) if n else None,
        "imev_veld_null": {v: c for v, c in imev_veld_null.items() if c},
        "imev_velden_niet_in_schema": imev_niet_in_schema,
        # structurele non-conformiteit: verplichte velden die de laag helemaal niet ontsluit
        "imev_niet_ontsloten": len(imev_niet_in_schema),
    }


def scan_lagen(wfs_url: str, lagen: list[str], sample_n: int = 300, cql: str | None = None,
               imev_velden=IMEV_VERPLICHTE_VELDEN, timeout_s: float = 45.0) -> dict:
    """Scan elke laag (optioneel met CQL-filter). Verzamelt ook de distinct bronhouders/activiteiten
    (voor selectie-dropdowns) en de IMEV-conformiteit. Geeft {gescand_op, wfs_url, sample_n, cql,
    imev_velden, lagen[], bronhouders[], activiteiten[]}."""
    nu = datetime.now(timezone.utc)
    resultaten = []
    bronhouders, activiteiten = set(), set()
    with httpx.Client(timeout=timeout_s) as client:
        for laag in lagen:
            rij = {"laag": laag, "totaal": None, "error": None}
            try:
                rij["totaal"] = _hits(client, wfs_url, laag, cql)          # exact (CQL-filter)
                rij.update(_metrics_uit_sample(_sample(client, wfs_url, laag, sample_n, cql),
                                               nu, bronhouders, activiteiten, imev_velden=imev_velden))
            except (httpx.HTTPError, ValueError) as exc:
                rij["error"] = str(exc)[:160]
            resultaten.append(rij)
    return {"gescand_op": nu.isoformat(timespec="seconds"), "wfs_url": wfs_url, "sample_n": sample_n,
            "cql": cql, "imev_velden": list(imev_velden), "lagen": resultaten,
            "bronhouders": sorted(bronhouders), "activiteiten": sorted(activiteiten)}
