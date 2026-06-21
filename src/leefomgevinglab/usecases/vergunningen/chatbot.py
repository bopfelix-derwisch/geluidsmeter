"""UC-03b: vergunningen-chatbot op RAG (IPLO) + Qwen, conservatief contract."""
import httpx

from leefomgevinglab.connectors.base import ConnectorError

DISCLAIMER = (
    "Indicatief, geen juridisch besluit. Het antwoord is gebaseerd op de getoonde "
    "IPLO-passages en kan onvolledig zijn."
)
VANGNET = (
    "Raadpleeg het bevoegd gezag of het Omgevingsloket (omgevingswet.overheid.nl) "
    "voor de officiele vergunning- of meldingsplicht."
)


def build_prompt(vraag: str, passages: list[dict]) -> str:
    context = "\n\n".join(f"[bron: {p['url']}]\n{p['text']}" for p in passages)
    return (
        "Je bent een feitelijke assistent over de Omgevingswet. Beantwoord de vraag "
        "uitsluitend op basis van onderstaande context. Verzin niets; trek geen juridische "
        "conclusies en doe geen stellige uitspraak over vergunningplicht. Als de context "
        "geen antwoord geeft, zeg dat eerlijk. Verwijs naar de gebruikte bron(nen).\n\n"
        f"Context:\n{context}\n\nVraag: {vraag}"
    )


def beantwoord(vraag: str, store, embed_fn, llm_base_url: str, model: str,
               top_k: int = 4, timeout_s: float = 60.0) -> dict:
    base = {
        "vraag": vraag,
        "onzekerheid": True,
        "disclaimer": DISCLAIMER,
        "vangnet": VANGNET,
    }
    try:
        qvec = embed_fn([vraag])[0]
        passages = store.search(qvec, top_k)
    except ConnectorError:
        return {**base, "antwoord": None, "bronnen": [], "beschikbaar": False}
    if not passages:
        return {**base, "antwoord": None, "bronnen": [], "beschikbaar": False}

    prompt = build_prompt(vraag, passages)
    try:
        resp = httpx.post(
            f"{llm_base_url.rstrip('/')}/chat/completions",
            json={"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.2},
            timeout=timeout_s,
        )
        resp.raise_for_status()
        antwoord = resp.json()["choices"][0]["message"]["content"].strip()
    except (httpx.HTTPError, KeyError, ValueError, IndexError):
        return {**base, "antwoord": None, "bronnen": [], "beschikbaar": False}

    bronnen = list(dict.fromkeys(p["url"] for p in passages))   # unieke URL's, volgorde behouden
    return {**base, "antwoord": antwoord, "bronnen": bronnen, "beschikbaar": True}
