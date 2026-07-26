import argparse
import re
from pathlib import Path

import pandas as pd


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SCRATCHPAD = Path(
    r"c:\temp\claude\C--Users-fkedziora-Desktop-Cloaude-ai-projekty\e0ad18d9-7d8a-4a55-aa9f-c4e0fe81d486\scratchpad"
)

EMPTY_INDUSTRIES = {"", "nieokreślona", "brak danych", "do weryfikacji", "nan"}
AI_MODELS = {"B2B", "B2C", "Mieszany", "Nieokreślona", "Nieokreślony"}


def clean_text(value):
    return str(value or "").replace("\ufeff", "").strip().strip('"')


def parse_deep_taxonomy_line(line):
    match = re.match(
        r"^(?P<domain>[^,]+),(?P<middle>.*),(?P<model>B2B|B2C|Mieszany|Nieokreślona|Nieokreślony|),"
        r"(?P<confidence>\d+),(?P<flag>[^,]+),(?P<evidence>.*)$",
        line,
    )
    if not match:
        raise ValueError(f"Nie umiem sparsować linii: {line[:180]}")

    middle_parts = match.group("middle").split(",", 2)
    if len(middle_parts) < 3:
        middle_parts += [""] * (3 - len(middle_parts))

    evidence = clean_text(match.group("evidence")).replace('""', '"')
    return {
        "domain_key": clean_text(match.group("domain")).lower(),
        "ai_branza_glowna": clean_text(middle_parts[0]),
        "ai_podbranza": clean_text(middle_parts[1]),
        "ai_usluga_glowna": clean_text(middle_parts[2]),
        "ai_model_b2b_b2c": clean_text(match.group("model")),
        "ai_confidence": int(match.group("confidence")),
        "ai_new_category_flag": clean_text(match.group("flag")),
        "ai_evidence": evidence,
    }


def read_deep_taxonomy(path):
    lines = Path(path).read_text(encoding="utf-8-sig", errors="replace").splitlines()
    records = []
    for line in lines[1:]:
        if line.strip():
            records.append(parse_deep_taxonomy_line(line))
    return pd.DataFrame(records)


def industry_is_filled(value):
    return str(value or "").strip().lower() not in EMPTY_INDUSTRIES


def build_quality_bucket(row):
    if not industry_is_filled(row.get("ai_branza_glowna")):
        return "DO_WERYFIKACJI"
    if pd.to_numeric(row.get("ai_confidence"), errors="coerce") < 60:
        return "NISKA_PEWNOSC_AI"
    if str(row.get("places_status") or "") == "OK" and pd.to_numeric(row.get("places_match_confidence"), errors="coerce") >= 70:
        return "AI_PLUS_PLACES"
    if pd.to_numeric(row.get("ai_confidence"), errors="coerce") >= 80:
        return "WYSOKA_AI"
    return "SREDNIA_AI"


def build_report(deep_path, places_path, old_output_path, output_path):
    deep = read_deep_taxonomy(deep_path)
    places = pd.read_csv(places_path, dtype=str, keep_default_na=False)
    old = pd.read_excel(
        old_output_path,
        dtype=str,
        keep_default_na=False,
        usecols=[
            "id",
            "detail_id",
            "nip",
            "company",
            "domain",
            "domain_key",
            "crawl_status",
            "detected_industry",
            "industry_confidence",
            "title",
            "meta_description",
        ],
    )

    for frame in [deep, places, old]:
        frame["domain_key"] = frame["domain_key"].astype(str).str.strip().str.lower()

    report = old.merge(deep, on="domain_key", how="inner").merge(places, on="domain_key", how="left")
    report["old_has_industry"] = report["detected_industry"].apply(industry_is_filled)
    report["ai_has_industry"] = report["ai_branza_glowna"].apply(industry_is_filled)
    report["places_ok"] = report["places_status"].eq("OK")
    report["category_quality_bucket"] = report.apply(build_quality_bucket, axis=1)
    report["old_vs_ai_changed"] = (
        report["old_has_industry"]
        & report["ai_has_industry"]
        & (report["detected_industry"].str.strip() != report["ai_branza_glowna"].str.strip())
    )

    metrics = pd.DataFrame(
        [
            {"metryka": "rekordy_w_probce", "wartosc": len(report)},
            {"metryka": "unikalne_domeny_w_probce", "wartosc": int(report["domain_key"].nunique())},
            {"metryka": "stare_pokrycie_keyword", "wartosc": int(report["old_has_industry"].sum())},
            {"metryka": "stare_pokrycie_keyword_pct", "wartosc": round(report["old_has_industry"].mean() * 100, 1)},
            {"metryka": "pokrycie_ai", "wartosc": int(report["ai_has_industry"].sum())},
            {"metryka": "pokrycie_ai_pct", "wartosc": round(report["ai_has_industry"].mean() * 100, 1)},
            {"metryka": "places_ok", "wartosc": int(report["places_ok"].sum())},
            {"metryka": "places_ok_pct", "wartosc": round(report["places_ok"].mean() * 100, 1)},
            {"metryka": "ai_plus_places", "wartosc": int(report["category_quality_bucket"].eq("AI_PLUS_PLACES").sum())},
            {"metryka": "do_weryfikacji", "wartosc": int(report["category_quality_bucket"].isin(["DO_WERYFIKACJI", "NISKA_PEWNOSC_AI"]).sum())},
            {"metryka": "nowe_kategorie_ai", "wartosc": int(report["ai_new_category_flag"].str.contains("NOWA", na=False).sum())},
        ]
    )

    main_columns = [
        "id",
        "detail_id",
        "nip",
        "company",
        "domain",
        "domain_key",
        "crawl_status",
        "detected_industry",
        "industry_confidence",
        "ai_branza_glowna",
        "ai_podbranza",
        "ai_usluga_glowna",
        "ai_model_b2b_b2c",
        "ai_confidence",
        "ai_new_category_flag",
        "category_quality_bucket",
        "places_status",
        "places_name",
        "places_primary_type",
        "places_types",
        "places_match_confidence",
        "places_match_reasons",
        "places_website",
        "places_industry_hint",
        "old_vs_ai_changed",
        "ai_evidence",
        "title",
        "meta_description",
    ]
    report = report[[col for col in main_columns if col in report.columns]]

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        metrics.to_excel(writer, sheet_name="metryki", index=False)
        report.to_excel(writer, sheet_name="kategoryzacja_500", index=False)
        report["ai_branza_glowna"].value_counts().rename_axis("branza_glowna").reset_index(name="liczba").to_excel(
            writer, sheet_name="branze_glowne", index=False
        )
        report["ai_podbranza"].value_counts().rename_axis("podbranza").reset_index(name="liczba").to_excel(
            writer, sheet_name="podbranze", index=False
        )
        report["ai_new_category_flag"].value_counts().rename_axis("flaga").reset_index(name="liczba").to_excel(
            writer, sheet_name="nowe_kategorie", index=False
        )
        report["places_primary_type"].value_counts().rename_axis("places_primary_type").reset_index(name="liczba").to_excel(
            writer, sheet_name="places_typy", index=False
        )
        report[report["category_quality_bucket"].isin(["DO_WERYFIKACJI", "NISKA_PEWNOSC_AI"])].to_excel(
            writer, sheet_name="do_weryfikacji", index=False
        )

    csv_path = output_path.with_suffix(".csv")
    report.to_csv(csv_path, index=False, encoding="utf-8-sig")
    return output_path, csv_path, metrics


def main():
    parser = argparse.ArgumentParser(description="Buduje raport jakości kategoryzacji LeadSeason.")
    parser.add_argument("--deep", default=str(DEFAULT_SCRATCHPAD / "deep_taxonomy_output.csv"))
    parser.add_argument("--places", default=str(DEFAULT_SCRATCHPAD / "places_500.csv"))
    parser.add_argument("--old", default=str(BASE_DIR / "output" / "karta_account_pelna_baza_branze.xlsx"))
    parser.add_argument("--out", default=str(BASE_DIR / "output" / "leadseason_kategoryzacja_ai_places_500.xlsx"))
    args = parser.parse_args()

    output_path, csv_path, metrics = build_report(args.deep, args.places, args.old, args.out)
    print(f"Zapisano: {output_path}")
    print(f"Zapisano: {csv_path}")
    print(metrics.to_string(index=False))


if __name__ == "__main__":
    main()
