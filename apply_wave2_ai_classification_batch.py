# -*- coding: utf-8 -*-
import json
import sys
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
CONSOLIDATED_PATH = BASE_DIR / "output" / "leadseason_pelna_baza_zeszyt2_consolidated.xlsx"


def apply_batch_to_frame(df, corrections, batch_label):
    result = df.copy()
    for domain, values in corrections.get("classified", {}).items():
        branza, podbranza = values[0], values[1]
        confidence = values[2] if len(values) > 2 else 55
        mask = result["domain_key"] == domain
        if not mask.any():
            print(f"UWAGA: nie znaleziono domeny (classified): {domain}")
            continue
        result.loc[mask, "ai_branza_glowna"] = branza
        result.loc[mask, "ai_podbranza"] = podbranza
        result.loc[mask, "ai_confidence"] = str(confidence)
        result.loc[mask, "classification_source"] = "llm_wave2"
        result.loc[mask, "ai_evidence"] = (
            result.loc[mask, "ai_evidence"].astype(str) + f" | Fala 2 (AI): rozumowanie nad tresc strony ({batch_label})."
        )

    for domain in corrections.get("no_signal", []):
        mask = result["domain_key"] == domain
        if not mask.any():
            print(f"UWAGA: nie znaleziono domeny (no_signal): {domain}")
            continue
        result.loc[mask, "classification_source"] = "ai_reviewed_no_signal"
        result.loc[mask, "ai_evidence"] = (
            result.loc[mask, "ai_evidence"].astype(str) + f" | Fala 2 (AI): sprawdzono, brak wystarczajacego sygnalu ({batch_label})."
        )

    return result


def apply_batch(corrections_path, batch_label):
    with open(corrections_path, encoding="utf-8") as f:
        corrections = json.load(f)
    df = pd.read_excel(CONSOLIDATED_PATH, dtype=str, keep_default_na=False)
    result = apply_batch_to_frame(df, corrections, batch_label)
    result.to_excel(CONSOLIDATED_PATH, index=False)
    print(
        f"[{batch_label}] Sklasyfikowano: {len(corrections.get('classified', {}))}, "
        f"brak sygnalu: {len(corrections.get('no_signal', []))}"
    )


if __name__ == "__main__":
    apply_batch(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else Path(sys.argv[1]).stem)
