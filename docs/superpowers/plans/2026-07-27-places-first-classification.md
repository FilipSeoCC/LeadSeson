# Places-first klasyfikacja branż — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Odwrócić kolejność klasyfikacji branż: Google Places/GMB staje się głównym dowodem, a LLM reklasyfikuje `ai_branza_glowna`/`ai_podbranza` na tej podstawie dla całej (przefiltrowanej) bazy — nie tylko dla rekordów bez wcześniejszej klasyfikacji.

**Architecture:** Nowy pre-filtr wyklucza z Places domeny z kończącą się/zakończoną umową (i docelowo dłużników) zanim poniesiemy koszt API. Reszta bazy przechodzi przez istniejący `apply_places_enrichment()` (bulk_crawler.py, z cache w `cache/places/`). Nowa para funkcji w `ai_classification.py` (`eligible_for_places_reclass`, `build_places_reclass_batch`) buduje paczkę JSONL dla LLM analogicznie do istniejącego `build_ai_batch`, ale z inną regułą kwalifikacji (dowolna wartość `ai_branza_glowna`, wymagany tylko `places_status == "OK"`) i jawną instrukcją, że dane z Places są głównym dowodem. Istniejące `read_ai_results`/`merge_ai_results` są reużyte bez zmian — scalanie wyników działa już generycznie po `record_key`/`domain_key`. Downstream (Senuto matching, dashboard) nie wymaga zmian, bo zmienia się tylko **źródło** wartości `ai_branza_glowna`/`ai_podbranza`, nie ich schemat.

**Tech Stack:** Python 3.11, pandas, requests (Places API), Streamlit (bulk_app.py UI), pytest (nowo dodany do projektu na potrzeby tego planu — projekt nie miał wcześniej testów).

## Global Constraints

- Nie modyfikować istniejących funkcji `build_ai_batch`, `eligible_for_ai`, `read_ai_results`, `merge_ai_results` — są używane w innych miejscach aplikacji (linia 2380, 2398-2399 w bulk_app.py) i muszą zachować dotychczasowe zachowanie. Nowa logika idzie w nowe, równoległe funkcje.
- Cache Places (`cache/places/`, klucz = `domain_key`) musi być reużyty — nie pobierać ponownie danych dla 150 domen z testowego batcha (`output/leadseason_places_batch_test_150.xlsx`) ani dla ~500 domen z wcześniejszego badania (`leadseason_kategoryzacja_ai_places_500.xlsx`).
- Pre-filtr wykluczeń (koniec umowy w H2 bieżącego roku lub przeszły) musi używać dokładnie tej samej definicji okna, co istniejąca logika w `build_q4_customer_care_base_from_leads` (bulk_app.py:1134-1135): `h2_start = 1 lipca roku bieżącego`, `h2_end = 31 grudnia roku bieżącego`.
- Realny koszt Places API za próbkę 150 domen musi zostać sprawdzony w Google Cloud Console i odnotowany, zanim uruchomi się pełny batch na ~3213 pozostałych domenach (Task 3) — to bramka, nie formalność.
- Żadna z nowych funkcji nie wywołuje faktycznie API LLM (Anthropic/OpenAI) — w tym projekcie klasyfikacja LLM to zawsze eksport JSONL → przetworzenie poza kodem → import wyników (istniejący wzorzec w bulk_app.py, zakładka "Eksport dla LLM"/"Import klasyfikacji"). Ten plan **nie** wprowadza automatycznego wywołania API LLM.

---

## File Structure

- **Modify:** `bulk_crawler.py` — nowa funkcja `filter_places_candidates(df, today=None, debtor_ids=None)` (pre-filtr przed Places).
- **Create:** `run_places_full_batch.py` (root repo, obok istniejących `build_senuto_groups.py` itp.) — resumable runner: wczytuje aktywną bazę, filtruje kandydatów, uruchamia `apply_places_enrichment` w kawałkach, zapisuje wynik i podsumowanie.
- **Modify:** `ai_classification.py` — nowe stałe/funkcje: `PLACES_RECLASS_CONTEXT_COLUMNS`, `eligible_for_places_reclass(row)`, `build_places_reclass_batch(df, limit=1000, start=0)`.
- **Modify:** `bulk_app.py` — nowa czysta funkcja `resolve_export_records(df, mode, limit, start)` (logika wyboru trybu eksportu, oddzielona od renderowania Streamlit) + nowy radio-wybór trybu w zakładce "Eksport dla LLM" (~linia 2368-2391), korzystający z tej funkcji.
- **Create:** `verify_reclassification_diff.py` (root repo) — skrypt porównujący `ai_branza_glowna`/`ai_podbranza` przed/po scaleniu wyników LLM, z konkretnym sprawdzeniem `higienika.eu`.
- **Create:** `tests/test_filter_places_candidates.py`
- **Create:** `tests/test_places_reclass_batch.py`
- **Create:** `tests/test_resolve_export_records.py`
- **Create:** `tests/test_run_places_full_batch.py`
- **Create:** `tests/test_verify_reclassification_diff.py`
- **Create:** `pytest.ini` (root) — minimalna konfiguracja, `testpaths = tests`.

---

## Task 1: Pre-filtr wykluczeń przed Places

**Files:**
- Modify: `bulk_crawler.py` (dodać funkcję obok `apply_places_enrichment`, ok. linii 807)
- Test: `tests/test_filter_places_candidates.py`
- Create: `pytest.ini`

**Interfaces:**
- Produces: `filter_places_candidates(df: pd.DataFrame, today: date | None = None, debtor_ids: set[str] | None = None) -> pd.DataFrame` — zwraca podzbiór wierszy `df` kwalifikujących się do Places (wyklucza `end_date` w H2 bieżącego roku lub przeszły; wyklucza wiersze, gdzie `id` jest w `debtor_ids`).

- [ ] **Step 1: Zainstalować pytest i utworzyć konfigurację**

```bash
pip install pytest
```

Utwórz `pytest.ini`:

```ini
[pytest]
testpaths = tests
```

- [ ] **Step 2: Napisać failing testy**

```python
# tests/test_filter_places_candidates.py
import pandas as pd
from datetime import date
from bulk_crawler import filter_places_candidates


def _row(domain_key, end_date, row_id="1"):
    return {"domain_key": domain_key, "end_date": end_date, "id": row_id}


def test_excludes_contract_ending_in_h2_current_year():
    today = date(2026, 7, 27)
    df = pd.DataFrame([
        _row("h2-end.pl", "2026-09-15"),
        _row("next-year.pl", "2027-03-01"),
    ])
    result = filter_places_candidates(df, today=today)
    assert list(result["domain_key"]) == ["next-year.pl"]


def test_excludes_contract_already_ended():
    today = date(2026, 7, 27)
    df = pd.DataFrame([
        _row("already-ended.pl", "2026-01-10"),
        _row("still-active.pl", "2027-01-10"),
    ])
    result = filter_places_candidates(df, today=today)
    assert list(result["domain_key"]) == ["still-active.pl"]


def test_keeps_rows_with_blank_end_date():
    today = date(2026, 7, 27)
    df = pd.DataFrame([_row("no-end-date.pl", "")])
    result = filter_places_candidates(df, today=today)
    assert list(result["domain_key"]) == ["no-end-date.pl"]


def test_excludes_debtor_ids():
    today = date(2026, 7, 27)
    df = pd.DataFrame([
        _row("debtor.pl", "2027-01-10", row_id="42"),
        _row("ok.pl", "2027-01-10", row_id="43"),
    ])
    result = filter_places_candidates(df, today=today, debtor_ids={"42"})
    assert list(result["domain_key"]) == ["ok.pl"]
```

- [ ] **Step 3: Uruchomić testy i potwierdzić, że failują**

Run: `pytest tests/test_filter_places_candidates.py -v`
Expected: FAIL z `ImportError: cannot import name 'filter_places_candidates'`

- [ ] **Step 4: Zaimplementować funkcję**

Dodać w `bulk_crawler.py` obok `apply_places_enrichment` (ok. linii 805, przed definicją tej funkcji):

```python
from datetime import date as _date


def filter_places_candidates(df, today=None, debtor_ids=None):
    if df.empty:
        return df.copy()

    today = today or _date.today()
    h2_start = pd.Timestamp(year=today.year, month=7, day=1)
    h2_end = pd.Timestamp(year=today.year, month=12, day=31)
    today_ts = pd.Timestamp(today)

    end_dt = pd.to_datetime(df.get("end_date", ""), errors="coerce")
    ending_in_h2 = end_dt.between(h2_start, h2_end, inclusive="both")
    already_ended = end_dt.notna() & (end_dt < today_ts)
    excluded_by_contract = ending_in_h2 | already_ended

    if debtor_ids:
        is_debtor = df.get("id", pd.Series("", index=df.index)).astype(str).isin(debtor_ids)
    else:
        is_debtor = pd.Series(False, index=df.index)

    return df[~(excluded_by_contract | is_debtor)].copy()
```

Sprawdź, czy `pandas as pd` jest już zaimportowany w `bulk_crawler.py` na górze pliku (jeśli tak, nie duplikować importu).

- [ ] **Step 5: Uruchomić testy i potwierdzić, że przechodzą**

Run: `pytest tests/test_filter_places_candidates.py -v`
Expected: PASS (4 testy)

- [ ] **Step 6: Commit**

```bash
git add bulk_crawler.py tests/test_filter_places_candidates.py pytest.ini
git commit -m "feat: add pre-Places contract/debtor exclusion filter"
```

---

## Task 2: Resumable runner dla pełnego batcha Places

**Files:**
- Create: `run_places_full_batch.py`
- Test: `tests/test_run_places_full_batch.py`

**Interfaces:**
- Consumes: `filter_places_candidates(df, today=None, debtor_ids=None)` z Task 1; `apply_places_enrichment(rows, api_key="", cache_dir="cache/places", timeout=10, force=False)` z `bulk_crawler.py` (istniejąca).
- Produces: `select_pending_rows(candidates_df: pd.DataFrame, already_enriched_domain_keys: set[str]) -> list[dict]` — zwraca rekordy jeszcze nie wzbogacone (do wznawiania przerwanego batcha); `run_places_full_batch(base_path, output_path, api_key, cache_dir="cache/places", chunk_size=100, debtor_ids=None, today=None) -> dict` — pełny przebieg z podsumowaniem `{"total_candidates": int, "processed": int, "status_counts": dict}`.

- [ ] **Step 1: Napisać failing test dla `select_pending_rows`**

```python
# tests/test_run_places_full_batch.py
import pandas as pd
from run_places_full_batch import select_pending_rows


def test_select_pending_rows_skips_already_enriched():
    df = pd.DataFrame([
        {"domain_key": "done.pl", "id": "1"},
        {"domain_key": "todo.pl", "id": "2"},
    ])
    pending = select_pending_rows(df, already_enriched_domain_keys={"done.pl"})
    assert [row["domain_key"] for row in pending] == ["todo.pl"]


def test_select_pending_rows_empty_when_all_done():
    df = pd.DataFrame([{"domain_key": "done.pl", "id": "1"}])
    pending = select_pending_rows(df, already_enriched_domain_keys={"done.pl"})
    assert pending == []
```

- [ ] **Step 2: Uruchomić i potwierdzić fail**

Run: `pytest tests/test_run_places_full_batch.py -v`
Expected: FAIL z `ModuleNotFoundError: No module named 'run_places_full_batch'`

- [ ] **Step 3: Zaimplementować `run_places_full_batch.py`**

```python
# -*- coding: utf-8 -*-
import argparse
import sys
from pathlib import Path

import pandas as pd

from bulk_crawler import apply_places_enrichment, filter_places_candidates

BASE_DIR = Path(__file__).resolve().parent


def select_pending_rows(candidates_df, already_enriched_domain_keys):
    if candidates_df.empty:
        return []
    mask = ~candidates_df["domain_key"].astype(str).isin(already_enriched_domain_keys)
    return candidates_df[mask].to_dict(orient="records")


def load_env_file(env_path):
    import os
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            os.environ[key] = value


def run_places_full_batch(base_path, output_path, api_key, cache_dir="cache/places", chunk_size=100, debtor_ids=None, today=None):
    df = pd.read_excel(base_path, dtype=str, keep_default_na=False)
    df = df.drop_duplicates("domain_key")

    candidates = filter_places_candidates(df, today=today, debtor_ids=debtor_ids)

    already_enriched = set()
    if Path(output_path).exists():
        existing = pd.read_excel(output_path, dtype=str, keep_default_na=False)
        already_enriched = set(existing["domain_key"].astype(str))

    pending = select_pending_rows(candidates, already_enriched)
    print(f"Kandydaci po pre-filtrze: {len(candidates)}, do przetworzenia: {len(pending)}")

    all_results = []
    if already_enriched and Path(output_path).exists():
        all_results = pd.read_excel(output_path, dtype=str, keep_default_na=False).to_dict(orient="records")

    for start in range(0, len(pending), chunk_size):
        chunk = pending[start:start + chunk_size]
        enriched = apply_places_enrichment(chunk, api_key=api_key, cache_dir=cache_dir, timeout=10, force=False)
        all_results.extend(enriched)
        pd.DataFrame(all_results).to_excel(output_path, index=False)
        print(f"Postęp: {min(start + chunk_size, len(pending))}/{len(pending)} — zapisano {output_path}")

    result_df = pd.DataFrame(all_results)
    status_counts = result_df["places_status"].value_counts().to_dict() if "places_status" in result_df else {}
    return {
        "total_candidates": len(candidates),
        "processed": len(all_results),
        "status_counts": status_counts,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=str(BASE_DIR / "output" / "leadseason_pelna_baza_po_llm_971.xlsx"))
    parser.add_argument("--output", default=str(BASE_DIR / "output" / "leadseason_places_full_batch.xlsx"))
    parser.add_argument("--chunk-size", type=int, default=100)
    args = parser.parse_args()

    load_env_file(BASE_DIR / ".env")
    import os
    api_key = os.environ.get("GOOGLE_PLACES_API_KEY", "")
    if not api_key:
        print("Brak GOOGLE_PLACES_API_KEY w .env")
        sys.exit(1)

    summary = run_places_full_batch(args.base, args.output, api_key, chunk_size=args.chunk_size)
    print(summary)
```

- [ ] **Step 4: Uruchomić testy i potwierdzić PASS**

Run: `pytest tests/test_run_places_full_batch.py -v`
Expected: PASS (2 testy)

- [ ] **Step 5: Commit**

```bash
git add run_places_full_batch.py tests/test_run_places_full_batch.py
git commit -m "feat: add resumable full-batch Places enrichment runner"
```

---

## Task 3: Kontrola realnego kosztu Places przed pełnym batchem

To krok operacyjny (nie kod), ale jest twardą bramką przed Task-iem 2 wykonanym na pełną skalę — nie pomijać.

- [ ] **Step 1:** Otworzyć Google Cloud Console → Billing → Reports, filtr usługi = "Places API (New)", zakres dat = dzień uruchomienia testu 150 domen.
- [ ] **Step 2:** Odczytać rzeczywistą kwotę naliczoną za te 150 zapytań.
- [ ] **Step 3:** Odnotować rzeczywistą kwotę na domenę (`rzeczywista_kwota / 150`) i ekstrapolować na pozostałe ~3213 domen po pre-filtrze (Task 1).
- [ ] **Step 4:** Dopisać odczytaną wartość do `docs/superpowers/specs/2026-07-27-places-first-classification-design.md` w sekcji "Ryzyka / otwarte pytania" (zastąpić szacunek `~$0.035/req` rzeczywistą stawką).
- [ ] **Step 5:** Podjąć decyzję: uruchomić `run_places_full_batch.py` na pełnym zbiorze, czy dalej dzielić na mniejsze partie (np. po 500 domen) w oparciu o rzeczywisty koszt.

---

## Task 4: Kwalifikacja i budowa paczki LLM z Places jako głównym dowodem

**Files:**
- Modify: `ai_classification.py`
- Test: `tests/test_places_reclass_batch.py`

**Interfaces:**
- Consumes: `clean_for_prompt(value, limit=1400)`, `build_record_key(row)` (istniejące w `ai_classification.py`).
- Produces: `PLACES_RECLASS_CONTEXT_COLUMNS: list[str]`; `eligible_for_places_reclass(row) -> bool`; `build_places_reclass_batch(df, limit=1000, start=0) -> list[dict]` — każdy element ma `record_key`, `task="classify_leadseason_industry_places_first"`, `instructions` (string wyjaśniający priorytet dowodów), `context` (w tym pola places_*), `expected_output_schema` (te same klucze co `AI_RESULT_FIELDS`, kompatybilne z istniejącym `merge_ai_results`).

- [ ] **Step 1: Napisać failing testy**

```python
# tests/test_places_reclass_batch.py
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
```

- [ ] **Step 2: Uruchomić testy i potwierdzić fail**

Run: `pytest tests/test_places_reclass_batch.py -v`
Expected: FAIL z `ImportError`

- [ ] **Step 3: Zaimplementować w `ai_classification.py`**

Dodać po istniejącej definicji `AI_RESULT_FIELDS` (ok. linii 50):

```python
PLACES_RECLASS_CONTEXT_COLUMNS = AI_CONTEXT_COLUMNS + [
    "places_address",
    "places_match_confidence",
    "places_match_reasons",
    "ai_branza_glowna",
    "ai_podbranza",
]

PLACES_RECLASS_INSTRUCTIONS = (
    "Dane z Google Places (places_name, places_primary_type, places_address) "
    "to GŁÓWNY dowód dla klasyfikacji branży — pochodzą z ustrukturyzowanej bazy Google "
    "o realnej działalności firmy. Treść strony WWW (title, meta_description, body_text_sample) "
    "to dowód POMOCNICZY — może być niejednoznaczna lub SEO-tekstowa. "
    "Istniejące pola ai_branza_glowna/ai_podbranza mogą być błędne (klasyfikowane wyłącznie "
    "z treści strony) — nie traktuj ich jako założenia, oceń branżę od nowa na podstawie "
    "danych z Places w pierwszej kolejności."
)


def eligible_for_places_reclass(row):
    return str(row.get("places_status") or "").strip() == "OK"


def build_places_reclass_batch(df, limit=1000, start=0):
    records = []
    working = df[df.apply(eligible_for_places_reclass, axis=1)]
    if start:
        working = working.iloc[int(start):]
    if limit:
        working = working.head(int(limit))

    for _, row in working.iterrows():
        item = {
            "record_key": build_record_key(row),
            "task": "classify_leadseason_industry_places_first",
            "instructions": PLACES_RECLASS_INSTRUCTIONS,
            "context": {},
            "expected_output_schema": {
                "record_key": "same as input",
                "branza_glowna": "string",
                "podbranza": "string",
                "usluga_glowna": "string",
                "model_b2b_b2c": "B2B | B2C | Mieszany | Nieokreślona",
                "confidence": "integer 0-100",
                "new_category_flag": "ISTNIEJACA | NOWA_BRANZA | NOWA_PODBRANZA | NOWA_USLUGA | BRAK_SYGNALU",
                "evidence": "short evidence string",
                "manual_review": "boolean",
            },
        }
        for column in PLACES_RECLASS_CONTEXT_COLUMNS:
            if column in row:
                item["context"][column] = clean_for_prompt(row.get(column))
        records.append(item)
    return records
```

- [ ] **Step 4: Uruchomić testy i potwierdzić PASS**

Run: `pytest tests/test_places_reclass_batch.py -v`
Expected: PASS (5 testów)

- [ ] **Step 5: Commit**

```bash
git add ai_classification.py tests/test_places_reclass_batch.py
git commit -m "feat: add Places-first reclassification batch builder"
```

---

## Task 5: Wpięcie trybu Places-first do UI eksportu w bulk_app.py

**Files:**
- Modify: `bulk_app.py` (funkcja logiki ok. nowego miejsca obok linii 2368-2391; UI radio w tej samej sekcji)
- Test: `tests/test_resolve_export_records.py`

**Interfaces:**
- Consumes: `build_ai_batch` (istniejąca), `build_places_reclass_batch` z Task 4.
- Produces: `resolve_export_records(df, mode, limit, start) -> list[dict]` gdzie `mode` to jedno z `"unclassified"`, `"places_first"`, `"all"`.

- [ ] **Step 1: Napisać failing test**

```python
# tests/test_resolve_export_records.py
import pandas as pd
from bulk_app import resolve_export_records


def test_mode_unclassified_uses_build_ai_batch_only_unclassified():
    df = pd.DataFrame([
        {"id": "1", "detail_id": "1", "domain_key": "a.pl", "branza_glowna": "", "crawl_status": "OK",
         "usable_for_llm": True, "site_health_status": "OK", "body_text_sample": "tekst", "title": "A"},
        {"id": "2", "detail_id": "2", "domain_key": "b.pl", "branza_glowna": "Gastronomia", "crawl_status": "OK",
         "usable_for_llm": True, "site_health_status": "OK", "body_text_sample": "tekst", "title": "B"},
    ])
    records = resolve_export_records(df, mode="unclassified", limit=10, start=0)
    assert [r["record_key"].split("|")[-1] for r in records] == ["a.pl"]


def test_mode_places_first_uses_places_reclass_batch():
    df = pd.DataFrame([
        {"id": "1", "detail_id": "1", "domain_key": "a.pl", "places_status": "OK", "ai_branza_glowna": "Nieruchomości"},
        {"id": "2", "detail_id": "2", "domain_key": "b.pl", "places_status": "NOT_FOUND"},
    ])
    records = resolve_export_records(df, mode="places_first", limit=10, start=0)
    assert [r["record_key"].split("|")[-1] for r in records] == ["a.pl"]
    assert records[0]["task"] == "classify_leadseason_industry_places_first"


def test_mode_all_uses_build_ai_batch_only_unclassified_false():
    df = pd.DataFrame([
        {"id": "1", "detail_id": "1", "domain_key": "a.pl", "branza_glowna": "Gastronomia", "crawl_status": "OK",
         "usable_for_llm": True, "site_health_status": "OK", "body_text_sample": "tekst", "title": "A"},
    ])
    records = resolve_export_records(df, mode="all", limit=10, start=0)
    assert len(records) == 1
```

- [ ] **Step 2: Uruchomić testy i potwierdzić fail**

Run: `pytest tests/test_resolve_export_records.py -v`
Expected: FAIL z `ImportError`

- [ ] **Step 3: Zaimplementować `resolve_export_records` w bulk_app.py**

Dodać funkcję tuż przed sekcją, w której dziś wywoływane jest `build_ai_batch` (przed linią ok. 2368):

```python
def resolve_export_records(df, mode, limit, start):
    if mode == "places_first":
        return build_places_reclass_batch(df, limit=int(limit), start=int(start))
    only_unclassified = mode == "unclassified"
    return build_ai_batch(df, only_unclassified=only_unclassified, limit=int(limit), start=int(start))
```

Dodać import na górze pliku (obok istniejącego importu z `ai_classification`):

```python
from ai_classification import (
    build_ai_batch,
    build_places_reclass_batch,
    eligible_for_ai,
    jsonl_bytes,
    merge_ai_results,
    read_ai_results,
)
```

Zmienić UI w zakładce `tab_export` (linie ok. 2370-2391) — zastąpić checkbox radio-buttonem i użyć nowej funkcji:

```python
with tab_export:
    st.markdown("### Paczka danych dla LLM")
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        mode = st.radio(
            "Tryb",
            options=["unclassified", "places_first", "all"],
            format_func=lambda m: {
                "unclassified": "Tylko nieklasyfikowane",
                "places_first": "Places-first reklasyfikacja (nadpisz istniejące)",
                "all": "Wszystkie rekordy",
            }[m],
        )
    with col_b:
        start = st.number_input("Offset", min_value=0, value=0, step=100)
    with col_c:
        limit = st.number_input("Limit batcha", min_value=1, max_value=1000, value=100, step=50)

    records = resolve_export_records(df, mode, limit, start)
    st.metric("Rekordy w paczce", len(records))
    if records:
        preview = pd.DataFrame([{"record_key": item["record_key"], **item["context"]} for item in records[:20]])
        st.dataframe(preview, width="stretch", height=260)
        st.download_button(
            "Pobierz JSONL dla LLM",
            jsonl_bytes(records),
            file_name=f"leadseason_claude_batch_{mode}_{int(start)}_{int(limit)}.jsonl",
            mime="application/jsonl",
            width="stretch",
        )
```

- [ ] **Step 4: Uruchomić testy i potwierdzić PASS**

Run: `pytest tests/test_resolve_export_records.py -v`
Expected: PASS (3 testy)

- [ ] **Step 5: Ręcznie zweryfikować w Streamlit**

Uruchomić `streamlit run bulk_app.py`, przejść do zakładki eksportu LLM, wybrać "Places-first reklasyfikacja", potwierdzić że podgląd paczki pokazuje kolumny `places_name`/`places_primary_type`/`places_address`.

- [ ] **Step 6: Commit**

```bash
git add bulk_app.py tests/test_resolve_export_records.py
git commit -m "feat: add Places-first mode to LLM export UI"
```

---

## Task 6: Uruchomienie klasyfikacji LLM i scalenie wyników

To krok operacyjny (wymaga faktycznego przejścia paczki przez LLM — zgodnie z istniejącym wzorcem w projekcie, to dzieje się poza kodem: eksport JSONL → przetworzenie → import).

- [ ] **Step 1:** W Streamlit, zakładka "Eksport dla LLM", tryb "Places-first reklasyfikacja", pobrać paczkę/paczki JSONL dla wszystkich domen z `places_status == "OK"` (offset/limit w kawałkach po np. 200-300, zgodnie z `expected_output_schema` z Task 4).
- [ ] **Step 2:** Przetworzyć każdą paczkę przez LLM (zgodnie z `instructions`/`expected_output_schema` w każdym rekordzie — Places jako główny dowód, treść strony jako pomocniczy), zapisać wyniki jako JSONL zgodny ze schematem.
- [ ] **Step 3:** W zakładce "Import klasyfikacji" wgrać wyniki — reużywa istniejących `read_ai_results`/`merge_ai_results` bez zmian kodu.
- [ ] **Step 4:** Po scaleniu wszystkich paczek, zapisać zaktualizowaną bazę jako nowy plik (np. `output/leadseason_pelna_baza_places_first.xlsx`), żeby zachować poprzednią wersję do porównania w Task 7.

---

## Task 7: Weryfikacja różnicy przed/po

**Files:**
- Create: `verify_reclassification_diff.py`
- Test: `tests/test_verify_reclassification_diff.py`

**Interfaces:**
- Produces: `summarize_reclassification_diff(before_df: pd.DataFrame, after_df: pd.DataFrame) -> dict` — zwraca `{"total_compared": int, "changed_branza_glowna": int, "changed_podbranza": int, "changed_domains": list[str]}`, dopasowanie po `domain_key`.

- [ ] **Step 1: Napisać failing test**

```python
# tests/test_verify_reclassification_diff.py
import pandas as pd
from verify_reclassification_diff import summarize_reclassification_diff


def test_detects_changed_branza():
    before = pd.DataFrame([
        {"domain_key": "higienika.eu", "ai_branza_glowna": "Nieruchomości", "ai_podbranza": "Biuro nieruchomości"},
        {"domain_key": "stable.pl", "ai_branza_glowna": "Gastronomia", "ai_podbranza": "Restauracja"},
    ])
    after = pd.DataFrame([
        {"domain_key": "higienika.eu", "ai_branza_glowna": "Usługi porządkowe", "ai_podbranza": "Sprzątanie biur"},
        {"domain_key": "stable.pl", "ai_branza_glowna": "Gastronomia", "ai_podbranza": "Restauracja"},
    ])
    result = summarize_reclassification_diff(before, after)
    assert result["total_compared"] == 2
    assert result["changed_branza_glowna"] == 1
    assert result["changed_domains"] == ["higienika.eu"]


def test_no_changes_returns_zero():
    df = pd.DataFrame([{"domain_key": "a.pl", "ai_branza_glowna": "X", "ai_podbranza": "Y"}])
    result = summarize_reclassification_diff(df, df.copy())
    assert result["changed_branza_glowna"] == 0
    assert result["changed_domains"] == []
```

- [ ] **Step 2: Uruchomić testy i potwierdzić fail**

Run: `pytest tests/test_verify_reclassification_diff.py -v`
Expected: FAIL z `ModuleNotFoundError`

- [ ] **Step 3: Zaimplementować `verify_reclassification_diff.py`**

```python
# -*- coding: utf-8 -*-
import argparse
import pandas as pd


def summarize_reclassification_diff(before_df, after_df):
    merged = before_df.merge(
        after_df, on="domain_key", suffixes=("_before", "_after"), how="inner"
    )
    changed_branza = merged["ai_branza_glowna_before"] != merged["ai_branza_glowna_after"]
    changed_podbranza = merged["ai_podbranza_before"] != merged["ai_podbranza_after"]
    return {
        "total_compared": len(merged),
        "changed_branza_glowna": int(changed_branza.sum()),
        "changed_podbranza": int(changed_podbranza.sum()),
        "changed_domains": sorted(merged[changed_branza]["domain_key"].tolist()),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--before", required=True)
    parser.add_argument("--after", required=True)
    args = parser.parse_args()

    before_df = pd.read_excel(args.before, dtype=str, keep_default_na=False).drop_duplicates("domain_key")
    after_df = pd.read_excel(args.after, dtype=str, keep_default_na=False).drop_duplicates("domain_key")
    summary = summarize_reclassification_diff(before_df, after_df)
    print(f"Porównano: {summary['total_compared']}")
    print(f"Zmieniona branza_glowna: {summary['changed_branza_glowna']}")
    print(f"Zmieniona podbranza: {summary['changed_podbranza']}")
    if "higienika.eu" in summary["changed_domains"]:
        print("higienika.eu: branża zmieniona (oczekiwane)")
    print("Przykładowe zmienione domeny:", summary["changed_domains"][:20])
```

- [ ] **Step 4: Uruchomić testy i potwierdzić PASS**

Run: `pytest tests/test_verify_reclassification_diff.py -v`
Expected: PASS (2 testy)

- [ ] **Step 5: Uruchomić na realnych danych po Task 6**

```bash
python3 verify_reclassification_diff.py --before "output/leadseason_pelna_baza_po_llm_971.xlsx" --after "output/leadseason_pelna_baza_places_first.xlsx"
```

Sprawdzić w wyniku, że `higienika.eu` pojawia się jako zmieniona domena.

- [ ] **Step 6: Commit**

```bash
git add verify_reclassification_diff.py tests/test_verify_reclassification_diff.py
git commit -m "feat: add before/after reclassification diff verification"
```

---

## Self-Review

**1. Spec coverage:**
- Pre-filtr (end_date H2/przeszły + dłużnicy) → Task 1. ✓
- Places API dla przefiltrowanej bazy z reużyciem cache → Task 2. ✓
- Kontrola realnego kosztu przed pełnym batchem → Task 3. ✓
- LLM reklasyfikacja z Places jako głównym dowodem, dla wszystkich domen z `places_status: OK` niezależnie od istniejącej etykiety → Task 4, 5, 6. ✓
- Domeny NOT_FOUND klasyfikowane po staremu → brak nowego kodu potrzebny: `eligible_for_places_reclass` je wyklucza, a istniejący `eligible_for_ai`/`build_ai_batch` (niezmienione, Global Constraints) nadal je obsługuje. Odnotowane w Global Constraints i architekturze. ✓
- Downstream bez zmian schematu → brak zadań, bo brak zmian — potwierdzone w Architecture. ✓

**2. Placeholder scan:** brak "TODO"/"do uzupełnienia" — każdy krok ma pełny kod lub konkretne, wykonywalne polecenie (Task 3 i częściowo Task 6 to kroki operacyjne, ale każdy ma jawną, konkretną akcję, nie ogólnik).

**3. Type consistency:** `filter_places_candidates(df, today, debtor_ids)` z Task 1 używane spójnie w Task 2 (`run_places_full_batch`) z tymi samymi nazwami parametrów. `build_places_reclass_batch(df, limit, start)` z Task 4 używane spójnie w Task 5 (`resolve_export_records`) i Task 6 (opis operacyjny). `summarize_reclassification_diff(before_df, after_df)` z Task 7 samodzielne, bez zależności od wcześniejszych sygnatur — spójne.

---

**Plan complete and saved to `docs/superpowers/plans/2026-07-27-places-first-classification.md`.** Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
