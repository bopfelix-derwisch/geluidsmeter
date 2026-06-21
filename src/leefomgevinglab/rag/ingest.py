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
