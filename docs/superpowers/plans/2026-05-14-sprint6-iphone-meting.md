# Sprint 6 — iPhone Meting Implementatieplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** iPhone-metingen via een mobiele webpagina insturen naar de Jetson en permanent tonen op de publieke kaart.

**Architecture:** Een nieuwe `POST /api/submit` endpoint slaat mobiele metingen op als JSONL op de NVMe. `GET /api/locations` wordt uitgebreid zodat het Jetson- én iPhone-metingen retourneert. Een nieuwe mobiele webpagina op `/meten` gebruikt Web Audio API + Geolocation API in Safari.

**Tech Stack:** FastAPI, Pydantic, Python 3.10+, Web Audio API, Geolocation API, Leaflet.js. Tests met pytest + fastapi.testclient (httpx).

---

## Codebase context

```
/home/bob/Geluidsmeter/
  src/geluidsmeter/
    api.py          ← hoofd FastAPI app — hier komen de meeste wijzigingen
    config.py       ← load_config() laadt core/config.yaml
    static/
      public.html   ← publieke kaartpagina — uitbreiden voor mobiele markers
      meten.html    ← NIEUW — mobiele meetpagina
  core/config.yaml  ← configuratie — mobile sectie toevoegen
  tests/
    test_api_locations.py  ← bestaande tests — niet aanraken
    test_api_submit.py     ← NIEUW
  requirements.txt         ← httpx toevoegen
```

**Bestaande `api.py` structuur (relevant):**
- `_config: dict` — module-level global, geladen in `startup()`
- `_location_entry(config, pub_lat, pub_lon, rms_dba, rivm_lden) -> dict` — bouwt Jetson-locatie-entry
- `GET /api/locations` — retourneert `[_location_entry(...)]`
- `GET /public` — serveert `static/public.html`

**Tests draaien met:**
```bash
cd /home/bob/Geluidsmeter
PYTHONPATH=src .venv/bin/pytest tests/ -v
```

---

## Bestandsoverzicht

| Bestand | Actie |
|---|---|
| `requirements.txt` | httpx toevoegen |
| `core/config.yaml` | `mobile` sectie toevoegen |
| `src/geluidsmeter/api.py` | `_mobile_location_entries()`, `POST /api/submit`, `GET /meten`, `GET /api/locations` uitbreiden, `source` aan Jetson-entry |
| `src/geluidsmeter/static/meten.html` | NIEUW — mobiele meetpagina |
| `src/geluidsmeter/static/public.html` | blauwe markers + mobile label |
| `tests/test_api_submit.py` | NIEUW — 7 tests |

---

## Task 1: httpx + config

**Files:**
- Modify: `requirements.txt`
- Modify: `core/config.yaml`

- [ ] **Stap 1: httpx toevoegen aan requirements.txt**

Voeg `httpx` toe na `requests`:

```
requests
httpx
aiofiles
```

- [ ] **Stap 2: installeer httpx in de venv**

```bash
cd /home/bob/Geluidsmeter
.venv/bin/pip install httpx
```

Verwacht: `Successfully installed httpx-...`

- [ ] **Stap 3: mobile sectie toevoegen aan core/config.yaml**

Voeg toe aan het einde van `core/config.yaml`, vóór de laatste regel:

```yaml
mobile:
  submit_token: "geluidsmeter-mobiel"   # verander dit naar een echt wachtwoord
  measurements_file: "/mnt/nvme/geluidsmeter/data/mobile_measurements.jsonl"
```

Het resultaat van de `mobile` sectie in `config.yaml`:
```yaml
mobile:
  submit_token: "geluidsmeter-mobiel"
  measurements_file: "/mnt/nvme/geluidsmeter/data/mobile_measurements.jsonl"
```

- [ ] **Stap 4: verifieer dat config inlaadbaar is**

```bash
cd /home/bob/Geluidsmeter
PYTHONPATH=src .venv/bin/python -c "
from geluidsmeter.config import load_config
cfg = load_config()
print(cfg['mobile'])
"
```

Verwacht:
```
{'submit_token': 'geluidsmeter-mobiel', 'measurements_file': '/mnt/nvme/geluidsmeter/data/mobile_measurements.jsonl'}
```

- [ ] **Stap 5: commit**

```bash
git add requirements.txt core/config.yaml
git commit -m "feat(sprint6): httpx + mobile config sectie"
```

---

## Task 2: `_mobile_location_entries()` helper + tests

**Files:**
- Modify: `src/geluidsmeter/api.py`
- Create: `tests/test_api_submit.py`

- [ ] **Stap 1: schrijf de falende tests**

Maak `tests/test_api_submit.py` aan met de volgende inhoud:

```python
import json
import geluidsmeter.api as api_module


def test_mobile_entries_leeg_als_geen_file():
    api_module._config = {"mobile": {"measurements_file": "/tmp/bestaat-niet-sprint6-xyz.jsonl"}}
    assert api_module._mobile_location_entries() == []


def test_mobile_entries_leeg_als_geen_mobile_config():
    api_module._config = {}
    assert api_module._mobile_location_entries() == []


def test_mobile_entries_boven_norm(tmp_path):
    fp = tmp_path / "mobile.jsonl"
    fp.write_text(json.dumps({
        "id": "abc-123",
        "ts": "2026-05-14T10:00:00+00:00",
        "lat": 52.079,
        "lon": 4.315,
        "naam": "Binnenhof, Den Haag",
        "dba": 55.0,
        "source": "mobile",
        "kwaliteit": "prototype_indicatief_niet_juridisch",
    }) + "\n")
    api_module._config = {"mobile": {"measurements_file": str(fp)}}

    entries = api_module._mobile_location_entries()

    assert len(entries) == 1
    e = entries[0]
    assert e["id"] == "abc-123"
    assert e["naam"] == "Binnenhof, Den Haag"
    assert e["lden_gemeten"] == 55.0
    assert e["norm_status"] == "boven_norm"
    assert e["rivm_lden"] is None
    assert e["precision_m"] == 20
    assert e["source"] == "mobile"


def test_mobile_entries_geen_dba(tmp_path):
    fp = tmp_path / "mobile.jsonl"
    fp.write_text(json.dumps({
        "id": "xyz", "ts": "2026-05-14T10:00:00+00:00",
        "lat": 52.0, "lon": 4.0, "naam": "Test",
        "dba": None, "source": "mobile",
        "kwaliteit": "prototype_indicatief_niet_juridisch",
    }) + "\n")
    api_module._config = {"mobile": {"measurements_file": str(fp)}}

    entries = api_module._mobile_location_entries()
    assert entries[0]["norm_status"] is None
    assert entries[0]["lden_gemeten"] is None
```

- [ ] **Stap 2: draai tests, verwacht FAIL**

```bash
cd /home/bob/Geluidsmeter
PYTHONPATH=src .venv/bin/pytest tests/test_api_submit.py::test_mobile_entries_leeg_als_geen_file -v
```

Verwacht: `FAILED` met `AttributeError: module 'geluidsmeter.api' has no attribute '_mobile_location_entries'`

- [ ] **Stap 3: implementeer `_mobile_location_entries()` in `api.py`**

Voeg toe in `src/geluidsmeter/api.py`, direct na de `_latest_feature()` functie (na regel 65):

```python
def _mobile_location_entries() -> list[dict]:
    fp_str = _config.get("mobile", {}).get("measurements_file", "")
    if not fp_str:
        return []
    fp = Path(fp_str)
    if not fp.exists():
        return []
    norm_lden = 48
    entries = []
    with open(fp) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            dba = rec.get("dba")
            norm_status = None
            if dba is not None:
                norm_status = "binnen_norm" if dba <= norm_lden else "boven_norm"
            entries.append({
                "id": rec["id"],
                "naam": rec.get("naam", "Mobiele meting"),
                "lat": rec["lat"],
                "lon": rec["lon"],
                "precision_m": 20,
                "lden_gemeten": dba,
                "rivm_lden": None,
                "norm_lden": norm_lden,
                "norm_status": norm_status,
                "laatste_meting": rec["ts"],
                "kwaliteit": rec.get("kwaliteit", "prototype_indicatief_niet_juridisch"),
                "source": "mobile",
            })
    return entries
```

- [ ] **Stap 4: draai tests, verwacht PASS**

```bash
PYTHONPATH=src .venv/bin/pytest tests/test_api_submit.py -k "mobile_entries" -v
```

Verwacht: `4 passed`

- [ ] **Stap 5: commit**

```bash
git add src/geluidsmeter/api.py tests/test_api_submit.py
git commit -m "feat(sprint6): _mobile_location_entries() + tests"
```

---

## Task 3: `POST /api/submit` endpoint + tests

**Files:**
- Modify: `src/geluidsmeter/api.py`
- Modify: `tests/test_api_submit.py`

- [ ] **Stap 1: voeg imports toe bovenaan `api.py`**

Zoek de bestaande imports in `api.py`:
```python
import json
from pathlib import Path
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
```

Vervang door:
```python
import json
import uuid
from pathlib import Path
from datetime import datetime, timezone

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from pydantic import BaseModel
```

- [ ] **Stap 2: voeg `MobileSubmission` model toe in `api.py`**

Voeg toe direct na de imports, vóór `_location_entry()`:

```python
class MobileSubmission(BaseModel):
    dba: float | None = None
    lat: float
    lon: float
    naam: str = "Mobiele meting"
```

- [ ] **Stap 3: schrijf falende tests voor submit**

Voeg toe aan `tests/test_api_submit.py`:

```python
from fastapi.testclient import TestClient


def _config_met_tmp(tmp_path):
    api_module._config = {
        "mobile": {
            "submit_token": "test-token-abc",
            "measurements_file": str(tmp_path / "mobile.jsonl"),
        },
        "project": {"quality_label": "prototype_indicatief_niet_juridisch"},
    }


def test_submit_401_verkeerde_token(tmp_path):
    _config_met_tmp(tmp_path)
    client = TestClient(api_module.app)
    resp = client.post(
        "/api/submit",
        json={"dba": 52.0, "lat": 52.08, "lon": 4.29, "naam": "Test"},
        headers={"Authorization": "Bearer verkeerd"},
    )
    assert resp.status_code == 401


def test_submit_201_correct(tmp_path):
    _config_met_tmp(tmp_path)
    client = TestClient(api_module.app)
    resp = client.post(
        "/api/submit",
        json={"dba": 63.2, "lat": 52.079, "lon": 4.315, "naam": "Binnenhof"},
        headers={"Authorization": "Bearer test-token-abc"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["accepted"] is True
    assert "id" in body


def test_submit_schrijft_jsonl(tmp_path):
    _config_met_tmp(tmp_path)
    client = TestClient(api_module.app)
    client.post(
        "/api/submit",
        json={"dba": 55.0, "lat": 52.079, "lon": 4.315, "naam": "Test locatie"},
        headers={"Authorization": "Bearer test-token-abc"},
    )
    fp = tmp_path / "mobile.jsonl"
    assert fp.exists()
    rec = json.loads(fp.read_text().strip())
    assert rec["dba"] == 55.0
    assert rec["naam"] == "Test locatie"
    assert rec["source"] == "mobile"
    assert rec["lat"] == 52.079


def test_submit_default_naam(tmp_path):
    _config_met_tmp(tmp_path)
    client = TestClient(api_module.app)
    client.post(
        "/api/submit",
        json={"dba": 40.0, "lat": 52.0, "lon": 4.3},
        headers={"Authorization": "Bearer test-token-abc"},
    )
    rec = json.loads((tmp_path / "mobile.jsonl").read_text().strip())
    assert rec["naam"] == "Mobiele meting"
```

- [ ] **Stap 4: draai submit-tests, verwacht FAIL**

```bash
PYTHONPATH=src .venv/bin/pytest tests/test_api_submit.py::test_submit_401_verkeerde_token -v
```

Verwacht: `FAILED` met `404 Not Found` (endpoint bestaat nog niet)

- [ ] **Stap 5: implementeer `POST /api/submit` in `api.py`**

Voeg toe na de `@app.get("/api/locations")` endpoint (na regel ~156):

```python
@app.post("/api/submit", status_code=201)
def api_submit(
    submission: MobileSubmission,
    authorization: str | None = Header(default=None),
):
    submit_token = _config.get("mobile", {}).get("submit_token", "")
    if not submit_token or authorization != f"Bearer {submit_token}":
        raise HTTPException(status_code=401, detail="Ongeldige token")

    record = {
        "id": str(uuid.uuid4()),
        "ts": datetime.now(timezone.utc).isoformat(),
        "lat": submission.lat,
        "lon": submission.lon,
        "naam": submission.naam,
        "dba": submission.dba,
        "source": "mobile",
        "kwaliteit": _config.get("project", {}).get(
            "quality_label", "prototype_indicatief_niet_juridisch"
        ),
    }

    fp = Path(_config["mobile"]["measurements_file"])
    fp.parent.mkdir(parents=True, exist_ok=True)
    with open(fp, "a") as f:
        f.write(json.dumps(record) + "\n")

    return {"id": record["id"], "accepted": True}
```

- [ ] **Stap 6: draai alle submit-tests, verwacht PASS**

```bash
PYTHONPATH=src .venv/bin/pytest tests/test_api_submit.py -v
```

Verwacht: `7 passed`

- [ ] **Stap 7: draai alle tests**

```bash
PYTHONPATH=src .venv/bin/pytest tests/ -v
```

Verwacht: alle tests groen.

- [ ] **Stap 8: commit**

```bash
git add src/geluidsmeter/api.py tests/test_api_submit.py
git commit -m "feat(sprint6): POST /api/submit endpoint + tests"
```

---

## Task 4: `GET /api/locations` uitbreiden + `GET /meten`

**Files:**
- Modify: `src/geluidsmeter/api.py`

- [ ] **Stap 1: voeg `source: "jetson"` toe aan `_location_entry()`**

Zoek in `api.py` de return-dict in `_location_entry()`:
```python
    return {
        "id": loc_cfg.get("public_id", "meetlocatie"),
        ...
        "kwaliteit": config.get("project", {}).get("quality_label", "prototype_indicatief_niet_juridisch"),
    }
```

Voeg `"source": "jetson",` toe als laatste veld, vóór de sluitende `}`:

```python
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
        "source": "jetson",
    }
```

- [ ] **Stap 2: pas `GET /api/locations` aan**

Zoek:
```python
    return [_location_entry(_config, pub_lat, pub_lon, rms_dba, rivm_lden)]
```

Vervang door:
```python
    return [_location_entry(_config, pub_lat, pub_lon, rms_dba, rivm_lden)] + _mobile_location_entries()
```

- [ ] **Stap 3: voeg `GET /meten` endpoint toe**

Voeg toe na `GET /public`:

```python
@app.get("/meten", response_class=HTMLResponse)
def meten_page():
    return (_static_dir / "meten.html").read_text()
```

- [ ] **Stap 4: verifieer bestaande tests nog steeds groen**

```bash
PYTHONPATH=src .venv/bin/pytest tests/ -v
```

Verwacht: alle tests groen. De bestaande `test_location_entry_velden` test checkt niet op `source`, dus die blijft groen.

- [ ] **Stap 5: commit**

```bash
git add src/geluidsmeter/api.py
git commit -m "feat(sprint6): /api/locations + mobile entries, GET /meten"
```

---

## Task 5: `static/meten.html` — mobiele meetpagina

**Files:**
- Create: `src/geluidsmeter/static/meten.html`

- [ ] **Stap 1: maak `src/geluidsmeter/static/meten.html` aan**

```html
<!DOCTYPE html>
<html lang="nl">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">
  <title>Geluidsmeting</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: system-ui, sans-serif; background: #0f172a; color: #e2e8f0;
           min-height: 100dvh; display: flex; flex-direction: column;
           align-items: center; justify-content: center; padding: 24px 16px; }
    h1 { font-size: 1.2rem; font-weight: 600; color: #94a3b8; margin-bottom: 24px; text-align: center; }
    .card { background: #1e293b; border-radius: 12px; padding: 24px; width: 100%; max-width: 360px; }
    .label { font-size: 0.7rem; color: #64748b; text-transform: uppercase; letter-spacing: .06em; margin-bottom: 6px; }
    .waarde-groot { font-size: 4rem; font-weight: 700; color: #4ade80; text-align: center;
                    line-height: 1; margin: 8px 0 4px; }
    .eenheid { font-size: 0.9rem; color: #64748b; text-align: center; margin-bottom: 16px; }
    .balk-wrap { background: #0f172a; border-radius: 6px; height: 10px; margin-bottom: 20px; overflow: hidden; }
    .balk { height: 100%; width: 0%; border-radius: 6px; background: #4ade80;
            transition: width .15s, background .15s; }
    .norm-lijn { display: flex; justify-content: flex-end; padding-right: 4px;
                 font-size: 0.65rem; color: #475569; margin-top: -16px; margin-bottom: 12px; }
    input[type=text] { width: 100%; background: #0f172a; border: 1px solid #334155;
                       border-radius: 8px; padding: 10px 12px; color: #e2e8f0;
                       font-size: 0.9rem; margin-bottom: 12px; }
    input[type=text]::placeholder { color: #475569; }
    .gps { font-size: 0.82rem; color: #64748b; margin-bottom: 16px; min-height: 20px; }
    button { width: 100%; background: #3b82f6; color: white; border: none; border-radius: 8px;
             padding: 14px; font-size: 1rem; font-weight: 600; cursor: pointer; }
    button:disabled { background: #1e3a5f; color: #475569; cursor: not-allowed; }
    .bevestiging { margin-top: 12px; font-size: 0.85rem; color: #4ade80;
                   text-align: center; display: none; }
    .disclaimer { margin-top: 12px; font-size: 0.75rem; color: #f59e0b;
                  background: #1c1a07; border-radius: 6px; padding: 8px 10px; }
    .fout { margin-top: 8px; font-size: 0.8rem; color: #f87171; display: none; }
    .geen-token { text-align: center; color: #f87171; padding: 24px; font-size: 0.9rem; }
  </style>
</head>
<body>
<h1>Geluidsmeting</h1>
<div class="card" id="hoofd-card">
  <div class="label">Gemeten geluidsniveau</div>
  <div class="waarde-groot" id="waarde">—</div>
  <div class="eenheid">dB(A)</div>
  <div class="balk-wrap">
    <div class="balk" id="balk"></div>
  </div>
  <div class="norm-lijn">norm 48 dB(A)</div>

  <div class="label" style="margin-top:4px">Locatienaam (optioneel)</div>
  <input type="text" id="naam" placeholder="bijv. Binnenhof, Den Haag">

  <div class="gps" id="gps-status">📍 GPS ophalen…</div>

  <button id="insturen-btn" disabled onclick="insturen()">Insturen</button>
  <div class="bevestiging" id="bevestiging"></div>
  <div class="fout" id="fout"></div>

  <div class="disclaimer" id="disclaimer" style="display:none">
    ⚠ Geen calibratie-offset — meting wordt opgeslagen als ongekalibreerd.
    Voeg <code>?offset=90.7</code> toe aan de URL voor gekalibreerde waarden.
  </div>
</div>

<script>
const params = new URLSearchParams(window.location.search);
const token = params.get("token") || "";
const offset = parseFloat(params.get("offset") || "0");
const isCalibrated = offset !== 0;

if (!token) {
  document.getElementById("hoofd-card").innerHTML =
    '<div class="geen-token">Geen token — gebruik de link die je gekregen hebt.<br><br>' +
    'Voorbeeld: <code>/meten?token=geluidsmeter-mobiel&amp;offset=90.7</code></div>';
}

if (!isCalibrated && token) {
  document.getElementById("disclaimer").style.display = "block";
}

let dbfsValue = -120;
let gpsCoords = null;

async function startMic() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
    const ctx = new AudioContext();
    const source = ctx.createMediaStreamSource(stream);
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 2048;
    source.connect(analyser);
    const buf = new Float32Array(analyser.fftSize);
    function tick() {
      analyser.getFloatTimeDomainData(buf);
      const rms = Math.sqrt(buf.reduce((s, v) => s + v * v, 0) / buf.length);
      dbfsValue = rms > 0 ? 20 * Math.log10(rms) : -120;
      const dba = isCalibrated ? Math.round((dbfsValue + offset) * 10) / 10 : null;
      updateDisplay(dba);
      requestAnimationFrame(tick);
    }
    tick();
  } catch (e) {
    document.getElementById("waarde").textContent = "mic?";
  }
}

function updateDisplay(dba) {
  const el = document.getElementById("waarde");
  const balk = document.getElementById("balk");
  if (dba !== null) {
    el.textContent = dba.toFixed(1);
    el.style.color = dba > 48 ? "#fb923c" : "#4ade80";
    const pct = Math.min(100, Math.max(0, (dba / 80) * 100));
    balk.style.width = pct + "%";
    balk.style.background = dba > 48 ? "#fb923c" : "#4ade80";
  } else {
    el.textContent = "—";
  }
}

navigator.geolocation.getCurrentPosition(
  pos => {
    gpsCoords = { lat: pos.coords.latitude, lon: pos.coords.longitude };
    document.getElementById("gps-status").textContent =
      `📍 ${gpsCoords.lat.toFixed(5)}, ${gpsCoords.lon.toFixed(5)} ✓`;
    document.getElementById("gps-status").style.color = "#4ade80";
    if (token) document.getElementById("insturen-btn").disabled = false;
  },
  () => {
    document.getElementById("gps-status").textContent = "📍 GPS niet beschikbaar";
    document.getElementById("gps-status").style.color = "#f87171";
  },
  { enableHighAccuracy: true, timeout: 15000 }
);

async function insturen() {
  const naam = document.getElementById("naam").value.trim() || "Mobiele meting";
  const dba = isCalibrated ? Math.round((dbfsValue + offset) * 10) / 10 : null;
  const btn = document.getElementById("insturen-btn");
  const foutEl = document.getElementById("fout");
  btn.disabled = true;
  btn.textContent = "Bezig…";
  foutEl.style.display = "none";
  try {
    const resp = await fetch("/api/submit", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${token}`,
      },
      body: JSON.stringify({ dba, lat: gpsCoords.lat, lon: gpsCoords.lon, naam }),
    });
    if (resp.ok) {
      const tijd = new Date().toLocaleTimeString("nl-NL", { hour: "2-digit", minute: "2-digit" });
      const bev = document.getElementById("bevestiging");
      bev.textContent = `✓ Meting verstuurd (${tijd})`;
      bev.style.display = "block";
      setTimeout(() => { btn.disabled = false; btn.textContent = "Insturen"; }, 5000);
    } else {
      foutEl.textContent = resp.status === 401 ? "Fout: ongeldig token." : `Fout ${resp.status}.`;
      foutEl.style.display = "block";
      btn.disabled = false;
      btn.textContent = "Insturen";
    }
  } catch (e) {
    foutEl.textContent = "Netwerkfout — probeer opnieuw.";
    foutEl.style.display = "block";
    btn.disabled = false;
    btn.textContent = "Insturen";
  }
}

if (token) startMic();
</script>
</body>
</html>
```

- [ ] **Stap 2: herstart uvicorn en test `/meten`**

```bash
pkill -f "uvicorn geluidsmeter" || true
sleep 1
cd /home/bob/Geluidsmeter
PYTHONPATH=src .venv/bin/uvicorn geluidsmeter.api:app --host 0.0.0.0 --port 8792 >> /tmp/geluidsmeter-api.log 2>&1 &
sleep 3
curl -s -o /dev/null -w "%{http_code}" http://localhost:8792/meten
```

Verwacht: `200`

- [ ] **Stap 3: test de pagina met token + offset**

Open in browser: `http://localhost:8792/meten?token=geluidsmeter-mobiel&offset=90.7`

Controleer:
- Pagina laadt zonder foutmelding
- Microfoon-toestemming wordt gevraagd
- Na toestemming: getal beweegt mee met omgevingsgeluid
- GPS wordt gevraagd
- "Insturen"-knop wordt enabled zodra GPS beschikbaar

- [ ] **Stap 4: commit**

```bash
git add src/geluidsmeter/static/meten.html
git commit -m "feat(sprint6): mobiele meetpagina /meten"
```

---

## Task 6: `public.html` — blauwe markers + mobile label

**Files:**
- Modify: `src/geluidsmeter/static/public.html`

- [ ] **Stap 1: voeg CSS toe voor mobiele kaarten**

Zoek in `public.html`:
```css
    .uitleg p:last-child { margin-bottom: 0; }
```

Voeg de regel erna toe:
```css
    .locatie.mobiel { border-left-color: #3b82f6; }
    .mobile-label { font-size: 0.72rem; color: #3b82f6; font-weight: 600; margin-bottom: 10px; }
```

- [ ] **Stap 2: pas de markerkleur-logica aan in het JavaScript**

Zoek in `public.html`:
```javascript
    const bovenNorm = loc.norm_status === "boven_norm";
    const kleur = bovenNorm ? "#f97316" : "#22c55e";
```

Vervang door:
```javascript
    const bovenNorm = loc.norm_status === "boven_norm";
    const isMobile = loc.source === "mobile";
    const kleur = isMobile ? "#3b82f6" : (bovenNorm ? "#f97316" : "#22c55e");
```

- [ ] **Stap 3: pas de locatiekaart class aan**

Zoek:
```javascript
    div.className = `locatie ${bovenNorm ? "boven-norm" : loc.norm_status ? "binnen-norm" : ""}`;
```

Vervang door:
```javascript
    div.className = `locatie ${isMobile ? "mobiel" : bovenNorm ? "boven-norm" : loc.norm_status ? "binnen-norm" : ""}`;
```

- [ ] **Stap 4: voeg mobile label toe in de kaartbody**

Zoek in de `body.innerHTML` template:
```javascript
      <div class="status-tekst ${bovenNorm ? "boven" : "binnen"}">${statusTekst}</div>
```

Voeg de regel erboven toe:
```javascript
      ${isMobile ? '<div class="mobile-label">📱 Mobiele meting</div>' : ''}
      <div class="status-tekst ${bovenNorm ? "boven" : "binnen"}">${statusTekst}</div>
```

- [ ] **Stap 5: test end-to-end**

Stuur een testmeting in via curl:

```bash
curl -s -X POST http://localhost:8792/api/submit \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer geluidsmeter-mobiel" \
  -d '{"dba": 67.5, "lat": 52.0800, "lon": 4.3120, "naam": "Testmeting Centrum"}'
```

Verwacht: `{"id":"...","accepted":true}`

Controleer dan `/api/locations`:
```bash
curl -s http://localhost:8792/api/locations | python3 -m json.tool
```

Verwacht: array met 2 entries — één met `"source":"jetson"` en één met `"source":"mobile"`.

Open `http://localhost:8792/public` — verwacht: blauwe marker op kaart + blauwe kaart met "📱 Mobiele meting" label.

- [ ] **Stap 6: draai volledige testsuite**

```bash
PYTHONPATH=src .venv/bin/pytest tests/ -v
```

Verwacht: alle tests groen.

- [ ] **Stap 7: commit en push**

```bash
git add src/geluidsmeter/static/public.html
git commit -m "feat(sprint6): blauwe markers en label voor mobiele metingen op publieke kaart"
git push origin master
```

---

## Gebruik na implementatie

iPhone-link (bookmark of deel via iMessage):
```
https://geluid.felixisfelix.com/meten?token=geluidsmeter-mobiel&offset=90.7
```

De `offset` pas je aan per apparaat. Voor de iPhone kalibreer je op dezelfde manier als de Jetson: meet tegelijk met een referentie-app en bereken `offset = referentie_dBA - dbfsValue`.
