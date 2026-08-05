"""AEO/GEO (Answer/Generative Engine Optimization) audit.

STRATEGIA_SYSTEM_POZYSKIWANIA_LEADOW.md sekcja 6 wskazuje `Auriti-Labs/geo-
optimizer-skill` jako gotowy kod pod audyt cytowalnosci w ChatGPT/Perplexity/
Gemini/AI Overviews. Zweryfikowane 2026-08-05: to prawdziwy, aktywnie
rozwijany pakiet PyPI (`pip install geo-optimizer-skill`, MIT, wersja 4.x) --
uzywamy go bezposrednio przez `geo_optimizer.audit()`, bez forka.

Dwa tryby pracy tego pakietu:
- Audyt techniczny (ten modul) -- BEZ kluczy API: robots.txt (27 botow AI),
  llms.txt, schema.org JSON-LD, meta tagi, struktura tresci, sygnaly marki/
  entity, punkty odkrywania AI (.well-known/ai.txt). To co mierzymy tutaj.
- `geo citations` (CLI pakietu, NIE zawarte w tym module) -- realne zapytania
  do ChatGPT/Perplexity/Anthropic API sprawdzajace czy marka jest faktycznie
  cytowana. Wymaga kluczy API (Perplexity/OpenAI/Anthropic) i kosztuje per
  zapytanie -- poza zakresem kroku 3, do rozwazenia gdy lejek bedzie dzialal
  na sygnalach technicznych.

Audyt trwa ~15-20s/domena (wiele sprawdzen HTTP) -- przy walidacji wsadowej
liczyc sie z czasem, nie z limitem zapytan (brak limitu, dziala lokalnie).
"""
import dataclasses

import geo_optimizer


def run_aeo_geo_audit(url: str, use_cache: bool = False) -> dict:
    """Run the technical AEO/GEO readiness audit for `url`.

    Returns {"score": int 0-100, "band": str, "issues": [str, ...], "raw_data": dict}.
    `issues` is geo_optimizer's own prioritized recommendations list (top 8).
    Raises whatever geo_optimizer.audit() raises on unreachable domains --
    caller decides how to record that as a failed audit.
    """
    result = geo_optimizer.audit(url, use_cache=use_cache)
    raw = dataclasses.asdict(result)
    recommendations = result.recommendations or []
    return {
        "score": result.score,
        "band": result.band,
        "issues": list(recommendations[:8]),
        "raw_data": raw,
    }
