"""LMA/RWS-loader: nationale afvalcijfers per Euralcode/verwerking (open jaarrapportage).

Dichtst bij het AMICE-schema (Euralcode + R/D). Extractie via pdfplumber met
curated-CSV-fallback; parse_rows is puur en offline testbaar.
"""
import csv

from leefomgevinglab.afvaldb.crosswalk import canoniek


def bron(jaar: int) -> dict:
    return {"bron_id": f"lma-rws-{jaar}", "naam": f"LMA/RWS afvaloverzicht {jaar} (openbaar)",
            "url": "https://www.lma.nl/", "licentie": "open (voorwaarden)",
            "type": "report_pdf", "opgehaald_op": None}


def parse_rows(rows: list[dict], jaar: int) -> list[dict]:
    out = []
    for r in rows:
        eural = str(r["euralcode"]).strip()
        verwerking = str(r["verwerking"]).strip().upper()
        out.append({"bron_id": f"lma-rws-{jaar}", "regio_code": "NL", "jaar": jaar,
                    "afvalstroom_canoniek": canoniek("euralcode", eural), "euralcode": eural,
                    "verwerking": verwerking if verwerking in ("R", "D") else "onbekend",
                    "indicator_type": "volume", "hoeveelheid": float(r["ton"]), "eenheid": "ton"})
    return out


def parse_csv(path: str, jaar: int) -> list[dict]:
    with open(path, newline="") as f:
        rows = list(csv.DictReader(r for r in f if not r.startswith("#")))
    return parse_rows(rows, jaar)


def extract_pdf(pdf_path: str) -> list[dict]:
    """Extraheer {'euralcode','verwerking','ton'}-rijen uit een LMA/RWS-PDF-tabel."""
    import pdfplumber
    out = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            for tbl in page.extract_tables() or []:
                for row in tbl:
                    cells = [str(c).strip() for c in row if c]
                    if len(cells) < 3 or not cells[0].isdigit():
                        continue
                    ton = cells[-1].replace(".", "").replace(",", ".")
                    try:
                        out.append({"euralcode": cells[0], "verwerking": cells[1], "ton": float(ton)})
                    except ValueError:
                        continue
    return out
