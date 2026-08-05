# -*- coding: utf-8 -*-
import pandas as pd

from qa_wave2_stale_filter import filter_stale


def test_filter_stale_clears_parked_domain_from_wave2():
    df = pd.DataFrame([{
        "domain_key": "zaparkowana.pl",
        "classification_source": "keyword_wave2",
        "ai_branza_glowna": "Coś", "ai_podbranza": "Coś", "ai_confidence": "60",
        "manual_review": "False",
        "title": "Domena na sprzedaż", "meta_description": "", "body_text_sample": "",
    }])
    result = filter_stale(df)
    row = result.iloc[0]
    assert row["ai_branza_glowna"] == ""
    assert row["classification_source"] == "excluded_stale_domain"
    assert row["manual_review"] == "True"


def test_filter_stale_ignores_records_outside_wave2():
    df = pd.DataFrame([{
        "domain_key": "inna-fala.pl",
        "classification_source": "google_type_mapping",
        "ai_branza_glowna": "Coś", "ai_podbranza": "Coś", "ai_confidence": "60",
        "manual_review": "False",
        "title": "Domena na sprzedaż", "meta_description": "", "body_text_sample": "",
    }])
    result = filter_stale(df)
    assert result.iloc[0]["ai_branza_glowna"] == "Coś"
