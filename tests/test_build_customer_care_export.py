# -*- coding: utf-8 -*-
import pandas as pd

from build_customer_care_export import build_customer_care_workbook


def _df():
    return pd.DataFrame([
        {
            "domain_key": "high.pl", "account_owner": "Jan Kowalski", "id": "1", "detail_id": "10",
            "nip": "111", "company": "Firma High", "monthly_value": "500",
            "branza_glowna": "Gastronomia / restauracje / eventy", "podbranza": "Restauracje",
            "ai_branza_glowna": "Gastronomia / restauracje / eventy", "ai_podbranza": "Restauracje",
            "ai_confidence": "85", "classification_confidence": "0",
            "q4_priority": "HIGH", "season_peak": "listopad, grudzień", "contact_start": "Szczyt teraz",
            "seasonality_confidence": "80", "lead_reason": "Zadzwoń teraz - sezonowy szczyt.",
        },
        {
            "domain_key": "review.pl", "account_owner": "Anna Nowak", "id": "2", "detail_id": "20",
            "nip": "222", "company": "Firma Review", "monthly_value": "200",
            "branza_glowna": "", "podbranza": "", "ai_branza_glowna": "", "ai_podbranza": "",
            "ai_confidence": "0", "classification_confidence": "0",
            "q4_priority": "DO_WERYFIKACJI", "season_peak": "", "contact_start": "",
            "seasonality_confidence": "0", "lead_reason": "",
        },
    ])


def test_workbook_has_three_sheets_with_expected_split():
    sheets = build_customer_care_workbook(_df())
    assert set(sheets.keys()) == {"Do dzwonienia", "Do weryfikacji", "Podsumowanie managera"}
    assert len(sheets["Do dzwonienia"]) == 1
    assert sheets["Do dzwonienia"].iloc[0]["domain_key"] == "high.pl"
    assert len(sheets["Do weryfikacji"]) == 1
    assert sheets["Do weryfikacji"].iloc[0]["domain_key"] == "review.pl"


def test_workbook_excludes_recommended_product_column():
    sheets = build_customer_care_workbook(_df())
    assert "recommended_product" not in sheets["Do dzwonienia"].columns


def test_manager_summary_has_owner_and_mrr_totals():
    sheets = build_customer_care_workbook(_df())
    summary = sheets["Podsumowanie managera"]
    summary_text = summary.to_string()
    assert "Jan Kowalski" in summary_text
    assert "500" in summary_text
