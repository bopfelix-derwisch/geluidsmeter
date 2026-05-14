# Sprint 6 — iPhone Geluidsmeting

**Datum:** 2026-05-14
**Status:** Goedgekeurd

---

## Doel

Mobiele geluidsmetingen via iPhone Safari insturen naar de Jetson en permanent tonen op de publieke kaart. Eén gebruiker (of kleine groep vertrouwden), token-authenticatie.

---

## Architectuur

```
iPhone Safari (/meten?token=xxx&offset=90.7)
  → Web Audio API: dBFS meten (live)
  → offset toepassen client-side → dB(A)
  → Geolocation API: GPS ophalen
  → POST /api/submit  { dba, lat, lon, naam, token }

Jetson API (api.py)
  → token valideren tegen config.mobile.submit_token
  → opslaan in mobile_measurements.jsonl (NVMe)
  → 201 Created + { id, accepted: true }

GET /api/locations (uitgebreid)
  → Jetson fixed meting (bestaande logica)
  → + alle regels uit mobile_measurements.jsonl
  → gecombineerde lijst

GET /public
  → Jetson: groen/oranje cirkelmarker
  → iPhone-metingen: blauwe cirkelmarkers
  → locatiekaarten tonen label "📱 Mobiele meting"
```

---

## Componenten

### 1. `POST /api/submit` — nieuw endpoint in `api.py`

**Request:**
```json
{
  "dba": 63.2,
  "lat": 52.079,
  "lon": 4.315,
  "naam": "Binnenhof, Den Haag"
}
```

Header: `Authorization: Bearer <submit_token>`

**Validatie:**
- Token klopt niet → 401
- `dba` is `null` (ongekalibreerd) → opslaan met `dba: null`, `norm_status: null`
- `lat`/`lon` ontbreken → 422
- `naam` leeg → default `"Mobiele meting"`

**Opslag (JSONL — één JSON-object per regel):**
```json
{
  "id": "uuid4",
  "ts": "2026-05-14T13:45:00Z",
  "lat": 52.079,
  "lon": 4.315,
  "naam": "Binnenhof, Den Haag",
  "dba": 63.2,
  "source": "mobile",
  "kwaliteit": "prototype_indicatief_niet_juridisch"
}
```

**Response 201:**
```json
{ "id": "uuid4", "accepted": true }
```

---

### 2. `GET /api/locations` — uitgebreid

Bestaande Jetson-logica blijft intact. Daarna worden alle regels uit `mobile_measurements.jsonl` gelezen en omgezet naar hetzelfde formaat als de Jetson-entry, met twee extra velden:

```json
{
  "id": "uuid4",
  "naam": "Binnenhof, Den Haag",
  "lat": 52.079,
  "lon": 4.315,
  "precision_m": 20,
  "lden_gemeten": 63.2,
  "rivm_lden": null,
  "norm_lden": 48,
  "norm_status": "boven_norm",
  "laatste_meting": "2026-05-14T13:45:00Z",
  "kwaliteit": "prototype_indicatief_niet_juridisch",
  "source": "mobile"
}
```

`rivm_lden` is altijd `null` voor mobiele metingen (wisselende locaties, geen lookup).
`precision_m` is 20 voor mobiele metingen (GPS-nauwkeurigheid telefoon).

---

### 3. `GET /meten` — nieuw endpoint in `api.py`

Serveert `static/meten.html`, zelfde patroon als `GET /public`.

---

### 4. `src/geluidsmeter/static/meten.html` — mobiele meetpagina

**URL-parameters:**
- `token` — wordt bij submit meegestuurd als Bearer-token
- `offset` — calibratie-offset in dB (default: 0, dan dba=null)

**Schermopbouw:**
```
┌─────────────────────────────────┐
│  Geluidsmeting                  │
│  [naam invoerveld]              │
│                                 │
│         52.3                    │
│         dB(A)                   │
│  ████████░░░░  [norm: 48 dB]    │  ← live balk, rood boven norm
│                                 │
│  📍 GPS: 52.079, 4.315  [✓]    │  ← grijs + spinner tot GPS bekend
│                                 │
│  [ Insturen ]                   │  ← disabled totdat GPS beschikbaar
│                                 │
│  ✓ Meting verstuurd (14:32)     │  ← zichtbaar na succesvolle submit
└─────────────────────────────────┘
```

**Gedrag:**
- Microfoon start direct bij laden (na toestemming)
- GPS wordt opgevraagd bij laden
- "Insturen" wordt enabled zodra GPS een fix heeft
- Na submit: bevestiging tonen, knop tijdelijk uitschakelen (voorkomt dubbel insturen)
- Als `offset` ontbreekt of 0 is: `dba` wordt `null` in de payload, disclaimer zichtbaar

**Geen token in URL:** knop disabled, melding "Geen token — gebruik de link die je gekregen hebt."

---

### 5. `src/geluidsmeter/static/public.html` — uitgebreid

**Kaart:**
- Jetson: groen (`#22c55e`) of oranje (`#f97316`) cirkelmarker (bestaand)
- Mobiele meting: blauw (`#3b82f6`) cirkelmarker

**Locatiekaarten:**
- Mobiele metingen tonen label `📱 Mobiele meting` onder de naam
- Zelfde grid (gemeten / norm / status) als Jetson-kaarten
- `rivm_lden`-vak toont "—" bij mobiele metingen
- Disclaimer "ongekalibreerd" bij `lden_gemeten === null` (bestaande logica)

---

### 6. `core/config.yaml` — uitbreiding

```yaml
mobile:
  submit_token: "vervang-dit-met-een-wachtwoord"
  measurements_file: "/mnt/nvme/geluidsmeter/data/mobile_measurements.jsonl"
```

Token wordt ingesteld door de gebruiker vóór deployment. Niet committen als de waarde echt is (maar het bestand staat al in git, alleen de waarde is gevoelig).

---

## Buiten scope Sprint 6

- Historische grafiek per mobiele locatie
- Meerdere inzenders met eigen accounts
- Groeperen van nabije metingen (clustering)
- Push-notificaties
- Offline/PWA-functionaliteit
