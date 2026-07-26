"""Hierarchiczna taksonomia branza -> podbranza -> usluga.

Rozwija plaska klasyfikacje z bulk_crawler.classify_industry() o glebsza
strukture, bez ruszania istniejacego silnika regul ani integracji (Places,
PKD/CEIDG zostaja poza zakresem - patrz notatka w README/planie).

Projekt zamierzony jako addytywny: istniejace pola (detected_industry,
industry_confidence, evidence_keywords, places_*) zostaja bez zmian.
Ten modul dokleja nowe, bogatsze pola obok nich.
"""

from functools import lru_cache
from pathlib import Path
import re
import unicodedata

import pandas as pd


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_TAXONOMY_PATH = BASE_DIR / "config" / "leadseason_taxonomy.csv"

B2B_HINTS = ["hurtownia", "hurt", "dla firm", "b2b", "dystrybutor", "producent", "wholesale", "przemysłowy", "przemysłowych"]
B2C_HINTS = ["klienci indywidualni", "dla domu", "dla klienta", "rezerwacja", "umów wizytę", "zapisz się"]

EMPTY_CLASSIFICATION = {
    "branza_glowna": "",
    "podbranza": "",
    "kategoria_uslugowa": "",
    "usluga_glowna": "",
    "uslugi_dodatkowe": "",
    "model_b2b_b2c": "",
    "classification_confidence": 0,
    "classification_evidence": "",
    "classification_sources": "",
    "classification_conflict": "",
}


@lru_cache(maxsize=4)
def load_taxonomy(path=str(DEFAULT_TAXONOMY_PATH)):
    taxonomy_path = Path(path)
    if not taxonomy_path.exists():
        return pd.DataFrame()
    df = pd.read_csv(taxonomy_path, dtype=str, keep_default_na=False)
    df.columns = [str(col).strip() for col in df.columns]
    return df


def normalize_key(value):
    text = str(value or "").strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(text.split())


def _split_pipe(value):
    return [normalize_key(part) for part in str(value or "").split("|") if part.strip()]


def _row_terms(row):
    return set(_split_pipe(row.get("keywords_pl", ""))) | set(_split_pipe(row.get("synonimy", "")))


def match_by_keywords(text, taxonomy_path=str(DEFAULT_TAXONOMY_PATH), top_n=3):
    """Zwraca do top_n najlepiej dopasowanych wierszy taksonomii wg trafien slow kluczowych."""
    df = load_taxonomy(taxonomy_path)
    if df.empty:
        return []

    haystack = normalize_key(text)
    if not haystack:
        return []

    scored = []
    for _, row in df.iterrows():
        terms = _row_terms(row)
        # Dopasowanie po granicach slow, nie golym podciagu - krotki token typu
        # dwu-trzyliterowy skrot potrafi trafic jako podciag w losowym slowie
        # (np. "AC" wewnatrz "lokalizacja") i psuc caly wynik klasyfikacji.
        hits = [term for term in terms if term and re.search(rf"\b{re.escape(term)}\b", haystack)]
        if hits:
            scored.append((len(hits), hits, row))

    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[:top_n]


def match_by_google_type(google_type, taxonomy_path=str(DEFAULT_TAXONOMY_PATH)):
    df = load_taxonomy(taxonomy_path)
    if df.empty or "google_types" not in df:
        return None
    key = normalize_key(google_type)
    if not key:
        return None
    for _, row in df.iterrows():
        types = _split_pipe(row.get("google_types", ""))
        if key in types:
            return row
    return None


def guess_b2b_b2c(text, taxonomy_default=""):
    haystack = normalize_key(text)
    b2b_hits = sum(1 for hint in B2B_HINTS if normalize_key(hint) in haystack)
    b2c_hits = sum(1 for hint in B2C_HINTS if normalize_key(hint) in haystack)
    if b2b_hits and not b2c_hits:
        return "B2B"
    if b2c_hits and not b2b_hits:
        return "B2C"
    if b2b_hits and b2c_hits:
        return "Mieszany"
    return taxonomy_default or "Do weryfikacji"


def classify_detailed(record, taxonomy_path=str(DEFAULT_TAXONOMY_PATH)):
    """Buduje bogatsza klasyfikacje na bazie sygnalow, ktore juz mamy w rekordzie:
    - tekst strony (title/meta/h1_h3/body_text_sample) -> dopasowanie po slowach kluczowych taksonomii
    - places_primary_type / places_types (jesli enrichment z Places byl wlaczony) -> dopasowanie po google_types
    - detected_industry z istniejacego silnika regul -> uzywane do wykrycia rozbieznosci

    Nie woła zadnego zewnetrznego API - dziala tylko na danych juz zebranych.
    """
    text = " ".join(
        str(record.get(field, "") or "")
        for field in ["title", "meta_description", "h1_h3", "body_text_sample"]
    )

    keyword_matches = match_by_keywords(text, taxonomy_path)

    places_row = None
    for candidate_type in [record.get("places_primary_type", "")] + str(record.get("places_types", "")).split("|"):
        places_row = match_by_google_type(candidate_type.strip(), taxonomy_path)
        if places_row is not None:
            break

    sources = []
    evidence_parts = []

    if not keyword_matches and places_row is None:
        output = {**EMPTY_CLASSIFICATION}
        output["classification_evidence"] = "Brak wystarczających sygnałów - do weryfikacji ręcznej."
        return output

    # Usluga glowna: preferuj dopasowanie po Places (bardziej wiarygodne, bo to
    # kategoria wybrana przez samą firmę w Google), keywords jako potwierdzenie/uzupelnienie.
    primary_row = places_row if places_row is not None else keyword_matches[0][2]
    if places_row is not None:
        sources.append("google_places")
        evidence_parts.append(f"Google Places primaryType: {record.get('places_primary_type', '')}")
    if keyword_matches:
        sources.append("slowa_kluczowe_strony")
        top_hits = keyword_matches[0][1]
        evidence_parts.append("Słowa kluczowe: " + ", ".join(top_hits[:8]))

    uslugi_dodatkowe = []
    for _, hits, row in keyword_matches:
        usluga = row.get("usluga_glowna", "")
        if usluga and usluga != primary_row.get("usluga_glowna", ""):
            uslugi_dodatkowe.append(usluga)
    uslugi_dodatkowe = list(dict.fromkeys(uslugi_dodatkowe))[:4]

    # Wykrywanie rozbieznosci: TYLKO miedzy dwoma sygnalami na tym samym poziomie
    # szczegolowosci - dopasowanie po slowach kluczowych vs dopasowanie po Google Places.
    # Nie porownujemy ze starym, plaskim detected_industry - ta taksonomia celowo
    # zagniezdza part starych branz (np. HVAC) jako podbranze/usluge gdzie indziej,
    # wiec "roznica" wobec starego systemu jest oczekiwana, nie jest to prawdziwy konflikt.
    def word_set(value):
        return {w for w in normalize_key(value).replace("/", " ").split() if len(w) >= 4}

    conflict = ""
    confidence = 60 if len(keyword_matches) <= 1 else min(90, 60 + len(keyword_matches[0][1]) * 5)
    if places_row is not None:
        confidence = min(95, confidence + 15)

    if places_row is not None and keyword_matches:
        places_words = word_set(places_row.get("branza_glowna", ""))
        keyword_words = word_set(keyword_matches[0][2].get("branza_glowna", ""))
        if places_words and keyword_words and not (places_words & keyword_words):
            conflict = (
                f"Google Places sugeruje '{places_row.get('usluga_glowna')}', "
                f"słowa kluczowe strony sugerują '{keyword_matches[0][2].get('usluga_glowna')}' - do sprawdzenia."
            )
            confidence = max(25, confidence - 30)

    return {
        "branza_glowna": primary_row.get("branza_glowna", ""),
        "podbranza": primary_row.get("podbranza", ""),
        "kategoria_uslugowa": primary_row.get("kategoria_uslugowa", ""),
        "usluga_glowna": primary_row.get("usluga_glowna", ""),
        "uslugi_dodatkowe": " | ".join(uslugi_dodatkowe),
        "model_b2b_b2c": guess_b2b_b2c(text, primary_row.get("model_domyslny", "")),
        "classification_confidence": confidence,
        "classification_evidence": " | ".join(evidence_parts),
        "classification_sources": ", ".join(sources),
        "classification_conflict": conflict,
    }
