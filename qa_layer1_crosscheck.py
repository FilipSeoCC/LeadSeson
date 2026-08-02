# -*- coding: utf-8 -*-
# Systemowa kontrola jakosci Warstwy 1 (google_type_mapping): dwa niezalezne,
# darmowe mechanizmy wykrywania bledow zamiast slepego zaufania jednemu zrodlu.
#
# 1. Rozszerzony detektor martwych/zaparkowanych domen (post-hoc skan tekstu,
#    bez ponownego crawlu) - lapie przypadki jak szkolka-tanca.wroclaw.pl.
# 2. Niezalezna klasyfikacja regulowa (classify_detailed, slowa kluczowe strony)
#    porownana z przypisaniem z Places - konflikt = flaga manual_review.
from pathlib import Path

import pandas as pd

from taxonomy import classify_detailed

BASE_DIR = Path(__file__).resolve().parent
CONSOLIDATED_PATH = BASE_DIR / "output" / "leadseason_pelna_baza_zeszyt2_consolidated.xlsx"

STALE_PATTERNS = [
    "domena jest zaparkowana", "domain is parked", "buy this domain", "domena na sprzedaż",
    "oferta sprzedaży domeny", "cena domeny", "kup domenę", "domena do kupienia",
    "aftermarket.pl", "this domain may be for sale", "sedo domain parking",
    "strona nieaktywna", "strona w trakcie zmian", "under construction", "coming soon",
    "w budowie", "domain suspended", "account suspended", "temporarily unavailable",
]


def detect_stale(row):
    text = " ".join(
        str(row.get(field, "") or "") for field in ["title", "meta_description", "body_text_sample"]
    ).lower()
    for pattern in STALE_PATTERNS:
        if pattern in text:
            return pattern
    return ""


def branza_family(value):
    # pierwszy segment przed "/" - do porownania na poziomie ogolnej rodziny branzy,
    # nie dokladnej podbranzy (np. "Motoryzacja / opony / wulkanizacja" -> "motoryzacja")
    return str(value or "").split("/")[0].strip().lower()


def main():
    df = pd.read_excel(CONSOLIDATED_PATH, dtype=str, keep_default_na=False)
    layer1_mask = df["classification_source"] == "google_type_mapping"
    layer1_idx = df[layer1_mask].index
    print(f"Warstwa 1 do sprawdzenia: {len(layer1_idx)}")

    stale_count = 0
    conflict_count = 0
    no_signal_count = 0

    for idx in layer1_idx:
        row = df.loc[idx]

        stale_pattern = detect_stale(row)
        if stale_pattern:
            stale_count += 1
            df.at[idx, "ai_branza_glowna"] = ""
            df.at[idx, "ai_podbranza"] = ""
            df.at[idx, "ai_confidence"] = "0"
            df.at[idx, "manual_review"] = "True"
            df.at[idx, "ai_evidence"] = f"WYKLUCZONO: martwa/zaparkowana domena (wzorzec: '{stale_pattern}')"
            df.at[idx, "classification_source"] = "excluded_stale_domain"
            continue

        detailed = classify_detailed(row.to_dict())
        rule_branza = detailed.get("branza_glowna", "")
        places_branza = row.get("ai_branza_glowna", "")

        if not rule_branza:
            no_signal_count += 1
            continue

        if branza_family(rule_branza) != branza_family(places_branza):
            conflict_count += 1
            df.at[idx, "manual_review"] = "True"
            df.at[idx, "ai_evidence"] = (
                f"{row.get('ai_evidence','')} | KONFLIKT z klasyfikacja regulowa: "
                f"slowa kluczowe strony sugeruja '{rule_branza}/{detailed.get('podbranza','')}' "
                f"(evidence: {detailed.get('classification_evidence','')})"
            )
        else:
            # zgodnosc dwoch niezaleznych zrodel - podnosimy pewnosc
            try:
                current_conf = int(float(row.get("ai_confidence") or 0))
            except (TypeError, ValueError):
                current_conf = 0
            df.at[idx, "ai_confidence"] = str(min(95, current_conf + 15))
            df.at[idx, "ai_evidence"] = f"{row.get('ai_evidence','')} | Potwierdzone niezaleznie slowami kluczowymi strony."

    print()
    print(f"Wykluczono jako martwe/zaparkowane domeny: {stale_count}")
    print(f"Konflikt Places vs slowa kluczowe (do manual_review): {conflict_count}")
    print(f"Brak sygnalu slow kluczowych (taxonomy.csv nie pokrywa - bez zmian): {no_signal_count}")
    print(f"Potwierdzone zgodnie (podniesiona pewnosc): {len(layer1_idx) - stale_count - conflict_count - no_signal_count}")

    df.to_excel(CONSOLIDATED_PATH, index=False)
    print()
    print("Zapisano.")


if __name__ == "__main__":
    main()
