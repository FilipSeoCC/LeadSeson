# -*- coding: utf-8 -*-
import pandas as pd

from matrix_gap_detector import find_matrix_gaps


def test_find_matrix_gaps_returns_pairs_missing_from_matrix():
    df = pd.DataFrame([
        {"ai_branza_glowna": "Ogrody / usługi ogrodnicze", "ai_podbranza": "Sklep i centrum ogrodnicze"},
        {"ai_branza_glowna": "Nowa Branza", "ai_podbranza": "Nowa Podbranza"},
        {"ai_branza_glowna": "Nowa Branza", "ai_podbranza": "Nowa Podbranza"},
        {"ai_branza_glowna": "", "ai_podbranza": ""},
    ])
    matrix = pd.DataFrame([
        {"branza_glowna": "Ogrody / usługi ogrodnicze", "podbranza": "Sklep i centrum ogrodnicze"},
    ])
    gaps = find_matrix_gaps(df, matrix)
    assert len(gaps) == 1
    row = gaps.iloc[0]
    assert row["branza_glowna"] == "Nowa Branza"
    assert row["podbranza"] == "Nowa Podbranza"
    assert row["liczba_domen"] == 2


def test_find_matrix_gaps_reads_rule_based_columns_too():
    df = pd.DataFrame([
        {"ai_branza_glowna": "", "ai_podbranza": "", "branza_glowna": "Regulowa Branza", "podbranza": "Regulowa Podbranza"},
    ])
    matrix = pd.DataFrame(columns=["branza_glowna", "podbranza"])
    gaps = find_matrix_gaps(df, matrix)
    assert len(gaps) == 1
    assert gaps.iloc[0]["branza_glowna"] == "Regulowa Branza"
