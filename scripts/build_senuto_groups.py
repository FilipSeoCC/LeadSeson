import argparse
from pathlib import Path

import pandas as pd


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CATEGORY_REPORT = BASE_DIR / "output" / "leadseason_kategoryzacja_ai_places_500.xlsx"
DEFAULT_OUTPUT = BASE_DIR / "output" / "leadseason_grupy_branze_do_senuto.xlsx"


def join_top(values, limit=5):
    seen = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.append(text)
        if len(seen) >= limit:
            break
    return " | ".join(seen)


def proposed_keywords(row):
    parts = [
        str(row.get("ai_podbranza") or "").strip(),
        str(row.get("ai_usluga_glowna") or "").strip(),
        str(row.get("ai_branza_glowna") or "").strip(),
    ]
    candidates = []
    for part in parts:
        if part and part.lower() not in ["nieokreślona", "brak danych"]:
            candidates.append(part)
    return " | ".join(candidates[:3])


def load_category_report(path):
    workbook = pd.ExcelFile(path)
    sheet = "kategoryzacja_500" if "kategoryzacja_500" in workbook.sheet_names else workbook.sheet_names[0]
    return pd.read_excel(workbook, sheet_name=sheet, dtype=str, keep_default_na=False)


def build_groups(input_path=DEFAULT_CATEGORY_REPORT, output_path=DEFAULT_OUTPUT):
    df = load_category_report(input_path)
    if df.empty:
        raise ValueError("Raport kategoryzacji jest pusty.")

    for column in ["ai_branza_glowna", "ai_podbranza", "ai_usluga_glowna", "ai_model_b2b_b2c"]:
        if column not in df:
            df[column] = ""

    df["_ai_confidence_num"] = pd.to_numeric(df.get("ai_confidence", 0), errors="coerce").fillna(0)
    df["_places_confidence_num"] = pd.to_numeric(df.get("places_match_confidence", 0), errors="coerce").fillna(0)
    df["_quality_rank"] = (
        df.get("category_quality_bucket", "").astype(str).eq("AI_PLUS_PLACES").astype(int) * 1000
        + df["_ai_confidence_num"] * 5
        + df["_places_confidence_num"]
    )

    group_cols = ["ai_branza_glowna", "ai_podbranza", "ai_usluga_glowna", "ai_model_b2b_b2c"]
    rows = []
    for keys, group in df.sort_values("_quality_rank", ascending=False).groupby(group_cols, dropna=False):
        item = dict(zip(group_cols, keys))
        item["liczba_rekordow"] = len(group)
        item["liczba_domen"] = group["domain_key"].nunique() if "domain_key" in group else len(group)
        item["reprezentatywne_domeny"] = join_top(group.get("domain_key", []), 6)
        item["reprezentatywne_firmy"] = join_top(group.get("company", []), 4)
        item["proponowane_frazy_senuto"] = proposed_keywords(item)
        item["places_primary_types"] = join_top(group.get("places_primary_type", []), 8)
        item["srednia_pewnosc_ai"] = round(group["_ai_confidence_num"].mean(), 1)
        item["najlepszy_status_jakosci"] = join_top(group.get("category_quality_bucket", []), 3)
        item["senuto_query_type"] = "keyword"
        item["senuto_queries_used"] = ""
        item["sezon_peak_miesiace"] = ""
        item["sezon_start_miesiac"] = ""
        item["sezon_end_miesiac"] = ""
        item["czy_sezonowosc_wyrazna"] = ""
        item["confidence_sezonowosci"] = ""
        item["senuto_evidence"] = ""
        item["status_senuto"] = "DO_SPRAWDZENIA"
        rows.append(item)

    output = pd.DataFrame(rows).sort_values(["liczba_rekordow", "liczba_domen"], ascending=False)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        output.to_excel(writer, sheet_name="grupy_do_senuto", index=False)
        output.head(30).to_excel(writer, sheet_name="top_30_priorytet", index=False)
        output[output["status_senuto"].eq("DO_SPRAWDZENIA")].to_excel(writer, sheet_name="do_sprawdzenia", index=False)

    csv_path = output_path.with_suffix(".csv")
    output.to_csv(csv_path, index=False, encoding="utf-8-sig")
    return output_path, csv_path, output


def main():
    parser = argparse.ArgumentParser(description="Buduje grupy branżowe do sprawdzenia sezonowości w Senuto.")
    parser.add_argument("--input", default=str(DEFAULT_CATEGORY_REPORT))
    parser.add_argument("--out", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    output_path, csv_path, output = build_groups(args.input, args.out)
    print(f"Zapisano: {output_path}")
    print(f"Zapisano: {csv_path}")
    print(f"Grupy: {len(output)}")
    print(output.head(15).to_string(index=False))


if __name__ == "__main__":
    main()
