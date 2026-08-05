"""Google PageSpeed Insights integration.

STRATEGIA_SYSTEM_POZYSKIWANIA_LEADOW.md sekcja 2, modul 1 opisuje to jako
"darmowe, bez klucza" -- zweryfikowane 2026-08-05: keyless requests teraz
dostaja przydzial 0 zapytan/dzien (Google przekierowuje je na projekt
anonimowy z zerowym limitem, error RESOURCE_EXHAUSTED). Klucz jest wiec
de facto wymagany. Zdobycie klucza jest nadal darmowe: Google Cloud Console ->
utworz projekt -> API i uslugi -> wlacz "PageSpeed Insights API" -> Poswiadczenia
-> API key. Ustaw go jako GOOGLE_PAGESPEED_API_KEY w .env.
"""
import os

import requests

PAGESPEED_ENDPOINT = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
DEFAULT_TIMEOUT = 30


class PageSpeedConfigError(RuntimeError):
    """Raised when GOOGLE_PAGESPEED_API_KEY is missing -- see module docstring."""


def run_pagespeed_audit(url: str, strategy: str = "mobile", timeout: int = DEFAULT_TIMEOUT) -> dict:
    """Call PageSpeed Insights for `url`. Returns category scores + core web vitals.

    Raises PageSpeedConfigError if no API key is configured, and
    requests.HTTPError/requests.RequestException on API failure (invalid
    domain, quota, timeout) -- caller decides how to record that as a failed
    audit rather than this module silently swallowing errors.
    """
    api_key = os.getenv("GOOGLE_PAGESPEED_API_KEY")
    if not api_key:
        raise PageSpeedConfigError(
            "GOOGLE_PAGESPEED_API_KEY nie jest ustawiony. Keyless PageSpeed API ma limit 0 "
            "zapytan/dzien od 2026 -- patrz docstring tego modulu po instrukcje zdobycia darmowego klucza."
        )

    params = {
        "url": url,
        "strategy": strategy,
        "category": ["performance", "seo", "accessibility", "best-practices"],
        "key": api_key,
    }

    resp = requests.get(PAGESPEED_ENDPOINT, params=params, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()

    lighthouse = data.get("lighthouseResult", {})
    categories = lighthouse.get("categories", {})
    audits = lighthouse.get("audits", {})

    def _score(cat_key):
        cat = categories.get(cat_key)
        return round(cat["score"] * 100, 1) if cat and cat.get("score") is not None else None

    def _metric(audit_key):
        a = audits.get(audit_key)
        return a.get("displayValue") if a else None

    return {
        "score": _score("performance"),
        "scores": {
            "performance": _score("performance"),
            "seo": _score("seo"),
            "accessibility": _score("accessibility"),
            "best_practices": _score("best-practices"),
        },
        "core_web_vitals": {
            "largest_contentful_paint": _metric("largest-contentful-paint"),
            "cumulative_layout_shift": _metric("cumulative-layout-shift"),
            "total_blocking_time": _metric("total-blocking-time"),
            "first_contentful_paint": _metric("first-contentful-paint"),
        },
        "strategy": strategy,
        "final_url": lighthouse.get("finalUrl"),
    }
