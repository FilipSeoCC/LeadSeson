# -*- coding: utf-8 -*-
import pandas as pd

from classify_keyword_wave2 import classify_pool


def test_classify_pool_fills_branza_from_keywords():
    df = pd.DataFrame([{
        "domain_key": "warsztat-tokarski.pl",
        "places_status": "OK",
        "ai_branza_glowna": "",
        "ai_podbranza": "",
        "branza_glowna": "",
        "podbranza": "",
        "title": "Zakład Tokarsko-Ślusarski - spawanie, toczenie, frezowanie",
        "meta_description": "Świadczymy usługi tokarskie i ślusarskie",
        "h1_h3": "",
        "body_text_sample": "",
    }])
    result = classify_pool(df)
    row = result.iloc[0]
    assert row["classification_source"] == "keyword_wave2"
    assert row["ai_branza_glowna"] != ""
    assert row["ai_confidence"] == "60"


def test_classify_pool_skips_records_with_existing_branza():
    df = pd.DataFrame([{
        "domain_key": "already-classified.pl",
        "places_status": "OK",
        "ai_branza_glowna": "Coś Już Ustalonego",
        "ai_podbranza": "Coś",
        "branza_glowna": "",
        "podbranza": "",
        "title": "", "meta_description": "", "h1_h3": "", "body_text_sample": "",
    }])
    result = classify_pool(df)
    assert result.iloc[0]["ai_branza_glowna"] == "Coś Już Ustalonego"
    assert result.iloc[0].get("classification_source", "") != "keyword_wave2"


def test_classify_pool_skips_records_without_places_ok():
    df = pd.DataFrame([{
        "domain_key": "not-found.pl",
        "places_status": "NOT_FOUND",
        "ai_branza_glowna": "", "ai_podbranza": "", "branza_glowna": "", "podbranza": "",
        "title": "Zakład Tokarsko-Ślusarski", "meta_description": "", "h1_h3": "", "body_text_sample": "",
    }])
    result = classify_pool(df)
    assert result.iloc[0]["ai_branza_glowna"] == ""
