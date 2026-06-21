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
