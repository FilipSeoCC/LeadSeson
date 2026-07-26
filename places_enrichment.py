import json
import os
import re
from pathlib import Path
from urllib.parse import urlparse

import requests

from seasonality_matrix import load_seasonality_matrix, lookup_by_google_type


PLACES_TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
DEFAULT_PLACES_FIELDS = [
    "places.id",
    "places.displayName",
    "places.formattedAddress",
    "places.primaryType",
    "places.types",
    "places.businessStatus",
    "places.nationalPhoneNumber",
    "places.websiteUri",
]

def get_places_api_key(explicit_key=""):
    return explicit_key or os.getenv("GOOGLE_PLACES_API_KEY") or os.getenv("GOOGLE_MAPS_API_KEY") or ""


def clean_query_part(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def domain_host(value):
    if not value:
        return ""
    text = str(value).strip()
    if not re.match(r"^https?://", text, flags=re.I):
        text = "https://" + text
    try:
        host = urlparse(text).netloc.lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""


def places_cache_path(cache_dir, key):
    safe = re.sub(r"[^a-z0-9.-]+", "_", key.lower()).strip("_") or "unknown"
    return Path(cache_dir) / f"{safe}.json"


def build_places_query(record):
    company = clean_query_part(record.get("company"))
    domain = clean_query_part(record.get("domain_key") or record.get("domain"))
    nip = clean_query_part(record.get("nip"))
    service = clean_query_part(record.get("service"))
    parts = [part for part in [company, domain, nip, service] if part]
    return " ".join(parts[:4])


def map_places_types_to_industry(primary_type, types):
    candidates = [primary_type] + list(types or [])
    for place_type in candidates:
        match = lookup_by_google_type(place_type)
        if match:
            matrix = load_seasonality_matrix()
            rows = matrix[matrix["google_type"].str.lower() == str(place_type).strip().lower()]
            if not rows.empty:
                return rows.iloc[0].get("leadseason_industry", "")
    return ""


def score_place_match(record, place):
    score = 0
    reasons = []
    record_domain = domain_host(record.get("domain") or record.get("domain_key"))
    place_domain = domain_host(place.get("websiteUri"))
    if record_domain and place_domain and record_domain == place_domain:
        score += 70
        reasons.append("domain")

    company = clean_query_part(record.get("company")).lower()
    display_name = clean_query_part((place.get("displayName") or {}).get("text")).lower()
    if company and display_name:
        company_tokens = {token for token in re.split(r"\W+", company) if len(token) >= 4}
        name_tokens = {token for token in re.split(r"\W+", display_name) if len(token) >= 4}
        overlap = company_tokens & name_tokens
        if overlap:
            score += min(25, len(overlap) * 8)
            reasons.append("name")

    if place.get("primaryType"):
        score += 5
        reasons.append("primaryType")

    return min(score, 100), ",".join(reasons)


def normalize_place(place, record):
    score, reasons = score_place_match(record, place)
    types = place.get("types") or []
    primary_type = place.get("primaryType") or ""
    return {
        "places_status": "OK",
        "places_id": place.get("id") or "",
        "places_name": (place.get("displayName") or {}).get("text") or "",
        "places_address": place.get("formattedAddress") or "",
        "places_primary_type": primary_type,
        "places_types": " | ".join(types),
        "places_business_status": place.get("businessStatus") or "",
        "places_phone": place.get("nationalPhoneNumber") or "",
        "places_website": place.get("websiteUri") or "",
        "places_match_confidence": score,
        "places_match_reasons": reasons,
        "places_industry_hint": map_places_types_to_industry(primary_type, types),
    }


def empty_places_result(status="SKIPPED", error=""):
    return {
        "places_status": status,
        "places_id": "",
        "places_name": "",
        "places_address": "",
        "places_primary_type": "",
        "places_types": "",
        "places_business_status": "",
        "places_phone": "",
        "places_website": "",
        "places_match_confidence": 0,
        "places_match_reasons": "",
        "places_industry_hint": "",
        "places_error": error,
    }


def enrich_record_with_places(record, api_key="", cache_dir="cache/places", timeout=10, force=False):
    key = get_places_api_key(api_key)
    if not key:
        return empty_places_result("NO_API_KEY", "Set GOOGLE_PLACES_API_KEY or pass an API key.")

    query = build_places_query(record)
    if not query:
        return empty_places_result("NO_QUERY", "No company, domain, NIP or service data for Places query.")

    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = places_cache_path(cache_dir, record.get("domain_key") or query)
    if cache_file.exists() and not force:
        cached = json.loads(cache_file.read_text(encoding="utf-8"))
        if cached.get("places_status") == "ERROR":
            pass
        else:
            return cached

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": key,
        "X-Goog-FieldMask": ",".join(DEFAULT_PLACES_FIELDS),
    }
    payload = {
        "textQuery": query,
        "languageCode": "pl",
        "regionCode": "PL",
        "pageSize": 3,
    }

    try:
        response = requests.post(PLACES_TEXT_SEARCH_URL, headers=headers, json=payload, timeout=(5, timeout))
        if not response.ok:
            result = empty_places_result("ERROR", f"HTTP {response.status_code}: {response.text[:300]}")
        else:
            places = response.json().get("places") or []
            if not places:
                result = empty_places_result("NOT_FOUND", "No Places result.")
            else:
                ranked = sorted(
                    (normalize_place(place, record) for place in places),
                    key=lambda item: item["places_match_confidence"],
                    reverse=True,
                )
                result = ranked[0]
        cache_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result
    except Exception as exc:
        return empty_places_result("ERROR", str(exc))
