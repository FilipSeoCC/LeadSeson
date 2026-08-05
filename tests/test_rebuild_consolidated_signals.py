# -*- coding: utf-8 -*-
import pandas as pd

from rebuild_consolidated_signals import rebuild_signals


def _matrix():
    return pd.DataFrame([{
        "branza_glowna": "Gastronomia / restauracje / eventy",
        "podbranza": "Restauracje",
        "usluga_glowna": "",
        "sezon_peak_miesiace": "lis, gru",
        "czy_sezonowosc_wyrazna": "tak",
        "confidence_sezonowosci": "80",
        "status": "OK",
    }])


def _stale_df():
    return pd.DataFrame([{
        "domain_key": "restauracja-test.pl",
        "ai_branza_glowna": "Gastronomia / restauracje / eventy",
        "ai_podbranza": "Restauracje",
        "ai_confidence": "85",
        "monthly_value": "500",
        "end_date": "",
        # symulacja STAREGO, nieaktualnego snapshotu w pliku
        "q4_priority": "DO_WERYFIKACJI",
        "season_peak": "przestarzała wartość",
        "contact_start": "przestarzała wartość",
        "seasonality_confidence": "0",
        "lead_reason": "stary, nieaktualny powód sprzed poprawki branży",
        "call_script": "stary, nieaktualny skrypt",
    }])


def test_rebuild_signals_overwrites_stale_q4_priority(monkeypatch):
    import rebuild_consolidated_signals as mod
    monkeypatch.setattr(mod.seasonal_signal, "load_senuto_matrix_frame", lambda: _matrix())
    result = rebuild_signals(_stale_df(), _matrix())
    row = result[result["domain_key"] == "restauracja-test.pl"].iloc[0]
    assert row["q4_priority"] == "HIGH"


def test_rebuild_signals_overwrites_stale_lead_reason(monkeypatch):
    import rebuild_consolidated_signals as mod
    monkeypatch.setattr(mod.seasonal_signal, "load_senuto_matrix_frame", lambda: _matrix())
    result = rebuild_signals(_stale_df(), _matrix())
    row = result[result["domain_key"] == "restauracja-test.pl"].iloc[0]
    assert row["lead_reason"] == row["call_script"]
    assert "nieaktualny" not in row["lead_reason"]
    assert row["lead_reason"] != ""


def test_rebuild_signals_leaves_recommended_product_untouched():
    df = _stale_df()
    df["recommended_product"] = "legacy produkt X"
    result = rebuild_signals(df, _matrix())
    assert result.iloc[0]["recommended_product"] == "legacy produkt X"
