# LeadSeason - workflow klasyfikacji przez Claude

## Cel

Claude ma poprawic pokrycie branż i sezonowosci dla rekordow, ktorych lokalny klasyfikator nie rozpoznal.

Najpierw LeadSeason robi ETL:

```text
CRM / Excel
-> crawl WWW
-> title, meta, h1_h3, offer_links, body_text_sample
-> dashboard
```

Potem eksportujemy tylko trudne rekordy:

```text
detected_industry = Nieokreślona
crawl_status = OK
body_text_sample lub title niepuste
```

## Eksport

W aplikacji:

```text
Menu -> Claude AI -> Eksport batcha
```

Ustaw:

- `Tylko Nieokreślona + crawl OK`,
- limit batcha, np. 100,
- offset, np. 0, 100, 200.

Pobierz:

```text
leadseason_claude_batch_<offset>_<limit>.jsonl
```

## Prompt

W aplikacji:

```text
Menu -> Claude AI -> Prompt
```

Skopiuj instrukcje do Claude i zalacz plik JSONL.

Claude ma zwrocic JSONL, jedna linia odpowiedzi na jedna linie wejscia.

## Import

W aplikacji:

```text
Menu -> Claude AI -> Import wyników
```

Wgraj wynik:

- JSONL,
- JSON,
- XLSX,
- CSV.

Po imporcie LeadSeason scala wynik po `record_key` i aktualizuje:

- `detected_industry`,
- `industry_confidence`,
- `season_peak`,
- `contact_start`,
- `q4_priority`,
- `recommended_product`,
- `lead_reason`,
- `call_script`,
- `ai_evidence`,
- `manual_review`,
- `classification_source`.

Na koncu pobierz:

```text
leadseason_po_claude.xlsx
```

## Zalecany rytm

1. Eksportuj batch 100 rekordow.
2. Daj Claude do klasyfikacji.
3. Zaimportuj wynik.
4. Sprawdz pokrycie w Dashboardzie.
5. Dopiero potem rob kolejne batche.

Nie wysylaj od razu calej bazy. Lepiej kontrolowac jakosc partiami.
