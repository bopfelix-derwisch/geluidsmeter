"""Lokale rdflib triple-store: Turtle op NVMe + lokale SPARQL."""
from pathlib import Path

import rdflib


def save_graph(graph: rdflib.Graph, store_dir: str, naam: str = "rev.ttl") -> None:
    d = Path(store_dir)
    d.mkdir(parents=True, exist_ok=True)
    graph.serialize(destination=str(d / naam), format="turtle")


def load_graph(store_dir: str, naam: str = "rev.ttl") -> rdflib.Graph | None:
    p = Path(store_dir) / naam
    if not p.exists():
        return None
    g = rdflib.Graph()
    g.parse(str(p), format="turtle")
    return g


def run_sparql(graph: rdflib.Graph, query: str) -> list[dict]:
    res = graph.query(query)
    rows = []
    for row in res:
        rows.append({str(var): (str(row[var]) if row[var] is not None else None) for var in res.vars})
    return rows
