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
