# Sprint 5 Demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publieke webpagina op `geluid.felixisfelix.com` die meetlocaties met geluidsniveaus toont voor niet-technisch publiek, via Cloudflare Tunnel op de bestaande FastAPI-service.

**Architecture:** Cloudflare Tunnel (`cloudflared` als systemd-service) koppelt `geluid.felixisfelix.com` aan `localhost:8792`. Twee nieuwe endpoints: `GET /api/locations` (JSON, multi-locatie-klaar) en `GET /public` (HTML-landingspagina in gewone taal). De pagina haalt `/api/locations` op en toont markers op een Leaflet-kaart + locatiekaarten per meetpunt.

**Tech Stack:** FastAPI, Leaflet 1.9.4, cloudflared (arm64), systemd

---

## Bestaande codebase (context)

- `src/geluidsmeter/api.py` — FastAPI app, endpoints `/summary`, `/dashboard`, `/geodata/*`
- `src/geluidsmeter/static/dashboard.html` — bestaand technisch dashboard
- `src/geluidsmeter/aggregate.py` — bevat `_round_location(lat, lon, precision_m)`
- `src/geluidsmeter/source_match.py` — bevat `get_rivm_lden(location, gdf)`
- `src/geluidsmeter/config.py` — `load_config()`, `load_private_location(config)`
- `core/config.yaml` — centrale config, incl. `location.public_location_precision_m: 100`
- `tests/test_source_match.py` — bestaande tests, run met `PYTHONPATH=src .venv/bin/pytest tests/ -v`
- `systemd/geluidsmeter-api.service` — voorbeeld voor nieuwe systemd unit

---

## Bestandsstructuur

| Bestand | Actie | Verantwoordelijkheid |
|---------|-------|----------------------|
| `core/config.yaml` | Modify | `location.public_name` en `location.public_id` toevoegen |
| `src/geluidsmeter/api.py` | Modify | `_location_entry()` helper, `/api/locations`, `/public` endpoints |
| `src/geluidsmeter/static/public.html` | Create | Publieke landingspagina (gewone taal, Leaflet, locatiekaarten) |
| `tests/test_api_locations.py` | Create | Test voor `_location_entry()` helper |
| `systemd/geluidsmeter-tunnel.service` | Create | Cloudflare Tunnel systemd unit |

---

## Task 1: Config uitbreiden met publieke locatienaam

**Files:**
- Modify: `core/config.yaml`

- [ ] **Stap 1: Voeg `public_name` en `public_id` toe aan `location` sectie**

Vervang in `core/config.yaml`:
```yaml
location:
  private_location_file: "core/location_private.yaml"
  publish_exact_location: false
  public_location_precision_m: 100
  crs: "EPSG:4326"
```
Door:
```yaml
location:
  private_location_file: "core/location_private.yaml"
  publish_exact_location: false
  public_location_precision_m: 100
  public_name: "Archipelbuurt, Den Haag"
  public_id: "archipelbuurt-denhaag"
  crs: "EPSG:4326"
```

- [ ] **Stap 2: Commit**

```bash
git add core/config.yaml
git commit -m "feat(sprint5): public_name en public_id in location config"
```

---

## Task 2: `_location_entry()` helper + test

**Files:**
- Modify: `src/geluidsmeter/api.py`
- Create: `tests/test_api_locations.py`

- [ ] **Stap 1: Schrijf de falende test**

Maak `tests/test_api_locations.py`:

```python
from geluidsmeter.api import _location_entry


def _make_config(public_name="Testbuurt", public_id="test-id"):
    return {
        "location": {
            "public_location_precision_m": 100,
            "public_name": public_name,
            "public_id": public_id,
        },
        "project": {"quality_label": "prototype_indicatief_niet_juridisch"},
    }


def test_location_entry_boven_norm():
    entry = _location_entry(
        config=_make_config(),
        pub_lat=52.08,
        pub_lon=4.29,
        rms_dba=55.0,
        rivm_lden=55.5,
    )
    assert entry["norm_status"] == "boven_norm"
    assert entry["lden_gemeten"] == 55.0
    assert entry["rivm_lden"] == 55.5
    assert entry["norm_lden"] == 48
    assert entry["laatste_meting"] is not None


def test_location_entry_binnen_norm():
    entry = _location_entry(
        config=_make_config(),
        pub_lat=52.08,
        pub_lon=4.29,
        rms_dba=44.0,
        rivm_lden=55.5,
    )
    assert entry["norm_status"] == "binnen_norm"


def test_location_entry_geen_meting():
    entry = _location_entry(
        config=_make_config(),
        pub_lat=52.08,
        pub_lon=4.29,
        rms_dba=None,
        rivm_lden=None,
    )
    assert entry["norm_status"] is None
    assert entry["lden_gemeten"] is None
    assert entry["laatste_meting"] is None


def test_location_entry_velden():
    entry = _location_entry(
        config=_make_config(public_name="Archipelbuurt, Den Haag", public_id="archipelbuurt-denhaag"),
        pub_lat=52.08,
        pub_lon=4.29,
        rms_dba=50.0,
        rivm_lden=55.5,
    )
    assert entry["id"] == "archipelbuurt-denhaag"
    assert entry["naam"] == "Archipelbuurt, Den Haag"
    assert entry["lat"] == 52.08
    assert entry["lon"] == 4.29
    assert entry["precision_m"] == 100
    assert entry["kwaliteit"] == "prototype_indicatief_niet_juridisch"
```

- [ ] **Stap 2: Run test — verwacht FAIL**

```bash
PYTHONPATH=src .venv/bin/pytest tests/test_api_locations.py -v
```

Verwacht: `ImportError: cannot import name '_location_entry' from 'geluidsmeter.api'`

- [ ] **Stap 3: Implementeer `_location_entry()` in `api.py`**

Voeg toe in `src/geluidsmeter/api.py`, direct na de imports:

```python
def _location_entry(
    config: dict,
    pub_lat: float,
    pub_lon: float,
    rms_dba: float | None,
    rivm_lden: float | None,
) -> dict:
    norm_lden = 48
    norm_status = None
    if rms_dba is not None:
        norm_status = "binnen_norm" if rms_dba <= norm_lden else "boven_norm"
    loc_cfg = config.get("location", {})
    return {
        "id": loc_cfg.get("public_id", "meetlocatie"),
        "naam": loc_cfg.get("public_name", "Meetlocatie"),
        "lat": pub_lat,
        "lon": pub_lon,
        "precision_m": loc_cfg.get("public_location_precision_m", 100),
        "lden_gemeten": rms_dba,
        "rivm_lden": rivm_lden,
        "norm_lden": norm_lden,
        "norm_status": norm_status,
        "laatste_meting": datetime.now(timezone.utc).isoformat() if rms_dba is not None else None,
        "kwaliteit": config.get("project", {}).get("quality_label", "prototype_indicatief_niet_juridisch"),
    }
```

- [ ] **Stap 4: Run test — verwacht PASS**

```bash
PYTHONPATH=src .venv/bin/pytest tests/test_api_locations.py -v
```

Verwacht: 4 tests PASSED

- [ ] **Stap 5: Commit**

```bash
git add tests/test_api_locations.py src/geluidsmeter/api.py
git commit -m "feat(sprint5): _location_entry helper + tests"
```

---

## Task 3: `GET /api/locations` endpoint

**Files:**
- Modify: `src/geluidsmeter/api.py`

- [ ] **Stap 1: Voeg het endpoint toe in `api.py`**

Voeg toe direct vóór `@app.get("/geodata/rivm")`:

```python
@app.get("/api/locations")
def api_locations():
    offset = _config.get("measurement", {}).get("calibration_offset_db", 0)
    feature = _latest_feature()
    rms_dba = round(feature["rms_dbfs"] + offset, 1) if feature else None

    loc = load_private_location(_config)
    precision_m = _config.get("location", {}).get("public_location_precision_m", 100)
    pub_lat, pub_lon = _round_location(loc["lat"], loc["lon"], precision_m)

    rivm_lden = None
    rivm_path = Path(_config["outputs"]["external_dir"]) / "rivm" / "geluid_buurt.geojson"
    if rivm_path.exists():
        rivm_gdf = gpd.read_file(rivm_path)
        rivm_lden = get_rivm_lden(ShapelyPoint(loc["lon"], loc["lat"]), rivm_gdf)

    return [_location_entry(_config, pub_lat, pub_lon, rms_dba, rivm_lden)]
```

- [ ] **Stap 2: Test handmatig**

Start de API:
```bash
pkill -f "uvicorn geluidsmeter" 2>/dev/null; sleep 1
PYTHONPATH=src .venv/bin/uvicorn geluidsmeter.api:app --host 0.0.0.0 --port 8792 &
```

Controleer response:
```bash
curl -s http://localhost:8792/api/locations | python3 -m json.tool
```

Verwacht: JSON-array met één object dat `id`, `naam`, `lat`, `lon`, `lden_gemeten`, `rivm_lden`, `norm_lden`, `norm_status`, `kwaliteit` bevat.

- [ ] **Stap 3: Commit**

```bash
git add src/geluidsmeter/api.py
git commit -m "feat(sprint5): GET /api/locations endpoint"
```

---

## Task 4: `public.html` + `GET /public` endpoint

**Files:**
- Create: `src/geluidsmeter/static/public.html`
- Modify: `src/geluidsmeter/api.py`

- [ ] **Stap 1: Maak `public.html` aan**

Maak `src/geluidsmeter/static/public.html`:

```html
<!DOCTYPE html>
<html lang="nl">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Geluidsmeting Nederland</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: system-ui, sans-serif; background: #f8fafc; color: #1e293b; max-width: 900px; margin: 0 auto; padding: 24px 16px; }
    h1 { font-size: 1.4rem; font-weight: 700; margin-bottom: 4px; }
    .subtitle { color: #64748b; font-size: 0.9rem; margin-bottom: 24px; }
    #map { height: 300px; border-radius: 8px; margin-bottom: 24px; border: 1px solid #e2e8f0; }
    .locatie { background: white; border-radius: 8px; padding: 20px; margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,.08); border-left: 4px solid #e2e8f0; }
    .locatie.boven-norm { border-left-color: #f97316; }
    .locatie.binnen-norm { border-left-color: #22c55e; }
    .locatie h2 { font-size: 1.05rem; margin-bottom: 14px; color: #0f172a; }
    .metingen { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px; margin-bottom: 14px; }
    @media (max-width: 600px) { .metingen { grid-template-columns: 1fr; } }
    .meting { background: #f8fafc; border-radius: 6px; padding: 10px 12px; }
    .meting .label { font-size: 0.72rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: 4px; }
    .meting .waarde { font-size: 1.4rem; font-weight: 700; color: #1e293b; }
    .status-tekst { font-size: 0.9rem; line-height: 1.5; }
    .boven { color: #c2410c; }
    .binnen { color: #15803d; }
    .tijdstip { font-size: 0.75rem; color: #94a3b8; margin-top: 6px; }
    footer { margin-top: 40px; font-size: 0.78rem; color: #94a3b8; border-top: 1px solid #e2e8f0; padding-top: 16px; line-height: 1.6; }
    .uitleg { background: white; border-radius: 8px; padding: 20px; margin-bottom: 24px; font-size: 0.9rem; line-height: 1.7; color: #334155; }
    .uitleg p { margin-bottom: 8px; }
    .uitleg p:last-child { margin-bottom: 0; }
  </style>
</head>
<body>

<h1>Geluidsmeting Nederland</h1>
<p class="subtitle">Onafhankelijke metingen van omgevingsgeluid op straatniveau</p>

<div id="map"></div>
<div id="locaties"></div>

<div class="uitleg">
  <p>Met een microfoon op een vaste locatie meten we continu het omgevingsgeluid in decibel.</p>
  <p>De gemeten waarde vergelijken we met de referentiewaarde van het RIVM voor de buurt en de wettelijke norm uit de Omgevingswet (48 dB(A) voor wonen overdag).</p>
  <p>Dit is een onafhankelijk burgeronderzoek — de waarden zijn indicatief en niet juridisch bindend.</p>
</div>

<footer>
  ⚠ <strong>Indicatief — niet juridisch bruikbaar.</strong> Consumentenhardware zonder officiële kalibratie.
  Bronnen: RIVM Digibeter (referentiewaarden buurt), Omgevingswet art. 5.67 (normen).
</footer>

<script>
const map = L.map("map").setView([52.3, 5.0], 7);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  attribution: "© OpenStreetMap"
}).addTo(map);

async function init() {
  const locs = await fetch("/api/locations").then(r => r.json());
  const container = document.getElementById("locaties");

  locs.forEach(loc => {
    const bovenNorm = loc.norm_status === "boven_norm";
    const kleur = bovenNorm ? "#f97316" : "#22c55e";

    const marker = L.circleMarker([loc.lat, loc.lon], {
      radius: 10, color: kleur, fillColor: kleur, fillOpacity: 0.85, weight: 2
    }).addTo(map);
    marker.bindPopup(`<b>${loc.naam}</b><br>Gemeten: ${loc.lden_gemeten ?? "—"} dB(A)`);

    const statusTekst = loc.norm_status === null
      ? "Nog geen meting beschikbaar."
      : bovenNorm
        ? "De gemeten waarde ligt <strong>boven</strong> de wettelijke norm voor wonen."
        : "De gemeten waarde ligt <strong>binnen</strong> de wettelijke norm voor wonen.";

    const tijdstip = loc.laatste_meting
      ? new Date(loc.laatste_meting).toLocaleString("nl-NL", {
          hour: "2-digit", minute: "2-digit", day: "numeric", month: "long", year: "numeric"
        })
      : "onbekend";

    const div = document.createElement("div");
    div.className = `locatie ${bovenNorm ? "boven-norm" : loc.norm_status ? "binnen-norm" : ""}`;
    div.innerHTML = `
      <h2>📍 ${loc.naam}</h2>
      <div class="metingen">
        <div class="meting">
          <div class="label">Gemeten geluidsniveau</div>
          <div class="waarde">${loc.lden_gemeten !== null ? loc.lden_gemeten + " dB(A)" : "—"}</div>
        </div>
        <div class="meting">
          <div class="label">Referentie buurt (RIVM)</div>
          <div class="waarde">${loc.rivm_lden !== null ? loc.rivm_lden + " dB(A)" : "—"}</div>
        </div>
        <div class="meting">
          <div class="label">Wettelijke norm</div>
          <div class="waarde">${loc.norm_lden} dB(A)</div>
        </div>
      </div>
      <div class="status-tekst ${bovenNorm ? "boven" : "binnen"}">${statusTekst}</div>
      <div class="tijdstip">Laatste meting: ${tijdstip}</div>
    `;
    container.appendChild(div);
  });
}
init();
</script>
</body>
</html>
```

- [ ] **Stap 2: Voeg `GET /public` toe in `api.py`**

Voeg toe aan het einde van `src/geluidsmeter/api.py`:

```python
@app.get("/public", response_class=HTMLResponse)
def public_page():
    return (_static_dir / "public.html").read_text()
```

- [ ] **Stap 3: Test in browser**

```bash
pkill -f "uvicorn geluidsmeter" 2>/dev/null; sleep 1
PYTHONPATH=src .venv/bin/uvicorn geluidsmeter.api:app --host 0.0.0.0 --port 8792 &
```

Open: `http://192.168.178.229:8792/public`

Verwacht: pagina met NL-kaart, locatiekaart voor Archipelbuurt met getallen en statustekst in gewone taal.

- [ ] **Stap 4: Alle tests draaien**

```bash
PYTHONPATH=src .venv/bin/pytest tests/ -v
```

Verwacht: alle tests (incl. test_source_match) PASS.

- [ ] **Stap 5: Commit**

```bash
git add src/geluidsmeter/static/public.html src/geluidsmeter/api.py
git commit -m "feat(sprint5): /public landingspagina + GET /public endpoint"
```

---

## Task 5: Cloudflare Tunnel installeren

**Files:**
- Geen bestanden in repo — installatie op systeem

- [ ] **Stap 1: Download en installeer cloudflared (arm64)**

```bash
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64 -o /tmp/cloudflared
sudo install /tmp/cloudflared /usr/local/bin/cloudflared
cloudflared --version
```

Verwacht output: `cloudflared version 20xx.x.x`

- [ ] **Stap 2: Authenticeer met Cloudflare-account**

```bash
cloudflared tunnel login
```

Dit opent een browser-URL. Ga naar de URL, log in op het Cloudflare-account van felixisfelix.com en selecteer het domein `felixisfelix.com`. Na autorisatie verschijnt `~/.cloudflared/cert.pem`.

Controleer:
```bash
ls -la ~/.cloudflared/cert.pem
```

Verwacht: bestand bestaat.

- [ ] **Stap 3: Maak de tunnel aan**

```bash
cloudflared tunnel create geluidsmeter
```

Verwacht output:
```
Created tunnel geluidsmeter with id <UUID>
```

Noteer de UUID. Controleer:
```bash
ls ~/.cloudflared/*.json
```

Verwacht: één `<UUID>.json` credentials-bestand.

- [ ] **Stap 4: Maak tunnel config aan**

Vervang `<UUID>` door de tunnel-ID uit stap 3:

```bash
cat > ~/.cloudflared/config.yml << EOF
tunnel: <UUID>
credentials-file: /home/bob/.cloudflared/<UUID>.json

ingress:
  - hostname: geluid.felixisfelix.com
    service: http://localhost:8792
  - service: http_status:404
EOF
```

- [ ] **Stap 5: Koppel DNS aan de tunnel**

```bash
cloudflared tunnel route dns geluidsmeter geluid.felixisfelix.com
```

Verwacht: `Added CNAME geluid.felixisfelix.com which will route to this tunnel`

- [ ] **Stap 6: Test de tunnel handmatig**

```bash
cloudflared tunnel run geluidsmeter &
sleep 5
curl -s https://geluid.felixisfelix.com/health | python3 -m json.tool
```

Verwacht: `{"status": "ok", ...}`

Stop daarna de handmatige tunnel:
```bash
pkill cloudflared
```

---

## Task 6: Systemd tunnel service

**Files:**
- Create: `systemd/geluidsmeter-tunnel.service`

- [ ] **Stap 1: Maak de systemd unit aan**

Maak `systemd/geluidsmeter-tunnel.service`:

```ini
[Unit]
Description=Geluidsmeter — Cloudflare Tunnel (geluid.felixisfelix.com)
After=network-online.target geluidsmeter-api.service
Wants=network-online.target
Requires=geluidsmeter-api.service

[Service]
User=bob
ExecStart=/usr/local/bin/cloudflared tunnel --config /home/bob/.cloudflared/config.yml run
Restart=on-failure
RestartSec=15

[Install]
WantedBy=multi-user.target
```

- [ ] **Stap 2: Installeer en start de service**

```bash
sudo cp systemd/geluidsmeter-tunnel.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now geluidsmeter-tunnel.service
```

- [ ] **Stap 3: Controleer status**

```bash
sudo systemctl status geluidsmeter-tunnel.service
```

Verwacht: `Active: active (running)`

- [ ] **Stap 4: Verifieer publieke URL**

```bash
curl -s https://geluid.felixisfelix.com/health
curl -s https://geluid.felixisfelix.com/api/locations | python3 -m json.tool
```

Verwacht: gezonde responses van beide endpoints.

Open in browser: `https://geluid.felixisfelix.com/public`

- [ ] **Stap 5: Commit systemd unit**

```bash
git add systemd/geluidsmeter-tunnel.service
git commit -m "feat(sprint5): Cloudflare Tunnel systemd service voor geluid.felixisfelix.com"
git push origin master
```

---

## Task 7: CLAUDE.md sprint status bijwerken

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Stap 1: Markeer Sprint 5 als afgerond in CLAUDE.md**

Wijzig de regel:
```
- ⏭️ **Sprint 5:** demo
```
naar:
```
- ✅ **Sprint 5:** publieke demo — geluid.felixisfelix.com via Cloudflare Tunnel
```

- [ ] **Stap 2: Commit en push**

```bash
git add CLAUDE.md
git commit -m "docs: Sprint 5 afgerond"
git push origin master
```
