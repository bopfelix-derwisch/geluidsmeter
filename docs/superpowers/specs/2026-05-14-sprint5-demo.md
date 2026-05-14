# Sprint 5 — Publieke Demo: Geluidsmeting Nederland

**Datum:** 2026-05-14
**Status:** Goedgekeurd

---

## Doel

Een publiek toegankelijke webpagina op `geluid.felixisfelix.com` die het geluidsniveau op straatniveau toont voor niet-technisch publiek (buren, gemeente, pers). De pagina is opgezet als meetnet — nu één vaste locatie (Archipelbuurt, Den Haag), straks uitbreidbaar met iPhone-metingen op andere locaties in NL.

---

## Architectuur

```
geluid.felixisfelix.com (Cloudflare Tunnel)
  → cloudflared (systemd service op orin3)
  → localhost:8792 (FastAPI)
    GET /public          → publieke HTML-landingspagina
    GET /api/locations   → JSON met alle meetlocaties + laatste waarden
```

`cloudflared` draait als systemd-service naast de bestaande `geluidsmeter-api.service`. De tunnel verbindt via Cloudflare's netwerk — geen port forwarding nodig.

---

## Componenten

### 1. `GET /api/locations` — nieuw endpoint in `api.py`

Retourneert een lijst van meetlocaties met hun laatste waarden. Structuur is direct geschikt voor meerdere locaties (iPhone-metingen Sprint 6+).

```json
[
  {
    "id": "archipelbuurt-denhaag",
    "naam": "Archipelbuurt, Den Haag",
    "lat": 52.08,
    "lon": 4.29,
    "precision_m": 100,
    "lden_gemeten": -42.3,
    "rivm_lden": 55.5,
    "norm_lden": 48,
    "norm_status": "boven_norm",
    "laatste_meting": "2026-05-14T10:23:00Z",
    "kwaliteit": "prototype_indicatief_niet_juridisch"
  }
]
```

`lden_gemeten` is `rms_dba_latest` uit de bestaande `/summary` logica. `rivm_lden` en `norm_lden` komen uit bestaande source_match en config.

### 2. `GET /public` — publieke HTML-landingspagina

Statische HTML geserveerd door FastAPI, zelfde patroon als `/dashboard`.

**Layout:**

```
┌─────────────────────────────────────────────────────┐
│  Geluidsmeting Nederland                             │
│  Onafhankelijke metingen op straatniveau             │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│  Kaart — meetlocaties (Leaflet, heel NL)             │
│  Marker per locatie: groen = binnen norm             │
│                      oranje = boven norm             │
└─────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────┐
│ Per locatie (kaart-klik of lijst):                    │
│   Naam buurt / stad                                   │
│   Gemeten: XX dB(A)   Referentie: XX dB(A) (RIVM)    │
│   Norm: 48 dB(A) (Omgevingswet)                      │
│   Status: "De gemeten waarde ligt [binnen / boven]    │
│            de wettelijke norm voor wonen."            │
│   Laatste meting: vandaag HH:MM                       │
└──────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│ Wat meten we?                                        │
│ [3 zinnen gewone taal — zie inhoud hieronder]        │
│                                                      │
│ ⚠ Indicatief — niet juridisch bruikbaar              │
└─────────────────────────────────────────────────────┘
```

**Uitleg-tekst (3 zinnen):**
> "Met een microfoon op een vaste locatie meten we continu het omgevingsgeluid. De gemeten waarde vergelijken we met de RIVM-referentiewaarde voor de buurt en de wettelijke norm uit de Omgevingswet (48 dB(A) voor wonen). Dit is een onafhankelijk burgeronderzoek — de waarden zijn indicatief en niet juridisch bindend."

**Taalregels:**
- Geen technische termen (geen dBFS, RMS, JSONL)
- "Gemeten geluidsniveau" in plaats van rms_dba
- Norm-status in volzinnen, niet als badge/code
- Kwaliteitslabel altijd zichtbaar onderaan

### 3. Cloudflare Tunnel — `systemd/geluidsmeter-tunnel.service`

- `cloudflared` installeren via apt (arm64 deb van Cloudflare)
- Tunnel aanmaken met bestaand CF-account (API-token uit Derwisch `.env`)
- Hostname: `geluid.felixisfelix.com` → `http://localhost:8792`
- Credentials opgeslagen in `~/.cloudflared/` (niet in git)
- Systemd unit enabled + started, start automatisch bij reboot

---

## Implementatievolgorde

1. `cloudflared` installeren + tunnel aanmaken
2. `systemd/geluidsmeter-tunnel.service` aanmaken + enablen
3. `/api/locations` endpoint in `api.py`
4. `src/geluidsmeter/static/public.html` aanmaken
5. `GET /public` endpoint in `api.py`
6. Testen op `geluid.felixisfelix.com`
7. Commit + push

---

## Buiten scope Sprint 5

- iPhone-metingen insturen (Sprint 6)
- Authenticatie / admin-interface
- Automatische kalibratie
- Historische data per locatie op publieke pagina
- Meerdere talen
