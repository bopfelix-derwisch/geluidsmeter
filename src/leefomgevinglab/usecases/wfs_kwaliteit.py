"""Datakwaliteit-scan op een (REV) WFS.

Per laag: exact totaal via resultType=hits + een sample (GetFeature/GeoJSON) waaruit we
geometrie-validiteit, bron-null-rate, maatgevende_stof-null-rate, verlopen objecten,
ruwe duplicaten en het aantal bronhouders afleiden. De scan is read-only en degradeert
per laag (een laag-fout blokkeert de rest niet).

De WFS is een presentatielaag; kwaliteitsissues ontstaan bij de aanlevering door de bronhouder.
Live geverifieerd tegen rev-portaal.nl 2026-07-04.
"""
import json
import re
from datetime import datetime, timezone

import httpx
from shapely.geometry import shape

_SRC_FIELDS = ("bedrijfsnaam", "naamexploitant", "bronhouder")


def _parse_dt(v):
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _check(r: httpx.Response) -> httpx.Response:
    # status-code-check i.p.v. raise_for_status: consistent met de rest van de codebase
    # en compatibel met test-mocks die geen request aan de Response koppelen.
    if r.status_code >= 400:
        raise httpx.HTTPError(f"HTTP {r.status_code}")
    return r


def _hits(client: httpx.Client, wfs_url: str, laag: str) -> int | None:
    r = _check(client.get(wfs_url, params={"service": "WFS", "version": "2.0.0", "request": "GetFeature",
                                           "typeNames": laag, "resultType": "hits"}))
    m = re.search(r'numberMatched="(\d+)"', r.text)
    return int(m.group(1)) if m else None


def _sample(client: httpx.Client, wfs_url: str, laag: str, n: int) -> list:
    r = _check(client.get(wfs_url, params={"service": "WFS", "version": "2.0.0", "request": "GetFeature",
                                           "typeNames": laag, "outputFormat": "application/json",
                                           "srsName": "EPSG:4326", "count": n}))
    return (r.json() or {}).get("features") or []


def _metrics_uit_sample(features: list, nu: datetime) -> dict:
    src_null = stof_null = verlopen = 0
    geom_valid = geom_invalid = geom_empty = geom_null = 0
    seen = set()
    dup = 0
    bronhouders = set()
    for f in features:
        p = f.get("properties") or {}
        if not any(p.get(k) for k in _SRC_FIELDS):
            src_null += 1
        if "maatgevende_stof" in p and not p.get("maatgevende_stof"):
            stof_null += 1
        bh = p.get("bronhouder") or p.get("bronhoudercode")
        if bh:
            bronhouders.add(bh)
        eg = _parse_dt(p.get("eind_geldigheid"))
        if eg and eg < nu:
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
        "sample": n,
        "bron_null": src_null, "stof_null": stof_null, "verlopen": verlopen,
        "geom_valid": geom_valid, "geom_invalid": geom_invalid,
        "geom_empty": geom_empty, "geom_null": geom_null,
        "duplicaten": dup, "n_bronhouders": len(bronhouders),
        "geom_invalid_pct": round(100 * geom_invalid / n, 1) if n else None,
    }


def scan_lagen(wfs_url: str, lagen: list[str], sample_n: int = 300, timeout_s: float = 45.0) -> dict:
    """Scan elke laag; geeft {gescand_op, wfs_url, sample_n, lagen: [{laag, totaal, ...metrics, error}]}."""
    nu = datetime.now(timezone.utc)
    resultaten = []
    with httpx.Client(timeout=timeout_s) as client:
        for laag in lagen:
            rij = {"laag": laag, "totaal": None, "error": None}
            try:
                rij["totaal"] = _hits(client, wfs_url, laag)
                rij.update(_metrics_uit_sample(_sample(client, wfs_url, laag, sample_n), nu))
            except (httpx.HTTPError, ValueError) as exc:
                rij["error"] = str(exc)[:160]
            resultaten.append(rij)
    return {"gescand_op": nu.isoformat(timespec="seconds"), "wfs_url": wfs_url,
            "sample_n": sample_n, "lagen": resultaten}
