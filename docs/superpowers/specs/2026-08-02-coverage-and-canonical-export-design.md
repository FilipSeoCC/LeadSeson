# LeadSeason — domknięcie pokrycia bazy i kanoniczny eksport dla Customer Care

## Kontekst

LeadSeason ma dostarczyć Customer Care listę klientów z aktywnej bazy (9421 rekordów z umowami), do których warto zadzwonić teraz, z konkretnym powodem wynikającym z sezonowości branży. Strategiczna wizja jest opisana w `PLAN_CUSTOMER_CARE_LEADSEASON.md`.

Po pełnej rundzie QA klasyfikacji Layer 1 (Google Places → branża, 483 ręcznie zweryfikowane konflikty, 6 nowych kategorii dodanych do macierzy Senuto) baza ma:

- **4275 / 9421 (45.4%)** rekordów z jakąkolwiek branżą (3047 przez Places/Layer1+QA, 1804 przez dopasowanie słów kluczowych),
- **3940 / 9421 (41.8%)** rekordów z branżą **i** dopasowaną sezonowością z macierzy Senuto (czyli realnie "gotowych do działania" wg dzisiejszej logiki aplikacji).

Właściciel produktu ocenił to jako za wąskie, żeby wydać jako "bazę jakościową do dzwonienia" — potrzebne jest pokrycie na poziomie **70-80%** całej bazy.

Po drodze wykryto drugi, niezależny problem: kolumna `q4_priority` (i powiązane `season_peak`, `contact_start`, `seasonality_confidence`, `sugerowana_akcja`/`lead_reason`) zapisana w skonsolidowanym pliku Excel jest **statycznym snapshotem** z wcześniejszego przebiegu i nie została przeliczona po dzisiejszych 483 poprawkach. Streamlit (`bulk_app.py`) liczy te pola na żywo przy każdym wczytaniu (`apply_senuto_q4_signal`), więc tam dane są aktualne — ale backend FastAPI (`backend/data_service.py::q4_action_frame`) czyta bezpośrednio statyczną kolumnę z pliku, więc `/q4/actions.xlsx` i `/q4/summary` pokazują dziś nieaktualny stan sprzed poprawek.

## Cel tego planu

1. Podnieść pokrycie bazy (branża + sezonowość) z 41.8% do **70-80%**.
2. Zlikwidować rozjazd Streamlit (live) vs backend (stale) — jeden kanoniczny, zawsze świeży wynik.
3. Wydać jeden plik XLSX, który realnie można dać opiekunom klienta, z jasnym rozdziałem "gotowe" vs "do weryfikacji".

**Poza zakresem** (świadomie odłożone na kolejne, osobne specyfikacje):
- inteligentniejsza logika upsell/cross-sell (dziś `sugerowana_akcja` to kilka statycznych szablonów tekstu, niezależnych od obecnego pakietu klienta i realnej oferty WeNet),
- integracja Voice AI / pilotaż z realnymi opiekunami / pomiar skuteczności,
- moduł Avaya + CRM2 Contact Penetration,
- atak na pulę 2045 rekordów `places_status=NOT_FOUND` (może się zdarzyć przy okazji, jeśli Strumień A da więcej niż potrzeba, ale nie jest celem tego planu).

## Strumień A — domknięcie pokrycia (45% → 70-80%)

**Pula docelowa**: 3093 rekordy z `places_status=OK`, ale bez żadnej branży (`ai_branza_glowna`/`ai_podbranza` i `branza_glowna`/`podbranza` puste). Typ Places w tej puli jest zbyt ogólny, żeby zadziałał deterministyczny słownik Layer 1 (dominują `service` 659, `general_contractor` 484, `manufacturer` 450, brak typu 387, `store` 358, `consultant` 167, `supplier` 115, `corporate_office` 110, `wholesaler` 95) — sygnał musi pochodzić z treści strony, którą już mamy z crawla (`title`, `meta_description`, `h1_h3`, `body_text_sample`).

### A1 — darmowy przebieg keyword

Uruchomić `taxonomy.py::classify_detailed()` na całej puli 3093 rekordów. Dla trafień (niepusty `branza_glowna`/`podbranza`):
- zapisać do `ai_branza_glowna` / `ai_podbranza`,
- `ai_confidence` = 60 (umiarkowana pewność, bo nie ma niezależnego potwierdzenia z Places),
- `classification_source = "keyword_wave2"`.

### A2 — fallback AI (rozumowanie nad treścią strony)

Dla rekordów bez trafienia w A1: rozumowanie AI nad `title/meta/h1/body_text_sample`, tym samym mechanizmem co wcześniejsze 2462 domeny (task #1). Wykonywane w partiach ~40-50 rekordów na turę, analogicznie do dzisiejszego manual review. To największy nakład czasowy w tym planie — realistycznie kilka sesji roboczych, nie jedna.

Zapis: `ai_branza_glowna`/`ai_podbranza`, `ai_confidence` wg pewności rozumowania (typowo 50-70), `classification_source = "llm_wave2"`.

### A3 — QA dopasowany do tej puli

Tu nie istnieje sygnał "Places mówi X, słowa kluczowe mówią Y" (Places był zbyt ogólny, żeby mieć zdanie) — więc mechanizm QA jest inny niż przy Layer 1:

1. **Automatyczne odrzucenie martwych domen** — te same `STALE_PATTERNS` z `bulk_crawler.py` uruchomione na nowo klasyfikowanych rekordach; dopasowania → `classification_source = "excluded_stale_domain"`, `ai_confidence = 0`, `manual_review = True`.
2. **Losowy spot-check** — próbka ~40-50 rekordów z A1+A2 łącznie, ręczna weryfikacja trafności branży wobec realnej treści strony. Jeśli error rate jest zauważalnie wyższy niż w Layer 1 (tam było ~20% przed poprawkami), poprawić słownik taksonomii / dopracować prompt rozumowania AI przed uznaniem fali za zamkniętą — nie wydawać puli z nieznaną jakością.

### A4 — uzupełnienie macierzy Senuto

Dla każdej nowej pary (branża, podbranża) wprowadzonej w A1/A2, sprawdzić czy istnieje w macierzy Senuto. Jeśli nie — dodać wiersz z status=`OK` i best-effort sezonowością (branżowe wnioskowanie, opisane wprost w `senuto_evidence` jako niezweryfikowane w Senuto), dokładnie jak dla 6 kategorii dodanych dzisiaj.

### Oczekiwany wynik

Przy realistycznym wskaźniku trafień 80-90% na tej puli (mniej pewnej niż oryginalny Layer 1, bo brak niezależnego potwierdzenia Places): +2500 do +2800 nowych rekordów z branżą → całkowite pokrycie ok. **73-76%** — w docelowym paśmie 70-80% bez konieczności atakowania trudniejszej puli `NOT_FOUND` (2045 rekordów).

## Strumień B — jeden kanoniczny wynik (naprawa rozjazdu Streamlit/backend)

### Problem

- `bulk_app.py` liczy `season_peak`, `contact_start`, `q4_priority`, `seasonality_confidence`, `sugerowana_akcja` **na żywo** przy każdym wczytaniu pliku, funkcją `apply_senuto_q4_signal()` → `build_seasonal_leads()`.
- Te same pola istnieją też jako **statyczne kolumny** w skonsolidowanym pliku Excel (`q4_priority`, `lead_reason`, `season_peak`, `contact_start`, `seasonality_confidence`), zapisane przy jakimś wcześniejszym uruchomieniu i **nigdy nieodświeżone** po zmianach w `ai_branza_glowna`/`ai_podbranza`.
- `backend/data_service.py::q4_action_frame()` czyta bezpośrednio te statyczne kolumny z pliku (`data[data["q4_priority"].isin(Q4_VALUES)]`) — nie wywołuje `apply_senuto_q4_signal()`. Backend/API (`/q4/summary`, `/q4/actions`, `/q4/actions.xlsx`) pokazuje więc dziś stan sprzed dzisiejszych 483 poprawek i sprzed dodania 6 kategorii do macierzy.

### Rozwiązanie

1. Wydzielić `build_seasonal_leads()` i `apply_senuto_q4_signal()` z `bulk_app.py` do wspólnego modułu, np. `seasonal_signal.py`, bez zmiany logiki — czysty przenoszenie kodu, żeby Streamlit i backend mogły importować to samo źródło.
2. Dodać skrypt `rebuild_consolidated_signals.py`, który:
   - wczytuje skonsolidowaną bazę i aktualną macierz Senuto,
   - woła `apply_senuto_q4_signal()` z `seasonal_signal.py`,
   - **nadpisuje** w pliku statyczne kolumny (`season_peak`, `contact_start`, `q4_priority`, `seasonality_confidence`, `lead_reason`/`sugerowana_akcja`) świeżo przeliczonymi wartościami,
   - drukuje podsumowanie zmian (ile rekordów zmieniło `q4_priority`, rozkład przed/po) — dla widoczności, że coś się realnie przeliczyło.
3. Ten skrypt uruchamiany jawnie po każdej fali klasyfikacji/QA (Strumień A, przyszłe fale) — udokumentowany krok kończący turę pracy, nie ukryta automatyzacja.
4. `backend/data_service.py` dalej czyta statyczne kolumny z pliku — ale teraz są zawsze świeże, bo są nadpisywane przez krok 2 zaraz po każdej zmianie klasyfikacji. (Alternatywa — przełączenie backendu na liczenie na żywo jak Streamlit — odrzucona na tym etapie: duplikowałaby wywołanie ciężkiej funkcji przy każdym request-cie API zamiast raz na turę pracy; do rozważenia później, jeśli świeżość "na żądanie" okaże się konieczna.)

## Deliverable — plik XLSX dla opiekunów

Jedna funkcja eksportu (używana i przez przycisk "Pobierz" w Streamlicie, i przez `/q4/actions.xlsx`), trzy arkusze:

- **"Do dzwonienia"** — wszystkie rekordy z pewną branżą i dopasowaną sezonowością (`q4_priority` w {HIGH, MEDIUM_HIGH, LOW_Q4} — nie tylko ścisły Q4), posortowane po `action_score`/`action_tier` malejąco. Kolumny zgodne z `PLAN_CUSTOMER_CARE_LEADSEASON.md`: `account_owner`, `id`/`client_id`, `detail_id`, `nip`, `company`, `domain`, `monthly_value`, `branza_glowna`, `podbranza`, `season_peak`, `contact_start`, `q4_priority`, `sugerowana_akcja`/`lead_reason`, `classification_confidence`/`ai_confidence`.
- **"Do weryfikacji"** — pozostałe rekordy (`q4_priority = DO_WERYFIKACJI`), jako transparentny backlog na kolejne fale, nie ukrywany.
- **"Podsumowanie managera"** — liczby per opiekun, per branża, per segment/MRR, suma MRR w puli, rozkład confidence, liczba rekordów do weryfikacji — zgodnie z sekcją "Widok managera" w `PLAN_CUSTOMER_CARE_LEADSEASON.md`.

## Testy / walidacja

1. **Spot-check jakości Strumienia A** — ręczna weryfikacja próbki ~40-50 rekordów z nowej klasyfikacji (A1+A2) przed uznaniem fali za zamkniętą.
2. **Regresja liczbowa Strumienia B** — po uruchomieniu `rebuild_consolidated_signals.py` porównać rozkład HIGH/MEDIUM_HIGH/LOW_Q4/DO_WERYFIKACJI z niezależnym przeliczeniem w osobnym skrypcie kontrolnym (ta sama dyscyplina, która dziś wykryła i wyjaśniła rozbieżność 3917 vs 4158).
3. **Przegląd próbki finalnego eksportu** — ręczne sprawdzenie kilkunastu wierszy z arkusza "Do dzwonienia" pod kątem sensowności `sugerowana_akcja`/`lead_reason` i poprawności danych klienta (opiekun, NIP, MRR).

## Kolejne kroki po tym planie (nie w zakresie)

- Prawdziwa logika upsell: `branża + obecny pakiet (kod_pakietu/service) → konkretny produkt WeNet do zaproponowania`, zamiast dzisiejszych generycznych szablonów `sugerowana_akcja`.
- Pilotaż z realnymi opiekunami + Voice AI jako miara skuteczności kontaktu.
- Moduł Avaya + CRM2 Contact Penetration (opisany w `PLAN_CUSTOMER_CARE_LEADSEASON.md` jako etap późniejszy).
- Ewentualny atak na pulę `NOT_FOUND` (2045 rekordów), jeśli po Strumieniu A pokrycie i tak wypadnie poniżej 70%.
