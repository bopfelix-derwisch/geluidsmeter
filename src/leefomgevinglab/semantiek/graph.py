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


# Velden in de IMEV vocab-JSON die als relatie tellen.
_VOCAB_REL = {"isEngerDan": "narrower", "isBrederDan": "broader"}


def bron_from_uri(uri: str, imxgeo_uris: set[str]) -> str:
    if uri in imxgeo_uris or "imx-geo" in uri:
        return "IMX-Geo"
    if "/imev/" in uri:
        return "IMEV"
    host = uri.split("//")[-1].split("/")[0]
    if "rev" in uri or "externe-veiligheid" in uri:
        return "REV"
    return _HOST_BRON.get(host, host)


def _label(g: rdflib.Graph, uri: rdflib.URIRef) -> str:
    for pred in (SKOS.prefLabel, RDFS.label):
        for o in g.objects(uri, pred):
            return str(o)
    return str(uri).rstrip("/").split("/")[-1]


def build_graph(ttl_texts: list[str], vocab_docs: list | None = None) -> dict:
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

    def add_node(uri: str, label: str | None = None, definitie: str | None = None) -> None:
        if uri in nodes:
            if definitie and not nodes[uri]["data"].get("definitie"):
                nodes[uri]["data"]["definitie"] = definitie
            return
        ref = rdflib.URIRef(uri)
        if label is None:
            label = _label(g, ref)
        if definitie is None:
            definitie = next((str(o) for o in g.objects(ref, SKOS.definition)), None)
        nodes[uri] = {"data": {
            "id": uri,
            "label": label,
            "bron": bron_from_uri(uri, imxgeo),
            "definitie": definitie,
        }}

    def add_edge(su: str, rel: str, ou: str) -> None:
        eid = f"{su}|{rel}|{ou}"
        if eid in seen:
            return
        seen.add(eid)
        edges.append({"data": {"id": eid, "source": su, "target": ou, "relatie": rel}})

    # TTL-bronnen (IMX-Geo)
    for s, p, o in g:
        if p in _REL and isinstance(o, rdflib.URIRef):
            su, ou = str(s), str(o)
            add_node(su)
            add_node(ou)
            add_edge(su, _REL[p], ou)

    # Vocab-JSON-bronnen (IMEV begrippen): elk een lijst skos:Concept-dicts
    for doc in (vocab_docs or []):
        for c in doc:
            if not isinstance(c, dict) or c.get("@type") != "skos:Concept":
                continue
            uri = c.get("uri")
            if not uri:
                continue
            add_node(uri, label=c.get("naam") or c.get("term"), definitie=c.get("definitie"))
            for field, rel in _VOCAB_REL.items():
                val = c.get(field)
                if not val:
                    continue
                for tgt in (val if isinstance(val, list) else [val]):
                    if isinstance(tgt, str) and tgt:
                        add_node(tgt)
                        add_edge(uri, rel, tgt)

    # Heuristische cross-model koppeling: IMX-Geo <-> IMEV op gelijke begripsnaam.
    # (IMX-Geo en IMEV leggen onderling geen expliciete match; dit verbindt de clusters.)
    by_label: dict[str, list[tuple[str, str]]] = {}
    for uri, node in nodes.items():
        lab = (node["data"]["label"] or "").strip().lower()
        if lab:
            by_label.setdefault(lab, []).append((uri, node["data"]["bron"]))
    for group in by_label.values():
        imx = [u for u, b in group if b == "IMX-Geo"]
        imev = [u for u, b in group if b == "IMEV"]
        for a in imx:
            for b in imev:
                add_edge(a, "gelijkeNaam", b)

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
