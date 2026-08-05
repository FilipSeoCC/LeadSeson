# -*- coding: utf-8 -*-
from pathlib import Path

import pandas as pd

from stale_domain_detector import detect_stale

BASE_DIR = Path(__file__).resolve().parent
CONSOLIDATED_PATH = BASE_DIR / "output" / "leadseason_pelna_baza_zeszyt2_consolidated.xlsx"
WAVE2_SOURCES = {"keyword_wave2", "llm_wave2"}


def filter_stale(df):
    result = df.copy()
    excluded = 0
    for idx, row in result.iterrows():
        if str(row.get("classification_source", "")) not in WAVE2_SOURCES:
            continue
        pattern = detect_stale(row)
        if not pattern:
            continue
        result.at[idx, "ai_branza_glowna"] = ""
        result.at[idx, "ai_podbranza"] = ""
        result.at[idx, "ai_confidence"] = "0"
        result.at[idx, "manual_review"] = "True"
        result.at[idx, "classification_source"] = "excluded_stale_domain"
        result.at[idx, "ai_evidence"] = f"WYKLUCZONO (fala 2): martwa/zaparkowana domena (wzorzec: '{pattern}')"
        excluded += 1
    print(f"Wykluczono jako martwe (fala 2): {excluded}")
    return result


def main():
    df = pd.read_excel(CONSOLIDATED_PATH, dtype=str, keep_default_na=False)
    result = filter_stale(df)
    result.to_excel(CONSOLIDATED_PATH, index=False)
    print(f"Zapisano {CONSOLIDATED_PATH.name}.")


if __name__ == "__main__":
    main()
