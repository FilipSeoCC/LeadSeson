# -*- coding: utf-8 -*-
import pandas as pd


def find_matrix_gaps(df, matrix):
    """Pary (branza, podbranza) uzywane w df (ai_* z pierwszenstwem, potem rule-based
    branza_glowna/podbranza), ktorych nie ma w macierzy Senuto. Zwraca liczbe domen na pare,
    posortowane malejaco - do decyzji, ktore braki warto najpierw uzupelnic.
    """
    branza_col = df.get("ai_branza_glowna", pd.Series("", index=df.index)).where(
        df.get("ai_branza_glowna", pd.Series("", index=df.index)).astype(str).str.strip().ne(""),
        df.get("branza_glowna", pd.Series("", index=df.index)),
    )
    podbranza_col = df.get("ai_podbranza", pd.Series("", index=df.index)).where(
        df.get("ai_branza_glowna", pd.Series("", index=df.index)).astype(str).str.strip().ne(""),
        df.get("podbranza", pd.Series("", index=df.index)),
    )
    pairs = pd.DataFrame({"branza_glowna": branza_col, "podbranza": podbranza_col})
    pairs = pairs[(pairs["branza_glowna"].astype(str).str.strip() != "") & (pairs["podbranza"].astype(str).str.strip() != "")]

    matrix_pairs = set()
    if not matrix.empty and {"branza_glowna", "podbranza"}.issubset(matrix.columns):
        matrix_pairs = set(zip(matrix["branza_glowna"], matrix["podbranza"]))

    counts = pairs.groupby(["branza_glowna", "podbranza"]).size().reset_index(name="liczba_domen")
    counts = counts[~counts.apply(lambda r: (r["branza_glowna"], r["podbranza"]) in matrix_pairs, axis=1)]
    return counts.sort_values("liczba_domen", ascending=False).reset_index(drop=True)
