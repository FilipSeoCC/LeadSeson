import json
import re
from pathlib import Path

import pandas as pd


BASE_DIR = Path(__file__).resolve().parents[1]
OUTPUT_DIR = BASE_DIR / "output"
CACHE_DIR = BASE_DIR / ".leadseason_cache"
UPLOAD_DIR = BASE_DIR / "uploads"
JOBS_DIR = BASE_DIR / ".leadseason_jobs"
Q4_VALUES = {"HIGH", "MEDIUM_HIGH"}
BAD_SITE_HEALTH = {"FETCH_ERROR", "BLOCKED", "PLACEHOLDER", "INACTIVE", "PARKED", "NO_SIGNAL"}


def _clean_number(value):
    text = str(value or "").strip().replace("\xa0", "").replace(" ", "").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return 0.0


def _normalize_domain(value):
    text = str(value or "").strip().lower()
    text = re.sub(r"^https?://", "", text)
    text = re.sub(r"^www\.", "", text)
    return text.strip("/")


def output_files():
    if not OUTPUT_DIR.exists():
        return []
    files = [
        path for path in OUTPUT_DIR.glob("*")
        if path.suffix.lower() in {".xlsx", ".csv", ".json"} and not path.name.endswith(".summary.json")
    ]
    return sorted(files, key=lambda path: path.stat().st_mtime, reverse=True)


def default_output_file():
    files = output_files()
    if not files:
        return None
    return next((path for path in files if "pelna" in path.name.lower()), files[0])


def safe_output_path(file_name):
    if not file_name:
        return default_output_file()
    requested = Path(file_name)
    if requested.name != file_name or requested.is_absolute():
        raise ValueError("Podaj samą nazwę pliku z katalogu output.")
    path = OUTPUT_DIR / requested.name
    if not path.exists() or not path.is_file():
        raise FileNotFoundError("Nie ma takiego pliku output.")
    if path.suffix.lower() not in {".xlsx", ".csv", ".json"} or path.name.endswith(".summary.json"):
        raise ValueError("Nieobsługiwany plik output.")
    return path


def safe_input_path(input_path):
    path = Path(input_path)
    if not path.is_absolute():
        path = BASE_DIR / path
    resolved = path.resolve()
    allowed_roots = [UPLOAD_DIR.resolve(), (BASE_DIR / "templates").resolve(), BASE_DIR.resolve()]
    if not any(resolved == root or root in resolved.parents for root in allowed_roots):
        raise ValueError("Plik wejściowy musi być w katalogu projektu, uploads albo templates.")
    if not resolved.exists() or not resolved.is_file():
        raise FileNotFoundError("Plik wejściowy nie istnieje.")
    if resolved.suffix.lower() not in {".xlsx", ".xls", ".csv", ".xml"}:
        raise ValueError("Obsługiwane formaty wejścia: XLSX, XLS, CSV, XML.")
    return resolved


def load_output(path=None):
    path = Path(path) if path else default_output_file()
    if not path:
        return pd.DataFrame(), ""
    CACHE_DIR.mkdir(exist_ok=True)
    sheet = None
    if path.suffix.lower() == ".xlsx":
        workbook = pd.ExcelFile(path)
        sheet = "kategoryzacja_500" if "kategoryzacja_500" in workbook.sheet_names else workbook.sheet_names[0]

    cache_key = f"{path.stem}_{path.stat().st_mtime_ns}_{sheet or 'file'}".replace(" ", "_")
    cache_path = CACHE_DIR / f"{cache_key}.pkl"
    if cache_path.exists():
        try:
            return pd.read_pickle(cache_path), path.name
        except Exception:
            cache_path.unlink(missing_ok=True)

    if path.suffix.lower() == ".xlsx":
        df = pd.read_excel(path, sheet_name=sheet, dtype=str, keep_default_na=False)
    elif path.suffix.lower() == ".csv":
        df = pd.read_csv(path, sep=None, engine="python", dtype=str, keep_default_na=False, encoding="utf-8-sig")
    else:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if isinstance(data, dict):
            for key in ["rows", "data", "records", "items"]:
                if isinstance(data.get(key), list):
                    data = data[key]
                    break
        df = pd.DataFrame(data)
    df.to_pickle(cache_path)
    return df, path.name


def prepare_frame(df):
    data = df.copy()
    if "monthly_value" in data:
        data["_mrr_num"] = data["monthly_value"].map(_clean_number)
    elif "mrr" in data:
        data["_mrr_num"] = data["mrr"].map(_clean_number)
    else:
        data["_mrr_num"] = 0.0

    for col in ["id", "domain", "domain_key", "q4_priority", "account_owner", "detected_industry", "branza_glowna", "podbranza", "site_health_status", "crawl_status"]:
        if col not in data:
            data[col] = ""
        data[col] = data[col].fillna("").astype(str).str.strip()

    data["domain_key_clean"] = data["domain_key"].where(data["domain_key"].ne(""), data["domain"]).map(_normalize_domain)
    return data


def dashboard_summary(path=None):
    df, label = load_output(path)
    if df.empty:
        return {"source": label, "records": 0}
    data = prepare_frame(df)
    total = len(data)
    q4 = data[data["q4_priority"].isin(Q4_VALUES)]
    bad = data[data["site_health_status"].isin(BAD_SITE_HEALTH)]
    usable = data.get("usable_for_llm", pd.Series([""] * total)).astype(str).str.lower().isin(["true", "1", "tak", "yes"]).sum()
    detected = pd.to_numeric(data.get("industry_confidence", 0), errors="coerce").fillna(0).gt(0).sum() if "industry_confidence" in data else data["branza_glowna"].ne("").sum()
    return {
        "source": label,
        "records": int(total),
        "clients": int(data["id"].replace("", pd.NA).dropna().nunique()),
        "domains": int(data["domain_key_clean"].replace("", pd.NA).dropna().nunique()),
        "q4_records": int(len(q4)),
        "q4_domains": int(q4["domain_key_clean"].replace("", pd.NA).dropna().nunique()),
        "q4_high": int(q4["q4_priority"].eq("HIGH").sum()),
        "q4_medium_high": int(q4["q4_priority"].eq("MEDIUM_HIGH").sum()),
        "q4_mrr": float(q4["_mrr_num"].sum()),
        "total_mrr": float(data["_mrr_num"].sum()),
        "crawl_ok_records": int(data["crawl_status"].eq("OK").sum()),
        "usable_for_llm_records": int(usable),
        "bad_site_records": int(len(bad)),
        "industry_detected_records": int(detected),
        "review_records": int(data["q4_priority"].eq("DO_WERYFIKACJI").sum()),
    }


def q4_action_frame(path=None):
    df, _ = load_output(path)
    data = prepare_frame(df)
    if data.empty:
        return pd.DataFrame()
    q4 = data[data["q4_priority"].isin(Q4_VALUES)].copy()
    if q4.empty:
        return q4

    rank = {"HIGH": 3, "MEDIUM_HIGH": 2}
    q4["q4_rank"] = q4["q4_priority"].map(rank).fillna(0)
    q4["seasonality_confidence_num"] = pd.to_numeric(q4.get("seasonality_confidence", 0), errors="coerce").fillna(0)
    q4["classification_confidence_num"] = pd.to_numeric(q4.get("classification_confidence", 0), errors="coerce").fillna(0)
    q4["site_ok_for_action"] = q4["site_health_status"].eq("OK")
    industry_signal = q4["branza_glowna"].where(q4["branza_glowna"].ne(""), q4["detected_industry"])
    industry_norm = industry_signal.fillna("").astype(str).str.strip().str.lower()
    q4["has_industry"] = industry_norm.ne("") & ~industry_norm.isin({"nieokreślona", "nieokreslona", "brak danych", "nan"})
    q4["action_score"] = (
        q4["q4_rank"] * 30
        + q4["seasonality_confidence_num"] * 0.35
        + q4["classification_confidence_num"] * 0.25
        + q4["site_ok_for_action"].astype(int) * 8
        + q4["has_industry"].astype(int) * 7
        + q4["_mrr_num"].clip(upper=5000) / 5000 * 5
    ).round(1)

    def tier(row):
        if row["q4_priority"] == "HIGH" and row["seasonality_confidence_num"] >= 80 and row["has_industry"]:
            return "1. Dzwonić w pierwszej kolejności"
        if row["q4_priority"] == "HIGH":
            return "2. Mocny Q4, sprawdzić kontekst"
        if row["q4_priority"] == "MEDIUM_HIGH" and row["seasonality_confidence_num"] >= 70:
            return "3. Dobry kandydat Q4"
        return "4. Kandydat Q4 do walidacji"

    q4["action_tier"] = q4.apply(tier, axis=1)
    columns = [
        "action_tier", "action_score", "q4_priority", "seasonality_confidence", "season_peak", "contact_start",
        "account_owner", "company", "nip", "id", "detail_id", "domain", "domain_key", "monthly_value", "service",
        "branza_glowna", "podbranza", "usluga_glowna", "model_b2b_b2c", "classification_confidence",
        "site_health_status", "site_health_reason", "usable_for_llm", "lead_reason", "recommended_product",
        "call_script", "title", "meta_description", "final_url",
    ]
    columns = [col for col in columns if col in q4.columns]
    return q4.sort_values(["action_score", "q4_rank", "_mrr_num"], ascending=[False, False, False])[columns]


def q4_summary(path=None):
    frame = q4_action_frame(path)
    if frame.empty:
        return {"records": 0, "domains": 0, "clients": 0, "tiers": {}, "branches": []}
    branches = []
    branch_col = "branza_glowna" if "branza_glowna" in frame else "detected_industry"
    if branch_col in frame:
        grouped = frame.groupby(branch_col, dropna=False).agg(
            records=("domain", "size"),
            domains=("domain_key", "nunique"),
        ).reset_index().sort_values("records", ascending=False).head(15)
        branches = grouped.rename(columns={branch_col: "branch"}).to_dict(orient="records")
    return {
        "records": int(len(frame)),
        "domains": int(frame["domain_key"].replace("", pd.NA).dropna().nunique()) if "domain_key" in frame else 0,
        "clients": int(frame["id"].replace("", pd.NA).dropna().nunique()) if "id" in frame else 0,
        "tiers": frame["action_tier"].value_counts().to_dict() if "action_tier" in frame else {},
        "branches": branches,
    }
