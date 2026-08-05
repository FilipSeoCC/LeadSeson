import json
from io import BytesIO

import pandas as pd


AI_CONTEXT_COLUMNS = [
    "id",
    "detail_id",
    "nip",
    "domain",
    "domain_key",
    "company",
    "service",
    "title",
    "meta_description",
    "meta_keywords",
    "h1_h3",
    "offer_links",
    "body_text_sample",
    "detected_industry",
    "industry_confidence",
    "evidence_keywords",
    "places_primary_type",
    "places_types",
    "places_name",
    "site_health_status",
    "site_health_reason",
    "usable_for_llm",
]

AI_RESULT_FIELDS = [
    "branza_glowna",
    "podbranza",
    "usluga_glowna",
    "model_b2b_b2c",
    "confidence",
    "new_category_flag",
    "leadseason_industry",
    "industry_confidence",
    "season_peak",
    "contact_start",
    "q4_priority",
    "recommended_product",
    "lead_reason",
    "call_script",
    "evidence",
    "manual_review",
]


PLACES_RECLASS_CONTEXT_COLUMNS = AI_CONTEXT_COLUMNS + [
    "places_address",
    "places_match_confidence",
    "places_match_reasons",
    "ai_branza_glowna",
    "ai_podbranza",
]

PLACES_RECLASS_INSTRUCTIONS = (
    "Dane z Google Places (places_name, places_primary_type, places_address) "
    "to GLOWNY dowod dla klasyfikacji branzy - pochodza z ustrukturyzowanej bazy Google "
    "o realnej dzialalnosci firmy. Tresc strony WWW (title, meta_description, body_text_sample) "
    "to dowod POMOCNICZY - moze byc niejednoznaczna lub SEO-tekstowa. "
    "Istniejace pola ai_branza_glowna/ai_podbranza moga byc bledne (klasyfikowane wylacznie "
    "z tresci strony) - nie traktuj ich jako zalozenia, ocen branze od nowa na podstawie "
    "danych z Places w pierwszej kolejnosci."
)


def clean_for_prompt(value, limit=1400):
    text = str(value or "").replace("\x00", " ")
    text = " ".join(text.split())
    return text[:limit]


def build_record_key(row):
    parts = [
        str(row.get("id") or "").strip(),
        str(row.get("detail_id") or "").strip(),
        str(row.get("domain_key") or row.get("domain") or "").strip(),
    ]
    key = "|".join(parts).strip("|")
    return key or str(row.name)


def eligible_for_ai(row):
    branch = str(row.get("branza_glowna") or "").strip()
    branch_norm = branch.lower()
    crawl_status = str(row.get("crawl_status") or "").strip()
    usable_raw = row.get("usable_for_llm", True)
    usable = str(usable_raw).strip().lower() not in ["false", "0", "nie", "no"]
    site_health = str(row.get("site_health_status") or "OK").strip()
    body = str(row.get("body_text_sample") or "").strip()
    title = str(row.get("title") or "").strip()
    weak_branch = branch_norm in ["", "brak danych", "nieokreślona", "nieokreslona", "do weryfikacji", "-"]
    needs_verification = weak_branch
    return needs_verification and crawl_status == "OK" and usable and site_health == "OK" and bool(body or title)


def build_ai_batch(df, only_unclassified=True, limit=100, start=0):
    records = []
    working = df.copy()
    if only_unclassified:
        mask = working.apply(eligible_for_ai, axis=1)
        working = working[mask]
    if start:
        working = working.iloc[int(start):]
    if limit:
        working = working.head(int(limit))

    for _, row in working.iterrows():
        item = {
            "record_key": build_record_key(row),
            "task": "classify_leadseason_industry",
            "context": {},
            "expected_output_schema": {
                "record_key": "same as input",
                "branza_glowna": "string",
                "podbranza": "string",
                "usluga_glowna": "string",
                "model_b2b_b2c": "B2B | B2C | Mieszany | Nieokreślona",
                "confidence": "integer 0-100",
                "new_category_flag": "ISTNIEJACA | NOWA_BRANZA | NOWA_PODBRANZA | NOWA_USLUGA | BRAK_SYGNALU",
                "evidence": "short evidence string",
                "manual_review": "boolean",
            },
        }
        for column in AI_CONTEXT_COLUMNS:
            if column in row:
                item["context"][column] = clean_for_prompt(row.get(column))
        records.append(item)
    return records


def eligible_for_places_reclass(row):
    return str(row.get("places_status") or "").strip() == "OK"


def build_places_reclass_batch(df, limit=1000, start=0):
    records = []
    working = df[df.apply(eligible_for_places_reclass, axis=1)]
    if start:
        working = working.iloc[int(start):]
    if limit:
        working = working.head(int(limit))

    for _, row in working.iterrows():
        item = {
            "record_key": build_record_key(row),
            "task": "classify_leadseason_industry_places_first",
            "instructions": PLACES_RECLASS_INSTRUCTIONS,
            "context": {},
            "expected_output_schema": {
                "record_key": "same as input",
                "branza_glowna": "string",
                "podbranza": "string",
                "usluga_glowna": "string",
                "model_b2b_b2c": "B2B | B2C | Mieszany | Nieokreslona",
                "confidence": "integer 0-100",
                "new_category_flag": "ISTNIEJACA | NOWA_BRANZA | NOWA_PODBRANZA | NOWA_USLUGA | BRAK_SYGNALU",
                "evidence": "short evidence string",
                "manual_review": "boolean",
            },
        }
        for column in PLACES_RECLASS_CONTEXT_COLUMNS:
            if column in row:
                item["context"][column] = clean_for_prompt(row.get(column))
        records.append(item)
    return records


def jsonl_bytes(records):
    payload = "\n".join(json.dumps(record, ensure_ascii=False) for record in records)
    if payload:
        payload += "\n"
    return payload.encode("utf-8")


def read_ai_results(uploaded_file):
    name = uploaded_file.name.lower()
    payload = uploaded_file.getvalue()
    if name.endswith(".jsonl"):
        rows = []
        for line in payload.decode("utf-8-sig").splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
        return pd.DataFrame(rows)
    if name.endswith(".json"):
        data = json.loads(payload.decode("utf-8-sig"))
        if isinstance(data, dict):
            for key in ["rows", "data", "records", "items", "results"]:
                if isinstance(data.get(key), list):
                    data = data[key]
                    break
        return pd.DataFrame(data)
    if name.endswith(".csv"):
        return pd.read_csv(BytesIO(payload), sep=None, engine="python", dtype=str, keep_default_na=False, encoding="utf-8-sig")
    return pd.read_excel(BytesIO(payload), dtype=str, keep_default_na=False)


def normalize_bool(value):
    text = str(value or "").strip().lower()
    return text in ["1", "true", "tak", "yes", "y"]


def first_present(row, fields):
    for field in fields:
        if field in row and not pd.isna(row.get(field)):
            value = row.get(field)
            if str(value).strip():
                return value
    return ""


def merge_ai_results(df, results_df):
    if df.empty or results_df.empty:
        return df.copy(), {"updated": 0, "input_results": len(results_df)}

    output = df.copy().astype("object")
    output["_record_key"] = output.apply(build_record_key, axis=1)
    if "domain_key" in output:
        output["_domain_key"] = output["domain_key"].astype(str).str.strip().str.lower()
    else:
        output["_domain_key"] = ""
    results = results_df.copy()

    if "record_key" in results:
        results["_merge_key"] = results["record_key"].astype(str)
        output["_merge_key"] = output["_record_key"].astype(str)
    elif "domain_key" in results:
        results["_merge_key"] = results["domain_key"].astype(str).str.strip().str.lower()
        output["_merge_key"] = output["_domain_key"]
    else:
        raise ValueError("Wynik AI musi mieć kolumnę/pole `record_key` albo `domain_key`.")

    results = results.drop_duplicates("_merge_key", keep="last").set_index("_merge_key")
    updated = 0
    for idx, row in output.iterrows():
        key = row["_merge_key"]
        if key not in results.index:
            continue
        result = results.loc[key]
        industry = first_present(result, ["branza_glowna", "ai_branza_glowna", "leadseason_industry", "detected_industry"])
        if industry:
            output.at[idx, "detected_industry"] = industry
            output.at[idx, "ai_branza_glowna"] = industry
        podbranza = first_present(result, ["podbranza", "ai_podbranza"])
        usluga = first_present(result, ["usluga_glowna", "ai_usluga_glowna"])
        model = first_present(result, ["model_b2b_b2c", "ai_model_b2b_b2c"])
        confidence = first_present(result, ["confidence", "ai_confidence", "industry_confidence"])
        category_flag = first_present(result, ["new_category_flag", "ai_new_category_flag"])
        if podbranza:
            output.at[idx, "ai_podbranza"] = podbranza
        if usluga:
            output.at[idx, "ai_usluga_glowna"] = usluga
        if model:
            output.at[idx, "ai_model_b2b_b2c"] = model
        if confidence:
            output.at[idx, "industry_confidence"] = confidence
            output.at[idx, "ai_confidence"] = confidence
        if category_flag:
            output.at[idx, "ai_new_category_flag"] = category_flag
        for field in AI_RESULT_FIELDS:
            if field not in result or pd.isna(result.get(field)):
                continue
            value = result.get(field)
            if field in ["branza_glowna", "leadseason_industry"]:
                output.at[idx, "detected_industry"] = value
                output.at[idx, "ai_branza_glowna"] = value
            elif field == "confidence":
                output.at[idx, "industry_confidence"] = value
                output.at[idx, "ai_confidence"] = value
            elif field == "podbranza":
                output.at[idx, "ai_podbranza"] = value
            elif field == "usluga_glowna":
                output.at[idx, "ai_usluga_glowna"] = value
            elif field == "model_b2b_b2c":
                output.at[idx, "ai_model_b2b_b2c"] = value
            elif field == "new_category_flag":
                output.at[idx, "ai_new_category_flag"] = value
            elif field == "evidence":
                output.at[idx, "ai_evidence"] = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
            elif field == "manual_review":
                output.at[idx, "manual_review"] = normalize_bool(value)
            else:
                output.at[idx, field] = value
        output.at[idx, "classification_source"] = "llm"
        updated += 1

    output = output.drop(columns=["_record_key", "_domain_key", "_merge_key"])
    return output, {"updated": updated, "input_results": len(results_df)}
