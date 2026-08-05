"""Lightweight on-page SEO audit.

STRATEGIA_SYSTEM_POZYSKIWANIA_LEADOW.md sekcja 2/10 proponuje fork/integracje
`StJudeWasHere/seonaut` (MIT). Seonaut jest osobna aplikacja Go dystrybuowana
przez docker-compose -- ten srodowisko nie ma Dockera ani Go, wiec zamiast
forka jest to natywna implementacja Pythonowa pokrywajaca ten sam zestaw
sprawdzen on-page co seonaut podkresla w swoim opisie: title, meta
description, naglowki, canonical, robots.txt, sitemap.xml, atrybuty alt,
viewport/RWD. To NIE jest port kodu seonaut -- niezalezna implementacja,
zeby uniknac pytan o licencje przy komercyjnym uzyciu.

Reuses bulk_crawler.is_safe_url() for SSRF protection -- domains here can
come from user-uploaded CRM files just like the main crawler, same threat
model applies.
"""
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from bulk_crawler import is_safe_url  # noqa: E402

DEFAULT_TIMEOUT = 10
USER_AGENT = "Mozilla/5.0 (compatible; LeadSeasonAuditBot/1.0; +https://ai-ops.pl)"

_PENALTIES = {
    "https": 15,
    "title_missing": 10,
    "title_length_bad": 5,
    "meta_description_missing": 10,
    "meta_description_length_bad": 4,
    "h1_missing": 10,
    "h1_multiple": 4,
    "canonical_missing": 8,
    "images_missing_alt": 8,
    "robots_missing": 5,
    "sitemap_missing": 5,
    "viewport_missing": 6,
}


def run_onpage_audit(url: str, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """Fetch `url` and score it against a fixed set of on-page SEO checks.

    Returns {"score": float 0-100, "issues": [str, ...], "checks": {...}, "final_url": str}.
    Raises ValueError if the URL is blocked by the SSRF guard, and
    requests.RequestException if the initial fetch fails -- caller decides
    how to record that as a failed audit.
    """
    if not is_safe_url(url):
        raise ValueError(f"Blocked: {url} resolves to a non-public address")

    resp = requests.get(url, timeout=timeout, headers={"User-Agent": USER_AGENT}, allow_redirects=True)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    parsed = urlparse(resp.url)
    origin = f"{parsed.scheme}://{parsed.netloc}"

    issues = []
    checks = {"https": parsed.scheme == "https"}
    if not checks["https"]:
        issues.append("Strona nie wymusza HTTPS.")

    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else ""
    checks["title_length"] = len(title)
    if not title:
        issues.append("Brak znacznika <title>.")
    elif not (10 <= len(title) <= 60):
        issues.append(f"Tytul poza zalecana dlugoscia 10-60 znakow ({len(title)}).")

    meta_desc = soup.find("meta", attrs={"name": "description"})
    desc = meta_desc.get("content", "").strip() if meta_desc else ""
    checks["meta_description_length"] = len(desc)
    if not desc:
        issues.append("Brak meta description.")
    elif not (50 <= len(desc) <= 160):
        issues.append(f"Meta description poza zalecana dlugoscia 50-160 znakow ({len(desc)}).")

    h1_tags = soup.find_all("h1")
    checks["h1_count"] = len(h1_tags)
    if len(h1_tags) == 0:
        issues.append("Brak znacznika H1.")
    elif len(h1_tags) > 1:
        issues.append(f"Wiecej niz jeden H1 ({len(h1_tags)}).")

    canonical = soup.find("link", attrs={"rel": "canonical"})
    checks["has_canonical"] = canonical is not None and bool(canonical.get("href"))
    if not checks["has_canonical"]:
        issues.append("Brak znacznika canonical.")

    images = soup.find_all("img")
    missing_alt = [img for img in images if not img.get("alt", "").strip()]
    checks["images_total"] = len(images)
    checks["images_missing_alt"] = len(missing_alt)
    if images and missing_alt:
        issues.append(f"{len(missing_alt)}/{len(images)} obrazkow bez atrybutu alt.")

    checks["has_robots_txt"] = _url_returns_200(urljoin(origin, "/robots.txt"), timeout)
    if not checks["has_robots_txt"]:
        issues.append("Brak dostepnego robots.txt.")

    checks["has_sitemap_xml"] = _url_returns_200(urljoin(origin, "/sitemap.xml"), timeout)
    if not checks["has_sitemap_xml"]:
        issues.append("Brak dostepnego sitemap.xml pod domyslna sciezka.")

    viewport = soup.find("meta", attrs={"name": "viewport"})
    checks["has_viewport_meta"] = viewport is not None
    if not checks["has_viewport_meta"]:
        issues.append("Brak meta viewport (mozliwy brak RWD).")

    return {"score": _score_from_checks(checks), "issues": issues, "checks": checks, "final_url": resp.url}


def _url_returns_200(url: str, timeout: int) -> bool:
    if not is_safe_url(url):
        return False
    try:
        resp = requests.get(url, timeout=timeout, headers={"User-Agent": USER_AGENT})
        return resp.status_code == 200
    except requests.RequestException:
        return False


def _score_from_checks(checks: dict) -> float:
    score = 100.0
    if not checks["https"]:
        score -= _PENALTIES["https"]
    if checks["title_length"] == 0:
        score -= _PENALTIES["title_missing"]
    elif not (10 <= checks["title_length"] <= 60):
        score -= _PENALTIES["title_length_bad"]
    if checks["meta_description_length"] == 0:
        score -= _PENALTIES["meta_description_missing"]
    elif not (50 <= checks["meta_description_length"] <= 160):
        score -= _PENALTIES["meta_description_length_bad"]
    if checks["h1_count"] == 0:
        score -= _PENALTIES["h1_missing"]
    elif checks["h1_count"] > 1:
        score -= _PENALTIES["h1_multiple"]
    if not checks["has_canonical"]:
        score -= _PENALTIES["canonical_missing"]
    if checks["images_total"] and checks["images_missing_alt"]:
        ratio = checks["images_missing_alt"] / checks["images_total"]
        score -= _PENALTIES["images_missing_alt"] * ratio
    if not checks["has_robots_txt"]:
        score -= _PENALTIES["robots_missing"]
    if not checks["has_sitemap_xml"]:
        score -= _PENALTIES["sitemap_missing"]
    if not checks["has_viewport_meta"]:
        score -= _PENALTIES["viewport_missing"]
    return max(0.0, round(score, 1))
