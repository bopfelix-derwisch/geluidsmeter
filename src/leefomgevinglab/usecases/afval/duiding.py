"""UC-08: rijkere AI-duiding van een afvalstroom via lokale Qwen.

No-hallucination: gebruikt uitsluitend de meegegeven cijfers + achtergrond, met bronverwijzing.
De context wordt server-side samengesteld door service.stroom_context().
"""
import httpx

from leefomgevinglab.connectors.base import ConnectorError

BRON = "CBS StatLine 83558NED (CC-BY 4.0)"
DISCLAIMER = (
    "Indicatief. Cijfers zijn een open proxy (CBS) voor het gesloten "
    "LMA/AMICE-aggregaat, geen officiele LMA-meldgegevens."
)


def build_prompt(regio_naam: str, afvalstroom: str, jaar: int, context: dict) -> str:
    c = context or {}
    regels = []
    if c.get("waarde_kton") is not None:
        regels.append(f"- Hoeveelheid in {jaar}: {round(c['waarde_kton'], 1)} kton")
    if c.get("landelijk_gemiddelde_kton") is not None:
        pos = ("boven" if c.get("boven_gemiddeld") else "onder") if c.get("boven_gemiddeld") is not None else "rond"
        rang = f"; {c['rang']}e van {c['aantal_provincies']}" if c.get("rang") else ""
        regels.append(
            f"- Landelijk gemiddelde (provincies): {round(c['landelijk_gemiddelde_kton'], 1)} kton "
            f"({pos} gemiddeld{rang})")
    if c.get("aandeel_van_totaal_pct") is not None:
        regels.append(f"- Aandeel van totaal gemeentelijk afval: {round(c['aandeel_van_totaal_pct'], 1)}%")
    mj = c.get("meerjaren") or {}
    if mj.get("volume_pct") is not None:
        extra = "" if mj.get("circ_pct_punt") is None else f", circulariteit {mj['circ_pct_punt']:+.0f} procentpunt"
        regels.append(f"- Verandering {mj.get('van_jaar')}–{mj.get('tot_jaar')}: volume {mj['volume_pct']:+.0f}%{extra}")
    if c.get("circulariteit_pct") is not None:
        regels.append(f"- Circulariteit provincie in {jaar}: {round(c['circulariteit_pct'], 1)}%")
    hi, lo = c.get("hoogste"), c.get("laagste")
    if hi and lo:
        regels.append(f"- Hoogste provincie: {hi['naam']} ({round(hi['waarde_kton'], 1)} kton); "
                      f"laagste: {lo['naam']} ({round(lo['waarde_kton'], 1)} kton)")
    if c.get("achtergrond"):
        regels.append(f"- Achtergrond: {c['achtergrond']}")
    body = "\n".join(regels)
    return (
        "Je bent een feitelijke data-assistent. Vat onderstaande cijfers over deze afvalstroom in "
        "3-5 zinnen begrijpelijk samen voor een burger: benoem hoe de provincie zich verhoudt tot het "
        "landelijk beeld, de meerjarentrend en het aandeel. Verzin niets; gebruik uitsluitend de gegeven "
        "getallen en achtergrond. Trek geen beleidsconclusies.\n\n"
        f"Provincie: {regio_naam}\nAfvalstroom: {afvalstroom}\nJaar: {jaar}\n{body}"
    )


def duiding(regio_naam: str, afvalstroom: str, jaar: int, context: dict,
            llm_base_url: str, model: str, timeout_s: float = 60.0) -> dict:
    prompt = build_prompt(regio_naam, afvalstroom, jaar, context)
    try:
        resp = httpx.post(
            f"{llm_base_url.rstrip('/')}/chat/completions",
            json={"model": model, "messages": [{"role": "user", "content": prompt}],
                  "temperature": 0.2},
            timeout=timeout_s,
        )
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"].strip()
    except (httpx.HTTPError, KeyError, ValueError, IndexError) as exc:
        raise ConnectorError("AI-duiding tijdelijk niet beschikbaar") from exc
    return {"duiding": text, "bron": BRON, "disclaimer": DISCLAIMER}
