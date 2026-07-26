from functools import lru_cache
from pathlib import Path
import unicodedata

import pandas as pd


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_MATRIX_PATH = BASE_DIR / "config" / "leadseason_seasonality_matrix.csv"

EMPTY_SEASONALITY = {
    "seasonality_source": "",
    "q4_priority": "DO_WERYFIKACJI",
    "lead_reason": "Do weryfikacji przez opiekuna.",
    "call_script": "Warto zweryfikować branżę klienta i potencjał sezonowy przed kontaktem.",
    "seasonality_source_url": "",
    "seasonality_source_quality": "",
    "seasonality_confidence": 0,
}


@lru_cache(maxsize=4)
def load_seasonality_matrix(path=str(DEFAULT_MATRIX_PATH)):
    matrix_path = Path(path)
    if not matrix_path.exists():
        return pd.DataFrame()
    df = pd.read_csv(matrix_path, dtype=str, keep_default_na=False)
    df.columns = [str(col).strip() for col in df.columns]
    return df


def normalize_key(value):
    text = str(value or "").strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(text.split())


def first_non_empty(*values):
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def row_to_seasonality(row, source):
    confidence = row.get("confidence", "0")
    try:
        confidence_value = int(float(confidence))
    except ValueError:
        confidence_value = 0
    return {
        "seasonality_source": source,
        "q4_priority": first_non_empty(row.get("q4_priority"), "DO_WERYFIKACJI"),
        "season_peak": first_non_empty(row.get("season_peak"), "Do weryfikacji"),
        "contact_start": first_non_empty(row.get("contact_start"), "Do weryfikacji"),
        "recommended_product": first_non_empty(row.get("recommended_product"), "SEO / Google Ads / AEO - po analizie ręcznej"),
        "lead_reason": first_non_empty(row.get("lead_reason_template"), "Do weryfikacji przez opiekuna."),
        "call_script": first_non_empty(row.get("call_script_template"), "Warto zweryfikować branżę klienta i potencjał sezonowy przed kontaktem."),
        "seasonality_source_url": row.get("source_url", ""),
        "seasonality_source_quality": row.get("source_quality", ""),
        "seasonality_confidence": confidence_value,
    }


def lookup_by_google_type(google_type, matrix_path=str(DEFAULT_MATRIX_PATH)):
    key = normalize_key(google_type)
    if not key:
        return {}
    df = load_seasonality_matrix(matrix_path)
    if df.empty or "google_type" not in df:
        return {}
    matches = df[df["google_type"].map(normalize_key) == key]
    if matches.empty:
        return {}
    return row_to_seasonality(matches.iloc[0], f"google_type:{key}")


def lookup_by_industry(industry, matrix_path=str(DEFAULT_MATRIX_PATH)):
    key = normalize_key(industry)
    if not key:
        return {}
    df = load_seasonality_matrix(matrix_path)
    if df.empty or "leadseason_industry" not in df:
        return {}
    matches = df[df["leadseason_industry"].map(normalize_key) == key]
    if matches.empty:
        return {}
    matches = matches.copy()
    if "confidence" in matches:
        matches["_confidence_num"] = pd.to_numeric(matches["confidence"], errors="coerce").fillna(0)
        matches = matches.sort_values("_confidence_num", ascending=False)
    return row_to_seasonality(matches.iloc[0], f"industry:{industry}")


def enrich_with_seasonality(row, matrix_path=str(DEFAULT_MATRIX_PATH)):
    output = {**EMPTY_SEASONALITY}

    places_types = []
    if row.get("places_primary_type"):
        places_types.append(row.get("places_primary_type"))
    if row.get("places_types"):
        places_types.extend(str(row.get("places_types")).split("|"))

    for place_type in places_types:
        match = lookup_by_google_type(place_type.strip(), matrix_path)
        if match:
            output.update(match)
            return output

    match = lookup_by_industry(row.get("detected_industry"), matrix_path)
    if match:
        output.update(match)
        return output

    return output
