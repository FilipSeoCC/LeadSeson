import argparse
import csv
import hashlib
import json
import re
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse

import pandas as pd
import requests
from bs4 import BeautifulSoup

from places_enrichment import enrich_record_with_places
from seasonality_matrix import enrich_with_seasonality
from taxonomy import classify_detailed


APP_NAME = "LeadSeason Bulk Crawler"
DEFAULT_WORKERS = 12
DEFAULT_TIMEOUT = 15
MAX_TEXT_CHARS = 8000
MAX_HEADINGS = 30
MAX_MENU_LINKS = 80

DOMAIN_KEYS = ["domain", "domena", "url", "website", "strona", "adres_www", "www"]
NIP_KEYS = ["nip", "tax_id", "taxid", "vat", "vat_id"]
ID_KEYS = ["id", "client_id", "id_klienta", "klient_id", "customer_id"]
DETAIL_KEYS = ["detail_id", "ditel", "id_ditel", "id_detail", "umowa", "contract_id", "agreement_id", "nr_umowy"]
SERVICE_KEYS = ["service", "product", "produkt", "typ_umowy", "kod_pakietu", "pakiet", "usluga", "usługa"]
COMPANY_KEYS = ["company", "firma", "nazwa", "nazwa_firmy", "klient"]

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) LeadSeasonBulkCrawler/0.1"
RETRY_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Connection": "close",
}
RETRY_HEADERS = {
    **HEADERS,
    "User-Agent": RETRY_USER_AGENT,
    "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7",
    "Upgrade-Insecure-Requests": "1",
}

OFFER_LINK_HINTS = [
    "oferta",
    "oferty",
    "uslugi",
    "usługi",
    "produkty",
    "produkt",
    "services",
    "service",
    "cennik",
    "realizacje",
    "kontakt",
    "o-nas",
]

SITE_HEALTH_PATTERNS = [
    {
        "status": "BLOCKED",
        "reason": "security verifier / anti-bot",
        "patterns": [
            "sprawdzamy, czy twoje połączenie jest bezpieczne",
            "automatyczna weryfikacja bezpieczeństwa",
            "nie masz uprawnień",
            "anubis.techaro",
            "weryfikator",
            "checking if the site connection is secure",
            "verify you are human",
            "cloudflare ray id",
        ],
    },
    {
        "status": "PLACEHOLDER",
        "reason": "hosting placeholder / default page",
        "patterns": [
            "strona dodana prawidłowo",
            "strona hostowana na",
            "możesz usunąć ten plik",
            "public_html",
            "index.html",
            "apache2 debian default page",
            "welcome to nginx",
            "plesk default page",
            "directadmin",
            "mydevil.net",
        ],
    },
    {
        "status": "INACTIVE",
        "reason": "inactive / under construction",
        "patterns": [
            "strona nieaktywna",
            "strona w trakcie zmian",
            "under construction",
            "coming soon",
            "w budowie",
            "domain suspended",
            "account suspended",
            "temporarily unavailable",
        ],
    },
    {
        "status": "PARKED",
        "reason": "parked domain / for sale",
        "patterns": [
            "domena jest zaparkowana",
            "domain is parked",
            "buy this domain",
            "domena na sprzedaż",
            "this domain may be for sale",
            "sedo domain parking",
        ],
    },
]

INDUSTRY_RULES = [
    {
        "industry": "E-commerce / wyposażenie domu / porcelana",
        "keywords": ["porcelana", "sklep internetowy", "hurtownia", "akcesoria kuchenne", "zastawa", "sztućce", "garnki", "patelnie", "szkło stołowe", "serwis obiadowy"],
        "peak": "listopad-grudzień oraz sezon ślubny maj-wrzesień",
        "contact_start": "wrzesień-październik oraz marzec-kwiecień",
        "recommended_product": "SEO e-commerce / Google Ads produktowe / content sezonowy",
        "lead_topic": "Widoczność kategorii prezentowych, ślubnych i wyposażenia domu przed sezonami zakupowymi.",
    },
    {
        "industry": "Klimatyzacja / HVAC",
        "keywords": ["klimatyzacja", "montaż klimatyzacji", "serwis klimatyzacji", "pompa ciepła", "pompy ciepła", "wentylacja", "rekuperacja", "hvac"],
        "peak": "maj-sierpień",
        "contact_start": "styczeń-marzec",
        "recommended_product": "Google Ads / SEO lokalne / AEO",
        "lead_topic": "Przygotowanie widoczności i kampanii przed sezonem upałów.",
    },
    {
        "industry": "Ogrody / usługi ogrodnicze",
        "keywords": ["ogród", "ogrody", "ogrodnicze", "trawnik", "nawadnianie", "projektowanie ogrodów", "zakładanie ogrodów", "pielęgnacja zieleni"],
        "peak": "marzec-czerwiec",
        "contact_start": "styczeń-marzec",
        "recommended_product": "SEO lokalne / Google Ads / treści sezonowe",
        "lead_topic": "Pozyskiwanie zapytań przed sezonem ogrodniczym.",
    },
    {
        "industry": "Motoryzacja / opony / wulkanizacja",
        "keywords": ["opony", "wulkanizacja", "wymiana opon", "serwis opon", "geometria kół", "mechanik", "warsztat samochodowy", "serwis samochodowy"],
        "peak": "marzec-kwiecień oraz październik-listopad",
        "contact_start": "luty-marzec oraz wrzesień",
        "recommended_product": "Google Ads / SEO lokalne / wizytówka Google",
        "lead_topic": "Kampanie przed sezonową wymianą opon i usługami serwisowymi.",
    },
    {
        "industry": "Gastronomia / restauracje / eventy",
        "keywords": ["restauracja", "menu", "catering", "wesele", "wesela", "event", "imprezy", "komunia", "bankiet", "ogród", "taras"],
        "peak": "maj-wrzesień oraz grudzień",
        "contact_start": "marzec-kwiecień oraz wrzesień-październik",
        "recommended_product": "SEO lokalne / Google Ads / Social Media / wizytówka Google",
        "lead_topic": "Rezerwacje na eventy, ogród, wesela i imprezy firmowe.",
    },
    {
        "industry": "Przeprowadzki / transport lokalny",
        "keywords": ["przeprowadzki", "przeprowadzk", "transport mebli", "taxi bagażowe", "relokacje", "pakowanie mienia", "magazynowanie"],
        "peak": "maj-wrzesień oraz koniec roku",
        "contact_start": "marzec-maj oraz wrzesień-listopad",
        "recommended_product": "SEO lokalne / Google Ads / AEO / treści sezonowe",
        "lead_topic": "Zwiększenie liczby zapytań o przeprowadzki mieszkań, biur i transport lokalny.",
    },
    {
        "industry": "Edukacja / kursy / szkoły językowe",
        "keywords": ["kurs", "kursy", "szkoła językowa", "angielski", "niemiecki", "zajęcia", "szkolenia", "lekcje", "matura", "egzamin"],
        "peak": "sierpień-październik oraz styczeń-luty",
        "contact_start": "czerwiec-sierpień oraz grudzień-styczeń",
        "recommended_product": "SEO / Google Ads / Social Media",
        "lead_topic": "Pozyskiwanie zapisów na kursy przed nowym semestrem.",
    },
    {
        "industry": "Medycyna / stomatologia / beauty",
        "keywords": ["gabinet", "stomatolog", "dentysta", "implanty", "fizjoterapia", "rehabilitacja", "kosmetologia", "medycyna estetyczna", "salon kosmetyczny"],
        "peak": "cały rok, piki przed wakacjami i końcem roku",
        "contact_start": "marzec-maj oraz wrzesień-listopad",
        "recommended_product": "SEO lokalne / Google Ads / wizytówka Google / Social Media",
        "lead_topic": "Zwiększenie liczby lokalnych rezerwacji i zapytań o usługi.",
    },
    {
        "industry": "Budownictwo / remonty / instalacje",
        "keywords": ["remont", "remonty", "budowa", "elewacje", "docieplenia", "instalacje", "hydraulik", "elektryk", "dachy", "wykończenia", "fotowoltaika"],
        "peak": "marzec-październik",
        "contact_start": "styczeń-kwiecień oraz sierpień-wrzesień",
        "recommended_product": "SEO lokalne / Google Ads / landing pages / treści poradnikowe",
        "lead_topic": "Pozyskiwanie zapytań przed sezonem prac budowlanych i remontowych.",
    },
    {
        "industry": "Hotel / noclegi / turystyka",
        "keywords": ["hotel", "noclegi", "apartamenty", "pensjonat", "rezerwacje", "pokoje", "spa", "wypoczynek", "turystyka"],
        "peak": "maj-wrzesień, ferie i długie weekendy",
        "contact_start": "luty-kwiecień oraz wrzesień-listopad",
        "recommended_product": "SEO lokalne / Google Ads / content sezonowy",
        "lead_topic": "Pozyskiwanie rezerwacji przed sezonem turystycznym.",
    },
]


def now_iso():
    return datetime.now(timezone.utc).isoformat()


# Znaki kontrolne niedozwolone w XML/XLSX (openpyxl rzuca IllegalCharacterError) -
# realne strony ze złym kodowaniem (np. mojibake z cp1250) potrafią je wstrzyknąć.
ILLEGAL_XLSX_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def clean_text(value):
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return ILLEGAL_XLSX_CHARS.sub("", text)


def clean_identifier(value):
    text = clean_text(value)
    if re.fullmatch(r"\d+\.0", text):
        return text[:-2]
    return text


def local_name(tag):
    return str(tag).split("}", 1)[-1].lower()


def normalize_nip(value):
    digits = re.sub(r"\D", "", clean_identifier(value))
    if len(digits) != 10:
        return ""
    weights = [6, 5, 7, 2, 3, 4, 5, 6, 7]
    checksum = sum(weights[i] * int(digits[i]) for i in range(9)) % 11
    return digits if checksum == int(digits[9]) else digits


def normalize_domain(value):
    raw = clean_text(value)
    raw = re.sub(r"^\s*(domena|domain|adres[_\s-]*www|www)\s*:?", "", raw, flags=re.I).strip()
    match = re.search(r"(?:https?://)?(?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)+(?:/[^\s]*)?", raw, flags=re.I)
    if not match:
        return ""
    domain = match.group(0).rstrip("),.;")
    if not re.match(r"^https?://", domain, flags=re.I):
        domain = "https://" + domain
    try:
        parsed = urlparse(domain)
        return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path or "/", "", "", ""))
    except ValueError:
        return domain.lower()


def domain_key(domain):
    try:
        host = urlparse(normalize_domain(domain)).netloc.lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""


def flatten_element(element):
    values = {}

    def add(key, value):
        key = local_name(key)
        text = clean_text(value)
        if text:
            values.setdefault(key, []).append(text)

    for key, value in element.attrib.items():
        add(key, value)

    for node in element.iter():
        tag = local_name(node.tag)
        if node.text and clean_text(node.text):
            add(tag, node.text)
        for key, value in node.attrib.items():
            add(key, value)

    return values


def find_by_keys(flat, keys):
    normalized = {key.lower(): values for key, values in flat.items()}
    for wanted in keys:
        wanted_norm = wanted.lower()
        for key, values in normalized.items():
            if key == wanted_norm or key.endswith(wanted_norm) or wanted_norm in key:
                for value in values:
                    if clean_text(value):
                        return clean_text(value)
    return ""


def find_domain(flat):
    by_key = find_by_keys(flat, DOMAIN_KEYS)
    if normalize_domain(by_key):
        return normalize_domain(by_key)
    for values in flat.values():
        for value in values:
            domain = normalize_domain(value)
            if domain:
                return domain
    return ""


def count_domains(flat):
    found = set()
    for values in flat.values():
        for value in values:
            key = domain_key(value)
            if key:
                found.add(key)
    return len(found)


def parse_xml_records(input_path):
    root = ET.parse(input_path).getroot()
    candidates = []

    for element in root.iter():
        if element is root:
            continue
        flat = flatten_element(element)
        domain = find_domain(flat)
        if not domain:
            continue
        score = 1
        score += 1 if find_by_keys(flat, NIP_KEYS) else 0
        score += 1 if find_by_keys(flat, ID_KEYS) else 0
        score += 1 if find_by_keys(flat, DETAIL_KEYS) else 0
        domain_count = count_domains(flat)
        if domain_count <= 3:
            candidates.append((score, domain_count, element, flat))

    strong = [item for item in candidates if item[0] >= 2 and item[1] <= 2]
    selected = strong or candidates
    records = []
    seen = set()

    for _, _, element, flat in selected:
        domain = find_domain(flat)
        nip = normalize_nip(find_by_keys(flat, NIP_KEYS))
        record = {
            "source_tag": local_name(element.tag),
            "id": find_by_keys(flat, ID_KEYS),
            "detail_id": find_by_keys(flat, DETAIL_KEYS),
            "nip": nip,
            "domain": domain,
            "domain_key": domain_key(domain),
            "company": find_by_keys(flat, COMPANY_KEYS),
            "service": find_by_keys(flat, SERVICE_KEYS),
        }
        identity = (record["id"], record["detail_id"], record["nip"], record["domain_key"], record["service"])
        if identity in seen:
            continue
        seen.add(identity)
        records.append(record)

    return records


def parse_tabular_records(input_path):
    input_path = Path(input_path)
    if input_path.suffix.lower() in [".xlsx", ".xls"]:
        df = pd.read_excel(input_path, sheet_name=0, dtype=str, keep_default_na=False)
    else:
        df = pd.read_csv(input_path, sep=None, engine="python", dtype=str, keep_default_na=False, encoding="utf-8-sig")

    df.columns = [clean_text(col) for col in df.columns]
    records = []

    for index, row in df.iterrows():
        flat = {clean_text(key).lower(): [row[key]] for key in df.columns}
        domain = normalize_domain(find_by_keys(flat, ["domain", "domena"]))
        if not domain:
            continue

        record = {
            "source_tag": "row",
            "id": clean_identifier(find_by_keys(flat, ["id", "client_id", "id klienta"])),
            "detail_id": clean_identifier(find_by_keys(flat, ["detail_id", "ditel", "nr druku", "umowa"])),
            "nip": normalize_nip(find_by_keys(flat, ["nip"])),
            "domain": domain,
            "domain_key": domain_key(domain),
            "company": clean_text(find_by_keys(flat, ["company", "firma", "nazwa"])),
            "service": clean_text(find_by_keys(flat, ["service", "kod pakietu", "typ_umowy", "produkt"])),
        }

        for optional in [
            "account_owner",
            "publication_code",
            "seo_basket",
            "access_type",
            "start_date",
            "end_date",
            "monthly_value",
            "source_row",
        ]:
            aliases = [optional, optional.replace("_", " ")]
            record[optional] = clean_text(find_by_keys(flat, aliases))

        records.append(record)

    return records


def parse_input_records(input_path):
    input_path = Path(input_path)
    if input_path.suffix.lower() == ".xml":
        return parse_xml_records(input_path)
    if input_path.suffix.lower() in [".xlsx", ".xls", ".csv"]:
        return parse_tabular_records(input_path)
    raise ValueError("Unsupported input format. Use XML, XLSX, XLS or CSV.")


def cache_path(cache_dir, key):
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()
    return Path(cache_dir) / f"{digest}.json"


def load_cached(cache_dir, key):
    path = cache_path(cache_dir, key)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def save_cached(cache_dir, key, data):
    Path(cache_dir).mkdir(parents=True, exist_ok=True)
    cache_path(cache_dir, key).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def ensure_site_health_fields(result):
    if not result or result.get("site_health_status"):
        return result
    fetch = {
        "ok": result.get("crawl_status") == "OK",
        "error": result.get("error", ""),
    }
    metadata = {
        "title": result.get("title", ""),
        "meta_description": result.get("meta_description", ""),
        "h1_h3": result.get("h1_h3", ""),
        "body_text_sample": result.get("body_text_sample", ""),
    }
    health = assess_site_health(metadata, fetch)
    result.update(health)
    if not health["usable_for_llm"]:
        result.update(classify_industry(""))
    return result


def fetch_url(url, timeout, headers=None, wait_before=0):
    started = time.time()
    try:
        if wait_before:
            time.sleep(float(wait_before))
        response = requests.get(url, headers=headers or HEADERS, timeout=(5, timeout), allow_redirects=True)
        content_type = response.headers.get("content-type", "")
        html = response.text if "html" in content_type.lower() or "<html" in response.text[:500].lower() else ""
        return {
            "ok": response.ok and bool(html),
            "status_code": response.status_code,
            "final_url": response.url,
            "html": html,
            "error": "" if response.ok else f"HTTP {response.status_code}",
            "seconds": round(time.time() - started, 2),
        }
    except Exception as exc:
        return {
            "ok": False,
            "status_code": None,
            "final_url": url,
            "html": "",
            "error": str(exc),
            "seconds": round(time.time() - started, 2),
        }


def fetch_url_browser(url, timeout, wait_after=10):
    started = time.time()
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=RETRY_USER_AGENT,
                locale="pl-PL",
                viewport={"width": 1366, "height": 900},
            )
            page = context.new_page()
            response = page.goto(url, wait_until="domcontentloaded", timeout=max(timeout, 10) * 1000)
            try:
                page.wait_for_load_state("networkidle", timeout=min(max(timeout, 10), 30) * 1000)
            except Exception:
                pass
            if wait_after:
                page.wait_for_timeout(int(wait_after * 1000))
            html = page.content()
            final_url = page.url
            status_code = response.status if response else None
            context.close()
            browser.close()
        return {
            "ok": bool(html) and ("<html" in html[:1000].lower() or "<body" in html[:1000].lower()),
            "status_code": status_code,
            "final_url": final_url,
            "html": html,
            "error": "" if status_code is None or status_code < 400 else f"HTTP {status_code}",
            "seconds": round(time.time() - started, 2),
        }
    except Exception as exc:
        return {
            "ok": False,
            "status_code": None,
            "final_url": url,
            "html": "",
            "error": f"browser fallback: {exc}",
            "seconds": round(time.time() - started, 2),
        }


def parse_and_classify_fetch(fetch):
    if not fetch["ok"]:
        health = assess_site_health({}, fetch)
        return {}, health, classify_industry("")
    metadata = parse_metadata(fetch["html"], fetch["final_url"])
    health = assess_site_health(metadata, fetch)
    classification_text = metadata["classification_text"] if health["usable_for_llm"] else ""
    classification = classify_industry(classification_text)
    metadata.pop("classification_text", None)
    return metadata, health, classification


def parse_metadata(html, final_url):
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "canvas", "iframe", "form"]):
        tag.decompose()

    def meta(name=None, prop=None):
        if name:
            node = soup.find("meta", attrs={"name": name})
        else:
            node = soup.find("meta", attrs={"property": prop})
        return clean_text(node.get("content")) if node and node.get("content") else ""

    title = clean_text(soup.title.text if soup.title else "")
    headings = [clean_text(node.get_text(" ")) for node in soup.find_all(["h1", "h2", "h3"])]
    headings = [item for item in headings if item][:MAX_HEADINGS]
    anchor_texts = []
    offer_links = []

    for link in soup.find_all("a", href=True):
        text = clean_text(link.get_text(" "))
        href = urljoin(final_url, link.get("href"))
        haystack = f"{text} {href}".lower()
        if text:
            anchor_texts.append(text)
        if any(hint in haystack for hint in OFFER_LINK_HINTS):
            offer_links.append(href.split("#")[0])

    schema_types = []
    for node in soup.find_all(attrs={"itemtype": True}):
        schema_types.append(clean_text(node.get("itemtype")))
    for node in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = node.string or ""
        schema_types.extend(re.findall(r'"@type"\s*:\s*"([^"]+)"', raw))

    body_text = clean_text(soup.get_text(" "))
    combined = clean_text(
        " ".join(
            [
                title,
                meta("description"),
                meta("keywords"),
                meta(prop="og:title"),
                meta(prop="og:description"),
                " ".join(headings),
                " ".join(anchor_texts[:MAX_MENU_LINKS]),
                " ".join(schema_types),
                body_text[:MAX_TEXT_CHARS],
            ]
        )
    )

    return {
        "title": title,
        "meta_description": meta("description"),
        "meta_keywords": meta("keywords"),
        "og_title": meta(prop="og:title"),
        "og_description": meta(prop="og:description"),
        "canonical": get_canonical(soup, final_url),
        "lang": clean_text(soup.html.get("lang")) if soup.html else "",
        "h1_h3": " | ".join(headings),
        "schema_types": " | ".join(sorted(set(schema_types))),
        "offer_links": " | ".join(dedupe(offer_links)[:12]),
        "body_text_sample": body_text[:MAX_TEXT_CHARS],
        "classification_text": combined,
    }


def assess_site_health(metadata, fetch):
    status = "OK" if fetch.get("ok") else "FETCH_ERROR"
    reason = "" if fetch.get("ok") else clean_text(fetch.get("error") or "fetch error")
    text = clean_text(
        " ".join(
            [
                metadata.get("title", ""),
                metadata.get("meta_description", ""),
                metadata.get("h1_h3", ""),
                metadata.get("body_text_sample", ""),
            ]
        )
    )
    lowered = text.lower()
    for rule in SITE_HEALTH_PATTERNS:
        for pattern in rule["patterns"]:
            if pattern in lowered:
                return {
                    "site_health_status": rule["status"],
                    "site_health_reason": rule["reason"],
                    "site_text_chars": len(text),
                    "usable_for_llm": False,
                }
    if fetch.get("ok") and len(text) < 180:
        return {
            "site_health_status": "NO_SIGNAL",
            "site_health_reason": "too little usable text",
            "site_text_chars": len(text),
            "usable_for_llm": False,
        }
    return {
        "site_health_status": status,
        "site_health_reason": reason,
        "site_text_chars": len(text),
        "usable_for_llm": status == "OK",
    }


def get_canonical(soup, final_url):
    node = soup.find("link", attrs={"rel": lambda value: value and "canonical" in value})
    if node and node.get("href"):
        return urljoin(final_url, node.get("href"))
    return ""


def dedupe(items):
    seen = set()
    output = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            output.append(item)
    return output


def classify_industry(text):
    haystack = clean_text(text).lower()
    best = None
    best_hits = []

    for rule in INDUSTRY_RULES:
        weighted_hits = []
        for keyword in rule["keywords"]:
            kw = keyword.lower()
            if kw in haystack:
                weight = 3 if kw in haystack[:1000] else 1
                weighted_hits.extend([keyword] * weight)
        if len(weighted_hits) > len(best_hits):
            best = rule
            best_hits = weighted_hits

    unique_hits = dedupe(best_hits)
    if not best or (len(unique_hits) < 2 and len(best_hits) < 4):
        return {
            "detected_industry": "Nieokreślona",
            "industry_confidence": 0,
            "season_peak": "Do weryfikacji",
            "contact_start": "Do weryfikacji",
            "recommended_product": "SEO / Google Ads / AEO - po analizie ręcznej",
            "lead_topic": "Do weryfikacji",
            "evidence_keywords": "",
        }

    confidence = min(100, 25 + len(best_hits) * 10 + min(len(unique_hits), 5) * 5)
    return {
        "detected_industry": best["industry"],
        "industry_confidence": confidence,
        "season_peak": best["peak"],
        "contact_start": best["contact_start"],
        "recommended_product": best["recommended_product"],
        "lead_topic": best["lead_topic"],
        "evidence_keywords": ", ".join(unique_hits[:15]),
    }


def crawl_domain(domain, cache_dir, timeout=DEFAULT_TIMEOUT, force=False):
    normalized = normalize_domain(domain)
    key = domain_key(normalized)
    if not key:
        return {"domain": domain, "domain_key": "", "crawl_status": "ERROR", "error": "Invalid domain"}

    if not force:
        cached = load_cached(cache_dir, key)
        if cached:
            cached = ensure_site_health_fields(cached)
            cached["cache_hit"] = True
            return cached

    fetch = fetch_url(normalized, timeout)
    result = {
        "domain": normalized,
        "domain_key": key,
        "crawl_status": "OK" if fetch["ok"] else "ERROR",
        "http_status": fetch["status_code"],
        "final_url": fetch["final_url"],
        "crawl_seconds": fetch["seconds"],
        "error": fetch["error"],
        "cache_hit": False,
        "crawled_at": now_iso(),
        "crawl_retry_used": False,
        "crawl_retry_reason": "",
    }

    metadata, health, classification = parse_and_classify_fetch(fetch)

    if health["site_health_status"] in ["BLOCKED", "NO_SIGNAL", "FETCH_ERROR"]:
        retry_timeout = max(timeout * 2, timeout + 15)
        retry_fetch = fetch_url(normalized, retry_timeout, headers=RETRY_HEADERS, wait_before=6)
        retry_metadata, retry_health, retry_classification = parse_and_classify_fetch(retry_fetch)
        retry_is_better = (
            retry_health["usable_for_llm"]
            or (retry_health["site_text_chars"] > health["site_text_chars"] + 250)
            or (health["site_health_status"] == "FETCH_ERROR" and retry_fetch["ok"])
        )
        if retry_is_better:
            fetch = retry_fetch
            metadata = retry_metadata
            health = retry_health
            classification = retry_classification
            result.update(
                {
                    "crawl_status": "OK" if fetch["ok"] else "ERROR",
                    "http_status": fetch["status_code"],
                    "final_url": fetch["final_url"],
                    "crawl_seconds": fetch["seconds"],
                    "error": fetch["error"],
                    "crawl_retry_used": True,
                    "crawl_retry_reason": "second pass improved site health",
                }
            )
        else:
            result["crawl_retry_used"] = True
            result["crawl_retry_reason"] = f"second pass no improvement: {retry_health['site_health_status']}"
            if health["site_health_status"] == "BLOCKED":
                browser_fetch = fetch_url_browser(normalized, max(timeout * 2, timeout + 20), wait_after=12)
                browser_metadata, browser_health, browser_classification = parse_and_classify_fetch(browser_fetch)
                browser_is_better = browser_health["usable_for_llm"] or browser_health["site_text_chars"] > health["site_text_chars"] + 500
                if browser_is_better:
                    fetch = browser_fetch
                    metadata = browser_metadata
                    health = browser_health
                    classification = browser_classification
                    result.update(
                        {
                            "crawl_status": "OK" if fetch["ok"] else "ERROR",
                            "http_status": fetch["status_code"],
                            "final_url": fetch["final_url"],
                            "crawl_seconds": fetch["seconds"],
                            "error": fetch["error"],
                            "crawl_retry_used": True,
                            "crawl_retry_reason": "browser fallback improved site health",
                        }
                    )
                else:
                    result["crawl_retry_reason"] = f"browser fallback no improvement: {browser_health['site_health_status']}"

    result.update(metadata)
    result.update(health)
    result.update(classification)

    save_cached(cache_dir, key, result)
    return result


def merge_records(records, domain_results):
    output = []
    for record in records:
        result = domain_results.get(record["domain_key"], {})
        row = {**record, **result}
        output.append(row)
    return output


def apply_places_enrichment(rows, api_key="", cache_dir="cache/places", timeout=10, force=False):
    enriched = []
    for index, row in enumerate(rows, start=1):
        places = enrich_record_with_places(
            row,
            api_key=api_key,
            cache_dir=cache_dir,
            timeout=timeout,
            force=force,
        )
        merged = {**row, **places}
        if (
            merged.get("places_industry_hint")
            and merged.get("detected_industry") == "Nieokreślona"
            and int(merged.get("places_match_confidence") or 0) >= 50
        ):
            merged["detected_industry"] = merged["places_industry_hint"]
            merged["industry_confidence"] = max(int(merged.get("industry_confidence") or 0), int(merged.get("places_match_confidence") or 0))
            merged["evidence_keywords"] = "Google Places: " + clean_text(merged.get("places_primary_type"))
        enriched.append(merged)
        if index % 25 == 0 or index == len(rows):
            print(f"Places enrichment {index}/{len(rows)}")
    return enriched


def apply_seasonality(rows):
    output = []
    for row in rows:
        seasonality = enrich_with_seasonality(row)
        output.append({**row, **seasonality})
    return output


def apply_detailed_classification(rows):
    # Dokleja glebsza taksonomie (branza/podbranza/usluga/B2B-B2C) obok
    # istniejacego detected_industry - nic z tego, co juz dziala, nie jest ruszane.
    output = []
    for row in rows:
        detailed = classify_detailed(row)
        output.append({**row, **detailed})
    return output


def sanitize_for_export(df):
    # Cache mógł zapisać tekst sprzed wprowadzenia ILLEGAL_XLSX_CHARS w clean_text -
    # czyścimy też tutaj, żeby nie trzeba było przekrawlować domen od nowa.
    text_cols = df.select_dtypes(include="object").columns
    for col in text_cols:
        df[col] = df[col].map(
            lambda value: ILLEGAL_XLSX_CHARS.sub("", value) if isinstance(value, str) else value
        )
    return df


def write_outputs(rows, output_path):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df = sanitize_for_export(pd.DataFrame(rows))

    if output_path.suffix.lower() == ".xlsx":
        df.to_excel(output_path, index=False)
    elif output_path.suffix.lower() == ".json":
        output_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        # sep=";" bo polskie ustawienia regionalne Excela dzielą CSV po
        # średniku, nie po przecinku - inaczej caly wiersz ląduje w kolumnie A
        df.to_csv(output_path, index=False, sep=";", encoding="utf-8-sig", quoting=csv.QUOTE_MINIMAL)

    return output_path


def write_summary(rows, output_path):
    output_path = Path(output_path)
    summary_path = output_path.with_suffix(".summary.json")
    total = len(rows)
    unique_domains = len({row.get("domain_key") for row in rows if row.get("domain_key")})
    ok = sum(1 for row in rows if row.get("crawl_status") == "OK")
    errors = sum(1 for row in rows if row.get("crawl_status") == "ERROR")
    industries = {}
    statuses = {}
    health_statuses = {}

    for row in rows:
        industry = row.get("detected_industry") or "Nieokreślona"
        status = row.get("crawl_status") or "UNKNOWN"
        industries[industry] = industries.get(industry, 0) + 1
        health = row.get("site_health_status") or "UNKNOWN"
        statuses[status] = statuses.get(status, 0) + 1
        health_statuses[health] = health_statuses.get(health, 0) + 1

    summary = {
        "generated_at": now_iso(),
        "total_records": total,
        "unique_domains": unique_domains,
        "ok_records": ok,
        "error_records": errors,
        "status_counts": dict(sorted(statuses.items())),
        "site_health_counts": dict(sorted(health_statuses.items())),
        "industry_counts": dict(sorted(industries.items(), key=lambda item: item[1], reverse=True)),
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary_path


def run_bulk(
    input_xml,
    output_path,
    cache_dir,
    workers=DEFAULT_WORKERS,
    timeout=DEFAULT_TIMEOUT,
    force=False,
    limit=0,
    use_places=False,
    places_api_key="",
    places_cache_dir="cache/places",
):
    records = parse_input_records(input_xml)
    if limit:
        records = records[:limit]

    workers = max(1, int(workers or 1))
    unique = {record["domain_key"]: record["domain"] for record in records if record["domain_key"]}
    domain_results = {}

    print(f"Loaded records: {len(records)}")
    print(f"Unique domains: {len(unique)}")
    print(f"Workers: {workers}")

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(crawl_domain, domain, cache_dir, timeout, force): key
            for key, domain in unique.items()
        }
        total = len(futures)
        for index, future in enumerate(as_completed(futures), start=1):
            key = futures[future]
            try:
                domain_results[key] = future.result()
            except Exception as exc:
                domain_results[key] = {"domain_key": key, "crawl_status": "ERROR", "error": str(exc)}
            if index % 25 == 0 or index == total:
                print(f"Done {index}/{total}")

    rows = merge_records(records, domain_results)
    if use_places:
        rows = apply_places_enrichment(
            rows,
            api_key=places_api_key,
            cache_dir=places_cache_dir,
            timeout=timeout,
            force=force,
        )
    rows = apply_detailed_classification(rows)
    rows = apply_seasonality(rows)
    written = write_outputs(rows, output_path)
    summary = write_summary(rows, output_path)
    print(f"Output: {written}")
    print(f"Summary: {summary}")
    return rows


def main():
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--input", required=True, help="Input XML file")
    parser.add_argument("--output", default="output/leadseason_results.csv", help="Output CSV/XLSX/JSON")
    parser.add_argument("--cache-dir", default="cache/domains", help="Domain cache directory")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    parser.add_argument("--force", action="store_true", help="Ignore domain cache")
    parser.add_argument("--limit", type=int, default=0, help="Process only first N records")
    parser.add_argument("--places", action="store_true", help="Enrich rows with Google Places category data")
    parser.add_argument("--places-api-key", default="", help="Google Places API key. Falls back to GOOGLE_PLACES_API_KEY.")
    parser.add_argument("--places-cache-dir", default="cache/places", help="Google Places cache directory")
    args = parser.parse_args()

    run_bulk(
        input_xml=args.input,
        output_path=args.output,
        cache_dir=args.cache_dir,
        workers=args.workers,
        timeout=args.timeout,
        force=args.force,
        limit=args.limit,
        use_places=args.places,
        places_api_key=args.places_api_key,
        places_cache_dir=args.places_cache_dir,
    )


if __name__ == "__main__":
    main()
