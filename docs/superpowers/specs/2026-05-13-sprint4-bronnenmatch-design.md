# Sprint 4 — Bronnenmatch + Visualisatie

**Datum:** 2026-05-13
**Status:** Goedgekeurd

---

## Doel

Gemeten geluidsniveaus vergelijken met referentiedata van PDOK/NGR (CVGG, Atlas Leefomgeving, BGT) op drie assen:
1. Meting vs. modelwaarde (CVGG Lden/Lnight)
2. Bronidentificatie (weg, rail, industrie)
3. Normtoetsing (Omgevingswet grenswaarden)

Output: Jupyter notebook voor analyse + uitbreiding van het bestaande FastAPI dashboard (poort 8792).

---

## Aanpak

**B — Download + cache + analyseer:**
WFS eenmalig bevragen voor een bounding box (~500m) rond de meetlocatie. Resultaat opgeslagen als GeoJSON in de bestaande `external/` mappen op NVMe. Analyse draait volledig lokaal.

---

## Componenten

### 1. `scripts/03_fetch_external.py` — WFS downloader

- Leest meetlocatie uit `core/location_private.yaml` (privé coördinaten)
- Berekent bbox van 500m rond de locatie
- Bevraagt WFS-services op PDOK/NGR voor:
  - **CVGG geluidkaarten** — Lden + Lnight per bron (weg, rail, industrie)
  - **Atlas Leefomgeving** — omgevingstype, geluidszones
  - **BGT** — wegtype en functiezone als broncontext
- Slaat op als GeoJSON in:
  - `external/cvgg/cvgg_bbox.geojson`
  - `external/atlas/atlas_bbox.geojson`
  - `external/bgt/bgt_bbox.geojson`
- Idempotent: overschrijft alleen als `--force` meegegeven

### 2. `src/geluidsmeter/source_match.py` — matchlogica

- `match_cvgg(df, cvgg_gdf)` — point-in-polygon: haalt Lden/Lnight op voor de meetlocatie
- `estimate_dba(rms_dbfs, offset_db)` — dBFS + kalibratiefactor → geschatte dB(A)
- `check_norm(lden_estimated, norm_db)` — delta t.o.v. norm, retourneert status + marge. Standaardnorm wonen: Lden 48 dB(A), Lnight 43 dB(A) (Omgevingswet art. 5.67)
- `identify_sources(cvgg_gdf)` — bronverdeling (weg/rail/industrie) als dict met percentages
- Kalibratiefactor via config: `measurement.calibration_offset_db` (default: 0, instellen na handmeting)

### 3. `notebooks/bronnenmatch.ipynb` — analyse notebook

Drie secties:

| Sectie | Inhoud |
|--------|--------|
| 1. Meting vs. model | Tijdreeks gemeten dBFS + geschatte dB(A), CVGG Lden/Lnight als horizontale referentielijnen |
| 2. Bronidentificatie | Staafdiagram bronverdeling (weg/rail/industrie), kaartje met bbox en bronnen |
| 3. Normtoetsing | Tabel: periode (dag/avond/nacht) × norm × gemeten × delta × status |

Notebook herbruikbaar: één run = actuele analyse op basis van opgeslagen data.

### 4. Dashboard uitbreiding — `GET /summary` in `src/geluidsmeter/api.py`

Layout: **KPI-rij + kaart + tijdreeks**

```
┌─────────────┬─────────────┬─────────────┐
│ 49 dB(A)    │ 52 dB(A)    │ ⚠ norm      │
│ gemeten     │ CVGG model  │ 48 dB(A)    │
└─────────────┴─────────────┴─────────────┘
┌──────────────────────┬──────────────────┐
│ 🗺 Leaflet kaart      │ 📈 tijdreeks     │
│ locatie + geluidzone │ rms_dbfs 7 dagen │
└──────────────────────┴──────────────────┘
```

- Leaflet kaart: meetpunt + CVGG geluidzone als GeoJSON overlay
- Tijdreeks: laatste 7 dagen rms_dbfs (dag/avond/nacht gekleurd)
- KPI-data: uit `daily_profile_*.json` + `source_match.py`
- Statische HTML geserveerd via FastAPI (`/static/dashboard.html`)

---

## Config uitbreiding (`core/config.yaml`)

```yaml
measurement:
  calibration_offset_db: 0   # dBFS → dB(A) offset; 0 = ongekalibreerd

sources:
  wfs_bbox_m: 500            # straal bbox rond meetlocatie in meters
  force_refresh: false       # true = WFS opnieuw ophalen ook als data bestaat
```

---

## Kalibratie — waarschuwing

`calibration_offset_db` is een ruwe schatting. Zonder kalibratie met een gecertificeerde meter geldt:
- Alle dB(A)-waarden zijn **indicatief**
- `quality_label: prototype_indicatief_niet_juridisch` blijft van toepassing
- Notebook en dashboard tonen expliciet: *"geschatte dB(A), ongekalibreerd"*

---

## Volgorde van implementatie

1. Config uitbreiden
2. `03_fetch_external.py` — WFS download
3. `source_match.py` — matchlogica + kalibratie
4. `bronnenmatch.ipynb` — notebook
5. Dashboard uitbreiding (`/summary` endpoint + HTML)
6. Commit

---

## Buiten scope Sprint 4

- Automatische kalibratie
- Push naar remote catalogus
- Historische vergelijking (>7 dagen)
- Meerdere meetlocaties
