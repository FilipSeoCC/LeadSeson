# Places-first klasyfikacja branż — design

## Problem

Obecna klasyfikacja branż (`ai_branza_glowna`/`ai_podbranza`) opiera się głównie na treści zeskrapowanej strony WWW i jest zawodna: strony bywają wieloznaczne, SEO-tekstowe albo puste wizytówki bez realnej treści o działalności. Przykład potwierdzony w praniu: `higienika.eu` — AI sklasyfikowało jako "Nieruchomości / Biuro nieruchomości", podczas gdy Google Places ze 100% pewnością dopasowania (domain+name+primaryType) zwraca "Firma sprzątająca... Higienika Sp. z o.o.".

Sprawdzona alternatywa (automatyczne mapowanie `google_type → branża` z tabeli w `config/leadseason_seasonality_matrix.csv`) nie wystarcza jako samodzielny mechanizm wykrywania konfliktów: tabela ma tylko 39 typów Google, a w próbce 150 domen 8 z 10 zwróconych typów (`service`, `store`, `supplier`, `consultant`, `health`, `funeral_home`, `clothing_store`, `sporting_goods_store`) w ogóle nie jest w niej ujętych.

Dodatkowo: z 4163 unikalnych domen w aktywnej bazie tylko 938 (22,5%) ma jakąkolwiek wartość `ai_branza_glowna` — 3225 domen (77,5%) nie ma klasyfikacji branży w ogóle. To nie jest tylko problem "weryfikacji niepewnych przypadków", tylko brakującego pokrycia większości bazy.

## Decyzja (potwierdzona przez użytkownika)

Zamiana kolejności procesu:

- **Stary proces:** AI klasyfikuje branżę z treści strony → Places API weryfikuje tylko część rekordów (niepewne/niskiej pewności).
- **Nowy proces:** Google Places/GMB dla **całej bazy** (nie tylko rekordów bez klasyfikacji) → LLM klasyfikuje/reklasyfikuje branżę, mając dane z Places (nazwa firmy, `primaryType`, adres) jako **główny dowód**, a treść zeskrapowanej strony jako dowód **pomocniczy**.

Uzasadnienie: Places to ustrukturyzowane dane samego Google o realnej działalności firmy, dużo mniej podatne na dwuznaczności niż tekst SEO ze strony. Test na 150 domenach: 143/150 (95,3%) OK match, średnia pewność dopasowania 70,8.

## Zakres

- **Pre-filtr przed Places (potwierdzone przez użytkownika — wykluczenie na tym etapie, nie tylko na etapie listy kontaktowej Q4):** pomijamy domeny, których `end_date` wypada w H2 bieżącego roku (1 lipca – 31 grudnia) lub jest już w przeszłości — to ten sam warunek, który dziś stosuje `build_q4_customer_care_base_from_leads` (bulk_app.py:1137-1141) do wykluczania z listy kontaktowej Q4, tylko zastosowany wcześniej, przed pobraniem danych Places. Na dziś (2026-07-27) to **800 z 4163 domen (19,2%)** — zostaje **3363 domeny**.
  - Dodatkowo: **dłużnicy** — do wykluczenia analogicznie, gdy użytkownik dostarczy plik z listą (kolumna `status_zadluzenia` już istnieje w kodzie jako zaślepka `BRAK_DANYCH_W_PLIKU` — do podpięcia realnych danych po otrzymaniu pliku).
  - Świadomy koszt tej decyzji: klient, który odnowi umowę później, nie będzie miał świeżych danych Places/klasyfikacji i trzeba go będzie dorobić osobnym, mniejszym batchem w przyszłości.
- Pobranie danych Places dla pozostałych ~3363 domen aktywnej bazy (`leadseason_pelna_baza_po_llm_971.xlsx`), nie tylko dla 938 już sklasyfikowanych.
- Reklasyfikacja przez LLM **wszystkich** domen (z tych ~3363), dla których Places zwrócił `status: OK` — niezależnie od tego, czy miały już wcześniej `ai_branza_glowna`, czy nie. Stara etykieta AI nie jest traktowana jako wiarygodna domyślnie.
- Domeny z `places_status: NOT_FOUND` — klasyfikacja LLM na starych zasadach (tylko treść strony), tak jak dotychczas.

### Poza zakresem (osobne, niższy priorytet — potwierdzone wcześniej przez użytkownika)
- Rozszerzenie długiego ogona Senuto (424 z 449 grup wciąż nieprzejrzanych) — osobny wątek po zakończeniu tego.
- Rozbudowa tabeli 39 `google_type` w `config/leadseason_seasonality_matrix.csv` — nieopłacalna: pokazane wyżej, że i tak trzeba przechodzić przez LLM, więc rozbudowa tabeli nie odciąży kosztu w sposób, który uzasadniałby utrzymanie.

## Proces krok po kroku

1. **Pre-filtr wykluczeń.** Odfiltrować z bazy domeny z `end_date` w H2 bieżącego roku lub już przeszłym oraz (jeśli dostarczony plik) dłużników — patrz Zakres wyżej. Wynik: lista ~3363 domen kwalifikujących się do Places.
2. **Places API — przefiltrowana baza.** Uruchomić `apply_places_enrichment()` na ~3363 domenach (batche, z cache w `cache/places/`, żeby nie płacić drugi raz za już pobrane — test 150-domenowy już w cache). 
3. **Kontrola kosztu przed pełnym uruchomieniem.** Sprawdzić rzeczywisty koszt rozliczony przez Google za test 150 domen (Google Cloud Console → Billing) i ekstrapolować na pozostałe ~3213, zanim ruszy pełny batch — nie zakładać ceny "na oko".
4. **LLM reklasyfikacja z Places jako głównym dowodem.** Dla rekordów z `places_status: OK`: prompt do LLM zawiera `places_name`, `places_primary_type`, `places_address` jako główny dowód + skrócony fragment treści strony jako pomocniczy kontekst. Wynik nadpisuje `ai_branza_glowna`/`ai_podbranza`/`ai_confidence` (stara wartość nie jest już auto-trusted).
5. **Rekordy NOT_FOUND** — klasyfikacja LLM po staremu (sama treść strony), bez zmian w tym kroku.
6. **Downstream bez zmian.** Reszta pipeline'u (dopasowanie do macierzy sezonowości Senuto, `build_seasonal_leads`, dashboard) korzysta z `ai_branza_glowna`/`ai_podbranza` tak jak dziś — nie wymaga zmian, bo tylko **źródło** tych dwóch kolumn się zmienia, nie ich schemat.

## Ryzyka / otwarte pytania
- Koszt Places API dla ~3213 pozostałych domen (po pre-filtrze) nieznany dopóki nie sprawdzimy rzeczywistego rozliczenia za próbkę 150 (krok 3 wyżej) — to jest twardy warunek przed uruchomieniem pełnego batcha, nie formalność.
- Koszt LLM rośnie, bo reklasyfikacji podlega cała przefiltrowana baza z Places OK (szacunkowo ~95% z ~3363 = ok. 3195 domen), a nie tylko 938 już sklasyfikowanych — do zaakceptowania jako świadomy koszt tej decyzji.
- Klienci wykluczeni pre-filtrem (koniec umowy w H2 / już zakończona) nie dostaną świeżych danych Places/klasyfikacji teraz — jeśli odnowią umowę, trzeba ich dorobić osobnym, mniejszym batchem później.
- Dane o dłużnikach jeszcze nie dostarczone — filtr do dopięcia po otrzymaniu pliku od użytkownika.
