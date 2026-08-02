# -*- coding: utf-8 -*-
from pathlib import Path

import pandas as pd

from taxonomy import classify_detailed

BASE_DIR = Path(__file__).resolve().parent
CONSOLIDATED_PATH = BASE_DIR / "output" / "leadseason_pelna_baza_zeszyt2_consolidated.xlsx"


def _needs_classification(row):
    if str(row.get("places_status", "")) != "OK":
        return False
    ai_branza = str(row.get("ai_branza_glowna", "") or "").strip()
    rule_branza = str(row.get("branza_glowna", "") or "").strip()
    return ai_branza == "" and rule_branza == ""


def classify_pool(df):
    result = df.copy()
    for col in ["ai_branza_glowna", "ai_podbranza", "ai_confidence", "classification_source", "ai_evidence"]:
        if col not in result.columns:
            result[col] = ""

    target_idx = [idx for idx, row in result.iterrows() if _needs_classification(row)]
    matched = 0
    for idx in target_idx:
        row = result.loc[idx]
        detailed = classify_detailed(row.to_dict())
        if not detailed.get("branza_glowna"):
            continue
        result.at[idx, "ai_branza_glowna"] = detailed["branza_glowna"]
        result.at[idx, "ai_podbranza"] = detailed.get("podbranza", "")
        result.at[idx, "ai_confidence"] = "60"
        result.at[idx, "classification_source"] = "keyword_wave2"
        result.at[idx, "ai_evidence"] = (
            f"Fala 2 (keyword): {detailed.get('classification_evidence', '')}"
        )
        matched += 1

    print(f"Warstwa 2 (keyword): sprawdzono {len(target_idx)} rekordow, dopasowano {matched}.")
    return result


def main():
    df = pd.read_excel(CONSOLIDATED_PATH, dtype=str, keep_default_na=False)
    result = classify_pool(df)
    result.to_excel(CONSOLIDATED_PATH, index=False)
    print(f"Zapisano {CONSOLIDATED_PATH.name}.")


if __name__ == "__main__":
    main()
