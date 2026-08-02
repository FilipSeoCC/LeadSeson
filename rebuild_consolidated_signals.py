# -*- coding: utf-8 -*-
from pathlib import Path

import pandas as pd

import seasonal_signal
from seasonal_signal import apply_senuto_q4_signal, build_seasonal_leads

BASE_DIR = Path(__file__).resolve().parent
CONSOLIDATED_PATH = BASE_DIR / "output" / "leadseason_pelna_baza_zeszyt2_consolidated.xlsx"

STATIC_SIGNAL_COLUMNS = [
    "q4_priority", "season_peak", "contact_start",
    "seasonality_confidence", "lead_reason", "call_script",
]


def rebuild_signals(df, matrix):
    """Przelicza q4_priority/season_peak na żywo (apply_senuto_q4_signal) i dokłada
    contact_start/seasonality_confidence/lead_reason/call_script z tego samego przebiegu
    build_seasonal_leads, nadpisując wszelkie stare, statyczne wartości w df.

    lead_reason i call_script dostają identyczną treść z sugerowana_akcja - nie ma dziś
    osobnego generatora treści rozmowy (patrz Global Constraints w planie). recommended_product
    jest świadomie NIE dotykane - poza zakresem tego kroku.
    """
    for col in STATIC_SIGNAL_COLUMNS:
        if col not in df.columns:
            df[col] = ""

    result = apply_senuto_q4_signal(df)

    leads = build_seasonal_leads(df, matrix)
    if leads.empty or "domain_key" not in leads.columns:
        return result

    lookup = leads.drop_duplicates("domain_key", keep="first").set_index("domain_key")

    def _lookup(domain, column, default=""):
        if domain not in lookup.index:
            return default
        return lookup.loc[domain, column]

    result["contact_start"] = result["domain_key"].map(lambda d: _lookup(d, "okno_kontaktu"))
    result["seasonality_confidence"] = result["domain_key"].map(lambda d: _lookup(d, "confidence_sezonowosci", 0))
    result["lead_reason"] = result["domain_key"].map(lambda d: _lookup(d, "sugerowana_akcja"))
    result["call_script"] = result["lead_reason"]
    return result


def main():
    df = pd.read_excel(CONSOLIDATED_PATH, dtype=str, keep_default_na=False)
    matrix = seasonal_signal.load_senuto_matrix_frame()

    before_counts = df["q4_priority"].value_counts().to_dict() if "q4_priority" in df.columns else {}
    result = rebuild_signals(df, matrix)
    after_counts = result["q4_priority"].value_counts().to_dict()

    result.to_excel(CONSOLIDATED_PATH, index=False)

    print("q4_priority PRZED:", before_counts)
    print("q4_priority PO:   ", after_counts)
    print(f"Zapisano {CONSOLIDATED_PATH.name}.")


if __name__ == "__main__":
    main()
