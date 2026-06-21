import pytest
from leefomgevinglab.rag.store import VectorStore


def test_build_empty_does_not_crash():
    s = VectorStore.build([], [])
    assert s.size == 0
    assert s.search([1.0, 0.0], k=3) == []


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
