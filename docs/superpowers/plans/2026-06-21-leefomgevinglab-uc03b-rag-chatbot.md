# LeefomgevingLab — UC-03b: RAG + vergunningen-chatbot (Plan 2b)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Een lokale RAG-pijplijn op IPLO-teksten + een conversationele vergunningen-chatbot die antwoordt onder het conservatieve antwoordcontract (altijd bronverwijzing naar de opgehaalde passages, expliciete onzekerheid, vangnet "raadpleeg bevoegd gezag", nooit een stellige vergunning-ja/nee). Met chat-frontend en een eval-set die het contract bewaakt.

**Architecture:** Een embedding-client praat met een lokale llama.cpp `/v1/embeddings`-server. Een dependency-vrije `VectorStore` (numpy, brute-force cosine) bewaart chunks + vectoren op NVMe. Een ingest-pijplijn haalt geconfigureerde IPLO-URL's op, zet HTML om naar tekst, chunkt, embedt en bouwt de store (via een CLI-script, niet in de request). De chatbot-service haalt top-k passages op, stelt een prompt samen met die context + citaties, roept Qwen (localhost:8080) aan en geeft het antwoordcontract terug. Een `POST /api/chat`-route en een chat-pagina ontsluiten het. Hergebruikt het bestaande `ConnectorError`/contract-patroon uit Plan 2a.

**Tech Stack:** Python 3.10, FastAPI, httpx, numpy (al aanwezig), pytest. Embeddings via llama.cpp `/v1/embeddings`; generatie via Qwen2.5 (`/v1/chat/completions`). Frontend: vanilla HTML/JS (geen buildstap).

## Global Constraints

- Tests draaien met: `PYTHONPATH=src python -m pytest` (geen pytest-config; src op het pad).
- App draait via `uvicorn geluidsmeter.api:app --app-dir src` op poort **8792**; service `geluidsmeter-api` (systemd). Bestaande routes/gedrag niet wijzigen; bestaande tests blijven groen.
- Nieuwe logica onder `src/leefomgevinglab/`; `src/geluidsmeter/*` alleen additief.
- **Conservatief antwoordcontract is een harde eis:** elk chat-antwoord bevat het antwoord, **bronnen** (URL's van de opgehaalde IPLO-passages), expliciete **onzekerheid**, en het **vangnet** "raadpleeg het bevoegd gezag / Omgevingsloket — indicatief, geen juridisch besluit". De prompt instrueert het model: gebruik **uitsluitend** de meegegeven context, verzin niets, trek geen juridische conclusies, en zeg het als de context geen antwoord geeft.
- **Externe afhankelijkheden (deferred, mock in tests):**
  - Een **embedding-model** moet in llama.cpp draaien op de geconfigureerde `embed.base_url` (default `http://localhost:8082/v1`). Niet aanwezig in de basis-infra (8080 Qwen, 8081 Nemo) → setup/verify-stap; alle tests mocken de embedding-call.
  - **Qwen** op `http://localhost:8080/v1` (al beschikbaar) voor generatie; tests mocken de call.
  - **IPLO-URL's** zijn config-gedreven (curated lijst); geen gegokte endpoints.
- Geen ruwe data in de repo: de RAG-index staat op **NVMe** (`/mnt/nvme/geluidsmeter/data/rag/`), niet in git.
- Commits eindigen met `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

## File Structure

```
src/leefomgevinglab/
  rag/
    __init__.py
    embed.py            # embed_texts() via llama.cpp /v1/embeddings
    store.py            # VectorStore: build/save/load (NVMe) + cosine search
    ingest.py           # IPLO URL's -> tekst -> chunks -> embed -> store
  usecases/vergunningen/
    chatbot.py          # beantwoord(vraag, store, embed_fn, llm_cfg) -> contract
  static/
    chat.html           # chat-frontend
scripts/
  07_build_rag_index.py # CLI: bouw/ververs de RAG-index (one-off / cron)
core/config.yaml        # + leefomgevinglab.rag-sectie (MODIFY)
src/geluidsmeter/api.py # + POST /api/chat + GET /chatbot (MODIFY)
tests/
  test_rag_embed.py
  test_rag_store.py
  test_rag_ingest.py
  test_chatbot.py
  test_api_chat.py
  test_chatbot_eval.py  # eval-set: contract-vorm op gemockte LLM
```

---

### Task 1: Embedding-client + config

**Files:**
- Create: `src/leefomgevinglab/rag/__init__.py` (leeg)
- Create: `src/leefomgevinglab/rag/embed.py`
- Modify: `core/config.yaml` (voeg `leefomgevinglab.rag` toe)
- Test: `tests/test_rag_embed.py`

**Interfaces:**
- Consumes: `ConnectorError` uit `leefomgevinglab.connectors.base`.
- Produces:
  - `embed_texts(texts: list[str], base_url: str, model: str, timeout_s: float = 60.0) -> list[list[float]]`
    — POST naar `{base_url}/embeddings` met `{"model": model, "input": texts}`, geeft de vectoren
    in volgorde terug. Raise `ConnectorError` bij fout of onverwacht antwoord.

- [ ] **Step 1: Schrijf de falende test**

`tests/test_rag_embed.py`:

```python
import httpx
import pytest
from leefomgevinglab.connectors.base import ConnectorError
from leefomgevinglab.rag import embed as emb


class _Resp:
    def __init__(self, payload, status=200):
        self._p = payload; self.status_code = status
    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("e", request=None, response=None)
    def json(self): return self._p


def test_embed_texts_returns_vectors_in_order(monkeypatch):
    def fake_post(url, json=None, timeout=None):
        assert url.endswith("/embeddings")
        assert json["input"] == ["a", "b"]
        return _Resp({"data": [{"embedding": [1.0, 0.0]}, {"embedding": [0.0, 1.0]}]})
    monkeypatch.setattr(httpx, "post", fake_post)
    out = emb.embed_texts(["a", "b"], base_url="http://localhost:8082/v1", model="bge")
    assert out == [[1.0, 0.0], [0.0, 1.0]]


def test_embed_texts_error_raises(monkeypatch):
    def fake_post(url, json=None, timeout=None):
        raise httpx.ConnectError("down")
    monkeypatch.setattr(httpx, "post", fake_post)
    with pytest.raises(ConnectorError):
        emb.embed_texts(["a"], base_url="http://localhost:8082/v1", model="bge")
```

- [ ] **Step 2: Run test om te zien dat hij faalt**

Run: `PYTHONPATH=src python -m pytest tests/test_rag_embed.py -q`
Expected: FAIL met `ModuleNotFoundError: No module named 'leefomgevinglab.rag.embed'`

- [ ] **Step 3: Schrijf de implementatie**

Maak `src/leefomgevinglab/rag/__init__.py` leeg. `src/leefomgevinglab/rag/embed.py`:

```python
"""Embedding-client voor de RAG-pijplijn via llama.cpp /v1/embeddings."""
import httpx

from leefomgevinglab.connectors.base import ConnectorError


def embed_texts(texts: list[str], base_url: str, model: str, timeout_s: float = 60.0) -> list[list[float]]:
    try:
        resp = httpx.post(
            f"{base_url.rstrip('/')}/embeddings",
            json={"model": model, "input": texts},
            timeout=timeout_s,
        )
        resp.raise_for_status()
        data = resp.json()["data"]
        return [row["embedding"] for row in data]
    except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
        raise ConnectorError("Embedding-service niet beschikbaar") from exc
```

- [ ] **Step 4: Run test om te zien dat hij slaagt**

Run: `PYTHONPATH=src python -m pytest tests/test_rag_embed.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Config-sectie toevoegen**

Voeg aan `core/config.yaml` onder `leefomgevinglab:` toe (naast `rev:`/`dso:`/`llm:`):

```yaml
  rag:
    embed:
      base_url: "http://localhost:8082/v1"   # llama.cpp embedding-server (model laden, zie plan Task 3 Step 0)
      model: "bge-m3"
    store_dir: "/mnt/nvme/geluidsmeter/data/rag"
    top_k: 4
    chunk_chars: 1200
    chunk_overlap: 200
    # Curated IPLO-bronpagina's; vul aan met relevante URL's.
    iplo_urls:
      - "https://iplo.nl/regelgeving/instrumenten/vergunningen-melding/"
```

- [ ] **Step 6: Commit**

```bash
git add src/leefomgevinglab/rag/__init__.py src/leefomgevinglab/rag/embed.py core/config.yaml tests/test_rag_embed.py
git commit -m "feat(llab): RAG embedding-client via llama.cpp /v1/embeddings

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: VectorStore (numpy, NVMe-persistent)

**Files:**
- Create: `src/leefomgevinglab/rag/store.py`
- Test: `tests/test_rag_store.py`

**Interfaces:**
- Produces:
  - `class VectorStore` met:
    - classmethod `build(chunks: list[dict], vectors: list[list[float]]) -> VectorStore`
      (`chunks` zijn dicts met minstens `text` en `url`).
    - `save(store_dir: str) -> None` (schrijft `vectors.npy` + `chunks.jsonl`).
    - classmethod `load(store_dir: str) -> VectorStore` (raise `FileNotFoundError` als index ontbreekt).
    - `search(query_vector: list[float], k: int) -> list[dict]` (top-k chunks op cosine-similariteit,
      elk chunk-dict aangevuld met `score`).
    - property `size -> int`.

- [ ] **Step 1: Schrijf de falende test**

`tests/test_rag_store.py`:

```python
import pytest
from leefomgevinglab.rag.store import VectorStore


def test_build_search_topk():
    chunks = [{"text": "a", "url": "u1"}, {"text": "b", "url": "u2"}, {"text": "c", "url": "u3"}]
    vectors = [[1.0, 0.0], [0.0, 1.0], [0.9, 0.1]]
    s = VectorStore.build(chunks, vectors)
    hits = s.search([1.0, 0.0], k=2)
    assert [h["url"] for h in hits] == ["u1", "u3"]      # dichtst bij [1,0]
    assert hits[0]["score"] >= hits[1]["score"]
    assert s.size == 3


def test_save_load_roundtrip(tmp_path):
    chunks = [{"text": "x", "url": "u"}]
    s = VectorStore.build(chunks, [[0.3, 0.4]])
    s.save(str(tmp_path))
    s2 = VectorStore.load(str(tmp_path))
    assert s2.size == 1
    assert s2.search([0.3, 0.4], k=1)[0]["url"] == "u"


def test_load_missing_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        VectorStore.load(str(tmp_path))
```

- [ ] **Step 2: Run test om te zien dat hij faalt**

Run: `PYTHONPATH=src python -m pytest tests/test_rag_store.py -q`
Expected: FAIL met `ModuleNotFoundError: No module named 'leefomgevinglab.rag.store'`

- [ ] **Step 3: Schrijf de implementatie**

`src/leefomgevinglab/rag/store.py`:

```python
"""Dependency-vrije vectorstore: numpy brute-force cosine, persistent op NVMe."""
import json
from pathlib import Path

import numpy as np


def _normalize(mat: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return mat / norms


class VectorStore:
    def __init__(self, chunks: list[dict], vectors: np.ndarray):
        self.chunks = chunks
        self._vectors = _normalize(np.asarray(vectors, dtype=np.float32))

    @classmethod
    def build(cls, chunks: list[dict], vectors: list[list[float]]) -> "VectorStore":
        return cls(list(chunks), np.asarray(vectors, dtype=np.float32))

    @property
    def size(self) -> int:
        return len(self.chunks)

    def save(self, store_dir: str) -> None:
        d = Path(store_dir)
        d.mkdir(parents=True, exist_ok=True)
        np.save(d / "vectors.npy", self._vectors)
        with open(d / "chunks.jsonl", "w") as f:
            for c in self.chunks:
                f.write(json.dumps(c) + "\n")

    @classmethod
    def load(cls, store_dir: str) -> "VectorStore":
        d = Path(store_dir)
        vec_path, chunk_path = d / "vectors.npy", d / "chunks.jsonl"
        if not vec_path.exists() or not chunk_path.exists():
            raise FileNotFoundError(f"RAG-index niet gevonden in {store_dir}")
        vectors = np.load(vec_path)
        chunks = [json.loads(line) for line in chunk_path.read_text().splitlines() if line.strip()]
        obj = cls.__new__(cls)
        obj.chunks = chunks
        obj._vectors = vectors  # al genormaliseerd bij save
        return obj

    def search(self, query_vector: list[float], k: int) -> list[dict]:
        if not self.chunks:
            return []
        q = np.asarray(query_vector, dtype=np.float32)
        nq = np.linalg.norm(q)
        if nq != 0:
            q = q / nq
        scores = self._vectors @ q
        idx = np.argsort(-scores)[:k]
        return [{**self.chunks[i], "score": float(scores[i])} for i in idx]
```

- [ ] **Step 4: Run test om te zien dat hij slaagt**

Run: `PYTHONPATH=src python -m pytest tests/test_rag_store.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/leefomgevinglab/rag/store.py tests/test_rag_store.py
git commit -m "feat(llab): VectorStore (numpy cosine, NVMe-persistent)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Ingest-pijplijn + build-script

**Files:**
- Create: `src/leefomgevinglab/rag/ingest.py`
- Create: `scripts/07_build_rag_index.py`
- Test: `tests/test_rag_ingest.py`

**Interfaces:**
- Consumes: `embed_texts` (Task 1), `VectorStore` (Task 2), `ConnectorError`.
- Produces:
  - `html_to_text(html: str) -> str` (stdlib HTML→tekst).
  - `chunk_text(text: str, chunk_chars: int, overlap: int) -> list[str]`.
  - `fetch_url(url: str, timeout_s: float = 20.0) -> str` (HTML; `ConnectorError` bij fout).
  - `build_index(urls, embed_fn, chunk_chars, overlap) -> VectorStore` waarbij
    `embed_fn(list[str]) -> list[list[float]]` (injecteerbaar; in productie een partial van `embed_texts`).

- [ ] **Step 1: Schrijf de falende test**

`tests/test_rag_ingest.py`:

```python
from leefomgevinglab.rag import ingest


def test_html_to_text_strips_tags():
    html = "<html><body><h1>Titel</h1><p>Hallo <b>wereld</b></p><script>x=1</script></body></html>"
    txt = ingest.html_to_text(html)
    assert "Titel" in txt and "Hallo" in txt and "wereld" in txt
    assert "x=1" not in txt          # script-inhoud weg
    assert "<" not in txt            # geen tags


def test_chunk_text_overlap():
    text = "abcdefghij" * 30          # 300 tekens
    chunks = ingest.chunk_text(text, chunk_chars=100, overlap=20)
    assert len(chunks) >= 3
    assert all(len(c) <= 100 for c in chunks)
    # overlap: einde van chunk0 komt terug in begin van chunk1
    assert chunks[0][-20:] == chunks[1][:20]


def test_build_index_uses_embed_fn(monkeypatch):
    monkeypatch.setattr(ingest, "fetch_url", lambda url, timeout_s=20.0: f"<p>inhoud van {url}</p>")
    captured = {}
    def fake_embed(texts):
        captured["n"] = len(texts)
        return [[float(i), 0.0] for i in range(len(texts))]
    store = ingest.build_index(["https://iplo.nl/a"], fake_embed, chunk_chars=1000, overlap=100)
    assert store.size == captured["n"] >= 1
    assert store.chunks[0]["url"] == "https://iplo.nl/a"
    assert "inhoud" in store.chunks[0]["text"]
```

- [ ] **Step 2: Run test om te zien dat hij faalt**

Run: `PYTHONPATH=src python -m pytest tests/test_rag_ingest.py -q`
Expected: FAIL met `ModuleNotFoundError: No module named 'leefomgevinglab.rag.ingest'`

- [ ] **Step 3: Schrijf de implementatie**

`src/leefomgevinglab/rag/ingest.py`:

```python
"""IPLO-ingest: HTML ophalen -> tekst -> chunks -> embeddings -> VectorStore."""
from html.parser import HTMLParser

import httpx

from leefomgevinglab.connectors.base import ConnectorError
from leefomgevinglab.rag.store import VectorStore

_SKIP_TAGS = {"script", "style", "head", "noscript"}


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self._parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP_TAGS:
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in _SKIP_TAGS and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if self._skip == 0 and data.strip():
            self._parts.append(data.strip())


def html_to_text(html: str) -> str:
    p = _TextExtractor()
    p.feed(html)
    return " ".join(p._parts)


def chunk_text(text: str, chunk_chars: int, overlap: int) -> list[str]:
    text = " ".join(text.split())
    if not text:
        return []
    step = max(1, chunk_chars - overlap)
    return [text[i:i + chunk_chars] for i in range(0, len(text), step)]


def fetch_url(url: str, timeout_s: float = 20.0) -> str:
    try:
        resp = httpx.get(url, timeout=timeout_s, follow_redirects=True)
        resp.raise_for_status()
        return resp.text
    except httpx.HTTPError as exc:
        raise ConnectorError(f"IPLO-pagina niet beschikbaar: {url}") from exc


def build_index(urls, embed_fn, chunk_chars: int, overlap: int) -> VectorStore:
    chunks: list[dict] = []
    for url in urls:
        text = html_to_text(fetch_url(url))
        for piece in chunk_text(text, chunk_chars, overlap):
            chunks.append({"text": piece, "url": url})
    if not chunks:
        return VectorStore.build([], [])
    vectors = embed_fn([c["text"] for c in chunks])
    return VectorStore.build(chunks, vectors)
```

`scripts/07_build_rag_index.py`:

```python
#!/usr/bin/env python3
"""Bouw/ververs de RAG-index uit de geconfigureerde IPLO-URL's."""
import sys
from functools import partial
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from leefomgevinglab.config_compat import load_cfg  # zie noot hieronder
from leefomgevinglab.rag.embed import embed_texts
from leefomgevinglab.rag.ingest import build_index


def main():
    import yaml
    cfg = yaml.safe_load(open(Path(__file__).parent.parent / "core" / "config.yaml"))["leefomgevinglab"]["rag"]
    embed_fn = partial(embed_texts, base_url=cfg["embed"]["base_url"], model=cfg["embed"]["model"])
    store = build_index(cfg["iplo_urls"], embed_fn, cfg["chunk_chars"], cfg["chunk_overlap"])
    store.save(cfg["store_dir"])
    print(f"RAG-index gebouwd: {store.size} chunks -> {cfg['store_dir']}")


if __name__ == "__main__":
    main()
```

> Noot: verwijder de `from leefomgevinglab.config_compat import load_cfg`-regel — het script
> leest de config direct met `yaml` (zoals getoond in `main`). De import is een overblijfsel;
> laat 'm weg.

- [ ] **Step 4: Run test om te zien dat hij slaagt**

Run: `PYTHONPATH=src python -m pytest tests/test_rag_ingest.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Verify-aantekening (geen code)**

De live index-bouw (`python scripts/07_build_rag_index.py`) vereist een draaiende embedding-server
op `rag.embed.base_url`. Die staat niet standaard in de infra (8080 Qwen, 8081 Nemo). Noteer als
open punt: embedding-model laden (bv. bge-m3 in llama.cpp op 8082) voordat de index live gebouwd
wordt. Tests draaien volledig op mocks en hebben dit niet nodig.

- [ ] **Step 6: Commit**

```bash
git add src/leefomgevinglab/rag/ingest.py scripts/07_build_rag_index.py tests/test_rag_ingest.py
git commit -m "feat(llab): RAG-ingest (IPLO HTML -> chunks -> index) + build-script

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Chatbot-service (RAG + Qwen, antwoordcontract)

**Files:**
- Create: `src/leefomgevinglab/usecases/vergunningen/chatbot.py`
- Test: `tests/test_chatbot.py`

**Interfaces:**
- Consumes: `VectorStore.search` (Task 2), `embed_texts`/een `embed_fn` (Task 1), `ConnectorError`,
  Qwen via httpx.
- Produces:
  - `DISCLAIMER: str`, `VANGNET: str`
  - `build_prompt(vraag: str, passages: list[dict]) -> str`
  - `beantwoord(vraag: str, store, embed_fn, llm_base_url: str, model: str, top_k: int = 4, timeout_s: float = 60.0) -> dict`
    met sleutels: `vraag`, `antwoord`, `bronnen` (list van URL's), `onzekerheid` (True),
    `disclaimer`, `vangnet`, `beschikbaar` (bool). `embed_fn(list[str]) -> list[list[float]]`.
    Degradeert (beschikbaar=False) bij `ConnectorError` van embeddings of LLM, en bij 0 passages.

- [ ] **Step 1: Schrijf de falende test**

`tests/test_chatbot.py`:

```python
import httpx
import pytest
from leefomgevinglab.connectors.base import ConnectorError
from leefomgevinglab.usecases.vergunningen import chatbot


class _Resp:
    def __init__(self, payload, status=200):
        self._p = payload; self.status_code = status
    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("e", request=None, response=None)
    def json(self): return self._p


class _Store:
    def __init__(self, hits): self._hits = hits
    def search(self, qv, k): return self._hits[:k]


def _embed_ok(texts): return [[1.0, 0.0] for _ in texts]


def test_build_prompt_bevat_context_en_instructie():
    p = chatbot.build_prompt("mag ik een boom kappen?",
                             [{"text": "Voor kappen geldt soms een vergunning.", "url": "u1"}])
    assert "mag ik een boom kappen?" in p
    assert "Voor kappen geldt soms een vergunning." in p
    assert "uitsluitend" in p.lower()      # gebruik alleen de context


def test_beantwoord_happy_contract(monkeypatch):
    store = _Store([{"text": "Voor kappen geldt soms een vergunning.", "url": "https://iplo.nl/a", "score": 0.9}])
    def fake_post(url, json=None, timeout=None):
        return _Resp({"choices": [{"message": {"content": "Mogelijk is een vergunning nodig."}}]})
    monkeypatch.setattr(httpx, "post", fake_post)
    out = chatbot.beantwoord("mag ik een boom kappen?", store, _embed_ok,
                             llm_base_url="http://localhost:8080/v1", model="qwen2.5-32b")
    assert out["beschikbaar"] is True
    assert out["antwoord"] == "Mogelijk is een vergunning nodig."
    assert out["bronnen"] == ["https://iplo.nl/a"]
    assert out["onzekerheid"] is True
    assert "bevoegd gezag" in out["vangnet"]
    assert out["disclaimer"] == chatbot.DISCLAIMER


def test_beantwoord_geen_context_degradeert(monkeypatch):
    store = _Store([])
    out = chatbot.beantwoord("iets", store, _embed_ok,
                             llm_base_url="http://localhost:8080/v1", model="qwen2.5-32b")
    assert out["beschikbaar"] is False
    assert out["bronnen"] == []
    assert out["disclaimer"] == chatbot.DISCLAIMER


def test_beantwoord_llm_down_degradeert(monkeypatch):
    store = _Store([{"text": "x", "url": "u", "score": 0.5}])
    def fake_post(url, json=None, timeout=None):
        raise httpx.ConnectError("down")
    monkeypatch.setattr(httpx, "post", fake_post)
    out = chatbot.beantwoord("iets", store, _embed_ok,
                             llm_base_url="http://localhost:8080/v1", model="qwen2.5-32b")
    assert out["beschikbaar"] is False
    assert "bevoegd gezag" in out["vangnet"]
```

- [ ] **Step 2: Run test om te zien dat hij faalt**

Run: `PYTHONPATH=src python -m pytest tests/test_chatbot.py -q`
Expected: FAIL met `ModuleNotFoundError: No module named 'leefomgevinglab.usecases.vergunningen.chatbot'`

- [ ] **Step 3: Schrijf de implementatie**

`src/leefomgevinglab/usecases/vergunningen/chatbot.py`:

```python
"""UC-03b: vergunningen-chatbot op RAG (IPLO) + Qwen, conservatief contract."""
import httpx

from leefomgevinglab.connectors.base import ConnectorError

DISCLAIMER = (
    "Indicatief, geen juridisch besluit. Het antwoord is gebaseerd op de getoonde "
    "IPLO-passages en kan onvolledig zijn."
)
VANGNET = (
    "Raadpleeg het bevoegd gezag of het Omgevingsloket (omgevingswet.overheid.nl) "
    "voor de officiele vergunning- of meldingsplicht."
)


def build_prompt(vraag: str, passages: list[dict]) -> str:
    context = "\n\n".join(f"[bron: {p['url']}]\n{p['text']}" for p in passages)
    return (
        "Je bent een feitelijke assistent over de Omgevingswet. Beantwoord de vraag "
        "uitsluitend op basis van onderstaande context. Verzin niets; trek geen juridische "
        "conclusies en doe geen stellige uitspraak over vergunningplicht. Als de context "
        "geen antwoord geeft, zeg dat eerlijk. Verwijs naar de gebruikte bron(nen).\n\n"
        f"Context:\n{context}\n\nVraag: {vraag}"
    )


def beantwoord(vraag: str, store, embed_fn, llm_base_url: str, model: str,
               top_k: int = 4, timeout_s: float = 60.0) -> dict:
    base = {
        "vraag": vraag,
        "onzekerheid": True,
        "disclaimer": DISCLAIMER,
        "vangnet": VANGNET,
    }
    try:
        qvec = embed_fn([vraag])[0]
        passages = store.search(qvec, top_k)
    except ConnectorError:
        return {**base, "antwoord": None, "bronnen": [], "beschikbaar": False}
    if not passages:
        return {**base, "antwoord": None, "bronnen": [], "beschikbaar": False}

    prompt = build_prompt(vraag, passages)
    try:
        resp = httpx.post(
            f"{llm_base_url.rstrip('/')}/chat/completions",
            json={"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.2},
            timeout=timeout_s,
        )
        resp.raise_for_status()
        antwoord = resp.json()["choices"][0]["message"]["content"].strip()
    except (httpx.HTTPError, KeyError, ValueError, IndexError):
        return {**base, "antwoord": None, "bronnen": [], "beschikbaar": False}

    bronnen = list(dict.fromkeys(p["url"] for p in passages))   # unieke URL's, volgorde behouden
    return {**base, "antwoord": antwoord, "bronnen": bronnen, "beschikbaar": True}
```

- [ ] **Step 4: Run test om te zien dat hij slaagt**

Run: `PYTHONPATH=src python -m pytest tests/test_chatbot.py -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/leefomgevinglab/usecases/vergunningen/chatbot.py tests/test_chatbot.py
git commit -m "feat(llab): vergunningen-chatbot (RAG + Qwen) met conservatief contract

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: REST-route POST /api/chat + GET /chatbot

**Files:**
- Modify: `src/geluidsmeter/api.py` (imports + helpers + 2 routes)
- Create: `src/leefomgevinglab/static/chat.html`
- Test: `tests/test_api_chat.py`

**Interfaces:**
- Consumes: `embed_texts` (Task 1), `VectorStore` (Task 2), `chatbot` (Task 4), `_config`.
- Produces (HTTP):
  - `POST /api/chat` body `{"vraag": str}` → het chatbot-contract (HTTP 200, ook bij
    `beschikbaar=False`; ook als de index ontbreekt → degradeert).
  - `GET /chatbot` → de chat-pagina (HTML).
  - Helpers: `_rag_store()` (laadt `VectorStore` uit `rag.store_dir`, of `None` als afwezig),
    `_rag_embed_fn()` (partial van `embed_texts` met config).

- [ ] **Step 1: Schrijf de falende test**

`tests/test_api_chat.py`:

```python
from fastapi.testclient import TestClient
import geluidsmeter.api as api


def _client(monkeypatch):
    api._config = {"leefomgevinglab": {
        "cache_dir": "/tmp/llab_test_cache",
        "rag": {"embed": {"base_url": "http://x/v1", "model": "bge"},
                "store_dir": "/tmp/llab_rag_test", "top_k": 4,
                "chunk_chars": 1200, "chunk_overlap": 200, "iplo_urls": []},
        "llm": {"base_url": "http://localhost:8080/v1", "model": "qwen2.5-32b", "timeout_s": 60},
    }}
    monkeypatch.setattr(api, "load_config", lambda *a, **k: api._config)
    return TestClient(api.app)


def test_chat_happy(monkeypatch):
    client = _client(monkeypatch)

    class _Store:
        def search(self, qv, k): return [{"text": "t", "url": "https://iplo.nl/a", "score": 0.9}]

    monkeypatch.setattr(api, "_rag_store", lambda: _Store())
    monkeypatch.setattr(api, "_rag_embed_fn", lambda: (lambda texts: [[1.0, 0.0] for _ in texts]))
    monkeypatch.setattr(api.chatbot, "beantwoord",
                        lambda vraag, store, embed_fn, **kw: {
                            "vraag": vraag, "antwoord": "ok", "bronnen": ["https://iplo.nl/a"],
                            "onzekerheid": True, "disclaimer": "d", "vangnet": "bevoegd gezag",
                            "beschikbaar": True})
    r = client.post("/api/chat", json={"vraag": "mag ik kappen?"})
    assert r.status_code == 200
    assert r.json()["antwoord"] == "ok"
    assert r.json()["bronnen"] == ["https://iplo.nl/a"]


def test_chat_no_index_degradeert(monkeypatch):
    client = _client(monkeypatch)
    monkeypatch.setattr(api, "_rag_store", lambda: None)
    r = client.post("/api/chat", json={"vraag": "iets"})
    assert r.status_code == 200
    assert r.json()["beschikbaar"] is False
```

- [ ] **Step 2: Run test om te zien dat hij faalt**

Run: `PYTHONPATH=src python -m pytest tests/test_api_chat.py -q`
Expected: FAIL (`AttributeError: ... has no attribute '_rag_store'`)

- [ ] **Step 3: Voeg imports toe bovenaan `src/geluidsmeter/api.py`**

Na de bestaande leefomgevinglab-imports:

```python
from functools import partial
from leefomgevinglab.rag.embed import embed_texts
from leefomgevinglab.rag.store import VectorStore
from leefomgevinglab.usecases.vergunningen import chatbot
```

- [ ] **Step 4: Voeg helpers + routes toe aan het eind van `src/geluidsmeter/api.py`**

```python
def _rag_embed_fn():
    rag = _config.get("leefomgevinglab", {}).get("rag", {})
    emb = rag.get("embed", {})
    return partial(embed_texts, base_url=emb.get("base_url", ""), model=emb.get("model", ""))


def _rag_store():
    rag = _config.get("leefomgevinglab", {}).get("rag", {})
    try:
        return VectorStore.load(rag.get("store_dir", ""))
    except FileNotFoundError:
        return None


class ChatRequest(BaseModel):
    vraag: str


@app.post("/api/chat")
def api_chat(req: ChatRequest):
    store = _rag_store()
    if store is None:
        return {
            "vraag": req.vraag, "antwoord": None, "bronnen": [], "onzekerheid": True,
            "disclaimer": chatbot.DISCLAIMER, "vangnet": chatbot.VANGNET, "beschikbaar": False,
        }
    rag = _config.get("leefomgevinglab", {}).get("rag", {})
    llm = _config.get("leefomgevinglab", {}).get("llm", {})
    return chatbot.beantwoord(
        req.vraag, store, _rag_embed_fn(),
        llm_base_url=llm.get("base_url", "http://localhost:8080/v1"),
        model=llm.get("model", "qwen2.5-32b"),
        top_k=rag.get("top_k", 4), timeout_s=llm.get("timeout_s", 60),
    )


@app.get("/chatbot", response_class=HTMLResponse)
def chatbot_page():
    return (Path(__file__).parent.parent / "leefomgevinglab" / "static" / "chat.html").read_text()
```

- [ ] **Step 5: Maak de chat-frontend**

`src/leefomgevinglab/static/chat.html`:

```html
<!DOCTYPE html>
<html lang="nl">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>LeefomgevingLab — Vergunningen-chatbot</title>
  <style>
    body { margin: 0; font-family: system-ui, sans-serif; background: #080c14; color: #e0e6ed; }
    header { background: #0d1b2a; border-bottom: 1px solid #1a3a5c; padding: 12px 18px; }
    header a { color: #2ecc8f; text-decoration: none; font-size: 13px; }
    main { max-width: 760px; margin: 0 auto; padding: 18px; }
    h1 { font-size: 18px; color: #eafff6; margin: 0 0 4px; }
    .muted { color: #8aa0b2; font-size: 12px; }
    #log { margin: 16px 0; display: flex; flex-direction: column; gap: 12px; }
    .msg { padding: 10px 12px; border-radius: 8px; font-size: 14px; line-height: 1.5; }
    .user { background: #14202e; align-self: flex-end; max-width: 80%; }
    .bot { background: #0d1b2a; border: 1px solid #1a3a5c; }
    .bronnen { font-size: 11px; color: #8aa0b2; margin-top: 8px; }
    .bronnen a { color: #4fc3f7; }
    .disc { font-size: 11px; color: #b89; margin-top: 8px; }
    form { display: flex; gap: 8px; }
    input { flex: 1; padding: 10px; border-radius: 8px; border: 1px solid #1a3a5c; background: #0a1220; color: #e0e6ed; }
    button { padding: 10px 16px; border-radius: 8px; border: none; background: #2ecc8f; color: #042; font-weight: 700; cursor: pointer; }
  </style>
</head>
<body>
  <header><a href="/">← LeefomgevingLab</a></header>
  <main>
    <h1>Vergunningen-chatbot</h1>
    <p class="muted">Vraag indicatief wat de regels zeggen over een activiteit. Antwoorden met bronverwijzing; geen juridisch besluit.</p>
    <div id="log"></div>
    <form id="f">
      <input id="q" placeholder="bv. mag ik een boom kappen in mijn tuin?" autocomplete="off" />
      <button>Vraag</button>
    </form>
  </main>
  <script>
    const log = document.getElementById("log");
    function add(cls, html) { const d = document.createElement("div"); d.className = "msg " + cls; d.innerHTML = html; log.appendChild(d); d.scrollIntoView(); return d; }
    document.getElementById("f").addEventListener("submit", async (e) => {
      e.preventDefault();
      const q = document.getElementById("q").value.trim();
      if (!q) return;
      add("user", q.replace(/</g, "&lt;"));
      document.getElementById("q").value = "";
      const pending = add("bot", "Bezig…");
      try {
        const r = await fetch("/api/chat", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ vraag: q }) });
        const d = await r.json();
        if (!d.beschikbaar) {
          pending.innerHTML = '<p>Geen antwoord beschikbaar (index of model offline).</p><div class="disc">' + d.vangnet + '</div>';
          return;
        }
        const bronnen = (d.bronnen || []).map(u => '<a href="' + u + '" target="_blank">' + u + '</a>').join("<br>");
        pending.innerHTML = "<p>" + d.antwoord.replace(/</g, "&lt;") + "</p>" +
          (bronnen ? '<div class="bronnen">Bronnen:<br>' + bronnen + "</div>" : "") +
          '<div class="disc">' + d.disclaimer + "<br>" + d.vangnet + "</div>";
      } catch (err) { pending.innerHTML = "Er ging iets mis."; }
    });
  </script>
</body>
</html>
```

- [ ] **Step 6: Run test + volledige suite**

Run: `PYTHONPATH=src python -m pytest tests/test_api_chat.py -q`
Expected: PASS (2 passed)
Run: `PYTHONPATH=src python -m pytest -q`
Expected: PASS — alles groen.

- [ ] **Step 7: Commit**

```bash
git add src/geluidsmeter/api.py src/leefomgevinglab/static/chat.html tests/test_api_chat.py
git commit -m "feat(llab): POST /api/chat + chat-frontend op /chatbot

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: Eval-set (contract-bewaking)

**Files:**
- Create: `tests/test_chatbot_eval.py`
- Create: `scripts/08_eval_chatbot_live.py`

**Interfaces:**
- Consumes: `chatbot.beantwoord` (Task 4) met gemockte LLM + store.
- Produces: een eval-test die op een set bekende vragen het **antwoordcontract** afdwingt
  (bronnen aanwezig bij beschikbaar antwoord, disclaimer + vangnet altijd aanwezig, geen veld dat
  een stellige vergunning-ja/nee claimt) en een los live-eval-script voor handmatige kwaliteitscheck.

- [ ] **Step 1: Schrijf de eval-test**

`tests/test_chatbot_eval.py`:

```python
import httpx
import pytest
from leefomgevinglab.usecases.vergunningen import chatbot

EVAL_VRAGEN = [
    "mag ik een boom kappen in mijn tuin?",
    "heb ik een vergunning nodig voor een dakkapel?",
    "moet ik een melding doen voor een uitrit?",
]


class _Resp:
    def __init__(self, payload): self._p = payload; self.status_code = 200
    def raise_for_status(self): pass
    def json(self): return self._p


class _Store:
    def search(self, qv, k): return [{"text": "relevante passage", "url": "https://iplo.nl/x", "score": 0.8}]


def _embed(texts): return [[1.0, 0.0] for _ in texts]


@pytest.mark.parametrize("vraag", EVAL_VRAGEN)
def test_contract_op_eval_vragen(vraag, monkeypatch):
    monkeypatch.setattr(httpx, "post",
                        lambda url, json=None, timeout=None: _Resp(
                            {"choices": [{"message": {"content": "Indicatief antwoord met verwijzing."}}]}))
    out = chatbot.beantwoord(vraag, _Store(), _embed,
                             llm_base_url="http://localhost:8080/v1", model="qwen2.5-32b")
    # antwoordcontract afdwingen
    assert out["beschikbaar"] is True
    assert out["bronnen"], "antwoord moet bronnen bevatten"
    assert out["onzekerheid"] is True
    assert "bevoegd gezag" in out["vangnet"]
    assert out["disclaimer"]
    # geen stellige vergunning-conclusie als gestructureerd veld
    assert "vergunningplichtig" not in out
    assert "conclusie" not in out
```

- [ ] **Step 2: Run de eval-test**

Run: `PYTHONPATH=src python -m pytest tests/test_chatbot_eval.py -q`
Expected: PASS (3 passed — één per eval-vraag)

- [ ] **Step 3: Live-eval-script (handmatig, geen test)**

`scripts/08_eval_chatbot_live.py`:

```python
#!/usr/bin/env python3
"""Handmatige kwaliteitscheck van de chatbot tegen de echte index + Qwen.
Vereist een gebouwde RAG-index en een draaiende embedding- en Qwen-server."""
import sys
from functools import partial
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import yaml
from leefomgevinglab.rag.embed import embed_texts
from leefomgevinglab.rag.store import VectorStore
from leefomgevinglab.usecases.vergunningen import chatbot

VRAGEN = [
    "mag ik een boom kappen in mijn tuin?",
    "heb ik een vergunning nodig voor een dakkapel?",
]


def main():
    cfg = yaml.safe_load(open(Path(__file__).parent.parent / "core" / "config.yaml"))["leefomgevinglab"]
    rag, llm = cfg["rag"], cfg["llm"]
    store = VectorStore.load(rag["store_dir"])
    embed_fn = partial(embed_texts, base_url=rag["embed"]["base_url"], model=rag["embed"]["model"])
    for v in VRAGEN:
        out = chatbot.beantwoord(v, store, embed_fn, llm_base_url=llm["base_url"], model=llm["model"], top_k=rag["top_k"])
        print(f"\nQ: {v}\nA: {out['antwoord']}\nbronnen: {out['bronnen']}\nbeschikbaar: {out['beschikbaar']}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Commit**

```bash
git add tests/test_chatbot_eval.py scripts/08_eval_chatbot_live.py
git commit -m "test(llab): eval-set die het chatbot-antwoordcontract bewaakt

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 7: Landing + docs

**Files:**
- Modify: `src/leefomgevinglab/static/index.html` (chatbot-kaart van "binnenkort" naar live + link `/chatbot`)
- Modify: `CLAUDE.md` (sprint-status + nieuwe routes/afhankelijkheden)

**Interfaces:** geen code.

- [ ] **Step 1: Landing bijwerken**

In `src/leefomgevinglab/static/index.html`: maak de "Vergunningen-chatbot"-kaart een live link
(`<a class="card live" href="/chatbot">`) en zet de pill van `binnenkort` naar `nieuw`. Voeg geen
nieuwe afhankelijkheid-tekst toe die niet klopt.

- [ ] **Step 2: CLAUDE.md bijwerken**

Voeg onder "Sprint status" een regel toe over UC-03b: RAG (IPLO via llama.cpp `/v1/embeddings`) +
vergunningen-chatbot op `/chatbot` (`POST /api/chat`), met noot dat een embedding-server (default
poort 8082) en een gebouwde index (`scripts/07_build_rag_index.py`) nodig zijn voor live gebruik.

- [ ] **Step 3: Commit**

```bash
git add src/leefomgevinglab/static/index.html CLAUDE.md
git commit -m "docs(llab): chatbot live op landing + CLAUDE.md UC-03b

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Out of scope (later)

- DSO-koppeling in de chatbot (rules-as-code uit Plan 2a meewegen) — wacht op `DSO_API_KEY`.
- Stelselcatalogus / begrippen-verkenner (UC-09).
- Herrank/embeddings-cache, conversatie-geheugen (multi-turn), streaming-antwoorden.
- Automatische herbouw van de index (cron) — nu handmatig via `scripts/07_build_rag_index.py`.

## Self-Review

- **Spec-dekking (ontwerp sectie D):** RAG-pijplijn (ingest→chunk→embed→vectorstore op NVMe) → Tasks 1-3; conversationele chatbot met antwoordcontract (bron/onzekerheid/vangnet, geen stellige uitspraak, prompt "alleen context") → Task 4 + Task 5; eval-set → Task 6; frontend → Task 5; embeddings via llama.cpp `/v1/embeddings` → Task 1 + config. DSO-rules-as-code in de chat → expliciet out of scope (key).
- **Placeholders:** geen TODO/TBD in code; embedding-server + IPLO-URL's zijn config-waarden met een gemarkeerde verify/setup-stap (Task 3 Step 5). De `config_compat`-import in het build-script is expliciet als te verwijderen overblijfsel gemarkeerd — implementer laat 'm weg (script leest config via `yaml`).
- **Type-consistentie:** `embed_texts(texts, base_url, model, timeout_s)`, `VectorStore.build/save/load/search/size`, `build_index(urls, embed_fn, chunk_chars, overlap)`, `chatbot.beantwoord(vraag, store, embed_fn, llm_base_url, model, top_k, timeout_s)`, `_rag_store()/_rag_embed_fn()` consistent over Tasks 1→6. `embed_fn`-signatuur (`list[str] -> list[list[float]]`) consistent tussen ingest, chatbot en de api-helper (partial van `embed_texts`).
- **Contract-garantie:** `chatbot.beantwoord` bouwt `base` (onzekerheid/disclaimer/vangnet) vóór elke vertakking en spreidt het in álle returns (happy + 3 degradatiepaden); `/api/chat` geeft hetzelfde contract terug als de index ontbreekt. Eval-test dwingt dit af.
```
