"""Afvalfonds/Verpact-loader: recyclingpercentage per materiaal (NL).

Bron = jaarrapportage (PDF) op verpact.nl. Extractie via pdfplumber met
curated-CSV-fallback; parse_rows is puur en offline testbaar.
"""
import csv

from leefomgevinglab.afvaldb.crosswalk import canoniek


def bron(jaar: int) -> dict:
    return {"bron_id": f"afvalfonds-{jaar}", "naam": f"Afvalfonds Verpakkingen — resultaten recycling {jaar}",
            "url": "https://www.verpact.nl/", "licentie": "open (voorwaarden)",
            "type": "report_pdf", "opgehaald_op": None}


def parse_rows(rows: list[dict], jaar: int) -> list[dict]:
    out = []
    for r in rows:
        stroom = canoniek("afvalfonds_materiaal", str(r["materiaal"]).strip())
        if stroom is None:
            continue
        out.append({"bron_id": f"afvalfonds-{jaar}", "regio_code": "NL", "jaar": jaar,
                    "afvalstroom_canoniek": stroom, "euralcode": None, "verwerking": "R",
                    "indicator_type": "recyclingpercentage", "hoeveelheid": float(r["recycling_pct"]),
                    "eenheid": "pct"})
    return out


def parse_csv(path: str, jaar: int) -> list[dict]:
    with open(path, newline="") as f:
        rows = list(csv.DictReader(r for r in f if not r.startswith("#")))
    return parse_rows(rows, jaar)


def extract_pdf(pdf_path: str) -> list[dict]:
    """Extraheer {'materiaal','recycling_pct'}-rijen uit een Afvalfonds-PDF-tabel.
    Zoekt regels 'Materiaal ... <getal>%'. Gebruikt door het ingest-script."""
    import pdfplumber
    out = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            for tbl in page.extract_tables() or []:
                for row in tbl:
                    cells = [c for c in row if c]
                    if len(cells) < 2:
                        continue
                    materiaal = str(cells[0]).strip()
                    pct = str(cells[-1]).replace("%", "").replace(",", ".").strip()
                    try:
                        out.append({"materiaal": materiaal, "recycling_pct": float(pct)})
                    except ValueError:
                        continue
    return out
