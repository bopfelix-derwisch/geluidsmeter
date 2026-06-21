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
