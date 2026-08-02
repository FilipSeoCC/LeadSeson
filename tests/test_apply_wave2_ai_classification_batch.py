# -*- coding: utf-8 -*-
import json

import pandas as pd
import pytest

from apply_wave2_ai_classification_batch import apply_batch_to_frame


def test_apply_batch_sets_branza_for_classified_domain():
    df = pd.DataFrame([{
        "domain_key": "firma-x.pl", "ai_branza_glowna": "", "ai_podbranza": "",
        "ai_confidence": "0", "classification_source": "", "ai_evidence": "",
    }])
    corrections = {"classified": {"firma-x.pl": ["Nowa Branza", "Nowa Podbranza", 55]}, "no_signal": []}
    result = apply_batch_to_frame(df, corrections, "test_batch")
    row = result.iloc[0]
    assert row["ai_branza_glowna"] == "Nowa Branza"
    assert row["ai_confidence"] == "55"
    assert row["classification_source"] == "llm_wave2"


def test_apply_batch_marks_no_signal_domain_as_reviewed():
    df = pd.DataFrame([{
        "domain_key": "brak-sygnalu.pl", "ai_branza_glowna": "", "ai_podbranza": "",
        "ai_confidence": "0", "classification_source": "", "ai_evidence": "",
    }])
    corrections = {"classified": {}, "no_signal": ["brak-sygnalu.pl"]}
    result = apply_batch_to_frame(df, corrections, "test_batch")
    row = result.iloc[0]
    assert row["ai_branza_glowna"] == ""
    assert row["classification_source"] == "ai_reviewed_no_signal"
