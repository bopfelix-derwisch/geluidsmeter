#!/usr/bin/env python3
"""Bouw/ververs de RAG-index uit de geconfigureerde IPLO-URL's."""
import sys
from functools import partial
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

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
