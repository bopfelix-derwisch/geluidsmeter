"""UC-08 service: leest het gebundelde afval-aggregaat en levert meta,
choropleth-GeoJSON en tijdreeksen. Geen netwerk — puur bestand-gebaseerd.
"""
import json
import math
from pathlib import Path

import pandas as pd


def _none_if_missing(val):
    """Geef None terug voor None, NaN of niet-numerieke waarden; anders float(val)."""
    if val is None:
        return None
    try:
        return None if math.isnan(float(val)) else float(val)
    except (TypeError, ValueError):
        return None

from .transform import AFVALSTROMEN

BRON = "CBS StatLine 83558NED (Gemeentelijke afvalstoffen; hoeveelheden)"
LICENTIE = "CC-BY 4.0"
LABEL = "Open proxy voor het gesloten LMA/AMICE-aggregaat — illustratief"
INDICATOREN = [
    {"key": "volume", "label": "Hoeveelheid (kton)"},
    {"key": "circulariteit", "label": "Circulariteit (%)"},
]

TOTAAL_LABEL = "Totaal gemeentelijk afval"

# Curated, feitelijke achtergrond per afvalstroom (algemene CBS-/afvalkennis).
# Achtergrondcontext voor de duiding — geen cijfers, geen beleidsoordeel.
AFVALSTROOM_ACHTERGROND = {
    "Totaal gemeentelijk afval": "Al het afval dat gemeenten inzamelen bij huishoudens en via reinigingsdiensten samen.",
    "Totaal huishoudelijk afval": "Al het afval dat huishoudens aanbieden, zowel gescheiden fracties als restafval.",
    "Huishoudelijk restafval": "Het niet-gescheiden deel van het huishoudelijk afval; gaat grotendeels naar verbranding met energieterugwinning.",
    "GFT-afval": "Groente-, fruit- en tuinafval; wordt gecomposteerd of vergist tot compost en groen gas.",
    "Oud papier en karton": "Gescheiden ingezameld en vrijwel volledig gerecycled tot nieuw papier en karton.",
    "Verpakkingsglas": "Flessen en potten; wordt omgesmolten tot nieuw glas en is in principe eindeloos herbruikbaar.",
    "Kunststof verpakkingen": "Plastic verpakkingen; deels mechanisch gerecycled, deels verbrand afhankelijk van de kwaliteit van de fractie.",
}


def _paths(data_dir: str):
    d = Path(data_dir)
    return d / "aggregaat.parquet", d / "circulariteit.parquet", d / "provincies.geojson"


def _load_geo(data_dir: str) -> dict:
    _, _, geo = _paths(data_dir)
    return json.loads(geo.read_text())


def meta(data_dir: str) -> dict:
    vol_p, _, _ = _paths(data_dir)
    vol = pd.read_parquet(vol_p)
    geo = _load_geo(data_dir)
    regios = [{"code": f["properties"]["identificatie"], "naam": f["properties"]["naam"]}
              for f in geo["features"]]
    jaren = sorted(int(j) for j in vol["jaar"].unique())
    return {
        "regios": regios,
        "afvalstromen": list(AFVALSTROMEN.keys()),
        "jaren": jaren,
        "indicatoren": list(INDICATOREN),
        "bron": BRON,
        "licentie": LICENTIE,
        "label": LABEL,
    }


def choropleth(data_dir: str, afvalstroom: str, jaar: int, indicator: str) -> dict:
    vol_p, circ_p, _ = _paths(data_dir)
    geo = _load_geo(data_dir)
    if indicator == "circulariteit":
        # Circulariteit is een per-provincie/jaar-aggregaat over alle stromen (spec §5);
        # afvalstroom wordt hier bewust genegeerd.
        df = pd.read_parquet(circ_p)
        df = df[df["jaar"] == int(jaar)]
        lookup = dict(zip(df["regio_code"], df["circulariteit_pct"]))
        eenheid = "%"
    else:
        df = pd.read_parquet(vol_p)
        df = df[(df["jaar"] == int(jaar)) & (df["afvalstroom"] == afvalstroom)]
        lookup = dict(zip(df["regio_code"], df["hoeveelheid_kton"]))
        eenheid = "kton"
    for f in geo["features"]:
        code = f["properties"]["identificatie"]
        val = lookup.get(code)
        f["properties"].update({
            "value": _none_if_missing(val),
            "indicator": indicator,
            "afvalstroom": afvalstroom,
            "jaar": int(jaar),
            "eenheid": eenheid,
        })
    return geo


def trend(data_dir: str, regio: str, afvalstroom: str) -> dict:
    vol_p, circ_p, _ = _paths(data_dir)
    vol = pd.read_parquet(vol_p)
    circ = pd.read_parquet(circ_p)
    geo = _load_geo(data_dir)
    naam = next((f["properties"]["naam"] for f in geo["features"]
                 if f["properties"]["identificatie"] == regio), regio)
    v = vol[(vol["regio_code"] == regio) & (vol["afvalstroom"] == afvalstroom)]
    circ_map = dict(zip(circ[circ["regio_code"] == regio]["jaar"],
                        circ[circ["regio_code"] == regio]["circulariteit_pct"]))
    reeks = []
    for _, r in v.sort_values("jaar").iterrows():
        jaar = int(r["jaar"])
        pct = circ_map.get(jaar)
        reeks.append({
            "jaar": jaar,
            "hoeveelheid_kton": float(r["hoeveelheid_kton"]),
            "circulariteit_pct": _none_if_missing(pct),
        })
    return {"regio": regio, "naam": naam, "afvalstroom": afvalstroom, "reeks": reeks}


def stroom_context(data_dir: str, regio: str, afvalstroom: str, jaar: int) -> dict:
    """Rijkere context voor de duiding: provinciewaarde + landelijke vergelijking/rang,
    meerjarentrend, aandeel van totaal afval, hoogste/laagste provincie en achtergrond.
    Puur afgeleid uit het bestaande aggregaat."""
    vol_p, circ_p, _ = _paths(data_dir)
    vol = pd.read_parquet(vol_p)
    circ = pd.read_parquet(circ_p)
    geo = _load_geo(data_dir)
    jaar = int(jaar)
    naam_map = {f["properties"]["identificatie"]: f["properties"]["naam"] for f in geo["features"]}
    naam = naam_map.get(regio, regio)

    stroom = vol[vol["afvalstroom"] == afvalstroom]
    jaar_df = stroom[stroom["jaar"] == jaar]

    prov_row = jaar_df[jaar_df["regio_code"] == regio]
    waarde = float(prov_row["hoeveelheid_kton"].iloc[0]) if len(prov_row) else None

    landelijk_gem = rang = aantal = boven = None
    hoogste = laagste = None
    if len(jaar_df):
        landelijk_gem = float(jaar_df["hoeveelheid_kton"].mean())
        aantal = int(jaar_df["regio_code"].nunique())
        if waarde is not None:
            gesorteerd = jaar_df.sort_values("hoeveelheid_kton", ascending=False)["regio_code"].tolist()
            rang = gesorteerd.index(regio) + 1
            boven = waarde > landelijk_gem
        hi = jaar_df.loc[jaar_df["hoeveelheid_kton"].idxmax()]
        lo = jaar_df.loc[jaar_df["hoeveelheid_kton"].idxmin()]
        hoogste = {"naam": naam_map.get(hi["regio_code"], hi["regio_code"]),
                   "waarde_kton": float(hi["hoeveelheid_kton"])}
        laagste = {"naam": naam_map.get(lo["regio_code"], lo["regio_code"]),
                   "waarde_kton": float(lo["hoeveelheid_kton"])}

    prov_stroom = stroom[stroom["regio_code"] == regio].sort_values("jaar")
    meerjaren = None
    if len(prov_stroom) >= 2:
        eerste, laatste = prov_stroom.iloc[0], prov_stroom.iloc[-1]
        e0 = float(eerste["hoeveelheid_kton"])
        volume_pct = ((float(laatste["hoeveelheid_kton"]) - e0) / e0 * 100) if e0 > 0 else None
        pc = circ[circ["regio_code"] == regio].sort_values("jaar")
        circ_punt = None
        if len(pc) >= 2:
            c0 = _none_if_missing(pc.iloc[0]["circulariteit_pct"])
            c1 = _none_if_missing(pc.iloc[-1]["circulariteit_pct"])
            if c0 is not None and c1 is not None:
                circ_punt = c1 - c0
        meerjaren = {"van_jaar": int(eerste["jaar"]), "tot_jaar": int(laatste["jaar"]),
                     "volume_pct": volume_pct, "circ_pct_punt": circ_punt}

    aandeel = None
    if afvalstroom != TOTAAL_LABEL and waarde is not None:
        tot = vol[(vol["regio_code"] == regio) & (vol["jaar"] == jaar)
                  & (vol["afvalstroom"] == TOTAAL_LABEL)]
        if len(tot) and float(tot["hoeveelheid_kton"].iloc[0]) > 0:
            aandeel = waarde / float(tot["hoeveelheid_kton"].iloc[0]) * 100

    cprov = circ[(circ["regio_code"] == regio) & (circ["jaar"] == jaar)]
    circ_pct = _none_if_missing(cprov["circulariteit_pct"].iloc[0]) if len(cprov) else None

    return {
        "regio": regio, "naam": naam, "afvalstroom": afvalstroom, "jaar": jaar,
        "waarde_kton": waarde, "circulariteit_pct": circ_pct,
        "landelijk_gemiddelde_kton": landelijk_gem, "rang": rang,
        "aantal_provincies": aantal, "boven_gemiddeld": boven,
        "meerjaren": meerjaren, "aandeel_van_totaal_pct": aandeel,
        "hoogste": hoogste, "laagste": laagste,
        "achtergrond": AFVALSTROOM_ACHTERGROND.get(afvalstroom),
    }


from leefomgevinglab.afvaldb import store as _afvaldb_store

FORECAST_LABEL = "Indicatieve modelmatige extrapolatie (Holt) — geen beleidsprognose"


def forecast(db_path: str, regio: str, afvalstroom: str) -> dict:
    con = _afvaldb_store.open_db(db_path)
    try:
        reeks = _afvaldb_store.series(con, regio, afvalstroom, indicator_type="volume")
        fc = _afvaldb_store.forecast_rows(con, regio, afvalstroom)
    finally:
        con.close()
    return {
        "regio": regio, "afvalstroom": afvalstroom,
        "historie": [{"jaar": j, "hoeveelheid_kton": h} for j, h in reeks],
        "forecast": [{"jaar": r["jaar"], "verwacht": r["verwacht"],
                      "ondergrens": r["ondergrens"], "bovengrens": r["bovengrens"]} for r in fc],
        "methode": "holt", "label": FORECAST_LABEL,
    }


def extra_context(db_path: str, afvalstroom: str) -> dict:
    con = _afvaldb_store.open_db(db_path)
    try:
        rec = con.execute(
            "SELECT hoeveelheid, bron_id FROM afval_feit WHERE afvalstroom_canoniek = ? "
            "AND indicator_type = 'recyclingpercentage' ORDER BY jaar DESC LIMIT 1", [afvalstroom]).fetchone()
        pi = con.execute(
            "SELECT jaar, hoeveelheid FROM afval_feit WHERE afvalstroom_canoniek = ? "
            "AND indicator_type = 'per_inwoner' ORDER BY jaar", [afvalstroom]).fetchall()
    finally:
        con.close()
    return {
        "recyclingpercentage": float(rec[0]) if rec else None,
        "recycling_bron": rec[1] if rec else None,
        "per_inwoner": [{"jaar": int(j), "waarde": float(h)} for j, h in pi] or None,
    }
