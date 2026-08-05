"""Validate the audit module (on-page SEO + PageSpeed + AEO/GEO + Senuto) against real domains.

STRATEGIA_SYSTEM_POZYSKIWANIA_LEADOW.md sekcja 12, krok 2 ("Modul danych --
fork/integracja seonaut + PageSpeed + Senuto, walidacja na 5-10 firmach") i
krok 3 (warstwa AEO, sekcja 6). Seonaut samo w sobie wymaga Dockera/Go
(niedostepne w tym srodowisku), wiec jego zestaw sprawdzen pokrywa
outreach/audits/seo_onpage.py (natywna implementacja Pythonowa, nie fork).
AEO/GEO pokrywa outreach/audits/aeo_geo.py przez prawdziwy pakiet PyPI
`geo-optimizer-skill`. Senuto jest pokryte przez outreach/audits/senuto.py
wczytujacy juz istniejaca macierz sezonowosci, zamiast duplikowac auth-gated
MCP flow.

Usage:
    python scripts/validate_audit_module.py
    python scripts/validate_audit_module.py --domains https://example.pl,https://foo.pl
    python scripts/validate_audit_module.py --limit 10 --skip-pagespeed
"""
import argparse
import csv
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from outreach import repository  # noqa: E402
from outreach.audits.aeo_geo import run_aeo_geo_audit  # noqa: E402
from outreach.audits.pagespeed import PageSpeedConfigError, run_pagespeed_audit  # noqa: E402
from outreach.audits.senuto import load_senuto_row_for_industry  # noqa: E402
from outreach.audits.seo_onpage import run_onpage_audit  # noqa: E402
from outreach.db import Base, SessionLocal, engine  # noqa: E402

DEFAULT_CRAWL_OUTPUT = Path(__file__).resolve().parent.parent / "output" / "full_test_50.csv"


def domains_from_crawl_output(path: Path, limit: int) -> list[tuple[str, str, str]]:
    """Pull (url, company, detected_industry) tuples from an existing bulk_crawler.py CSV."""
    out = []
    with path.open(encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            if row.get("http_status") == "200" and row.get("domain"):
                out.append((row["domain"], row.get("company") or row["domain"], row.get("detected_industry", "")))
            if len(out) >= limit:
                break
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--domains", help="Comma-separated list of URLs to validate instead of --crawl-output")
    parser.add_argument("--crawl-output", default=str(DEFAULT_CRAWL_OUTPUT), help="Path to an existing bulk_crawler.py CSV output")
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--skip-pagespeed", action="store_true", help="Skip PageSpeed (needs GOOGLE_PAGESPEED_API_KEY)")
    parser.add_argument("--skip-aeo", action="store_true", help="Skip AEO/GEO audit (~15-20s/domain)")
    args = parser.parse_args()

    if args.domains:
        targets = [(d.strip(), d.strip(), "") for d in args.domains.split(",") if d.strip()]
    else:
        crawl_path = Path(args.crawl_output)
        if not crawl_path.exists():
            print(f"Brak pliku {crawl_path} i nie podano --domains. Nic do zwalidowania.")
            return
        targets = domains_from_crawl_output(crawl_path, args.limit)

    if not targets:
        print("Brak domen do walidacji.")
        return

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    results = []
    for url, company, industry in targets:
        print(f"\n=== {url} ===")
        lead = repository.get_lead_by_domain(db, url) or repository.create_lead(
            db, company_name=company, domain=url, detected_industry=industry or None, source="audit_validation"
        )

        onpage_score = None
        try:
            onpage = run_onpage_audit(url)
            onpage_score = onpage["score"]
            repository.add_audit_result(
                db,
                lead.id,
                "seo",
                raw_data=onpage["checks"],
                summary_text="; ".join(onpage["issues"]) or "Brak wykrytych problemow.",
                score=onpage_score,
            )
            print(f"  SEO on-page: {onpage_score}/100 ({len(onpage['issues'])} problemow)")
        except Exception as exc:
            print(f"  SEO on-page: BLAD ({exc})")

        pagespeed_score = "pominiete"
        if not args.skip_pagespeed:
            try:
                ps = run_pagespeed_audit(url)
                pagespeed_score = ps["score"]
                repository.add_audit_result(
                    db,
                    lead.id,
                    "pagespeed",
                    raw_data=ps,
                    summary_text=f"Performance {ps['score']}, SEO {ps['scores']['seo']}, A11y {ps['scores']['accessibility']}",
                    score=pagespeed_score,
                )
                print(f"  PageSpeed (mobile): performance={ps['score']}")
                time.sleep(1)  # be polite to the shared free-tier quota
            except PageSpeedConfigError as exc:
                pagespeed_score = "brak klucza"
                print(f"  PageSpeed: POMINIETE ({exc})")
            except Exception as exc:
                pagespeed_score = "blad"
                print(f"  PageSpeed: BLAD ({exc})")

        aeo_score = "pominiete"
        if not args.skip_aeo:
            try:
                aeo = run_aeo_geo_audit(url)
                aeo_score = aeo["score"]
                repository.add_audit_result(
                    db,
                    lead.id,
                    "aeo_geo",
                    raw_data=aeo["raw_data"],
                    summary_text="; ".join(aeo["issues"][:3]) or "Brak rekomendacji.",
                    score=aeo_score,
                )
                print(f"  AEO/GEO: {aeo_score}/100 ({aeo['band']})")
            except Exception as exc:
                aeo_score = "blad"
                print(f"  AEO/GEO: BLAD ({exc})")

        senuto_row = load_senuto_row_for_industry(industry)
        if senuto_row:
            repository.add_audit_result(db, lead.id, "senuto", raw_data=senuto_row, summary_text="Dopasowanie z macierzy sezonowosci Senuto.")
            print("  Senuto: dopasowanie znalezione w macierzy")
        else:
            print("  Senuto: brak macierzy lub brak dopasowania (workflow bulk_app.py nie uruchomiony / brak danych dla tej branzy)")

        results.append((url, onpage_score, pagespeed_score, aeo_score, senuto_row is not None))

    print("\n=== PODSUMOWANIE ===")
    print(f"{'domena':<45} {'seo_onpage':>11} {'pagespeed':>11} {'aeo_geo':>9} {'senuto':>8}")
    for url, onpage_score, pagespeed_score, aeo_score, has_senuto in results:
        print(f"{url:<45} {str(onpage_score):>11} {str(pagespeed_score):>11} {str(aeo_score):>9} {str(has_senuto):>8}")

    db.close()


if __name__ == "__main__":
    main()
