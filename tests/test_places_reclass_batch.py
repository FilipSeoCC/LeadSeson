import pandas as pd

from ai_classification import eligible_for_places_reclass, build_places_reclass_batch


def test_eligible_when_places_ok_even_with_existing_branza():
    row = pd.Series({"places_status": "OK", "ai_branza_glowna": "Nieruchomości"})
    assert eligible_for_places_reclass(row) is True


def test_not_eligible_when_places_not_found():
    row = pd.Series({"places_status": "NOT_FOUND", "ai_branza_glowna": "Nieruchomości"})
    assert eligible_for_places_reclass(row) is False


def test_not_eligible_when_places_status_missing():
    row = pd.Series({"ai_branza_glowna": "Nieruchomości"})
    assert eligible_for_places_reclass(row) is False


def test_build_batch_includes_places_evidence_and_instructions():
    df = pd.DataFrame([{
        "id": "1", "detail_id": "1", "domain_key": "higienika.eu", "company": "",
        "places_status": "OK", "places_name": "Firma sprzątająca Higienika",
        "places_primary_type": "service", "places_address": "Zawieprzycka 8/L, Lublin",
        "places_match_confidence": "100", "places_match_reasons": "domain,name,primaryType",
        "ai_branza_glowna": "Nieruchomości", "ai_podbranza": "Biuro nieruchomości",
    }])
    batch = build_places_reclass_batch(df, limit=10, start=0)
    assert len(batch) == 1
    item = batch[0]
    assert item["task"] == "classify_leadseason_industry_places_first"
    assert "Places" in item["instructions"]
    assert item["context"]["places_name"] == "Firma sprzątająca Higienika"
    assert item["context"]["places_address"] == "Zawieprzycka 8/L, Lublin"
    assert item["expected_output_schema"]["branza_glowna"] == "string"


def test_build_batch_respects_limit_and_start():
    rows = [
        {"id": str(i), "detail_id": str(i), "domain_key": f"d{i}.pl", "places_status": "OK"}
        for i in range(5)
    ]
    df = pd.DataFrame(rows)
    batch = build_places_reclass_batch(df, limit=2, start=1)
    assert [item["record_key"] for item in batch] == ["1|1|d1.pl", "2|2|d2.pl"]


def test_build_batch_excludes_not_found():
    df = pd.DataFrame([
        {"id": "1", "detail_id": "1", "domain_key": "ok.pl", "places_status": "OK"},
        {"id": "2", "detail_id": "2", "domain_key": "missing.pl", "places_status": "NOT_FOUND"},
    ])
    batch = build_places_reclass_batch(df, limit=10, start=0)
    assert [item["record_key"] for item in batch] == ["1|1|ok.pl"]
