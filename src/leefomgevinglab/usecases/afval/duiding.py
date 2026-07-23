"""UC-08: korte AI-duiding van een afval-trend via lokale Qwen.

No-hallucination: gebruikt uitsluitend de meegegeven cijfers, met bronverwijzing.
"""
import httpx

from leefomgevinglab.connectors.base import ConnectorError

BRON = "CBS StatLine 83558NED (CC-BY 4.0)"
DISCLAIMER = (
    "Indicatief. Cijfers zijn een open proxy (CBS) voor het gesloten "
    "LMA/AMICE-aggregaat, geen officiele LMA-meldgegevens."
)


def build_prompt(regio_naam: str, afvalstroom: str, reeks: list[dict]) -> str:
    regels = "\n".join(
        f"- {p['jaar']}: {p['hoeveelheid_kton']} kton"
        + ("" if p.get("circulariteit_pct") is None
           else f", circulariteit {round(p['circulariteit_pct'], 1)}%")
        for p in reeks
    )
    return (
        "Je bent een feitelijke data-assistent. Vat de trend hieronder in 2-3 zinnen "
        "begrijpelijk samen voor een burger. Verzin niets; gebruik uitsluitend de "
        "gegeven getallen. Trek geen beleidsconclusies.\n\n"
        f"Provincie: {regio_naam}\nAfvalstroom: {afvalstroom}\nReeks:\n{regels}"
    )


def duiding(regio_naam: str, afvalstroom: str, reeks: list[dict],
            llm_base_url: str, model: str, timeout_s: float = 60.0) -> dict:
    prompt = build_prompt(regio_naam, afvalstroom, reeks)
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
