#!/usr/bin/env python3
"""Bouw de semantiek-graaf uit de geconfigureerde IMX-Geo TTL-URL's."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import yaml
from leefomgevinglab.semantiek.ingest import fetch_all, fetch_all_json
from leefomgevinglab.semantiek.graph import build_graph, save_graph


def main():
    cfg = yaml.safe_load(open(Path(__file__).parent.parent / "core" / "config.yaml"))["leefomgevinglab"]["semantiek"]
    texts = fetch_all(cfg["ttl_urls"])
    vocab_docs = fetch_all_json(cfg.get("vocab_json_urls", []))
    graph = build_graph(texts, vocab_docs)
    save_graph(graph, cfg["store_dir"])
    print(f"Semantiek-graaf: {len(graph['nodes'])} nodes, {len(graph['edges'])} edges, "
          f"bronnen {graph['bronnen']} -> {cfg['store_dir']}")


if __name__ == "__main__":
    main()
