# Domknięcie pokrycia bazy i kanoniczny eksport Customer Care — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Podnieść pokrycie bazy klientów (branża + sezonowość) z 41.8% do 70-80%, naprawić rozjazd między tym, co Streamlit liczy na żywo i tym, co backend/API czyta ze statycznego pliku, i wydać jeden plik XLSX, który realnie można dać opiekunom Customer Care.

**Architecture:** Wydzielić logikę liczenia sygnału sezonowego (`build_seasonal_leads`/`apply_senuto_q4_signal`) z `bulk_app.py` do wspólnego modułu `seasonal_signal.py`, dodać skrypt przeliczający i nadpisujący statyczne kolumny w skonsolidowanym pliku (`rebuild_consolidated_signals.py`), rozszerzyć pokrycie klasyfikacji przez falę keyword+AI na puli rekordów bez branży, i zbudować jeden wspólny moduł eksportu XLSX (`build_customer_care_export.py`) używany i przez Streamlit, i przez FastAPI.

**Tech Stack:** Python 3, pandas, openpyxl, Streamlit, FastAPI, pytest (nowa zależność deweloperska — repo nie miało dotąd testów).

## Global Constraints

- Skonsolidowany plik bazy: `output/leadseason_pelna_baza_zeszyt2_consolidated.xlsx` — czytany/zapisywany z `dtype=str, keep_default_na=False` (spójnie z istniejącymi skryptami `apply_manual_review_batch.py`, `qa_layer1_crosscheck.py`).
- Macierz Senuto: `output/leadseason_macierz_sezonowosci_senuto.xlsx`.
- Klucz łączenia rekordów: kolumna `domain_key` (string, dokładne dopasowanie — nie normalizować domeny w tym planie, istniejący kod już tak robi).
- Branża/podbranża wybierana wg istniejącej reguły: `ai_branza_glowna`/`ai_podbranza` ma pierwszeństwo (jeśli niepuste i nie w `NIEOKRESLONA_VALUES`), inaczej `branza_glowna`/`podbranza` (klasyfikator regułowy). Ta reguła już istnieje w `build_seasonal_leads` — nie zmieniać jej semantyki, tylko przenieść.
- Nowe pliki Python w stylu istniejących skryptów repo: `# -*- coding: utf-8 -*-` nagłówek, `BASE_DIR = Path(__file__).resolve().parent`, brak zależności od Streamlit/FastAPI w logice czysto-danych.
- `lead_reason` i `call_script` w tym planie dostają **identyczną** treść z `sugerowana_akcja` (nie ma dziś osobnego generatora treści rozmowy) — to świadome uproszczenie, udokumentowane w kodzie komentarzem, docelowo do zastąpienia w osobnej specyfikacji o logice upsell.
- Kolumna `recommended_product` **nie jest** przeliczana w tym planie (legacy, poza zakresem) i **nie wchodzi** do eksportu dla opiekunów — pokazywanie nieaktualnej rekomendacji obok świeżo przeliczonego powodu kontaktu byłoby mylące.

---

## Milestone 1 — Kanoniczny pipeline sygnału sezonowego (Stream B)

Ships independently: po tym milestone `q4_priority`/`season_peak`/`contact_start`/`seasonality_confidence`/`lead_reason`/`call_script` w pliku są zawsze świeże, i istnieje jeden eksport XLSX używany wspólnie przez Streamlit i backend — działa nawet bez Milestone 2.

### Task 1: Wydzielenie `seasonal_signal.py` z `bulk_app.py`

**Files:**
- Create: `seasonal_signal.py` (root repo)
- Modify: `bulk_app.py:38` (usunąć definicję `SENUTO_MATRIX_PATH`, zaimportować), `bulk_app.py:960-978` (usunąć stałe, zaimportować), `bulk_app.py:981-1133` (usunąć `build_seasonal_leads`, zaimportować), `bulk_app.py:1706-1712` (usunąć `clean_number`, zaimportować), `bulk_app.py:2070-2107` (usunąć `apply_senuto_q4_signal`, zaimportować), `bulk_app.py:2654-2657` (usunąć `load_senuto_matrix_frame`, zaimportować)
- Test: `tests/test_seasonal_signal.py`

**Interfaces:**
- Produces: `seasonal_signal.py` eksportuje: `MONTHS_PL`, `MONTH_NAMES_PL`, `QUARTER_OF_MONTH`, `QUARTER_LABELS`, `NIEOKRESLONA_VALUES`, `SENUTO_MATRIX_PATH`, `clean_number(value) -> float`, `months_between(today, target) -> int`, `load_senuto_matrix_frame() -> pd.DataFrame`, `build_seasonal_leads(df, matrix, today=None) -> pd.DataFrame`, `apply_senuto_q4_signal(df) -> pd.DataFrame`. Wszystkie kolejne taski w tym planie importują z tego modułu.

To jest czyste przeniesienie kodu — logika `build_seasonal_leads`/`apply_senuto_q4_signal` (widziana w `bulk_app.py:981-1133` i `bulk_app.py:2070-2107`) zostaje bajt w bajt taka sama, tylko zmienia plik.

- [ ] **Step 1: Dodać pytest do zależności deweloperskich**

Repo nie ma dziś żadnych testów ani pytest. Dodać na końcu `requirements.txt`:

```text
pytest
```

Zainstalować:

```bash
pip install pytest
```

- [ ] **Step 2: Napisać nieprzechodzący test na `build_seasonal_leads`**

Utworzyć `tests/test_seasonal_signal.py`:

```python
# -*- coding: utf-8 -*-
from datetime import date

import pandas as pd

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


def test_apply_senuto_q4_signal_sets_high_for_strong_q4_match():
    result = apply_senuto_q4_signal(_df())
    row = result[result["domain_key"] == "restauracja-test.pl"].iloc[0]
    assert row["q4_priority"] == "HIGH"


def test_apply_senuto_q4_signal_sets_do_weryfikacji_when_branza_missing():
    result = apply_senuto_q4_signal(_df())
    row = result[result["domain_key"] == "brak-branzy-test.pl"].iloc[0]
    assert row["q4_priority"] == "DO_WERYFIKACJI"
```

Uwaga: `apply_senuto_q4_signal` w obecnym kodzie woła `load_senuto_matrix_frame()` (czyta z dysku), więc powyższy test na `apply_senuto_q4_signal` wymaga tymczasowej podmiany — patrz Step 3.

- [ ] **Step 3: Uruchomić test i potwierdzić, że pada (moduł jeszcze nie istnieje)**

Run: `pytest tests/test_seasonal_signal.py -v`
Expected: FAIL z `ModuleNotFoundError: No module named 'seasonal_signal'`

- [ ] **Step 4: Utworzyć `seasonal_signal.py`, przenosząc kod bez zmian semantyki**

```python
# -*- coding: utf-8 -*-
from datetime import date
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"
SENUTO_MATRIX_PATH = OUTPUT_DIR / "leadseason_macierz_sezonowosci_senuto.xlsx"

MONTHS_PL = ["sty", "lut", "mar", "kwi", "maj", "cze", "lip", "sie", "wrz", "paz", "lis", "gru"]
MONTH_NAMES_PL = {
    "sty": "styczeń", "lut": "luty", "mar": "marzec", "kwi": "kwiecień", "maj": "maj", "cze": "czerwiec",
    "lip": "lipiec", "sie": "sierpień", "wrz": "wrzesień", "paz": "październik", "lis": "listopad", "gru": "grudzień",
}
QUARTER_OF_MONTH = {
    "sty": "Q1", "lut": "Q1", "mar": "Q1", "kwi": "Q2", "maj": "Q2", "cze": "Q2",
    "lip": "Q3", "sie": "Q3", "wrz": "Q3", "paz": "Q4", "lis": "Q4", "gru": "Q4",
}
QUARTER_LABELS = {
    "Q1": "Q1 (sty-mar)", "Q2": "Q2 (kwi-cze)", "Q3": "Q3 (lip-wrz)", "Q4": "Q4 (paź-gru)",
}
NIEOKRESLONA_VALUES = {"", "nieokreślona", "brak danych"}


def months_between(today, target):
    return (target.year - today.year) * 12 + (target.month - today.month)


def clean_number(value):
    text = str(value or "").strip().replace("\xa0", "").replace(" ", "")
    text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return 0.0


def load_senuto_matrix_frame():
    if not SENUTO_MATRIX_PATH.exists():
        return pd.DataFrame()
    return pd.read_excel(SENUTO_MATRIX_PATH, dtype=str, keep_default_na=False)


def build_seasonal_leads(df, matrix, today=None):
    if df.empty or matrix.empty:
        return pd.DataFrame()
    has_ai = "ai_branza_glowna" in df.columns and "ai_podbranza" in df.columns
    has_rule = "branza_glowna" in df.columns and "podbranza" in df.columns
    if not has_ai and not has_rule:
        return pd.DataFrame()

    # Matrix rows can be keyed by (branza, podbranza, usluga_glowna) once the long-tail Senuto
    # ingestion adds real usluga_glowna values, so more than one row can share a (branza, podbranza)
    # pair. Leads only carry branza+podbranza, so pick the single best row per pair deterministically
    # (OK status first, then highest confidence) instead of letting the last row seen win arbitrarily.
    matrix_candidates = {}
    for _, row in matrix.iterrows():
        key = (str(row.get("branza_glowna") or "").strip(), str(row.get("podbranza") or "").strip())
        matrix_candidates.setdefault(key, []).append(row)

    def _matrix_row_rank(row):
        try:
            confidence = float(row.get("confidence_sezonowosci") or 0)
        except (TypeError, ValueError):
            confidence = 0.0
        return (str(row.get("status", "")) == "OK", confidence)

    matrix_by_key = {
        key: max(candidates, key=_matrix_row_rank)
        for key, candidates in matrix_candidates.items()
    }

    today = today or date.today()
    current_idx = today.month - 1
    optional_cols = {
        "id": "id",
        "detail_id": "detail_id",
        "nip": "nip",
        "account_owner": "account_owner",
        "company": "company",
        "service": "service",
        "seo_basket": "seo_basket",
        "access_type": "access_type",
        "start_date": "start_date",
        "end_date": "end_date",
        "monthly_value": "monthly_value",
    }
    present = {label: col for label, col in optional_cols.items() if col in df.columns}

    end_dates = pd.to_datetime(df[present["end_date"]], errors="coerce") if "end_date" in present else None
    start_dates = pd.to_datetime(df[present["start_date"]], errors="coerce") if "start_date" in present else None
    mrr_series = df[present["monthly_value"]].map(clean_number) if "monthly_value" in present else None

    rows = []
    for pos, (_, row) in enumerate(df.iterrows()):
        ai_branza = str(row.get("ai_branza_glowna") or "").strip() if has_ai else ""
        if has_ai and ai_branza.lower() not in NIEOKRESLONA_VALUES:
            branza = ai_branza
            podbranza = str(row.get("ai_podbranza") or "").strip()
            branza_zrodlo = "LLM (zweryfikowane)"
            try:
                branza_confidence = int(float(row.get("ai_confidence") or 0))
            except (TypeError, ValueError):
                branza_confidence = 0
        elif has_rule and str(row.get("branza_glowna") or "").strip():
            branza = str(row.get("branza_glowna") or "").strip()
            podbranza = str(row.get("podbranza") or "").strip()
            branza_zrodlo = "Klasyfikator regułowy"
            try:
                branza_confidence = int(float(row.get("classification_confidence") or 0))
            except (TypeError, ValueError):
                branza_confidence = 0
        else:
            branza, podbranza, branza_zrodlo, branza_confidence = "Nieokreślona", "Nieokreślona", "Brak", 0
        key = (branza, podbranza)

        match = matrix_by_key.get(key)
        item = {label: (row.get(col) or "") for label, col in present.items() if label not in ("start_date", "end_date", "monthly_value")}
        item["domain_key"] = row.get("domain_key", "")
        item["branza_glowna"] = branza or "Nieokreślona"
        item["podbranza"] = podbranza or "Nieokreślona"
        item["branza_zrodlo"] = branza_zrodlo
        item["branza_confidence"] = branza_confidence
        item["mrr"] = float(mrr_series.iloc[pos]) if mrr_series is not None and pd.notna(mrr_series.iloc[pos]) else 0.0

        if end_dates is not None and pd.notna(end_dates.iloc[pos]):
            end_dt = end_dates.iloc[pos].date()
            item["end_date"] = end_dt.isoformat()
            item["miesiecy_do_konca_umowy"] = months_between(today, end_dt)
        else:
            item["end_date"] = ""
            item["miesiecy_do_konca_umowy"] = None
        if start_dates is not None and pd.notna(start_dates.iloc[pos]):
            item["start_date"] = start_dates.iloc[pos].date().isoformat()
        else:
            item["start_date"] = ""

        peak_months = []
        if match is not None and str(match.get("status", "")) == "OK":
            peak_raw = str(match.get("sezon_peak_miesiace") or "")
            peak_months = [m.strip() for m in peak_raw.split(",") if m.strip() in MONTHS_PL]

        if not peak_months:
            item.update({
                "sezon_peak_miesiace": "",
                "miesiecy_do_szczytu": 99,
                "okno_kontaktu": "Brak danych sezonowości",
                "czy_sezonowosc_wyrazna": "",
                "confidence_sezonowosci": 0,
                "kwartaly_szczytu": "",
            })
        else:
            peak_indices = [MONTHS_PL.index(m) for m in peak_months]
            dist = min((idx - current_idx) % 12 for idx in peak_indices)
            okno = "Szczyt teraz" if dist == 0 else ("Szczyt za miesiąc" if dist == 1 else f"Szczyt za {dist} mies.")
            wyrazna = str(match.get("czy_sezonowosc_wyrazna") or "")
            try:
                conf = int(float(match.get("confidence_sezonowosci") or 0))
            except ValueError:
                conf = 0
            kwartaly = sorted({QUARTER_OF_MONTH[m] for m in peak_months})
            item.update({
                "sezon_peak_miesiace": ", ".join(MONTH_NAMES_PL.get(m, m) for m in peak_months),
                "miesiecy_do_szczytu": dist,
                "okno_kontaktu": okno,
                "czy_sezonowosc_wyrazna": wyrazna,
                "confidence_sezonowosci": conf,
                "kwartaly_szczytu": ", ".join(kwartaly),
            })

        renewal_close = item["miesiecy_do_konca_umowy"] is not None and 0 <= item["miesiecy_do_konca_umowy"] <= 3
        season_close = item["miesiecy_do_szczytu"] <= 1
        season_ok = item["okno_kontaktu"] != "Brak danych sezonowości"
        if season_ok and season_close and renewal_close:
            item["priorytet_kontaktu"] = "Wysoki: sezon + koniec umowy"
            item["sugerowana_akcja"] = "Zadzwoń teraz — sezonowy szczyt i koniec umowy się pokrywają, dobry moment na odnowienie + upsell."
        elif season_ok and season_close:
            item["priorytet_kontaktu"] = "Sezonowy"
            item["sugerowana_akcja"] = "Zadzwoń teraz — branża wchodzi w sezonowy szczyt, zaproponuj dodatkową usługę."
        elif renewal_close:
            item["priorytet_kontaktu"] = "Odnowienie umowy"
            item["sugerowana_akcja"] = "Umowa kończy się niebawem — zaplanuj kontakt odnowieniowy."
        elif season_ok and item["czy_sezonowosc_wyrazna"] == "tak":
            item["priorytet_kontaktu"] = "Sezonowy (later)"
            item["sugerowana_akcja"] = "Zaplanuj kontakt przed nadchodzącym szczytem."
        elif not season_ok:
            item["priorytet_kontaktu"] = "Brak danych"
            item["sugerowana_akcja"] = "Brak dopasowania do sprawdzonej grupy Senuto — zweryfikuj ręcznie."
        else:
            item["priorytet_kontaktu"] = "Standardowy"
            item["sugerowana_akcja"] = "Słaby sygnał sezonowości — niski priorytet kontaktu."

        rows.append(item)

    result = pd.DataFrame(rows)
    return result.sort_values(["miesiecy_do_szczytu", "confidence_sezonowosci"], ascending=[True, False]).reset_index(drop=True)


def apply_senuto_q4_signal(df):
    # q4_priority/season_peak came from the old static google_type/industry lookup
    # (seasonality_matrix.py). Once a real Senuto seasonality matrix exists, that's the
    # trustworthy signal - override the legacy heuristic with it wherever we can match a
    # domain, instead of letting stale DO_WERYFIKACJI/HIGH values linger on screen.
    if df.empty or "domain_key" not in df.columns:
        return df
    matrix = load_senuto_matrix_frame()
    if matrix.empty:
        return df
    leads = build_seasonal_leads(df, matrix)
    if leads.empty or "domain_key" not in leads.columns:
        return df

    lookup_cols = [c for c in ["kwartaly_szczytu", "czy_sezonowosc_wyrazna", "sezon_peak_miesiace"] if c in leads.columns]
    lookup = leads.drop_duplicates("domain_key", keep="first").set_index("domain_key")[lookup_cols]

    def resolve_priority(domain):
        if domain not in lookup.index:
            return "DO_WERYFIKACJI"
        row = lookup.loc[domain]
        peak = str(row.get("sezon_peak_miesiace") or "")
        if not peak:
            return "DO_WERYFIKACJI"
        has_q4 = "Q4" in str(row.get("kwartaly_szczytu") or "")
        strong = str(row.get("czy_sezonowosc_wyrazna") or "") == "tak"
        if has_q4 and strong:
            return "HIGH"
        if has_q4:
            return "MEDIUM_HIGH"
        return "LOW_Q4"

    result = df.copy()
    result["q4_priority"] = result["domain_key"].map(resolve_priority)
    if "sezon_peak_miesiace" in lookup.columns:
        peak_map = lookup["sezon_peak_miesiace"]
        result["season_peak"] = result["domain_key"].map(lambda d: peak_map.get(d, "") if d in peak_map.index else "")
    return result
```

- [ ] **Step 5: Podmienić w teście `apply_senuto_q4_signal`, żeby nie czytał macierzy z dysku**

W `tests/test_seasonal_signal.py` dodać na górze `import seasonal_signal` i w obu testach `test_apply_senuto_q4_signal_*` podmienić `load_senuto_matrix_frame` przez `monkeypatch`:

```python
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
```

- [ ] **Step 6: Uruchomić testy i potwierdzić, że przechodzą**

Run: `pytest tests/test_seasonal_signal.py -v`
Expected: 4 PASSED

- [ ] **Step 7: Zaktualizować `bulk_app.py`, żeby importował z `seasonal_signal.py` zamiast definiować lokalnie**

W `bulk_app.py` po istniejącym imporcie `from seasonality_matrix import enrich_with_seasonality` (linia 21) dodać:

```python
from seasonal_signal import (
    MONTHS_PL,
    MONTH_NAMES_PL,
    QUARTER_OF_MONTH,
    QUARTER_LABELS,
    NIEOKRESLONA_VALUES,
    SENUTO_MATRIX_PATH,
    clean_number,
    months_between,
    load_senuto_matrix_frame,
    build_seasonal_leads,
    apply_senuto_q4_signal,
)
```

Usunąć z `bulk_app.py`:
- linię 38 (`SENUTO_MATRIX_PATH = OUTPUT_DIR / ...`),
- bloki 960-978 (stałe miesięcy/kwartałów + `NIEOKRESLONA_VALUES`),
- funkcję `build_seasonal_leads` (981-1133),
- funkcję `clean_number` (1706-1712),
- funkcję `apply_senuto_q4_signal` (2070-2107),
- funkcję `load_senuto_matrix_frame` (2654-2657).

- [ ] **Step 8: Ręcznie zweryfikować, że `bulk_app.py` nadal się importuje bez błędu**

Run: `python -c "import ast; ast.parse(open('bulk_app.py', encoding='utf-8').read())"`
Expected: brak błędu (walidacja składni bez odpalania Streamlit).

- [ ] **Step 9: Odpalić Streamlit i sprawdzić dashboard ręcznie**

Run: `START_BULK_APP.bat` (lub `streamlit run bulk_app.py`), otworzyć `http://localhost:8510`, wejść w "Dashboard" — liczby `q4_priority`/HIGH/MEDIUM_HIGH muszą wyglądać tak samo jak przed refaktorem (żadna literka logiki się nie zmieniła, tylko lokalizacja kodu).

- [ ] **Step 10: Commit**

```bash
git add seasonal_signal.py bulk_app.py tests/test_seasonal_signal.py requirements.txt
git commit -m "refactor: extract seasonal signal logic into seasonal_signal.py"
```

---

### Task 2: `rebuild_consolidated_signals.py` — przeliczenie i nadpisanie statycznych kolumn

**Files:**
- Create: `rebuild_consolidated_signals.py` (root repo)
- Test: `tests/test_rebuild_consolidated_signals.py`

**Interfaces:**
- Consumes: `seasonal_signal.build_seasonal_leads(df, matrix)`, `seasonal_signal.apply_senuto_q4_signal(df)` z Task 1.
- Produces: `rebuild_signals(df: pd.DataFrame, matrix: pd.DataFrame) -> pd.DataFrame` — czysta funkcja bez I/O, używana też przez Task 4 (eksport) i przez CLI `main()` w tym samym pliku. Nadpisuje w zwracanym df kolumny: `q4_priority`, `season_peak`, `contact_start`, `seasonality_confidence`, `lead_reason`, `call_script`.

- [ ] **Step 1: Napisać nieprzechodzący test**

Utworzyć `tests/test_rebuild_consolidated_signals.py`:

```python
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
```

- [ ] **Step 2: Uruchomić i potwierdzić fail**

Run: `pytest tests/test_rebuild_consolidated_signals.py -v`
Expected: FAIL z `ModuleNotFoundError: No module named 'rebuild_consolidated_signals'`

- [ ] **Step 3: Napisać `rebuild_consolidated_signals.py`**

```python
# -*- coding: utf-8 -*-
from pathlib import Path

import pandas as pd

import seasonal_signal
from seasonal_signal import apply_senuto_q4_signal, build_seasonal_leads

BASE_DIR = Path(__file__).resolve().parent
CONSOLIDATED_PATH = BASE_DIR / "output" / "leadseason_pelna_baza_zeszyt2_consolidated.xlsx"

STATIC_SIGNAL_COLUMNS = [
    "q4_priority", "season_peak", "contact_start",
    "seasonality_confidence", "lead_reason", "call_script",
]


def rebuild_signals(df, matrix):
    """Przelicza q4_priority/season_peak na żywo (apply_senuto_q4_signal) i dokłada
    contact_start/seasonality_confidence/lead_reason/call_script z tego samego przebiegu
    build_seasonal_leads, nadpisując wszelkie stare, statyczne wartości w df.

    lead_reason i call_script dostają identyczną treść z sugerowana_akcja - nie ma dziś
    osobnego generatora treści rozmowy (patrz Global Constraints w planie). recommended_product
    jest świadomie NIE dotykane - poza zakresem tego kroku.
    """
    for col in STATIC_SIGNAL_COLUMNS:
        if col not in df.columns:
            df[col] = ""

    result = apply_senuto_q4_signal(df)

    leads = build_seasonal_leads(df, matrix)
    if leads.empty or "domain_key" not in leads.columns:
        return result

    lookup = leads.drop_duplicates("domain_key", keep="first").set_index("domain_key")

    def _lookup(domain, column, default=""):
        if domain not in lookup.index:
            return default
        return lookup.loc[domain, column]

    result["contact_start"] = result["domain_key"].map(lambda d: _lookup(d, "okno_kontaktu"))
    result["seasonality_confidence"] = result["domain_key"].map(lambda d: _lookup(d, "confidence_sezonowosci", 0))
    result["lead_reason"] = result["domain_key"].map(lambda d: _lookup(d, "sugerowana_akcja"))
    result["call_script"] = result["lead_reason"]
    return result


def main():
    df = pd.read_excel(CONSOLIDATED_PATH, dtype=str, keep_default_na=False)
    matrix = seasonal_signal.load_senuto_matrix_frame()

    before_counts = df["q4_priority"].value_counts().to_dict() if "q4_priority" in df.columns else {}
    result = rebuild_signals(df, matrix)
    after_counts = result["q4_priority"].value_counts().to_dict()

    result.to_excel(CONSOLIDATED_PATH, index=False)

    print("q4_priority PRZED:", before_counts)
    print("q4_priority PO:   ", after_counts)
    print(f"Zapisano {CONSOLIDATED_PATH.name}.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Uruchomić testy i potwierdzić, że przechodzą**

Run: `pytest tests/test_rebuild_consolidated_signals.py -v`
Expected: 3 PASSED

- [ ] **Step 5: Uruchomić na prawdziwej bazie i sprawdzić podsumowanie**

Run: `python rebuild_consolidated_signals.py`
Expected: wypisane dwa słowniki `q4_priority PRZED`/`PO` — PRZED powinno pokazać stary rozkład (sprzed dzisiejszych 483 poprawek), PO powinno pokazać HIGH=3238, MEDIUM_HIGH=324, LOW_Q4=378, DO_WERYFIKACJI=5481 (te same liczby, które wyliczyłeś ręcznie po dzisiejszym QA — to jest dowód, że skrypt odtwarza znany, zweryfikowany wynik).

- [ ] **Step 6: Commit**

```bash
git add rebuild_consolidated_signals.py tests/test_rebuild_consolidated_signals.py
git commit -m "feat: add rebuild_consolidated_signals.py to refresh stale q4/season columns"
```

---

### Task 3: `matrix_gap_detector.py` — wspólny, testowalny helper do wykrywania brakujących kategorii w macierzy Senuto

**Files:**
- Create: `matrix_gap_detector.py` (root repo)
- Test: `tests/test_matrix_gap_detector.py`

**Interfaces:**
- Produces: `find_matrix_gaps(df: pd.DataFrame, matrix: pd.DataFrame) -> pd.DataFrame` z kolumnami `branza_glowna`, `podbranza`, `liczba_domen` — używane w Task 9 (Milestone 2) i w każdym przyszłym uzupełnieniu macierzy, zamiast pisać ten sam pandasowy fragment ad hoc za każdym razem (tak jak dziś w `add_matrix_gaps.py`/`add_new_senuto_categories.py`).

- [ ] **Step 1: Napisać nieprzechodzący test**

Utworzyć `tests/test_matrix_gap_detector.py`:

```python
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
```

- [ ] **Step 2: Uruchomić i potwierdzić fail**

Run: `pytest tests/test_matrix_gap_detector.py -v`
Expected: FAIL z `ModuleNotFoundError: No module named 'matrix_gap_detector'`

- [ ] **Step 3: Napisać `matrix_gap_detector.py`**

```python
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
```

- [ ] **Step 4: Uruchomić testy i potwierdzić, że przechodzą**

Run: `pytest tests/test_matrix_gap_detector.py -v`
Expected: 2 PASSED

- [ ] **Step 5: Commit**

```bash
git add matrix_gap_detector.py tests/test_matrix_gap_detector.py
git commit -m "feat: add reusable matrix_gap_detector helper"
```

---

### Task 4: `build_customer_care_export.py` — wspólny moduł eksportu XLSX (3 arkusze)

**Files:**
- Create: `build_customer_care_export.py` (root repo)
- Test: `tests/test_build_customer_care_export.py`

**Interfaces:**
- Consumes: df ze świeżo przeliczonymi kolumnami z Task 2 (`q4_priority`, `season_peak`, `contact_start`, `seasonality_confidence`, `lead_reason`).
- Produces: `build_customer_care_workbook(df: pd.DataFrame) -> dict[str, pd.DataFrame]` z kluczami `"Do dzwonienia"`, `"Do weryfikacji"`, `"Podsumowanie managera"` — używane przez Task 5 (Streamlit + backend).

- [ ] **Step 1: Napisać nieprzechodzący test**

Utworzyć `tests/test_build_customer_care_export.py`:

```python
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
```

- [ ] **Step 2: Uruchomić i potwierdzić fail**

Run: `pytest tests/test_build_customer_care_export.py -v`
Expected: FAIL z `ModuleNotFoundError: No module named 'build_customer_care_export'`

- [ ] **Step 3: Napisać `build_customer_care_export.py`**

```python
# -*- coding: utf-8 -*-
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
CONSOLIDATED_PATH = BASE_DIR / "output" / "leadseason_pelna_baza_zeszyt2_consolidated.xlsx"
EXPORT_PATH = BASE_DIR / "output" / "leadseason_customer_care_export.xlsx"

READY_PRIORITIES = {"HIGH", "MEDIUM_HIGH", "LOW_Q4"}

DO_DZWONIENIA_COLUMNS = [
    "account_owner", "id", "detail_id", "nip", "company", "domain_key", "monthly_value",
    "branza_glowna", "podbranza", "q4_priority", "season_peak", "contact_start",
    "lead_reason", "call_script", "effective_confidence",
]
DO_WERYFIKACJI_COLUMNS = [
    "account_owner", "id", "detail_id", "nip", "company", "domain_key", "monthly_value",
    "q4_priority", "classification_source",
]


def _effective_branza(df):
    ai = df.get("ai_branza_glowna", pd.Series("", index=df.index)).astype(str).str.strip()
    rule = df.get("branza_glowna", pd.Series("", index=df.index)).astype(str).str.strip()
    return ai.where(ai.ne(""), rule)


def _effective_podbranza(df):
    ai = df.get("ai_branza_glowna", pd.Series("", index=df.index)).astype(str).str.strip()
    ai_pod = df.get("ai_podbranza", pd.Series("", index=df.index)).astype(str)
    rule_pod = df.get("podbranza", pd.Series("", index=df.index)).astype(str)
    return ai_pod.where(ai.ne(""), rule_pod)


def _effective_confidence(df):
    ai = df.get("ai_branza_glowna", pd.Series("", index=df.index)).astype(str).str.strip()
    ai_conf = pd.to_numeric(df.get("ai_confidence", pd.Series(0, index=df.index)), errors="coerce").fillna(0)
    rule_conf = pd.to_numeric(df.get("classification_confidence", pd.Series(0, index=df.index)), errors="coerce").fillna(0)
    return ai_conf.where(ai.ne(""), rule_conf)


def build_customer_care_workbook(df):
    work = df.copy()
    work["branza_glowna"] = _effective_branza(work)
    work["podbranza"] = _effective_podbranza(work)
    work["effective_confidence"] = _effective_confidence(work)
    work["call_script"] = work.get("call_script", work.get("lead_reason", ""))
    work["_mrr_num"] = pd.to_numeric(work.get("monthly_value", pd.Series(0, index=work.index)), errors="coerce").fillna(0)

    ready_mask = work["q4_priority"].astype(str).isin(READY_PRIORITIES)
    ready = work[ready_mask].copy()
    review = work[~ready_mask].copy()

    rank = {"HIGH": 3, "MEDIUM_HIGH": 2, "LOW_Q4": 1}
    ready["_rank"] = ready["q4_priority"].map(rank).fillna(0)
    ready = ready.sort_values(["_rank", "_mrr_num"], ascending=[False, False])

    do_dzwonienia = ready[[c for c in DO_DZWONIENIA_COLUMNS if c in ready.columns]].reset_index(drop=True)
    do_weryfikacji = review[[c for c in DO_WERYFIKACJI_COLUMNS if c in review.columns]].reset_index(drop=True)

    per_owner = ready.groupby("account_owner", dropna=False).agg(
        liczba_leadow=("domain_key", "count"),
        suma_mrr=("_mrr_num", "sum"),
        high=("q4_priority", lambda s: (s == "HIGH").sum()),
        medium_high=("q4_priority", lambda s: (s == "MEDIUM_HIGH").sum()),
        low_q4=("q4_priority", lambda s: (s == "LOW_Q4").sum()),
    ).reset_index().sort_values("liczba_leadow", ascending=False)

    per_branza = ready.groupby("branza_glowna", dropna=False).agg(
        liczba_leadow=("domain_key", "count"),
        suma_mrr=("_mrr_num", "sum"),
    ).reset_index().sort_values("liczba_leadow", ascending=False)

    kpi = pd.DataFrame([{
        "rekordy_gotowe": len(ready),
        "rekordy_do_weryfikacji": len(review),
        "pokrycie_procent": round(len(ready) / len(work) * 100, 1) if len(work) else 0.0,
        "suma_mrr_gotowe": round(ready["_mrr_num"].sum(), 2),
    }])

    summary = pd.concat(
        [
            pd.DataFrame([{"sekcja": "KPI"}]), kpi,
            pd.DataFrame([{"sekcja": "Per opiekun"}]), per_owner,
            pd.DataFrame([{"sekcja": "Per branża"}]), per_branza,
        ],
        ignore_index=True,
    )

    return {
        "Do dzwonienia": do_dzwonienia,
        "Do weryfikacji": do_weryfikacji,
        "Podsumowanie managera": summary,
    }


def main():
    df = pd.read_excel(CONSOLIDATED_PATH, dtype=str, keep_default_na=False)
    sheets = build_customer_care_workbook(df)
    with pd.ExcelWriter(EXPORT_PATH, engine="openpyxl") as writer:
        for name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=name, index=False)
    print(f"Zapisano {EXPORT_PATH.name}: Do dzwonienia={len(sheets['Do dzwonienia'])}, "
          f"Do weryfikacji={len(sheets['Do weryfikacji'])}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Uruchomić testy i potwierdzić, że przechodzą**

Run: `pytest tests/test_build_customer_care_export.py -v`
Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add build_customer_care_export.py tests/test_build_customer_care_export.py
git commit -m "feat: add shared 3-sheet customer care export builder"
```

---

### Task 5: Podłączenie eksportu do Streamlit i backendu FastAPI

**Files:**
- Modify: `bulk_app.py` (dodać przycisk pobrania w widoku "Plan działania" — funkcja `render_leads_view`, okolice istniejących `st.download_button` w tej sekcji, np. koło linii 1697-1703)
- Modify: `backend/api.py` (dodać endpoint)
- Modify: `backend/data_service.py` (dodać cienki wrapper)

**Interfaces:**
- Consumes: `build_customer_care_export.build_customer_care_workbook(df)` z Task 4.

- [ ] **Step 1: Dodać wrapper w `backend/data_service.py`**

Na końcu pliku dodać:

```python
def customer_care_export_frame(path=None):
    df, _ = load_output(path)
    if df.empty:
        return {}
    from build_customer_care_export import build_customer_care_workbook
    return build_customer_care_workbook(df)
```

- [ ] **Step 2: Dodać endpoint w `backend/api.py`**

W importach z `backend.data_service` dodać `customer_care_export_frame`. Po istniejącym `download_q4_actions` (za linią 250) dodać:

```python
@app.get("/customer-care/export.xlsx")
@app.get("/api/customer-care/export.xlsx")
def download_customer_care_export(file: str | None = Query(default=None)):
    try:
        path = safe_output_path(file) if file else None
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Nie ma takiego pliku output.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    sheets = customer_care_export_frame(path)
    if not sheets:
        raise HTTPException(status_code=404, detail="Brak danych do eksportu.")
    OUTPUT_DIR.mkdir(exist_ok=True)
    output_path = OUTPUT_DIR / "leadseason_api_customer_care_export.xlsx"
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        for name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=name, index=False)
    return FileResponse(
        output_path,
        filename=output_path.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
```

- [ ] **Step 3: Dodać przycisk pobrania w Streamlit**

W `bulk_app.py` w `render_leads_view` (w miejscu istniejącego `st.download_button(... file_name="leadseason_plan_dzialania.xlsx" ...)` koło linii 1697) dodać obok:

```python
    from build_customer_care_export import build_customer_care_workbook

    cc_sheets = build_customer_care_workbook(df)
    cc_buffer = BytesIO()
    with pd.ExcelWriter(cc_buffer, engine="openpyxl") as writer:
        for name, frame in cc_sheets.items():
            frame.to_excel(writer, sheet_name=name, index=False)
    st.download_button(
        "Pobierz bazę dla Customer Care (Do dzwonienia / Do weryfikacji / Podsumowanie)",
        cc_buffer.getvalue(),
        file_name="leadseason_customer_care_export.xlsx",
        mime=OUTPUT_MIME_TYPES[".xlsx"],
        width="stretch",
    )
```

- [ ] **Step 4: Ręcznie zweryfikować oba kanały**

Run backend: `START_BACKEND.bat`, potem w przeglądarce `http://127.0.0.1:8010/customer-care/export.xlsx` — plik musi się pobrać i mieć 3 arkusze.
Run Streamlit: `START_BULK_APP.bat`, wejść w "Plan działania", kliknąć nowy przycisk, otworzyć pobrany plik — te same 3 arkusze, te same liczby co z backendu (oba czytają ten sam, świeżo przeliczony w Task 2 plik).

- [ ] **Step 5: Commit**

```bash
git add bulk_app.py backend/api.py backend/data_service.py
git commit -m "feat: wire shared customer care export into Streamlit and backend API"
```

---

## Milestone 2 — Domknięcie pokrycia klasyfikacji (Stream A)

Cel: podnieść pokrycie z 45.4% do 70-80%, przez pulę 3093 rekordów `places_status=OK` bez branży. Po każdym z tasków 6-11 uruchomić ponownie `python rebuild_consolidated_signals.py` (Task 2), żeby świeże `ai_branza_glowna` od razu przełożyły się na `q4_priority`.

### Task 6: `stale_domain_detector.py` — wydzielenie wykrywacza martwych domen

**Files:**
- Create: `stale_domain_detector.py` (root repo)
- Modify: `qa_layer1_crosscheck.py:18-34` (usunąć lokalną kopię `STALE_PATTERNS`/`detect_stale`, zaimportować)
- Test: `tests/test_stale_domain_detector.py`

**Interfaces:**
- Produces: `STALE_PATTERNS: list[str]`, `detect_stale(row: dict) -> str` (pusty string = nie wykryto, inaczej dopasowany wzorzec). Używane przez Task 8 (`qa_wave2_stale_filter.py`) i nadal przez `qa_layer1_crosscheck.py`.

- [ ] **Step 1: Napisać nieprzechodzący test**

Utworzyć `tests/test_stale_domain_detector.py`:

```python
# -*- coding: utf-8 -*-
from stale_domain_detector import detect_stale


def test_detect_stale_finds_domain_for_sale_pattern():
    row = {"title": "Domena na sprzedaż", "meta_description": "", "body_text_sample": ""}
    assert detect_stale(row) == "domena na sprzedaż"


def test_detect_stale_returns_empty_for_normal_site():
    row = {"title": "Restauracja Pod Lipą", "meta_description": "Menu i rezerwacje", "body_text_sample": "Zapraszamy"}
    assert detect_stale(row) == ""
```

- [ ] **Step 2: Uruchomić i potwierdzić fail**

Run: `pytest tests/test_stale_domain_detector.py -v`
Expected: FAIL z `ModuleNotFoundError`

- [ ] **Step 3: Napisać `stale_domain_detector.py`**

```python
# -*- coding: utf-8 -*-
STALE_PATTERNS = [
    "domena jest zaparkowana", "domain is parked", "buy this domain", "domena na sprzedaż",
    "oferta sprzedaży domeny", "cena domeny", "kup domenę", "domena do kupienia",
    "aftermarket.pl", "this domain may be for sale", "sedo domain parking",
    "strona nieaktywna", "strona w trakcie zmian", "under construction", "coming soon",
    "w budowie", "domain suspended", "account suspended", "temporarily unavailable",
]


def detect_stale(row):
    text = " ".join(
        str(row.get(field, "") or "") for field in ["title", "meta_description", "body_text_sample"]
    ).lower()
    for pattern in STALE_PATTERNS:
        if pattern in text:
            return pattern
    return ""
```

- [ ] **Step 4: Uruchomić testy i potwierdzić, że przechodzą**

Run: `pytest tests/test_stale_domain_detector.py -v`
Expected: 2 PASSED

- [ ] **Step 5: Zaktualizować `qa_layer1_crosscheck.py`, żeby importował zamiast duplikować**

W `qa_layer1_crosscheck.py` zamienić linie 18-34 (definicję `STALE_PATTERNS` i `detect_stale`) na:

```python
from stale_domain_detector import STALE_PATTERNS, detect_stale
```

- [ ] **Step 6: Ręcznie zweryfikować, że `qa_layer1_crosscheck.py` nadal się importuje**

Run: `python -c "import ast; ast.parse(open('qa_layer1_crosscheck.py', encoding='utf-8').read())"`
Expected: brak błędu.

- [ ] **Step 7: Commit**

```bash
git add stale_domain_detector.py qa_layer1_crosscheck.py tests/test_stale_domain_detector.py
git commit -m "refactor: extract stale domain detector into shared module"
```

---

### Task 7: `classify_keyword_wave2.py` — darmowy przebieg klasyfikacji słów kluczowych (Strumień A1)

**Files:**
- Create: `classify_keyword_wave2.py` (root repo)
- Test: `tests/test_classify_keyword_wave2.py`

**Interfaces:**
- Consumes: `taxonomy.classify_detailed(record) -> dict` (istniejąca funkcja, `taxonomy.py:116`).
- Produces: `classify_pool(df: pd.DataFrame) -> pd.DataFrame` — czysta funkcja, zwraca df z nadpisanymi `ai_branza_glowna`/`ai_podbranza`/`ai_confidence`/`classification_source`/`ai_evidence` tam, gdzie `classify_detailed` znalazł dopasowanie, dla wierszy z `places_status == "OK"` i pustym `ai_branza_glowna`/`branza_glowna`.

- [ ] **Step 1: Napisać nieprzechodzący test**

Utworzyć `tests/test_classify_keyword_wave2.py`:

```python
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
    assert row["ai_confidence"] == 60


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
```

- [ ] **Step 2: Uruchomić i potwierdzić fail**

Run: `pytest tests/test_classify_keyword_wave2.py -v`
Expected: FAIL z `ModuleNotFoundError`

Uwaga: pierwszy test zależy od tego, że `config/leadseason_taxonomy.csv` ma wpis pokrywający słowa "tokarski"/"ślusarski"/"spawanie" — te słowa kluczowe zostały dodane dziś wcześniej w tej sesji (kategoria metalurgii/obróbki metali) przy okazji manual review batchy. Jeśli test padnie na asercji (nie na `ModuleNotFoundError`) po Step 3, sprawdzić `config/leadseason_taxonomy.csv` i dopisać brakujące `keywords_pl` dla obróbki metali, zanim pójdziesz dalej.

- [ ] **Step 3: Napisać `classify_keyword_wave2.py`**

```python
# -*- coding: utf-8 -*-
from pathlib import Path

import pandas as pd

from taxonomy import classify_detailed

BASE_DIR = Path(__file__).resolve().parent
CONSOLIDATED_PATH = BASE_DIR / "output" / "leadseason_pelna_baza_zeszyt2_consolidated.xlsx"


def _needs_classification(row):
    if str(row.get("places_status", "")) != "OK":
        return False
    ai_branza = str(row.get("ai_branza_glowna", "") or "").strip()
    rule_branza = str(row.get("branza_glowna", "") or "").strip()
    return ai_branza == "" and rule_branza == ""


def classify_pool(df):
    result = df.copy()
    for col in ["ai_branza_glowna", "ai_podbranza", "ai_confidence", "classification_source", "ai_evidence"]:
        if col not in result.columns:
            result[col] = ""

    target_idx = [idx for idx, row in result.iterrows() if _needs_classification(row)]
    matched = 0
    for idx in target_idx:
        row = result.loc[idx]
        detailed = classify_detailed(row.to_dict())
        if not detailed.get("branza_glowna"):
            continue
        result.at[idx, "ai_branza_glowna"] = detailed["branza_glowna"]
        result.at[idx, "ai_podbranza"] = detailed.get("podbranza", "")
        result.at[idx, "ai_confidence"] = 60
        result.at[idx, "classification_source"] = "keyword_wave2"
        result.at[idx, "ai_evidence"] = (
            f"Fala 2 (keyword): {detailed.get('classification_evidence', '')}"
        )
        matched += 1

    print(f"Warstwa 2 (keyword): sprawdzono {len(target_idx)} rekordow, dopasowano {matched}.")
    return result


def main():
    df = pd.read_excel(CONSOLIDATED_PATH, dtype=str, keep_default_na=False)
    result = classify_pool(df)
    result.to_excel(CONSOLIDATED_PATH, index=False)
    print(f"Zapisano {CONSOLIDATED_PATH.name}.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Uruchomić testy i potwierdzić, że przechodzą**

Run: `pytest tests/test_classify_keyword_wave2.py -v`
Expected: 3 PASSED

- [ ] **Step 5: Uruchomić na prawdziwej bazie**

Run: `python classify_keyword_wave2.py`
Expected: wypisana liczba sprawdzonych (docelowo 3093) i dopasowanych rekordów. Zanotować liczbę dopasowanych — to bezpośrednio pomniejsza pulę do ręcznej pracy w Task 9.

- [ ] **Step 6: Commit**

```bash
git add classify_keyword_wave2.py tests/test_classify_keyword_wave2.py
git commit -m "feat: add wave 2 keyword classification pass for Places-generic-type pool"
```

---

### Task 8: `qa_wave2_stale_filter.py` — odrzucenie martwych domen z fali 2

**Files:**
- Create: `qa_wave2_stale_filter.py` (root repo)
- Test: `tests/test_qa_wave2_stale_filter.py`

**Interfaces:**
- Consumes: `stale_domain_detector.detect_stale(row)` z Task 6.
- Produces: `filter_stale(df: pd.DataFrame) -> pd.DataFrame` — dla wierszy z `classification_source` w `{"keyword_wave2", "llm_wave2"}`, jeśli `detect_stale` znajdzie wzorzec, czyści `ai_branza_glowna`/`ai_podbranza`, ustawia `ai_confidence=0`, `manual_review=True`, `classification_source="excluded_stale_domain"`.

- [ ] **Step 1: Napisać nieprzechodzący test**

Utworzyć `tests/test_qa_wave2_stale_filter.py`:

```python
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
```

- [ ] **Step 2: Uruchomić i potwierdzić fail**

Run: `pytest tests/test_qa_wave2_stale_filter.py -v`
Expected: FAIL z `ModuleNotFoundError`

- [ ] **Step 3: Napisać `qa_wave2_stale_filter.py`**

```python
# -*- coding: utf-8 -*-
from pathlib import Path

import pandas as pd

from stale_domain_detector import detect_stale

BASE_DIR = Path(__file__).resolve().parent
CONSOLIDATED_PATH = BASE_DIR / "output" / "leadseason_pelna_baza_zeszyt2_consolidated.xlsx"
WAVE2_SOURCES = {"keyword_wave2", "llm_wave2"}


def filter_stale(df):
    result = df.copy()
    excluded = 0
    for idx, row in result.iterrows():
        if str(row.get("classification_source", "")) not in WAVE2_SOURCES:
            continue
        pattern = detect_stale(row)
        if not pattern:
            continue
        result.at[idx, "ai_branza_glowna"] = ""
        result.at[idx, "ai_podbranza"] = ""
        result.at[idx, "ai_confidence"] = "0"
        result.at[idx, "manual_review"] = "True"
        result.at[idx, "classification_source"] = "excluded_stale_domain"
        result.at[idx, "ai_evidence"] = f"WYKLUCZONO (fala 2): martwa/zaparkowana domena (wzorzec: '{pattern}')"
        excluded += 1
    print(f"Wykluczono jako martwe (fala 2): {excluded}")
    return result


def main():
    df = pd.read_excel(CONSOLIDATED_PATH, dtype=str, keep_default_na=False)
    result = filter_stale(df)
    result.to_excel(CONSOLIDATED_PATH, index=False)
    print(f"Zapisano {CONSOLIDATED_PATH.name}.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Uruchomić testy i potwierdzić, że przechodzą**

Run: `pytest tests/test_qa_wave2_stale_filter.py -v`
Expected: 2 PASSED

- [ ] **Step 5: Uruchomić na prawdziwej bazie (po Task 7)**

Run: `python qa_wave2_stale_filter.py`
Expected: wypisana liczba wykluczonych rekordów fali 2.

- [ ] **Step 6: Commit**

```bash
git add qa_wave2_stale_filter.py tests/test_qa_wave2_stale_filter.py
git commit -m "feat: filter stale domains out of wave 2 classification"
```

---

### Task 9: Rozumowanie AI nad resztą puli (Strumień A2) — zadanie operacyjne, nie kod

To zadanie nie jest testowalne pytestem — to seria ręcznych/agentowych partii, dokładnie tym samym mechanizmem co dzisiejszy manual review 483 rekordów. Jego "testem" jest spot-check w Task 10.

**Files:**
- Create: `apply_wave2_ai_classification_batch.py` (root repo, narzędzie do zapisu wyników partii)
- Create (w scratchpadzie, nie w repo): pliki JSON per partia, np. `wave2_ai_batch1.json`
- Test: `tests/test_apply_wave2_ai_classification_batch.py`

**Interfaces:**
- Produces: `apply_batch(corrections_path: str, batch_label: str) -> None` — czyta JSON `{"classified": {"domain_key": [branza, podbranza, confidence]}, "no_signal": ["domain_key", ...]}`, zapisuje do skonsolidowanego pliku.

- [ ] **Step 1: Napisać nieprzechodzący test dla logiki stosowania partii**

Utworzyć `tests/test_apply_wave2_ai_classification_batch.py`:

```python
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
```

- [ ] **Step 2: Uruchomić i potwierdzić fail**

Run: `pytest tests/test_apply_wave2_ai_classification_batch.py -v`
Expected: FAIL z `ModuleNotFoundError`

- [ ] **Step 3: Napisać `apply_wave2_ai_classification_batch.py`**

```python
# -*- coding: utf-8 -*-
import json
import sys
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
CONSOLIDATED_PATH = BASE_DIR / "output" / "leadseason_pelna_baza_zeszyt2_consolidated.xlsx"


def apply_batch_to_frame(df, corrections, batch_label):
    result = df.copy()
    for domain, values in corrections.get("classified", {}).items():
        branza, podbranza = values[0], values[1]
        confidence = values[2] if len(values) > 2 else 55
        mask = result["domain_key"] == domain
        if not mask.any():
            print(f"UWAGA: nie znaleziono domeny (classified): {domain}")
            continue
        result.loc[mask, "ai_branza_glowna"] = branza
        result.loc[mask, "ai_podbranza"] = podbranza
        result.loc[mask, "ai_confidence"] = str(confidence)
        result.loc[mask, "classification_source"] = "llm_wave2"
        result.loc[mask, "ai_evidence"] = (
            result.loc[mask, "ai_evidence"].astype(str) + f" | Fala 2 (AI): rozumowanie nad tresc strony ({batch_label})."
        )

    for domain in corrections.get("no_signal", []):
        mask = result["domain_key"] == domain
        if not mask.any():
            print(f"UWAGA: nie znaleziono domeny (no_signal): {domain}")
            continue
        result.loc[mask, "classification_source"] = "ai_reviewed_no_signal"
        result.loc[mask, "ai_evidence"] = (
            result.loc[mask, "ai_evidence"].astype(str) + f" | Fala 2 (AI): sprawdzono, brak wystarczajacego sygnalu ({batch_label})."
        )

    return result


def apply_batch(corrections_path, batch_label):
    with open(corrections_path, encoding="utf-8") as f:
        corrections = json.load(f)
    df = pd.read_excel(CONSOLIDATED_PATH, dtype=str, keep_default_na=False)
    result = apply_batch_to_frame(df, corrections, batch_label)
    result.to_excel(CONSOLIDATED_PATH, index=False)
    print(
        f"[{batch_label}] Sklasyfikowano: {len(corrections.get('classified', {}))}, "
        f"brak sygnalu: {len(corrections.get('no_signal', []))}"
    )


if __name__ == "__main__":
    apply_batch(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else Path(sys.argv[1]).stem)
```

- [ ] **Step 4: Uruchomić testy i potwierdzić, że przechodzą**

Run: `pytest tests/test_apply_wave2_ai_classification_batch.py -v`
Expected: 2 PASSED

- [ ] **Step 5: Commit narzędzia**

```bash
git add apply_wave2_ai_classification_batch.py tests/test_apply_wave2_ai_classification_batch.py
git commit -m "feat: add wave 2 AI classification batch applier"
```

- [ ] **Step 6 (operacyjny, powtarzalny): Wygenerować listę rekordów bez sygnału keyword**

Run:

```bash
python -c "
import pandas as pd
df = pd.read_excel('output/leadseason_pelna_baza_zeszyt2_consolidated.xlsx', dtype=str, keep_default_na=False)
pool = df[(df['classification_source']=='') & (df['places_status']=='OK')]
print(len(pool))
pool[['domain_key','places_name','places_primary_type','title','meta_description','h1_h3','body_text_sample']].to_csv('wave2_remaining_pool.csv', index=False)
"
```

Expected: plik `wave2_remaining_pool.csv` z rekordami, które A1 (keyword) nie złapał.

- [ ] **Step 7 (operacyjny, powtarzalny, wykonywany w partiach ~40-50 rekordów): rozumowanie AI**

Wczytać kolejny fragment `wave2_remaining_pool.csv` (Read z `offset`/`limit`), dla każdego rekordu ocenić na podstawie `title`/`meta_description`/`h1_h3`/`body_text_sample`/`places_name`/`places_primary_type`, czy treść strony jednoznacznie wskazuje branżę. Zapisać wynik jako `wave2_ai_batchN.json` w formacie zgodnym z testem w Step 1 (`{"classified": {...}, "no_signal": [...]}`), zastosować:

```bash
python apply_wave2_ai_classification_batch.py wave2_ai_batchN.json "wave2_batchN"
```

Powtarzać, aż `wave2_remaining_pool.csv` zostanie w całości przetworzone (regenerować plik po każdej partii, żeby nie przetwarzać dwa razy tych samych rekordów — rekordy oznaczone `llm_wave2` albo `ai_reviewed_no_signal` znikają z filtra `classification_source==''`).

---

### Task 10: Uzupełnienie macierzy Senuto o nowe kategorie z fali 2

**Files:**
- Modify: macierz `output/leadseason_macierz_sezonowosci_senuto.xlsx` (przez skrypt jednorazowy, wzorem `add_new_senuto_categories.py`)

**Interfaces:**
- Consumes: `matrix_gap_detector.find_matrix_gaps(df, matrix)` z Task 3.

- [ ] **Step 1: Wygenerować listę braków po fali 2**

Run:

```bash
python -c "
import pandas as pd
from matrix_gap_detector import find_matrix_gaps
df = pd.read_excel('output/leadseason_pelna_baza_zeszyt2_consolidated.xlsx', dtype=str, keep_default_na=False)
matrix = pd.read_excel('output/leadseason_macierz_sezonowosci_senuto.xlsx', dtype=str, keep_default_na=False)
gaps = find_matrix_gaps(df, matrix)
print(gaps.to_string())
"
```

- [ ] **Step 2: Dla par z istotnym wolumenem (np. >= 5 domen) dopisać wiersze do macierzy**

Napisać jednorazowy skrypt (wzorem `add_new_senuto_categories.py`/dzisiejszego `add_matrix_gaps.py`) z ręcznie wywnioskowaną sezonowością dla każdej nowej pary, `status="OK"` (nie inny status — pamiętać o buggu z wcześniej w tej sesji: `build_seasonal_leads` czyta tylko `status=="OK"`), i jawnym zapisem w `senuto_evidence`, że to wnioskowanie branżowe, nie realne dane z Senuto.

- [ ] **Step 3: Uruchomić `rebuild_consolidated_signals.py` ponownie i sprawdzić wzrost pokrycia**

Run: `python rebuild_consolidated_signals.py`
Expected: rozkład `q4_priority` pokazuje więcej rekordów poza `DO_WERYFIKACJI` niż przed Milestone 2.

- [ ] **Step 4: Commit**

```bash
git add output/leadseason_macierz_sezonowosci_senuto.xlsx
git commit -m "data: add senuto matrix categories discovered in classification wave 2"
```

---

### Task 11: Spot-check jakości fali 2 (Strumień A3, druga połowa) i finalny raport pokrycia

**Files:** brak nowych plików — zadanie weryfikacyjne.

- [ ] **Step 1: Wylosować próbkę do ręcznej weryfikacji**

Run:

```bash
python -c "
import pandas as pd
df = pd.read_excel('output/leadseason_pelna_baza_zeszyt2_consolidated.xlsx', dtype=str, keep_default_na=False)
wave2 = df[df['classification_source'].isin(['keyword_wave2','llm_wave2'])]
sample = wave2.sample(n=min(45, len(wave2)), random_state=42)
sample[['domain_key','places_name','places_primary_type','ai_branza_glowna','ai_podbranza','title','meta_description','h1_h3','body_text_sample']].to_csv('wave2_spotcheck_sample.csv', index=False)
print(len(sample))
"
```

- [ ] **Step 2: Ręcznie przejrzeć próbkę i policzyć błędy**

Dla każdego rekordu w `wave2_spotcheck_sample.csv` ocenić, czy `ai_branza_glowna`/`ai_podbranza` zgadza się z realną treścią strony. Policzyć error rate = błędne / wszystkie w próbce.

- [ ] **Step 3: Decyzja wg progu**

Jeśli error rate > 15-20% (podobnie jak w oryginalnym spot-checku Warstwy 1): wrócić do Task 7 (rozszerzyć `config/leadseason_taxonomy.csv` o brakujące słowa kluczowe) i/lub do Task 9 (dokładniejsze rozumowanie AI w kolejnych partiach) dla kategorii, gdzie błędy się skupiają, zanim uznasz falę 2 za zamkniętą. Jeśli error rate jest akceptowalny — przejść do Step 4.

- [ ] **Step 4: Finalny przelicznik pokrycia**

Run:

```bash
python -c "
import pandas as pd
df = pd.read_excel('output/leadseason_pelna_baza_zeszyt2_consolidated.xlsx', dtype=str, keep_default_na=False)
total = len(df)
ready = df[df['q4_priority'].isin(['HIGH','MEDIUM_HIGH','LOW_Q4'])]
print(f'Pokrycie: {len(ready)}/{total} = {len(ready)/total*100:.1f}%')
print(df['q4_priority'].value_counts())
"
```

Expected: pokrycie w paśmie 70-80%. Jeśli poniżej 70% — rozważyć rozszerzenie o pulę `places_status=NOT_FOUND` (poza zakresem tego planu, patrz spec, sekcja "Kolejne kroki").

- [ ] **Step 5: Wygenerować finalny eksport i podsumowanie dla użytkownika**

Run: `python build_customer_care_export.py`
Zgłosić użytkownikowi: finalne % pokrycia, liczby HIGH/MEDIUM_HIGH/LOW_Q4/DO_WERYFIKACJI, error rate ze spot-checku, ścieżkę do gotowego pliku `output/leadseason_customer_care_export.xlsx`.

---

## Self-review notes

- **Pokrycie spec:** Milestone 1 pokrywa całą sekcję "Strumień B" specyfikacji (wydzielenie modułu, skrypt przeliczający, jeden eksport używany przez oba kanały). Milestone 2 pokrywa "Strumień A" (A1 keyword, A2 AI fallback, A3 stale-filter + spot-check, A4 uzupełnienie macierzy). Sekcja "Deliverable" specyfikacji pokryta przez Task 4 (3 arkusze). Sekcja "Testy/walidacja" specyfikacji pokryta przez Task 11 (spot-check + regresja liczbowa już wbudowana w Step 5 Tasku 2).
- **Placeholder scan:** brak TBD/TODO; jedyne miejsca "operacyjne, nie kod" (Task 9, Task 11) mają jawnie wypisane kryteria akceptacji zamiast fikcyjnych testów pytest.
- **Spójność typów:** `classification_source` używa spójnych wartości w całym planie: `"keyword_wave2"`, `"llm_wave2"`, `"ai_reviewed_no_signal"`, `"excluded_stale_domain"` — te same stringi w testach, skryptach i opisie Task 9/11.
- **`recommended_product`** świadomie pominięte z eksportu i nietykane przez `rebuild_consolidated_signals.py` — zgodnie z Global Constraints i testem w Task 2/Task 4.
