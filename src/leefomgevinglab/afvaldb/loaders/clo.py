"""CLO-loader: huishoudelijk afval per inwoner (curated CSV-snapshot, CBS-afgeleid)."""
import csv

BRON = {"bron_id": "clo-nl014437", "naam": "Compendium voor de Leefomgeving — afval huishoudens per inwoner",
        "url": "https://www.clo.nl/indicatoren/nl014437-afval-van-huishoudens-per-inwoner-1950-2024",
        "licentie": "CC-BY (CLO)", "type": "report_data", "opgehaald_op": None}


def parse_csv(path: str) -> list[dict]:
    out = []
    with open(path, newline="") as f:
        for row in csv.DictReader(r for r in f if not r.startswith("#")):
            out.append({"bron_id": "clo-nl014437", "regio_code": "NL", "jaar": int(row["jaar"]),
                        "afvalstroom_canoniek": "Totaal huishoudelijk afval", "euralcode": None,
                        "verwerking": "onbekend", "indicator_type": "per_inwoner",
                        "hoeveelheid": float(row["kg_per_inwoner"]), "eenheid": "kg_per_inwoner"})
    return out
