"""IPLO-ingest: HTML ophalen -> tekst -> chunks -> embeddings -> VectorStore."""
import html as _html
import re

import httpx

from leefomgevinglab.connectors.base import ConnectorError
from leefomgevinglab.rag.store import VectorStore

# Verwijder eerst hele script/style/head/noscript-blokken (incl. inhoud), strip
# daarna de resterende tags. Robuuster dan html.parser op echte HTML met scripts.
_BLOCK_RE = re.compile(r"(?is)<(script|style|head|noscript)\b[^>]*>.*?</\1>")
_TAG_RE = re.compile(r"(?s)<[^>]+>")


def html_to_text(html: str) -> str:
    s = _BLOCK_RE.sub(" ", html)
    s = _TAG_RE.sub(" ", s)
    s = _html.unescape(s)
    return " ".join(s.split())


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
