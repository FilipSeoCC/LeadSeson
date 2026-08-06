"""Senuto seasonality matrix loader.

STRATEGIA_SYSTEM_POZYSKIWANIA_LEADOW.md sekcja 2 zaklada "Senuto API/MCP -- juz
podpiete". W praktyce ten MCP connector wymaga autoryzacji per-user (patrz
system prompt tej sesji) i tak czy inaczej ten repo's istniejaca integracja
Senuto jest Claude-w-petli, nie skryptowalnym REST clientem: bulk_app.py's
"Zasilenie danych -> Sezonowosc" widok uruchamia SENUTO_MCP_PROMPT recznie w
sesji Claude Code i zapisuje wynik do output/leadseason_macierz_sezonowosci_
senuto.xlsx (patrz bulk_app.py:SENUTO_MATRIX_PATH). Zamiast duplikowac ten
auth-gated flow, ten modul czyta juz istniejacy plik z tego workflow.

Jesli plik nie istnieje, oznacza to ze workflow z bulk_app.py nie zostal
jeszcze uruchomiony dla biezacej bazy klientow -- nie blad, brak sygnalu.
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from seasonality_matrix import normalize_key  # noqa: E402

DEFAULT_MATRIX_PATH = Path(__file__).resolve().parent.parent.parent / "output" / "leadseason_macierz_sezonowosci_senuto.xlsx"


def load_senuto_row_for_industry(detected_industry: str, matrix_path: Path = DEFAULT_MATRIX_PATH) -> dict | None:
    """Look up the Senuto seasonality matrix row for a given industry/group.

    Returns None if the matrix hasn't been built yet or the industry has no
    matched row -- caller should treat that as "no Senuto signal available"
    (the matrix's own BRAK_DANYCH convention), not an error.
    """
    if not detected_industry or not matrix_path.exists():
        return None
    df = pd.read_excel(matrix_path, dtype=str, keep_default_na=False)
    match_col = next((c for c in ("branza_glowna", "ai_branza_glowna") if c in df.columns), None)
    if match_col is None:
        return None
    # normalize_key() (not a bare .strip().lower()) so Polish-diacritic
    # differences between this industry string and the matrix's own spelling
    # -- two independently-produced values (crawler taxonomy vs. manual
    # Senuto workflow) -- don't silently fail to match.
    needle = normalize_key(detected_industry)
    matches = df[df[match_col].apply(normalize_key) == needle]
    if matches.empty:
        return None
    return matches.iloc[0].to_dict()
