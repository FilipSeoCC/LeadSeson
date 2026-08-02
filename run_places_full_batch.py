# -*- coding: utf-8 -*-
import argparse
import os
import sys
from pathlib import Path

import pandas as pd

from bulk_crawler import apply_places_enrichment, filter_places_candidates, load_debtor_domains

BASE_DIR = Path(__file__).resolve().parent


def select_pending_rows(candidates_df, already_enriched_domain_keys):
    if candidates_df.empty:
        return []
    mask = ~candidates_df["domain_key"].astype(str).isin(already_enriched_domain_keys)
    return candidates_df[mask].to_dict(orient="records")


def load_env_file(env_path):
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            os.environ[key] = value


def run_places_full_batch(base_path, output_path, api_key, cache_dir="cache/places", chunk_size=100, debtor_domain_keys=None, today=None):
    df = pd.read_excel(base_path, dtype=str, keep_default_na=False)
    df = df.drop_duplicates("domain_key")

    candidates = filter_places_candidates(df, today=today, debtor_domain_keys=debtor_domain_keys)

    all_results = []
    already_enriched = set()
    if Path(output_path).exists():
        existing = pd.read_excel(output_path, dtype=str, keep_default_na=False)
        already_enriched = set(existing["domain_key"].astype(str))
        all_results = existing.to_dict(orient="records")

    pending = select_pending_rows(candidates, already_enriched)
    print(f"Kandydaci po pre-filtrze: {len(candidates)}, juz zrobione: {len(already_enriched)}, do przetworzenia: {len(pending)}")

    for start in range(0, len(pending), chunk_size):
        chunk = pending[start:start + chunk_size]
        enriched = apply_places_enrichment(chunk, api_key=api_key, cache_dir=cache_dir, timeout=10, force=False)
        all_results.extend(enriched)
        pd.DataFrame(all_results).to_excel(output_path, index=False)
        print(f"Postep: {min(start + chunk_size, len(pending))}/{len(pending)} - zapisano {output_path}")

    result_df = pd.DataFrame(all_results)
    status_counts = result_df["places_status"].value_counts().to_dict() if "places_status" in result_df else {}
    return {
        "total_candidates": len(candidates),
        "processed": len(all_results),
        "status_counts": status_counts,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=str(BASE_DIR / "output" / "leadseason_pelna_baza_po_llm_971.xlsx"))
    parser.add_argument("--output", default=str(BASE_DIR / "output" / "leadseason_places_full_batch.xlsx"))
    parser.add_argument("--chunk-size", type=int, default=100)
    parser.add_argument("--debtor-file", default="")
    parser.add_argument("--debtor-min-dpd", type=int, default=80)
    args = parser.parse_args()

    load_env_file(BASE_DIR / ".env")
    api_key = os.environ.get("GOOGLE_PLACES_API_KEY", "")
    if not api_key:
        print("Brak GOOGLE_PLACES_API_KEY w .env")
        sys.exit(1)

    debtor_domain_keys = None
    if args.debtor_file:
        debtor_domain_keys = load_debtor_domains(args.debtor_file, min_dpd=args.debtor_min_dpd)
        print(f"Dluznicy z DPD > {args.debtor_min_dpd}: {len(debtor_domain_keys)} domen")

    summary = run_places_full_batch(args.base, args.output, api_key, chunk_size=args.chunk_size, debtor_domain_keys=debtor_domain_keys)
    print(summary)
