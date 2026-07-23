# UC-08 — Afval/circulair-dashboard (POC) — ontwerp

**Datum:** 2026-07-23
**Use case:** UC-08 uit *LeefomgevingLab architectuuropzet v0.3* — "Afval/circulair-dashboard: afvalstroom-indicatoren per regio op openbare LMA-aggregaten; API-patroon verkennen in BTO."
**Status:** ontwerp, goedgekeurd voor plan-fase.

---

## 1. Doel en afbakening

Een proof-of-concept dat het BALO/LeefomgevingLab-patroon (connector → usecase → façade-route → eigen dashboard, met lokale-LLM-duiding) toepast op het thema **afval/circulariteit**.

Het dashboard toont een **provincie-choropleth** met een afvalstroom-indicator, en per aangeklikte provincie een **trendpaneel** (tijdreeks per afvalstroom) plus een korte **AI-duiding** door de lokale Qwen.

### Bron en bronhouderschap-afweging

AMICE / LMA (het Landelijk Meldpunt Afvalstoffen) is **bewust geen open bron**: de meldgegevens zitten achter eHerkenning/BTO (`test.lma.nl`) en er is geen live open API. Alleen geaggregeerde afvalstatistieken zijn openbaar. Conform de rolzuiverheid in BALO ontsluit de lab dus **geen meldgegevens** en bouwt het **geen schaduwregister**.

De POC draait daarom op een **open, gebundeld aggregaat**: **CBS StatLine tabel `83558NED` "Gemeentelijke afvalstoffen; hoeveelheden"** (OData `https://opendata.cbs.nl/ODataApi/OData/83558NED`, licentie **CC-BY 4.0**). Deze tabel bevat hoeveelheden per **afvalsoort × verwerkingsmethode × regio (NL, provincies, grootteklasse) × jaar** en dient als **open proxy** voor het gesloten LMA/AMICE-aggregaat. Dit wordt in UI en metadata expliciet zo benoemd.

### Buiten scope (YAGNI)

- **eHerkenning / AMICE-BTO** — het "eerste echte gat" (BALO-bouwsteen 2). Niet in deze POC.
- **Per-gemeente** granulariteit — POC blijft op **provincie-niveau**.
- Meerdere CBS-tabellen; alleen `83558NED`.
- Zware STAC-tagging — alleen als triviaal mee te nemen.

---

## 2. Architectuur

Volgt het bestaande patroon in `src/leefomgevinglab/` (connectors + usecases + routes in `geluidsmeter/api.py` + static dashboard). Één FastAPI-app (`geluidsmeter.api:app`), poort **8792**.

| Component | Pad | Eén taak |
|---|---|---|
| **Connector** | `src/leefomgevinglab/connectors/cbs_afval.py` — `CbsAfvalConnector(BaseConnector)` | CBS OData 83558NED ophalen (TypedDataSet + code-tabellen `RegioS`, `Perioden`, `Afvalsoort`, `Verwerkingsmethode`) en normaliseren naar tidy records. Erft on-disk cache + nette degradatie van `BaseConnector`. |
| **Ingest-script** | `scripts/11_fetch_afval_aggregaat.py` | Connector éénmaal aanroepen; genormaliseerd aggregaat (Parquet) + provincie-geometrie schrijven naar NVMe. Volgt `scripts/03_fetch_external.py`. |
| **Usecase-service** | `src/leefomgevinglab/usecases/afval/service.py` | Aggregaat inlezen; `meta()`, `choropleth(afvalstroom, jaar, indicator)` → GeoJSON, `trend(regio, afvalstroom)` → tijdreeks. |
| **AI-duiding** | `src/leefomgevinglab/usecases/afval/duiding.py` | Geselecteerde cijfers → lokale Qwen (`localhost:8080`, OpenAI-compatibel), no-hallucination-prompt, bronverwijzing CBS 83558NED. |
| **Routes** | in `src/leefomgevinglab/geluidsmeter/api.py` | Nieuwe endpoints (zie §4). |
| **Frontend** | `src/leefomgevinglab/static/afval.html` | MapLibre GL + PDOK BRT-achtergrond, provincie-choropleth, filters, klik-provincie → trend + duiding. |

### Databestanden (NVMe, buiten repo)

Onder `/mnt/nvme/geluidsmeter/data/external/afval/`:
- `aggregaat.parquet` — tidy: `regio_code, regio_naam, jaar, afvalsoort, verwerkingsmethode, hoeveelheid_kton`.
- `provincies.geojson` — provincie-geometrie (PDOK), key op `regio_code`.
- Connector-cache in `.../afval/cache/`.

---

## 3. Datastroom

```
CBS OData 83558NED
  → CbsAfvalConnector (on-disk cache)
  → scripts/11_fetch_afval_aggregaat.py  → aggregaat.parquet + provincies.geojson
  → usecases/afval/service.py
  → REST /api/afval/*  (façade in geluidsmeter/api.py)
  → static/afval.html  (choropleth + trend)
  → POST /api/afval/duiding → Qwen localhost:8080
```

Eén online fetch bij bouw (ingest-script); daarna leest alles uit Parquet/cache → **offline-veilig**.

---

## 4. Façade — REST-endpoints

Alle onder `/api/afval/`, stijl consistent met bestaande routes.

| Route | Methode | Levert |
|---|---|---|
| `/afval` | GET | Dashboard-HTML (`afval.html`). |
| `/api/afval/meta` | GET | Lijsten: `regios`, `afvalstromen`, `jaren`, `indicatoren`; en bron-/licentie-info. |
| `/api/afval/choropleth?afvalstroom=&jaar=&indicator=` | GET | GeoJSON FeatureCollection per provincie met `value` + `label` voor de gekozen indicator. |
| `/api/afval/trend?regio=&afvalstroom=` | GET | Tijdreeks `[{jaar, hoeveelheid_kton, circulariteit}]` voor één provincie. |
| `/api/afval/duiding` | POST | `{regio, afvalstroom, reeks}` → korte trendduiding (Qwen) met bronverwijzing. |

---

## 5. Indicatoren

Per provincie × jaar × afvalsoort, afgeleid uit de CBS-dimensies:

1. **Totaal (kton)** — som hoeveelheid over verwerkingsmethoden. Primaire volume-indicator.
2. **Circulariteit** — **aandeel nuttige toepassing (R-codes) t.o.v. verwijderen (D-codes)**, afgeleid uit de dimensie `Verwerkingsmethode`. Range 0–100%. Kern-indicator voor het circulaire karakter van de POC.

Beide indicatoren komen uit dezelfde tabel `83558NED` — **harde grens: één CBS-tabel**. "Kg per inwoner" vereist een tweede tabel (83452NED) en valt daarom buiten scope van deze POC.

De choropleth toont de door de gebruiker gekozen indicator (totaal óf circulariteit); het trendpaneel toont beide tijdreeksen voor de aangeklikte provincie.

> **Uitvoerings-noot:** de exacte mapping van `Verwerkingsmethode`-codes naar R (nuttige toepassing) vs. D (verwijderen) wordt in de implementatie bepaald op basis van de code-tabel van 83558NED. Als de tabel verwerkingsmethode niet fijnmazig genoeg splitst voor R/D, valt circulariteit terug op de wél beschikbare uitsplitsing (bijv. recycling/verbranden/storten) — het dashboard labelt dan wat het toont.

---

## 6. AI-duiding (lokale Qwen)

- Endpoint bouwt een prompt met **alleen de meegegeven getallen** (geen vrije kennis), vraagt om een korte NL-duiding van de trend en circulariteit, met expliciete **bronverwijzing (CBS 83558NED, CC-BY 4.0)** en een vangnet-zin dat het om een open proxy voor LMA gaat.
- Consistent met het bestaande duiding-/chatbot-patroon (no-hallucination-prompt).
- Qwen offline → endpoint geeft nette melding "duiding tijdelijk niet beschikbaar"; dashboard blijft volledig werken.

---

## 7. Foutafhandeling

- **CBS onbereikbaar bij ingest** → `ConnectorError`; script stopt met duidelijke melding, bestaande cache/parquet blijft.
- **Runtime bron weg** → service leest lokaal parquet, dus onafhankelijk van CBS-uptime.
- **Qwen offline** → duiding-endpoint degradeert netjes (zie §6).
- **Ontbrekende regio/jaar/afvalstroom** → lege GeoJSON/lege reeks, dashboard toont lege staat i.p.v. crash.

---

## 8. Testen

Offline, via gecachte CBS-fixture (geen live calls in tests).

- **Connector:** normalisatie van een mock-OData-respons (TypedDataSet + code-tabellen) naar tidy records; cache-fallback bij fout.
- **Service:** `choropleth()` levert geldige GeoJSON met juiste `value` per provincie; `trend()` levert oplopende jaren; circulariteit 0–100%.
- **Duiding:** promptopbouw bevat de meegegeven getallen en de bronverwijzing; LLM-call gemockt; offline-degradatie getest.

---

## 9. Metadata & herleidbaarheid

- Elk API-antwoord en het dashboard vermelden **bron = CBS 83558NED, licentie CC-BY 4.0**, en het label **"open proxy voor het gesloten LMA/AMICE-aggregaat — illustratief"**.
- Korte DQ-notitie bij het aggregaat (peiljaar-bereik, dekking = provincies).
- STAC-collection-tag alleen als triviaal mee te nemen; anders latere stap.

---

## 10. Aansluiting op de architectuur

- Vult **L1-connector** ("LMA-aggregaat") en **L6-toepassing** (dashboard) uit v0.3 §4.
- Realiseert BALO-bouwstenen 1 (API-/uitwisselingsstrategie), 3 (datakwaliteit/metadata), 4 (geo/locatie), 6 (analyse/signalering) en 7 (kennis/AI-ontsluiting).
- Bouwsteen 2 (IAM/eHerkenning, AMICE-BTO) blijft expliciet buiten scope — de POC toont juist hoe je met de **open uitvoer** waarde levert zonder de gesloten bron te raken.
