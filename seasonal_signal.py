# -*- coding: utf-8 -*-
from datetime import date
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"
SENUTO_MATRIX_PATH = OUTPUT_DIR / "leadseason_macierz_sezonowosci_senuto.xlsx"

MONTHS_PL = ["sty", "lut", "mar", "kwi", "maj", "cze", "lip", "sie", "wrz", "paz", "lis", "gru"]
MONTH_NAMES_PL = {
    "sty": "styczeń", "lut": "luty", "mar": "marzec", "kwi": "kwiecień", "maj": "maj", "cze": "czerwiec",
    "lip": "lipiec", "sie": "sierpień", "wrz": "wrzesień", "paz": "październik", "lis": "listopad", "gru": "grudzień",
}
QUARTER_OF_MONTH = {
    "sty": "Q1", "lut": "Q1", "mar": "Q1", "kwi": "Q2", "maj": "Q2", "cze": "Q2",
    "lip": "Q3", "sie": "Q3", "wrz": "Q3", "paz": "Q4", "lis": "Q4", "gru": "Q4",
}
QUARTER_LABELS = {
    "Q1": "Q1 (sty-mar)", "Q2": "Q2 (kwi-cze)", "Q3": "Q3 (lip-wrz)", "Q4": "Q4 (paź-gru)",
}
NIEOKRESLONA_VALUES = {"", "nieokreślona", "brak danych"}


def months_between(today, target):
    return (target.year - today.year) * 12 + (target.month - today.month)


def clean_number(value):
    text = str(value or "").strip().replace("\xa0", "").replace(" ", "")
    text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return 0.0


def load_senuto_matrix_frame():
    if not SENUTO_MATRIX_PATH.exists():
        return pd.DataFrame()
    return pd.read_excel(SENUTO_MATRIX_PATH, dtype=str, keep_default_na=False)


def build_seasonal_leads(df, matrix, today=None):
    if df.empty or matrix.empty:
        return pd.DataFrame()
    has_ai = "ai_branza_glowna" in df.columns and "ai_podbranza" in df.columns
    has_rule = "branza_glowna" in df.columns and "podbranza" in df.columns
    if not has_ai and not has_rule:
        return pd.DataFrame()

    # Matrix rows can be keyed by (branza, podbranza, usluga_glowna) once the long-tail Senuto
    # ingestion adds real usluga_glowna values, so more than one row can share a (branza, podbranza)
    # pair. Leads only carry branza+podbranza, so pick the single best row per pair deterministically
    # (OK status first, then highest confidence) instead of letting the last row seen win arbitrarily.
    matrix_candidates = {}
    for _, row in matrix.iterrows():
        key = (str(row.get("branza_glowna") or "").strip(), str(row.get("podbranza") or "").strip())
        matrix_candidates.setdefault(key, []).append(row)

    def _matrix_row_rank(row):
        try:
            confidence = float(row.get("confidence_sezonowosci") or 0)
        except (TypeError, ValueError):
            confidence = 0.0
        return (str(row.get("status", "")) == "OK", confidence)

    matrix_by_key = {
        key: max(candidates, key=_matrix_row_rank)
        for key, candidates in matrix_candidates.items()
    }

    today = today or date.today()
    current_idx = today.month - 1
    optional_cols = {
        "id": "id",
        "detail_id": "detail_id",
        "nip": "nip",
        "account_owner": "account_owner",
        "company": "company",
        "service": "service",
        "seo_basket": "seo_basket",
        "access_type": "access_type",
        "start_date": "start_date",
        "end_date": "end_date",
        "monthly_value": "monthly_value",
    }
    present = {label: col for label, col in optional_cols.items() if col in df.columns}

    end_dates = pd.to_datetime(df[present["end_date"]], errors="coerce") if "end_date" in present else None
    start_dates = pd.to_datetime(df[present["start_date"]], errors="coerce") if "start_date" in present else None
    mrr_series = df[present["monthly_value"]].map(clean_number) if "monthly_value" in present else None

    rows = []
    for pos, (_, row) in enumerate(df.iterrows()):
        ai_branza = str(row.get("ai_branza_glowna") or "").strip() if has_ai else ""
        if has_ai and ai_branza.lower() not in NIEOKRESLONA_VALUES:
            branza = ai_branza
            podbranza = str(row.get("ai_podbranza") or "").strip()
            branza_zrodlo = "LLM (zweryfikowane)"
            try:
                branza_confidence = int(float(row.get("ai_confidence") or 0))
            except (TypeError, ValueError):
                branza_confidence = 0
        elif has_rule and str(row.get("branza_glowna") or "").strip():
            branza = str(row.get("branza_glowna") or "").strip()
            podbranza = str(row.get("podbranza") or "").strip()
            branza_zrodlo = "Klasyfikator regułowy"
            try:
                branza_confidence = int(float(row.get("classification_confidence") or 0))
            except (TypeError, ValueError):
                branza_confidence = 0
        else:
            branza, podbranza, branza_zrodlo, branza_confidence = "Nieokreślona", "Nieokreślona", "Brak", 0
        key = (branza, podbranza)

        match = matrix_by_key.get(key)
        item = {label: (row.get(col) or "") for label, col in present.items() if label not in ("start_date", "end_date", "monthly_value")}
        item["domain_key"] = row.get("domain_key", "")
        item["branza_glowna"] = branza or "Nieokreślona"
        item["podbranza"] = podbranza or "Nieokreślona"
        item["branza_zrodlo"] = branza_zrodlo
        item["branza_confidence"] = branza_confidence
        item["mrr"] = float(mrr_series.iloc[pos]) if mrr_series is not None and pd.notna(mrr_series.iloc[pos]) else 0.0

        if end_dates is not None and pd.notna(end_dates.iloc[pos]):
            end_dt = end_dates.iloc[pos].date()
            item["end_date"] = end_dt.isoformat()
            item["miesiecy_do_konca_umowy"] = months_between(today, end_dt)
        else:
            item["end_date"] = ""
            item["miesiecy_do_konca_umowy"] = None
        if start_dates is not None and pd.notna(start_dates.iloc[pos]):
            item["start_date"] = start_dates.iloc[pos].date().isoformat()
        else:
            item["start_date"] = ""

        peak_months = []
        if match is not None and str(match.get("status", "")) == "OK":
            peak_raw = str(match.get("sezon_peak_miesiace") or "")
            peak_months = [m.strip() for m in peak_raw.split(",") if m.strip() in MONTHS_PL]

        if not peak_months:
            item.update({
                "sezon_peak_miesiace": "",
                "miesiecy_do_szczytu": 99,
                "okno_kontaktu": "Brak danych sezonowości",
                "czy_sezonowosc_wyrazna": "",
                "confidence_sezonowosci": 0,
                "kwartaly_szczytu": "",
            })
        else:
            peak_indices = [MONTHS_PL.index(m) for m in peak_months]
            dist = min((idx - current_idx) % 12 for idx in peak_indices)
            okno = "Szczyt teraz" if dist == 0 else ("Szczyt za miesiąc" if dist == 1 else f"Szczyt za {dist} mies.")
            wyrazna = str(match.get("czy_sezonowosc_wyrazna") or "")
            try:
                conf = int(float(match.get("confidence_sezonowosci") or 0))
            except ValueError:
                conf = 0
            kwartaly = sorted({QUARTER_OF_MONTH[m] for m in peak_months})
            item.update({
                "sezon_peak_miesiace": ", ".join(MONTH_NAMES_PL.get(m, m) for m in peak_months),
                "miesiecy_do_szczytu": dist,
                "okno_kontaktu": okno,
                "czy_sezonowosc_wyrazna": wyrazna,
                "confidence_sezonowosci": conf,
                "kwartaly_szczytu": ", ".join(kwartaly),
            })

        renewal_close = item["miesiecy_do_konca_umowy"] is not None and 0 <= item["miesiecy_do_konca_umowy"] <= 3
        season_close = item["miesiecy_do_szczytu"] <= 1
        season_ok = item["okno_kontaktu"] != "Brak danych sezonowości"
        if season_ok and season_close and renewal_close:
            item["priorytet_kontaktu"] = "Wysoki: sezon + koniec umowy"
            item["sugerowana_akcja"] = "Zadzwoń teraz — sezonowy szczyt i koniec umowy się pokrywają, dobry moment na odnowienie + upsell."
        elif season_ok and season_close:
            item["priorytet_kontaktu"] = "Sezonowy"
            item["sugerowana_akcja"] = "Zadzwoń teraz — branża wchodzi w sezonowy szczyt, zaproponuj dodatkową usługę."
        elif renewal_close:
            item["priorytet_kontaktu"] = "Odnowienie umowy"
            item["sugerowana_akcja"] = "Umowa kończy się niebawem — zaplanuj kontakt odnowieniowy."
        elif season_ok and item["czy_sezonowosc_wyrazna"] == "tak":
            item["priorytet_kontaktu"] = "Sezonowy (later)"
            item["sugerowana_akcja"] = "Zaplanuj kontakt przed nadchodzącym szczytem."
        elif not season_ok:
            item["priorytet_kontaktu"] = "Brak danych"
            item["sugerowana_akcja"] = "Brak dopasowania do sprawdzonej grupy Senuto — zweryfikuj ręcznie."
        else:
            item["priorytet_kontaktu"] = "Standardowy"
            item["sugerowana_akcja"] = "Słaby sygnał sezonowości — niski priorytet kontaktu."

        rows.append(item)

    result = pd.DataFrame(rows)
    return result.sort_values(["miesiecy_do_szczytu", "confidence_sezonowosci"], ascending=[True, False]).reset_index(drop=True)


def apply_senuto_q4_signal(df):
    # q4_priority/season_peak came from the old static google_type/industry lookup
    # (seasonality_matrix.py). Once a real Senuto seasonality matrix exists, that's the
    # trustworthy signal - override the legacy heuristic with it wherever we can match a
    # domain, instead of letting stale DO_WERYFIKACJI/HIGH values linger on screen.
    if df.empty or "domain_key" not in df.columns:
        return df
    matrix = load_senuto_matrix_frame()
    if matrix.empty:
        return df
    leads = build_seasonal_leads(df, matrix)
    if leads.empty or "domain_key" not in leads.columns:
        return df

    lookup_cols = [c for c in ["kwartaly_szczytu", "czy_sezonowosc_wyrazna", "sezon_peak_miesiace"] if c in leads.columns]
    lookup = leads.drop_duplicates("domain_key", keep="first").set_index("domain_key")[lookup_cols]

    def resolve_priority(domain):
        if domain not in lookup.index:
            return "DO_WERYFIKACJI"
        row = lookup.loc[domain]
        peak = str(row.get("sezon_peak_miesiace") or "")
        if not peak:
            return "DO_WERYFIKACJI"
        has_q4 = "Q4" in str(row.get("kwartaly_szczytu") or "")
        strong = str(row.get("czy_sezonowosc_wyrazna") or "") == "tak"
        if has_q4 and strong:
            return "HIGH"
        if has_q4:
            return "MEDIUM_HIGH"
        return "LOW_Q4"

    result = df.copy()
    result["q4_priority"] = result["domain_key"].map(resolve_priority)
    if "sezon_peak_miesiace" in lookup.columns:
        peak_map = lookup["sezon_peak_miesiace"]
        result["season_peak"] = result["domain_key"].map(lambda d: peak_map.get(d, "") if d in peak_map.index else "")
    return result
