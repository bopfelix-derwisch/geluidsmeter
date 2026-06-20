"""UC-04: AI-duiding van een REV-object via lokale Qwen."""
import httpx

from leefomgevinglab.connectors.base import ConnectorError

DISCLAIMER = (
    "Indicatief, geen juridisch oordeel. Raadpleeg het bevoegd gezag en "
    "registerexterneveiligheid.nl voor de officiele situatie."
)


def build_prompt(properties: dict) -> str:
    velden = "\n".join(f"- {k}: {v}" for k, v in properties.items() if v not in (None, ""))
    return (
        "Je bent een feitelijke assistent voor externe veiligheid. "
        "Vat onderstaand REV-object in 2-3 zinnen begrijpelijk samen voor een burger. "
        "Verzin niets; gebruik uitsluitend de gegeven velden. Trek geen juridische conclusies.\n\n"
        f"REV-object:\n{velden}"
    )


def duiding(properties: dict, llm_base_url: str, model: str, timeout_s: float = 60.0) -> dict:
    prompt = build_prompt(properties)
    try:
        resp = httpx.post(
            f"{llm_base_url.rstrip('/')}/chat/completions",
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
            },
            timeout=timeout_s,
        )
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"].strip()
    except (httpx.HTTPError, KeyError, ValueError, IndexError) as exc:
        raise ConnectorError("AI-duiding tijdelijk niet beschikbaar") from exc
    return {"duiding": text, "bron": "REV (PDOK OGC API Features)", "disclaimer": DISCLAIMER}
