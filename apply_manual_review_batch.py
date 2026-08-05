# -*- coding: utf-8 -*-
import json
import sys
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
CONSOLIDATED_PATH = BASE_DIR / "output" / "leadseason_pelna_baza_zeszyt2_consolidated.xlsx"


def apply_batch(corrections_path, batch_label):
    with open(corrections_path, encoding="utf-8") as f:
        corrections = json.load(f)

    df = pd.read_excel(CONSOLIDATED_PATH, dtype=str, keep_default_na=False)

    for domain in corrections.get("confirmed", []):
        mask = df["domain_key"] == domain
        if not mask.any():
            print(f"UWAGA: nie znaleziono domeny (confirmed): {domain}")
            continue
        df.loc[mask, "manual_review"] = "False"
        df.loc[mask, "ai_evidence"] = df.loc[mask, "ai_evidence"].astype(str) + f" | RECZNIE POTWIERDZONE ({batch_label})."
        try:
            conf = int(float(df.loc[mask, "ai_confidence"].iloc[0] or 0))
        except (TypeError, ValueError):
            conf = 0
        df.loc[mask, "ai_confidence"] = str(min(95, conf + 10))

    for domain, pair in corrections.get("corrected", {}).items():
        branza, podbranza = pair
        mask = df["domain_key"] == domain
        if not mask.any():
            print(f"UWAGA: nie znaleziono domeny (corrected): {domain}")
            continue
        df.loc[mask, "ai_branza_glowna"] = branza
        df.loc[mask, "ai_podbranza"] = podbranza
        df.loc[mask, "manual_review"] = "False"
        df.loc[mask, "ai_confidence"] = "80"
        df.loc[mask, "ai_evidence"] = df.loc[mask, "ai_evidence"].astype(str) + f" | RECZNIE POPRAWIONE ({batch_label}): tresc strony jednoznacznie wskazuje inna branze niz Places."

    df.to_excel(CONSOLIDATED_PATH, index=False)
    print(f"[{batch_label}] Potwierdzono: {len(corrections.get('confirmed', []))}, Poprawiono: {len(corrections.get('corrected', {}))}")


if __name__ == "__main__":
    apply_batch(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else Path(sys.argv[1]).stem)
