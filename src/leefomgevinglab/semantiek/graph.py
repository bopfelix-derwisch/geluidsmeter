"""Bouw een Cytoscape-graaf uit IMX-Geo linked data (rdflib)."""
import json
from pathlib import Path

import rdflib
from rdflib.namespace import SKOS, RDFS

_REL = {
    SKOS.closeMatch: "closeMatch",
    SKOS.exactMatch: "exactMatch",
    SKOS.broader: "broader",
    SKOS.narrower: "narrower",
    SKOS.related: "related",
}

_HOST_BRON = {
    "bag.basisregistraties.overheid.nl": "BAG",
    "bgt.basisregistraties.overheid.nl": "BGT",
    "brk.basisregistraties.overheid.nl": "BRK",
}


def bron_from_uri(uri: str, imxgeo_uris: set[str]) -> str:
    if uri in imxgeo_uris or "imx-geo" in uri:
        return "IMX-Geo"
    host = uri.split("//")[-1].split("/")[0]
    if "rev" in uri or "externe-veiligheid" in uri:
        return "REV"
    return _HOST_BRON.get(host, host)


def _label(g: rdflib.Graph, uri: rdflib.URIRef) -> str:
    for pred in (SKOS.prefLabel, RDFS.label):
        for o in g.objects(uri, pred):
            return str(o)
    return str(uri).rstrip("/").split("/")[-1]


def build_graph(ttl_texts: list[str]) -> dict:
    g = rdflib.Graph()
    for text in ttl_texts:
        try:
            g.parse(data=text, format="turtle")
        except Exception:
            continue
    imxgeo = {str(s) for s in g.subjects(SKOS.inScheme, None)}
    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    seen: set[str] = set()

    def add_node(uri: str) -> None:
        if uri in nodes:
            return
        ref = rdflib.URIRef(uri)
        definitie = next((str(o) for o in g.objects(ref, SKOS.definition)), None)
        nodes[uri] = {"data": {
            "id": uri,
            "label": _label(g, ref),
            "bron": bron_from_uri(uri, imxgeo),
            "definitie": definitie,
        }}

    for s, p, o in g:
        if p in _REL and isinstance(o, rdflib.URIRef):
            su, ou = str(s), str(o)
            add_node(su)
            add_node(ou)
            eid = f"{su}|{_REL[p]}|{ou}"
            if eid in seen:
                continue
            seen.add(eid)
            edges.append({"data": {"id": eid, "source": su, "target": ou, "relatie": _REL[p]}})

    bronnen = sorted({n["data"]["bron"] for n in nodes.values()})
    return {"nodes": list(nodes.values()), "edges": edges, "bronnen": bronnen}


def save_graph(graph: dict, store_dir: str) -> None:
    d = Path(store_dir)
    d.mkdir(parents=True, exist_ok=True)
    (d / "graph.json").write_text(json.dumps(graph))


def load_graph(store_dir: str) -> dict | None:
    p = Path(store_dir) / "graph.json"
    if not p.exists():
        return None
    return json.loads(p.read_text())
