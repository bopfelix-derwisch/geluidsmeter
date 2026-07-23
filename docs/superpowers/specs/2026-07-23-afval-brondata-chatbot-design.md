# Afval — brondata-uitleg & data-chatbot (NL→SQL) — ontwerp

**Datum:** 2026-07-23
**Bouwt op:** het afval-dashboard (`/afval`) en de DuckDB-afvaldatabase (`afvaldb/`, tabellen `bron`, `afval_feit`, `afvalstroom_crosswalk`, `forecast`).
**Status:** ontwerp, goedgekeurd voor plan-fase.

---

## 1. Doel

Twee toevoegingen aan het afval-dashboard, in een **nieuw linkerpaneel** naast de kaart:

1. **Brondata-uitleg** — welke open bronnen de cijfers voeden, met licentie en een korte omschrijving.
2. **Data-chatbot (NL→SQL)** — de gebruiker stelt in gewone taal een vraag; de lokale Qwen vertaalt die naar een read-only DuckDB `SELECT` over de afvaldata, die wordt gevalideerd, uitgevoerd, en waarvan het resultaat in 2–3 zinnen wordt samengevat — met de gebruikte SQL zichtbaar en een bronvermelding.

Consistent met de projectlijn: open data, elke uitspraak herleidbaar (bron + de uitgevoerde query), modelmatige/indicatieve elementen gelabeld, geen schaduwregister. Spiegelt het bestaande conservatieve `datavraag`-contract (NL→SPARQL), nu als NL→SQL over DuckDB.

### Afbakening (YAGNI)
- Alleen **lezen**: read-only connectie; geen enkele mutatie mogelijk.
- Eén DuckDB-bestand (de bestaande afvaldatabase); geen nieuwe bron.
- Geen gespreksgeheugen over meerdere beurten (elke vraag staat op zichzelf); YAGNI voor nu.
- Geen nieuwe pagina — alles in `/afval`.

---

## 2. Layout (`afval.html`)

`.wrap` wordt driekoloms met flexbox:
- **Links** — nieuw paneel `aside.left` (~300px): bovenaan **Brondata**, daaronder de **Chatbot**.
- **Midden** — de kaart (`#map`, flex:1).
- **Rechts** — het bestaande paneel (`aside`, 340px): afvalstroom/jaar/indicator-filters, legenda, trend.

Op smalle schermen (`max-width: 900px`) stapelen de kolommen verticaal. De bestaande modal (AI-duiding + forecast-grafiek) blijft ongewijzigd.

---

## 3. Backend

### 3.1 Brondata-endpoint
`GET /api/afval/bronnen` → leest de `bron`-tabel uit DuckDB, verrijkt elke rij met een curated 1-regel-omschrijving (mapping `bron_id`-prefix → tekst), en levert:
```json
[{"bron_id","naam","url","licentie","type","opgehaald_op","omschrijving"}]
```
- 503 als de DB-file ontbreekt (zelfde bestandscheck als `/api/afval/forecast`).
- Nieuwe store-helper `bronnen(con) -> list[dict]`.

### 3.2 Chatbot — `usecases/afval/chat.py`
Publieke functie:
```
beantwoord(vraag: str, db_path: str, llm_base_url: str, model: str, timeout_s: float = 60.0) -> dict
```
Retourcontract (spiegelt `datavraag`):
```json
{"vraag","antwoord","sql","rijen","beschikbaar","disclaimer","vangnet","bron"}
```

**Flow:**
1. DB-file afwezig → `{... "beschikbaar": false, "antwoord": null, "sql": null, "rijen": []}`.
2. **Grounding** (`bouw_grounding(con) -> str`): dynamisch uit de DB — distinct `afvalstroom_canoniek`, distinct `regio_code`, distinct `indicator_type`, distinct `bron_id`, en het `jaar`-bereik — plus een vaste **provincie-naam↔code-map** (`PV20`–`PV31` → provincienamen) en een compacte schema-beschrijving van `afval_feit` en `forecast`. Instructie: geef **uitsluitend één** DuckDB-`SELECT` terug, geen uitleg.
3. **NL→SQL** (`genereer_sql(vraag, grounding, llm_*) -> str`): één Qwen-call; strip code-fences.
4. **Validatie** (`valideer_sql(sql) -> str` of raise): zie §4. Ongeldig → `beschikbaar: false` met een nette `antwoord`-melding en de geweigerde SQL in `sql`.
5. **Uitvoeren** (`store.run_select(con, sql) -> list[dict]`): voert de gevalideerde query uit op de **read-only** connectie die `beantwoord` één keer opent (`duckdb.connect(db_path, read_only=True)`, gedeeld met de grounding-stap), geeft rijen als dicts; fout → `beschikbaar: false`.
6. **Samenvatten** (`vat_samen(vraag, rijen, llm_*) -> str`): tweede Qwen-call die **uitsluitend** de teruggekomen rijen in 2–3 zinnen samenvat (no-hallucination); lege rijen → deterministisch "Geen resultaten voor deze vraag."
7. Retour met `antwoord`, de uitgevoerde `sql`, de `rijen`, `beschikbaar: true`, disclaimer/vangnet/bron.

### 3.3 Chat-route
`POST /api/afval/chat` body `{vraag: str}` → `chat.beantwoord(_afvaldb_path(), ...)` met de LLM-config uit `_config`. Altijd HTTP 200 met het contract (de `beschikbaar`-vlag draagt de status), behalve interne fouten.

---

## 4. SQL-veiligheid (kern)

Meerlaagse guard rond door-LLM-gegenereerde SQL over **uitsluitend open, publieke cijfers**:

1. **Read-only connectie** — `duckdb.connect(db_path, read_only=True)`. Mutaties zijn onmogelijk, ongeacht de query.
2. **Statement-validatie** (`valideer_sql`):
   - Precies **één** statement: geen `;` (behalve optioneel een enkele trailing `;` die wordt gestript); meerdere statements → weigeren.
   - Moet (na strippen/lowercasing) beginnen met `select` of `with`.
   - **Verboden trefwoorden** (woordgrens, case-insensitief): `insert, update, delete, drop, alter, create, attach, copy, pragma, install, load, export, replace`. Aanwezig → weigeren.
3. **LIMIT afdwingen** — bevat de query geen `limit`, dan wordt ` LIMIT 200` toegevoegd; een hogere limit wordt naar 200 verlaagd.
4. Bij weigering: niets uitvoeren; `antwoord` = "Deze vraag kon niet veilig naar een query worden vertaald." en de geweigerde SQL staat in `sql` voor transparantie.

De guard staat expliciet ook al is de connectie read-only (defence-in-depth) en houdt resultaten begrensd.

---

## 5. Frontend-gedrag

### Brondata-paneel
Bij laden: `GET /api/afval/bronnen` → render een korte kop ("Deze cijfers komen uit open bronnen:") + per bron een blokje met naam, `licentie`, `type` en `omschrijving`, met een link naar `url` (nieuw tabblad, `rel="noopener"`). Waarden via `textContent`/escaping (geen raw innerHTML van bronvelden).

### Chatbot
Invoerveld + verzendknop + gespreksvenster. Bij verzenden: toon de vraag, toon "denkt na…", `POST /api/afval/chat`. Antwoord: render het `antwoord`, een inklapbare **"toon query"** met de uitgevoerde `sql` (monospace), en een klein bron/disclaimer-regeltje. `beschikbaar:false` → toon de nette melding. Alle server-strings via `textContent`/escaping; de SQL in een `<pre>` via `textContent`.

---

## 6. Foutafhandeling

- DB-file afwezig → `/api/afval/bronnen` 503; `chat` geeft `beschikbaar:false`.
- Qwen offline → SQL-generatie of samenvatting faalt → `beschikbaar:false`, nette melding.
- Ongeldige/gevaarlijke SQL → geweigerd, niets uitgevoerd (zie §4).
- SQL-uitvoerfout (bijv. onbekende kolom) → `beschikbaar:false`, de (geweigerde/mislukte) SQL blijft zichtbaar.
- Lege resultaten → deterministisch "Geen resultaten".

---

## 7. Testen (offline)

- **Validatie** (`valideer_sql`): accepteert `SELECT …`/`WITH …`; weigert `INSERT/UPDATE/DELETE/DROP/ALTER/CREATE/ATTACH/COPY/PRAGMA`; weigert meerdere statements (`;`); dwingt `LIMIT` af (toevoegen + verlagen > 200).
- **run_select**: op een tmp-DuckDB met seed-rijen geeft een `SELECT` de verwachte rijen; een mutatie faalt (read-only).
- **Grounding**: `bouw_grounding` bevat de schema-namen, de distinct-waarden uit de seed-DB en de provincie-map.
- **beantwoord**: LLM gemockt voor NL→SQL én samenvatting → correct contract met `sql`, `rijen`, `antwoord`, `beschikbaar:true`; gevaarlijke gegenereerde SQL → `beschikbaar:false` en niets uitgevoerd; DB-afwezig → `beschikbaar:false`.
- **Endpoints**: `GET /api/afval/bronnen` (store gemockt) en `POST /api/afval/chat` (service gemockt) leveren de juiste vorm; bronnen 503 bij afwezige DB.

---

## 8. Componenten & bestanden

| Component | Pad | Taak |
|---|---|---|
| Store-helpers | `afvaldb/store.py` | `bronnen(con)`, `open_readonly(db_path)`, `run_select(con, sql)`. |
| SQL-validatie | `usecases/afval/chat.py` | `valideer_sql(sql) -> str`. |
| Grounding | `usecases/afval/chat.py` | `bouw_grounding(con) -> str` + provincie-map. |
| Chatbot | `usecases/afval/chat.py` | `genereer_sql`, `vat_samen`, `beantwoord`. |
| Routes | `geluidsmeter/api.py` | `GET /api/afval/bronnen`, `POST /api/afval/chat`. |
| Frontend | `static/afval.html` | linkerpaneel: brondata + chatbot; driekoloms layout. |

---

## 9. Herkomst & eerlijkheid

- Brondata-paneel toont per bron licentie + link.
- Chat-antwoord bevat: de uitgevoerde SQL (herleidbaar), `bron` ("CBS 83558NED, CLO, Afvalfonds, LMA/RWS via de afvaldatabase"), en `disclaimer`/`vangnet` ("Indicatief; open proxy voor het gesloten LMA/AMICE. Raadpleeg de bronhouder voor officiele cijfers.").
- Geen mutaties; read-only over open data.
