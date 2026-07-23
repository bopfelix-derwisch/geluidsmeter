# Afval — rapportcijfers, canoniek datamodel & doorkijk naar de toekomst — ontwerp

**Datum:** 2026-07-23
**Bouwt op:** UC-08 afval/circulair-dashboard (CBS 83558NED). Uitbreiding: meer bronnen, een echte database met een canoniek datamodel dat op CBS én AMICE/LMA aansluit, en een statistische extrapolatie ("doorkijk naar de toekomst").
**Status:** ontwerp, goedgekeurd voor plan-fase.

---

## 1. Doel

Het afval-dashboard verrijken met (a) cijfers uit meer openbare bronnen per afvalsoort, (b) opslag in een echte database geordend naar een canoniek datamodel dat consistent is met de datamodellen van CBS en AMICE/LMA, en (c) een betrouwbare, statistische doorkijk naar de toekomst (extrapolatie met onzekerheidsband) vanuit de huidige en historische cijfers.

Consistent met de projectlijn: alle bronnen zijn openbaar/openbaar-gelicentieerd, elke waarde is herleidbaar naar bron + licentie, en modelmatige of niet-open elementen worden expliciet gelabeld. Geen schaduwregister; AMICE/LMA-meldgegevens blijven buiten scope — het canonieke model is compatibel met het AMICE-schema, maar wordt gevuld met open cijfers.

### Afbakening (YAGNI)
- Geen live AMICE/LMA-meldgegevens (eHerkenning) — alleen open aggregaten.
- Extrapolatie is **beschrijvend/statistisch** (Holt), geen beleids- of scenariomodel.
- Provincieniveau (+ landelijk NL waar bronnen dat leveren); geen gemeenten.
- Eén DuckDB-bestand; geen externe databaseserver.

---

## 2. Database & canoniek datamodel

Eén **DuckDB**-bestand op NVMe: `/mnt/nvme/geluidsmeter/data/external/afval/afval.duckdb` (DuckDB staat al in `requirements.txt`; wordt geïnstalleerd). DuckDB is één bestand, SQL-queryable, en past bij de edge-stack.

### Tabellen

**`bron`** — herkomst per databron.
| kolom | type | toelichting |
|---|---|---|
| `bron_id` | TEXT PK | bijv. `cbs-83558NED`, `cbs-<id>`, `clo-<nr>`, `afvalfonds-<jaar>`, `lma-rws-<jaar>` |
| `naam` | TEXT | leesbare naam |
| `url` | TEXT | bron-URL/portaal |
| `licentie` | TEXT | bijv. `CC-BY 4.0`, `open (voorwaarden)` |
| `type` | TEXT | `api` \| `report_data` \| `report_pdf` |
| `opgehaald_op` | DATE | datum van de gebundelde snapshot |

**`afval_feit`** — de feitentabel (het canonieke model; verenigt CBS én AMICE).
| kolom | type | toelichting |
|---|---|---|
| `bron_id` | TEXT FK→bron | herkomst |
| `regio_code` | TEXT | `NL` of `PVxx` |
| `jaar` | INTEGER | |
| `afvalstroom_canoniek` | TEXT | canonieke stroomnaam (zie crosswalk) |
| `euralcode` | TEXT NULL | AMICE-aansluiting; leeg waar niet van toepassing |
| `verwerking` | TEXT | `R` (nuttige toepassing) \| `D` (verwijderen) \| `onbekend` |
| `indicator_type` | TEXT | `volume` \| `recyclingpercentage` \| `per_inwoner` |
| `hoeveelheid` | DOUBLE | |
| `eenheid` | TEXT | `kton` \| `ton` \| `kg_per_inwoner` \| `pct` |

**`afvalstroom_crosswalk`** — de brug tussen bron-vocabulaires en het canonieke model (dit is de expliciete CBS↔AMICE-mapping).
| kolom | type | toelichting |
|---|---|---|
| `bron_type` | TEXT | `cbs_topic` \| `afvalfonds_materiaal` \| `euralcode` \| `clo_indicator` |
| `bron_sleutel` | TEXT | bijv. `GFTAfval_6`, `Verpakkingsglas`, `200108`, indicator-id |
| `afvalstroom_canoniek` | TEXT | doelnaam, bijv. `GFT-afval`, `Verpakkingsglas` |

**`forecast`** — modelmatige doorkijk.
| kolom | type | toelichting |
|---|---|---|
| `regio_code` | TEXT | |
| `afvalstroom_canoniek` | TEXT | |
| `jaar` | INTEGER | toekomstjaar |
| `verwacht` | DOUBLE | puntvoorspelling (kton) |
| `ondergrens` | DOUBLE | onder-band |
| `bovengrens` | DOUBLE | boven-band |
| `methode` | TEXT | `holt` |

De canonieke afvalstroomnamen sluiten aan op de al bestaande curated set in `usecases/afval/transform.AFVALSTROMEN`, uitgebreid waar nieuwe bronnen extra stromen aandragen.

---

## 3. Architectuur & componenten

Nieuw pakket `src/leefomgevinglab/afvaldb/` (los van de bestaande dun-bestand-service, want dit introduceert een databaselaag):

| Component | Pad | Eén taak |
|---|---|---|
| **DB-laag** | `afvaldb/store.py` | DuckDB openen/initialiseren (schema uit §2), upsert per bron, en query-helpers (`feiten(regio, afvalstroom)`, `crosswalk_map()`, `forecast(regio, afvalstroom)`). |
| **Crosswalk** | `afvaldb/crosswalk.py` | Curated mapping bron-sleutel → `afvalstroom_canoniek` (CBS-topics, Afvalfonds-materialen, Euralcodes, CLO-indicatoren) + helper om een rij te canoniseren. |
| **Loaders** | `afvaldb/loaders/cbs.py`, `clo.py`, `afvalfonds.py`, `lma_rws.py` | Per bron: snapshot inlezen → normaliseren naar `afval_feit`-records → `bron`-rij. Elk pure `parse_*()` + `load(store)`; netwerk alleen in `fetch_*()`. |
| **Snapshots** | `scripts/12_fetch_afval_bronnen.py` | Haalt elke bron éénmalig op, bewaart de ruwe snapshot (CSV/JSON/PDF) op NVMe (`…/afval/snapshots/`), en laadt alles in DuckDB. Volgt `11_fetch_afval_aggregaat.py`. |
| **Forecast** | `afvaldb/forecast.py` | Holt (numpy, zelf-geïmplementeerd) op een tijdreeks → punt + band; `bouw_forecasts(store, horizon)` schrijft de `forecast`-tabel. |
| **Service-uitbreiding** | `usecases/afval/service.py` | `forecast(regio, afvalstroom)` en verrijking van `stroom_context()` met extra-broncijfers (recyclingpercentage/doel, per-inwoner) uit DuckDB. |
| **API** | `geluidsmeter/api.py` | `GET /api/afval/forecast`; bestaande `/api/afval/duiding` krijgt de forecast + extra cijfers mee in de context. |
| **Frontend** | `static/afval.html` | Modal: historie-+-forecast-lijngrafiek met band; kerncijfers uitgebreid met extra bronnen. |

### Datastroom
```
open bronnen (CBS OData · CLO · Afvalfonds PDF · LMA/RWS PDF)
  → scripts/12_fetch_afval_bronnen.py  → snapshots/ (ruwe kopie, herkomst)
  → loaders/*  (parse + crosswalk → canoniek)
  → afval.duckdb : bron, afval_feit, afvalstroom_crosswalk
  → forecast.py (Holt) → afval.duckdb : forecast
  → service (DuckDB) → REST /api/afval/{forecast,duiding,...}
  → afval.html (grafiek + rijke duiding)
```
Eén online fetch bij bouw; daarna draait alles op DuckDB/snapshots → offline-veilig.

---

## 4. Bronontsluiting (robuust & eerlijk)

Gemeenschappelijk patroon per loader:
1. **Fetch-once + snapshot** — de ruwe bron wordt één keer opgehaald en als bestand bewaard (reproduceerbaar, offline tests).
2. **Gerichte extractie** — een bekende tabel/kolommen, geen vrije-vorm.
3. **Validatie** — rij-aantallen en waardenranges; bij afwijking faalt de loader luid (geen stille rommel).
4. **Herkomst** — schrijft een `bron`-rij met url/licentie/datum.

Per bron:
- **CBS** (`type=api`) — 83558NED (hergebruik van de bestaande connector/transform) + 1–2 extra OData-tabellen voor verwerking/recycling. Exacte tabel-id's worden in de plan-fase live gepind (zoals bij UC-08).
- **CLO/Compendium** (`type=report_data`) — de datatabel achter een indicatorpagina (lange tijdreeks, bv. huishoudelijk afval per inwoner). Exacte indicator-URL('s) in de plan-fase.
- **Afvalfonds Verpakkingen** (`type=report_pdf`/`report_data`) — recyclingpercentages + doelen per materiaal uit de jaarrapportage.
- **LMA/RWS-jaarrapportage** (`type=report_pdf`) — nationale cijfers per Euralcode/verwerking via **`pdfplumber`** (gerichte tabel-extractie).

**PDF-robuustheid:** waar automatische PDF-extractie onbetrouwbaar blijkt, is de fallback een **curated, in de repo gebundelde CSV** met bronvermelding (handmatig overgenomen kerntabel). De loader gebruikt de CSV als die aanwezig is; anders `pdfplumber`. Zo is het resultaat altijd reproduceerbaar en eerlijk herleidbaar.

**Regioniveau per bron:** CLO, Afvalfonds en LMA/RWS leveren **landelijke** cijfers (`regio_code = NL`) en dienen als landelijke context/duiding en als extra reeks voor de landelijke forecast. De **provincie-reeksen** (`PVxx`) — en daarmee de provincie-forecasts — komen uit CBS. De crosswalk zorgt dat een landelijke Afvalfonds-materiaalreeks en de CBS-provinciereeks van dezelfde canonieke stroom naast elkaar in `afval_feit` staan, onderscheiden door `regio_code` en `bron_id`.

Toe te voegen dependency: **`pdfplumber`** (+ `duckdb` installeren; staat al in requirements).

---

## 5. Doorkijk naar de toekomst (Holt)

**Holt's lineaire exponential smoothing**, zelf geïmplementeerd met numpy (geen statsmodels):
- Level- en trend-smoothing met parameters α, β; forecast \(h\) jaar vooruit = `level + h·trend`.
- α, β worden gefit door de som van gekwadrateerde één-stap-vooruit-fouten (SSE) te minimaliseren (grid/bounded search) — deterministisch en testbaar.
- **Onzekerheidsband** uit de residu-standaardfout `s`: band ≈ `verwacht ± z·s·√h` (z=1,28 voor ~80%), duidelijk als indicatief gelabeld.
- **Horizon:** t/m **2035**.
- **Robuustheid:** een reeks met < 5 waarnemingen of met te veel gaten → geen forecast (skip + notitie); negatieve ondergrens wordt op 0 geklemd (afval kan niet < 0).

Per `regio_code` × `afvalstroom_canoniek` op de canonieke volume-reeks. Resultaat in de `forecast`-tabel. Overal gelabeld: *indicatieve modelmatige extrapolatie (Holt), geen beleidsprognose.*

---

## 6. API & UI

### Endpoints
| Route | Levert |
|---|---|
| `GET /api/afval/forecast?regio=&afvalstroom=` | `{regio, naam, afvalstroom, historie:[{jaar,hoeveelheid_kton}], forecast:[{jaar,verwacht,ondergrens,bovengrens}], methode, label}` |
| `POST /api/afval/duiding` (bestaand) | context uitgebreid met `forecast` (richting + waarde ~2035) en extra-broncijfers (bv. recyclingpercentage/doel, per-inwoner); duiding-prompt benoemt de doorkijk. |

### Frontend (modal)
- Compacte **lijngrafiek**: historische reeks + forecast-lijn met gearceerde band tot ~2035 (inline SVG, geen extra libs).
- Kerncijfer-blok uitgebreid met de extra bronnen (recyclingpercentage/doel, per-inwoner) mét bronlabel.
- AI-duiding benoemt expliciet de doorkijk en de herkomst; disclaimer voor extrapolatie.

---

## 7. Foutafhandeling
- Bron onbereikbaar bij fetch → bestaande snapshot blijft; loader stopt luid als er geen snapshot is.
- DuckDB ontbreekt/leeg → API 503 ("afval-database nog niet gevuld").
- Forecast onbetrouwbaar (te korte reeks) → geen forecast voor die combinatie; UI toont alleen historie.
- Qwen offline → duiding degradeert (bestaand gedrag), cijfers + grafiek blijven.

## 8. Testen (offline)
- **Crosswalk:** bron-sleutels mappen naar de juiste canonieke stroom; onbekende sleutel → herkenbaar gemarkeerd.
- **Store:** schema-init + upsert + query op een tmp-DuckDB.
- **Loaders:** `parse_*` op gebundelde mini-snapshots (CSV/JSON + een klein PDF-fixture of curated-CSV-pad) → correcte `afval_feit`-records; validatie faalt op kapotte input.
- **Forecast:** Holt op een synthetische reeks met bekende lineaire trend → verwachte punt binnen tolerantie; band > 0; korte reeks → skip.
- **Service/API:** `forecast`-endpoint-vorm; duiding-context bevat forecast + extra cijfers (LLM gemockt).

## 9. Herkomst & eerlijkheid
- Elke `afval_feit`-rij draagt `bron_id` → `bron`(url, licentie, datum).
- UI en duiding tonen bron + licentie per getal; extrapolatie en niet-open/afgeleide cijfers expliciet gelabeld.
- Snapshots + curated CSV's staan in de repo/NVMe met bronvermelding, zodat elk cijfer reproduceerbaar herleidbaar is.

## 10. Dependencies
- Toevoegen aan `requirements.txt`: `pdfplumber`. Installeren: `duckdb` (al gedeclareerd).
- Géén statsmodels (Holt zelf geïmplementeerd).
