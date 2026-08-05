# -*- coding: utf-8 -*-
import argparse
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

from bulk_crawler import DEFAULT_TIMEOUT, DEFAULT_WORKERS, crawl_domain

BASE_DIR = Path(__file__).resolve().parent


def run_full_crawl(input_path, output_path, cache_dir="cache/crawl", workers=DEFAULT_WORKERS, timeout=DEFAULT_TIMEOUT, save_every=100):
    df = pd.read_excel(input_path, dtype=str, keep_default_na=False)
    domains = sorted(set(df["domain_key"].astype(str).str.strip().str.lower()) - {""})

    results = []
    already_done = set()
    if Path(output_path).exists():
        existing = pd.read_excel(output_path, dtype=str, keep_default_na=False)
        already_done = set(existing["domain_key"].astype(str))
        results = existing.to_dict(orient="records")

    pending = [d for d in domains if d not in already_done]
    print(f"Domeny razem: {len(domains)}, juz zrobione: {len(already_done)}, do zrobienia: {len(pending)}")

    start = time.time()
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(crawl_domain, d, cache_dir, timeout, False): d for d in pending}
        for index, future in enumerate(as_completed(futures), start=1):
            domain = futures[future]
            try:
                results.append(future.result())
            except Exception as exc:
                results.append({"domain_key": domain, "crawl_status": "ERROR", "error": str(exc)})
            if index % save_every == 0 or index == len(pending):
                pd.DataFrame(results).to_excel(output_path, index=False)
                elapsed = time.time() - start
                print(f"Postep: {index}/{len(pending)} - {elapsed:.0f}s - zapisano {output_path}")

    result_df = pd.DataFrame(results)
    status_counts = result_df["crawl_status"].value_counts().to_dict() if "crawl_status" in result_df else {}
    print("Gotowe. Status crawlu:", status_counts)
    return {"total": len(domains), "processed": len(results), "status_counts": status_counts}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(BASE_DIR / "output" / "leadseason_nowe_do_crawlu.xlsx"))
    parser.add_argument("--output", default=str(BASE_DIR / "output" / "leadseason_crawl_nowe_wyniki.xlsx"))
    parser.add_argument("--cache-dir", default=str(BASE_DIR / "cache" / "crawl"))
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    args = parser.parse_args()

    summary = run_full_crawl(args.input, args.output, cache_dir=args.cache_dir, workers=args.workers, timeout=args.timeout)
    print(summary)
