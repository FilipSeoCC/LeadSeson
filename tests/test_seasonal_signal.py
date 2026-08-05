# -*- coding: utf-8 -*-
from datetime import date

import pandas as pd

import seasonal_signal
from seasonal_signal import build_seasonal_leads, apply_senuto_q4_signal


def _matrix():
    return pd.DataFrame([
        {
            "branza_glowna": "Gastronomia / restauracje / eventy",
            "podbranza": "Restauracje",
            "usluga_glowna": "",
            "sezon_peak_miesiace": "lis, gru",
            "czy_sezonowosc_wyrazna": "tak",
            "confidence_sezonowosci": "80",
            "status": "OK",
        },
        {
            "branza_glowna": "Transport / spedycja",
            "podbranza": "Transport drogowy",
            "usluga_glowna": "",
            "sezon_peak_miesiace": "",
            "czy_sezonowosc_wyrazna": "nie",
            "confidence_sezonowosci": "40",
            "status": "OK",
        },
    ])


def _df():
    return pd.DataFrame([
        {
            "domain_key": "restauracja-test.pl",
            "ai_branza_glowna": "Gastronomia / restauracje / eventy",
            "ai_podbranza": "Restauracje",
            "ai_confidence": "85",
            "monthly_value": "500",
            "end_date": "2026-12-15",
        },
        {
            "domain_key": "transport-test.pl",
            "ai_branza_glowna": "Transport / spedycja",
            "ai_podbranza": "Transport drogowy",
            "ai_confidence": "70",
            "monthly_value": "300",
            "end_date": "",
        },
        {
            "domain_key": "brak-branzy-test.pl",
            "ai_branza_glowna": "",
            "ai_podbranza": "",
            "ai_confidence": "0",
            "monthly_value": "0",
            "end_date": "",
        },
    ])


def test_build_seasonal_leads_matches_q4_peak_to_high_priority():
    leads = build_seasonal_leads(_df(), _matrix(), today=date(2026, 11, 1))
    row = leads[leads["domain_key"] == "restauracja-test.pl"].iloc[0]
    assert row["kwartaly_szczytu"] == "Q4"
    assert row["czy_sezonowosc_wyrazna"] == "tak"
    assert "Zadzwoń" in row["sugerowana_akcja"]


def test_build_seasonal_leads_no_matrix_match_is_brak_danych():
    leads = build_seasonal_leads(_df(), _matrix(), today=date(2026, 11, 1))
    row = leads[leads["domain_key"] == "transport-test.pl"].iloc[0]
    assert row["okno_kontaktu"] == "Brak danych sezonowości"


def test_apply_senuto_q4_signal_sets_high_for_strong_q4_match(monkeypatch):
    monkeypatch.setattr(seasonal_signal, "load_senuto_matrix_frame", lambda: _matrix())
    result = apply_senuto_q4_signal(_df())
    row = result[result["domain_key"] == "restauracja-test.pl"].iloc[0]
    assert row["q4_priority"] == "HIGH"


def test_apply_senuto_q4_signal_sets_do_weryfikacji_when_branza_missing(monkeypatch):
    monkeypatch.setattr(seasonal_signal, "load_senuto_matrix_frame", lambda: _matrix())
    result = apply_senuto_q4_signal(_df())
    row = result[result["domain_key"] == "brak-branzy-test.pl"].iloc[0]
    assert row["q4_priority"] == "DO_WERYFIKACJI"
