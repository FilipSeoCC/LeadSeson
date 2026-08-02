# -*- coding: utf-8 -*-
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
CONSOLIDATED_PATH = BASE_DIR / "output" / "leadseason_pelna_baza_zeszyt2_consolidated.xlsx"
EXPORT_PATH = BASE_DIR / "output" / "leadseason_customer_care_export.xlsx"

READY_PRIORITIES = {"HIGH", "MEDIUM_HIGH", "LOW_Q4"}

DO_DZWONIENIA_COLUMNS = [
    "account_owner", "id", "detail_id", "nip", "company", "domain_key", "monthly_value",
    "branza_glowna", "podbranza", "q4_priority", "season_peak", "contact_start",
    "lead_reason", "call_script", "effective_confidence",
]
DO_WERYFIKACJI_COLUMNS = [
    "account_owner", "id", "detail_id", "nip", "company", "domain_key", "monthly_value",
    "q4_priority", "classification_source",
]


def _effective_branza(df):
    ai = df.get("ai_branza_glowna", pd.Series("", index=df.index)).astype(str).str.strip()
    rule = df.get("branza_glowna", pd.Series("", index=df.index)).astype(str).str.strip()
    return ai.where(ai.ne(""), rule)


def _effective_podbranza(df):
    ai = df.get("ai_branza_glowna", pd.Series("", index=df.index)).astype(str).str.strip()
    ai_pod = df.get("ai_podbranza", pd.Series("", index=df.index)).astype(str)
    rule_pod = df.get("podbranza", pd.Series("", index=df.index)).astype(str)
    return ai_pod.where(ai.ne(""), rule_pod)


def _effective_confidence(df):
    ai = df.get("ai_branza_glowna", pd.Series("", index=df.index)).astype(str).str.strip()
    ai_conf = pd.to_numeric(df.get("ai_confidence", pd.Series(0, index=df.index)), errors="coerce").fillna(0)
    rule_conf = pd.to_numeric(df.get("classification_confidence", pd.Series(0, index=df.index)), errors="coerce").fillna(0)
    return ai_conf.where(ai.ne(""), rule_conf)


def build_customer_care_workbook(df):
    work = df.copy()
    work["branza_glowna"] = _effective_branza(work)
    work["podbranza"] = _effective_podbranza(work)
    work["effective_confidence"] = _effective_confidence(work)
    work["call_script"] = work.get("call_script", work.get("lead_reason", ""))
    work["_mrr_num"] = pd.to_numeric(work.get("monthly_value", pd.Series(0, index=work.index)), errors="coerce").fillna(0)

    ready_mask = work["q4_priority"].astype(str).isin(READY_PRIORITIES)
    ready = work[ready_mask].copy()
    review = work[~ready_mask].copy()

    rank = {"HIGH": 3, "MEDIUM_HIGH": 2, "LOW_Q4": 1}
    ready["_rank"] = ready["q4_priority"].map(rank).fillna(0)
    ready = ready.sort_values(["_rank", "_mrr_num"], ascending=[False, False])

    do_dzwonienia = ready[[c for c in DO_DZWONIENIA_COLUMNS if c in ready.columns]].reset_index(drop=True)
    do_weryfikacji = review[[c for c in DO_WERYFIKACJI_COLUMNS if c in review.columns]].reset_index(drop=True)

    per_owner = ready.groupby("account_owner", dropna=False).agg(
        liczba_leadow=("domain_key", "count"),
        suma_mrr=("_mrr_num", "sum"),
        high=("q4_priority", lambda s: (s == "HIGH").sum()),
        medium_high=("q4_priority", lambda s: (s == "MEDIUM_HIGH").sum()),
        low_q4=("q4_priority", lambda s: (s == "LOW_Q4").sum()),
    ).reset_index().sort_values("liczba_leadow", ascending=False)

    per_branza = ready.groupby("branza_glowna", dropna=False).agg(
        liczba_leadow=("domain_key", "count"),
        suma_mrr=("_mrr_num", "sum"),
    ).reset_index().sort_values("liczba_leadow", ascending=False)

    kpi = pd.DataFrame([{
        "rekordy_gotowe": len(ready),
        "rekordy_do_weryfikacji": len(review),
        "pokrycie_procent": round(len(ready) / len(work) * 100, 1) if len(work) else 0.0,
        "suma_mrr_gotowe": round(ready["_mrr_num"].sum(), 2),
    }])

    summary = pd.concat(
        [
            pd.DataFrame([{"sekcja": "KPI"}]), kpi,
            pd.DataFrame([{"sekcja": "Per opiekun"}]), per_owner,
            pd.DataFrame([{"sekcja": "Per branża"}]), per_branza,
        ],
        ignore_index=True,
    )

    return {
        "Do dzwonienia": do_dzwonienia,
        "Do weryfikacji": do_weryfikacji,
        "Podsumowanie managera": summary,
    }


def main():
    df = pd.read_excel(CONSOLIDATED_PATH, dtype=str, keep_default_na=False)
    sheets = build_customer_care_workbook(df)
    with pd.ExcelWriter(EXPORT_PATH, engine="openpyxl") as writer:
        for name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=name, index=False)
    print(f"Zapisano {EXPORT_PATH.name}: Do dzwonienia={len(sheets['Do dzwonienia'])}, "
          f"Do weryfikacji={len(sheets['Do weryfikacji'])}")


if __name__ == "__main__":
    main()
