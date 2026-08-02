# -*- coding: utf-8 -*-
# Konsoliduje: aktywna baza z Zeszyt2 (opiekun/TL, wykluczenia) + dotychczasowy
# dorobek (crawl+AI dla 4163) + nowy crawl (6851) + nowy Places (polowa 4668)
# w jeden plik, ktory auto_pick_dataset() w bulk_app.py wybierze automatycznie
# (najnowszy plik z "pelna" w nazwie w output/).
from pathlib import Path

import pandas as pd

from bulk_crawler import filter_places_candidates, load_debtor_domains

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"


def blank_to_na(df):
    return df.replace("", pd.NA)


def na_to_blank(df):
    return df.fillna("")


def load_zeszyt2_active_base(zeszyt2_path, debtor_path, today=None):
    full = pd.read_excel(zeszyt2_path, dtype=str, keep_default_na=False)
    cols = list(full.columns)
    rename_map = {
        cols[0]: "obieg", cols[1]: "numer_umowy", cols[2]: "nip", cols[3]: "domain_key",
        cols[4]: "kod_pakietu", cols[5]: "wartosc_pakietu", cols[6]: "typ_klienta",
        cols[7]: "start_date", cols[8]: "end_date", cols[9]: "data_podpisania",
        cols[10]: "status_zamowienia", cols[11]: "status", cols[12]: "nazwa_obiegu",
        cols[13]: "account_owner", cols[14]: "team_leader",
    }
    full = full.rename(columns=rename_map)
    full["domain_key"] = full["domain_key"].astype(str).str.strip().str.lower()
    full = full[full["domain_key"] != ""].copy()
    full["_end_dt"] = pd.to_datetime(full["end_date"], errors="coerce")
    full = full.sort_values("_end_dt", ascending=False).drop_duplicates("domain_key", keep="first")
    full = full.drop(columns=["_end_dt"])

    debtor_domains = load_debtor_domains(debtor_path, min_dpd=80)
    active = filter_places_candidates(full, today=today, debtor_domain_keys=debtor_domains)
    return active.reset_index(drop=True)


def coalesce_fill(base_df, fill_df, key="domain_key", exclude_cols=()):
    base_idx = blank_to_na(base_df).set_index(key)
    fill_cols = [c for c in fill_df.columns if c != key and c not in exclude_cols]
    fill_idx = blank_to_na(fill_df[[key] + fill_cols]).drop_duplicates(key).set_index(key)
    combined = base_idx.combine_first(fill_idx)
    # combine_first can reorder/introduce extra rows from fill_idx not in base_idx - restrict back
    combined = combined.loc[combined.index.isin(base_idx.index)]
    return na_to_blank(combined).reset_index()


def main():
    zeszyt2_path = r"C:\Users\fkedziora\Desktop\Zeszyt2 (4).xlsx"
    debtor_path = r"C:\Users\fkedziora\Downloads\_SEO - Dłużnik Obsługa(19).xlsx"

    active = load_zeszyt2_active_base(zeszyt2_path, debtor_path)
    print(f"Aktywna baza (Zeszyt2, po wykluczeniach): {len(active)}")

    old_worked = pd.read_excel(OUTPUT_DIR / "leadseason_pelna_baza_po_llm_971.xlsx", dtype=str, keep_default_na=False)
    old_worked = old_worked.drop_duplicates("domain_key")
    old_worked["domain_key"] = old_worked["domain_key"].astype(str).str.strip().str.lower()
    consolidated = coalesce_fill(active, old_worked, exclude_cols=["nip", "domain", "end_date", "start_date", "account_owner"])
    print(f"Po dolaczeniu starej bazy (crawl+AI dla 4163): {len(consolidated)}")

    places_test150 = pd.read_excel(OUTPUT_DIR / "leadseason_places_batch_test_150.xlsx", dtype=str, keep_default_na=False)
    places_test150["domain_key"] = places_test150["domain_key"].astype(str).str.strip().str.lower()
    places_cols_test = [c for c in places_test150.columns if c.startswith("places_")]
    consolidated = coalesce_fill(consolidated, places_test150[["domain_key"] + places_cols_test])
    print("Po dolaczeniu Places z testu 150")

    new_crawl = pd.read_excel(OUTPUT_DIR / "leadseason_crawl_nowe_wyniki.xlsx", dtype=str, keep_default_na=False)
    new_crawl["domain_key"] = new_crawl["domain_key"].astype(str).str.strip().str.lower()
    consolidated = coalesce_fill(consolidated, new_crawl, exclude_cols=["domain"])
    print(f"Po dolaczeniu nowego crawlu (6851): {len(consolidated)}")

    places_polowa = pd.read_excel(OUTPUT_DIR / "leadseason_places_batch_polowa_wyniki.xlsx", dtype=str, keep_default_na=False)
    places_polowa["domain_key"] = places_polowa["domain_key"].astype(str).str.strip().str.lower()
    places_cols_polowa = [c for c in places_polowa.columns if c.startswith("places_")]
    consolidated = coalesce_fill(consolidated, places_polowa[["domain_key"] + places_cols_polowa])
    print(f"Po dolaczeniu Places polowa 1 (4668): {len(consolidated)}")

    places_polowa2 = pd.read_excel(OUTPUT_DIR / "leadseason_places_batch_polowa2_wyniki_fix.xlsx", dtype=str, keep_default_na=False)
    places_polowa2["domain_key"] = places_polowa2["domain_key"].astype(str).str.strip().str.lower()
    places_cols_polowa2 = [c for c in places_polowa2.columns if c.startswith("places_")]
    consolidated = coalesce_fill(consolidated, places_polowa2[["domain_key"] + places_cols_polowa2])
    print(f"Po dolaczeniu Places polowa 2 - naprawiona (4669): {len(consolidated)}")

    out_path = OUTPUT_DIR / "leadseason_pelna_baza_zeszyt2_consolidated.xlsx"
    consolidated.to_excel(out_path, index=False)
    print(f"Zapisano: {out_path} ({len(consolidated)} wierszy, {len(consolidated.columns)} kolumn)")

    has_crawl = (consolidated.get("crawl_status", pd.Series("", index=consolidated.index)).astype(str) != "").sum()
    has_ai = (consolidated.get("ai_branza_glowna", pd.Series("", index=consolidated.index)).astype(str) != "").sum()
    has_places = (consolidated.get("places_status", pd.Series("", index=consolidated.index)).astype(str) != "").sum()
    print()
    print(f"Pokrycie: crawl={has_crawl}, ai_branza_glowna={has_ai}, places_status={has_places} (z {len(consolidated)})")


if __name__ == "__main__":
    main()
