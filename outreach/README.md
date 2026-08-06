# outreach/ — baza danych systemu pozyskiwania leadów (ai-ops.pl)

Fundament (krok 1, sekcja 12) opisany w [`../STRATEGIA_SYSTEM_POZYSKIWANIA_LEADOW.md`](../STRATEGIA_SYSTEM_POZYSKIWANIA_LEADOW.md).
Osobny, niezależny store od pipeline'u Q4/Customer Care (`backend/data_service.py`,
CSV/XLSX) — ten moduł to "kręgosłup systemu" dla przyszłego audytu → AI → głos →
wideo → outreach → konwersja.

## Struktura

| Plik | Zawartość |
|---|---|
| `db.py` | silnik SQLAlchemy + sesja. SQLite domyślnie (`outreach/data/leadgen.db`), Postgres przez `LEADGEN_DATABASE_URL` |
| `models.py` | ORM: `Lead`, `AuditResult`, `ConsentEvent`, `OutreachEvent`, `LeadScoreEvent`, `MicroAppVisit` |
| `schemas.py` | Pydantic Create/Read — tu żyją dozwolone wartości kategoryczne (`Literal`) |
| `repository.py` | CRUD + `has_valid_consent()` |
| `init_db.py` | `python -m outreach.init_db` tworzy tabele |
| `audits/pagespeed.py` | Google PageSpeed Insights (**wymaga `GOOGLE_PAGESPEED_API_KEY`** — keyless ma limit 0/dzień od 2026) |
| `audits/seo_onpage.py` | Audyt on-page SEO (title/meta/H1/canonical/alt/robots/sitemap/viewport) — natywna implementacja zamiast forka `seonaut` (wymaga Docker/Go, niedostępne tutaj), pokrywa te same kategorie sprawdzeń |
| `audits/senuto.py` | Czyta istniejącą macierz sezonowości Senuto (`output/leadseason_macierz_sezonowosci_senuto.xlsx`) budowaną ręcznie w `bulk_app.py` — konektor Senuto MCP wymaga osobnej autoryzacji |
| `audits/aeo_geo.py` | Audyt AEO/GEO (cytowalność w AI) przez prawdziwy pakiet PyPI `geo-optimizer-skill` (MIT) — bez kluczy API, ~15-20s/domena |
| `voice/script.py` | Generator tekstu narracji (szablon Python, bez LLM) z danych audytu leada |
| `voice/elevenlabs_tts.py` | Klient ElevenLabs TTS (**wymaga `ELEVENLABS_API_KEY`** + uprawnienia "Głosy: Przeczytane" na kluczu) |
| `send/email.py` | Klient Resend (**wymaga `RESEND_API_KEY`**), ten sam dostawca co formularz audytu w repo `startupai` |
| `send/outreach_email.py` | Buduje treść maila outreachowego (insight-trigger + link do `/audyt/{slug}`) i wysyła, dołączając narrację głosową jeśli istnieje; zawsze loguje próbę jako `OutreachEvent` |

## Mapowanie schematu na strategię

- **`Lead`** — dane źródłowe (firma/domena/NIP/branża/sezonowość z LeadSeason), `tier` i `lead_score` (sekcja 4, 7D)
- **`AuditResult`** — jeden wiersz na moduł audytu (`seo`, `pagespeed`, `places`, `aeo_geo`, `senuto`, `seasonality`) — sekcja 2 i 6
- **`ConsentEvent`** — dokładna treść zgody + IP/UA jako dowód (sekcja 7C: gate w mikro-apce), `revoked_at` na wycofanie
- **`OutreachEvent`** — log każdego kontaktu (mail/SMS/wideo/telefon), `ai_generated`/`ai_disclosed` pod AI Act (sekcja 9)
- **`LeadScoreEvent`** — audit trail tierowania (rejestracja w gate = najsilniejszy sygnał → Tier 3)
- **`MicroAppVisit`** — tracking zachowania w mikro-apce per-lead (sekcja 7D)

## Ważne: bramka zgody (sekcja 9)

`repository.has_valid_consent(db, lead_id, consent_type)` **musi** być wywołane
przed każdą wysyłką SMS lub inicjacją połączenia głosowego — art. 172 Prawa
telekomunikacyjnego wymaga zgody dla obu kanałów. Nie duplikować tej logiki gdzie
indziej.

## Użycie

```powershell
pip install -r requirements.txt
python -m outreach.init_db
python scripts/verify_leadgen_schema.py   # smoke test pełnego round-tripu
```

## Walidacja modułu audytu (kroki 2–3)

```powershell
python scripts/validate_audit_module.py --limit 8 --skip-pagespeed
```

Uruchamia audyt on-page + AEO/GEO + próbę dopasowania Senuto na realnych
domenach z `output/full_test_50.csv` (istniejący crawl), zapisuje
`AuditResult` do bazy. Zweryfikowane 2026-08-05 na 8 realnych domenach
klientów WeNet:

- **SEO on-page**: 64–100/100, poprawnie różnicuje wg realnych braków
- **AEO/GEO** (`geo-optimizer-skill`): 18–53/100, wszystkie w paśmie
  "critical"/"foundation" — nikt z próbki nie ma podstaw pod cytowalność AI.
  Przykład sygnału z sekcji 6: `deltacon.eu` ma SEO 64/100 ale AEO/GEO tylko
  **18/100 "critical"** — rozjazd między klasycznym SEO a gotowością pod AI
  to dokładnie ten hak outreachowy z dokumentu strategii.
- `--skip-aeo` pomija ten krok (każda domena ~15-20s, bez limitu zapytań)

`--skip-pagespeed` bo `GOOGLE_PAGESPEED_API_KEY` nie jest jeszcze ustawiony —
zdobądź darmowy klucz (Google Cloud Console → włącz "PageSpeed Insights API" →
Poświadczenia → API key) i dopisz do `.env`, żeby przetestować ten moduł.

Senuto nie zwróciło dopasowań w tym przebiegu, bo `output/leadseason_macierz_
sezonowosci_senuto.xlsx` jeszcze nie istnieje lokalnie — trzeba raz uruchomić
workflow "Zasilenie danych → Sezonowość" w `bulk_app.py`, żeby go zbudować.

## Mikro-apka per-lead (krok 4)

`backend/microapp.py` — server-renderowana (bez osobnego frontend toolchaina,
ten sam wzorzec co `LANDING_HTML` w `backend/api.py`):

```
GET  /audyt/{slug}        — strona z progressive disclosure (sekcja 7A/7B)
POST /audyt/{slug}/track  — zdarzenia MicroAppVisit (sekcja 7D)
POST /audyt/{slug}/gate   — gate ze zgodą (sekcja 7C)
```

`Lead.slug` generowany z `company_name` (`outreach/slug.py`, usuwa "Sp. z o.o."
itp., diakrytyki -> ASCII, kolizje -> numeryczny sufiks). Nowe leady dostają
slug automatycznie w `create_lead()`; istniejące wiersze sprzed tej zmiany
wymagają jednorazowego `repository.backfill_slugs(db)`.

Insight-trigger (nagłówek) wybierany wg priorytetu: AEO/GEO (sekcja 6 —
potencjalnie mocniejszy trigger) → sezonowość (`Lead.season_peak`) → SEO
on-page → generyczny fallback.

Gate: pola e-mail + telefon w jednym kroku, checkbox zgody **domyślnie
odznaczony**, dokładna treść zgody (nie ogólne "przetwarzanie danych"). Po
zapisaniu zgody: `Lead.tier` -> 3, `+15` do `lead_score`
(`registered_via_gate`), `ConsentEvent(contact_phone_sms)` z IP/user-agent
jako dowód. Endpoint zwraca pełny raport dopiero w odpowiedzi na udaną
rejestrację — żadne dane z "zamkniętej" części nie trafiają do klienta przed
zgodą (inaczej niż zwykłe blur-w-CSS, które i tak wysyła dane z góry).

Zweryfikowane 2026-08-05 end-to-end w prawdziwej przeglądarce (Chrome przez
Claude Browser pane): strona się renderuje, gate odsłania się przez
`IntersectionObserver`, formularz + checkbox + submit działają, dane trafiają
do `ConsentEvent`/`LeadScoreEvent`/`MicroAppVisit`/`Lead.tier` w bazie.

**Świadomie pominięte na tym etapie**: double opt-in mailem (wymaga infry
wysyłki, której backend nie ma — `RESEND_API_KEY` żyje w repo `startupai`/
ai-ops.pl, nie tutaj), free-konto retencyjne (sekcja 7E), routing pod
faktyczną subdomenę `audyt.ai-ops.pl` (DNS/Vercel poza zakresem kodu).

Uruchomienie lokalnie: `python -m uvicorn backend.api:app --port 8010`, potem
`/audyt/{slug}` dla dowolnego leada z bazy (`python -c "from outreach.db import SessionLocal; from outreach import models; db=SessionLocal(); print([l.slug for l in db.query(models.Lead).all()])"`).

## Moduł głosu (krok 5)

`outreach/voice/` — narracja audytu jako audio (sekcja 3, ekonomia w sekcji
11: ~0,60 USD / audyt na planie Creator, pomijalne wobec CAC 1200–1800 zł).

- **`script.py`** — buduje tekst narracji po polsku z `Lead` + `AuditResult`.
  Deterministyczny szablon, nie wywołanie LLM — moduł 2 dokumentu ("Claude API
  — narracja audytu z JSON-a") to osobny, jeszcze niezbudowany krok; ten
  szablon wystarcza, żeby przetestować jakość/koszt samego ElevenLabs. Cytuje
  dosłownie tylko podsumowania z **naszych własnych, polskojęzycznych**
  audytów (`seo`, `senuto`, `seasonality`) — `aeo_geo`/`pagespeed` zwracają
  rekomendacje po angielsku (`geo-optimizer-skill`, PageSpeed), więc dla nich
  mówimy tylko wynik liczbowy, żeby nie wkleić angielskiego zdania w środek
  polskiej narracji TTS.
- **`elevenlabs_tts.py`** — `synthesize_narration()`, `get_usage()` (limit
  znaków), `list_voices()`. Wymaga `ELEVENLABS_API_KEY` **z uprawnieniem
  "Głosy: Przeczytane"** włączonym na kluczu (domyślnie wyłączone w panelu
  ElevenLabs — bez niego `list_voices()`/`get_usage()` zwracają 401).
- **`scripts/generate_voice_narration.py --slug <slug>`** — pełny pipeline:
  buduje narrację, sprawdza pozostały limit znaków PRZED wysyłką (przerywa,
  jeśli tekst by go przekroczył), syntezuje, zapisuje `.mp3` do
  `outreach/data/audio/`, loguje w `VoiceNarration`. `--dry-run` pokazuje sam
  tekst bez wywołania API.

**Ważna pułapka odkryta 2026-08-05**: domyślny `DEFAULT_VOICE_ID` z przykładów
w dokumentacji ElevenLabs ("Rachel", `21m00Tcm4TlvDq8ikWAM`) jest
przestarzały i zwraca `402 paid_plan_required` — wygląda jak blokada planu
darmowego, a to tylko nieaktualne ID spoza aktualnej biblioteki konta. Zawsze
pobieraj `voice_id` przez `list_voices()` dla konkretnego konta. Po
przełączeniu na potwierdzony działający głos ("Adam", `pNInz6obpgDQGcFmaJgB`)
TTS przez API **działa na darmowym planie** (10 000 znaków/miesiąc, bez
klonowania) — zweryfikowane realną syntezą polskiego tekstu (64 827 bajtów
MP3, 502 znaki zużyte z limitu).

`total_voice_characters_used(db)` w `repository.py` sumuje zużycie ze
wszystkich dotychczasowych syntez — porównaj z darmowym limitem przed
większym testem wsadowym.

## Wysyłka outreachowa (krok 6)

`outreach/send/` — infrastruktura do testu wysyłki (mail+audio, sekcja 12
krok 8/"6" w kolejności tego repo), **NIE do wysyłki na realnych leadów bez
osobnej decyzji o zgodzie/RODO** (sekcja 9).

- **`email.py`** — klient Resend (`send_email()`), ten sam dostawca co
  formularz audytu w `startupai`. Wymaga `RESEND_API_KEY`; `RESEND_FROM_EMAIL`
  opcjonalny (domyślnie `AI-Ops <kontakt@ai-ops.pl>`).
- **`outreach_email.py`** — `build_outreach_email(lead, db)` (temat+HTML z
  tego samego `pick_hook()` co mikro-apka, link do `/audyt/{slug}`) i
  `send_outreach_email_for_lead(db, lead, to_email)`. Automatycznie dołącza
  najnowszą narrację głosową jako załącznik jeśli istnieje dla leada
  (przybliżenie Tier 2 z sekcji 4 bez czekania na osobny etap tierowania).
  **Zawsze** loguje próbę jako `OutreachEvent(channel="email", status="sent"|
  "failed")` — nawet przy błędzie, żeby mieć ślad audytowy. AI Act (sekcja 9):
  `ai_generated=True`, `ai_disclosed=True`, jawna wzmianka w treści maila.
- **`scripts/send_outreach_email.py --slug ... --to ... [--dry-run]`** —
  `pick_hook()` w `outreach/audit_utils.py` (przeniesiony tu z
  `backend/microapp.py`, żeby mikro-apka i mail używały tego samego haka).

`MICROAPP_BASE_URL` (domyślnie `http://localhost:8010`) generuje link w
mailu — ustawić na publiczny URL przy realnym wdrożeniu.

Podpięte też jako akcja w dashboardzie (`POST /dashboard/{lead_id}/send-email`)
z polem na adres — domyślnie puste, operator wpisuje adres testowy ręcznie.

## Co dalej (sekcja 12)

Kroki 1–6 gotowe. Krok 6 (wysyłka) zbudowany jako infrastruktura testowa —
realny test na małej próbie wymaga decyzji usera o zakresie/zgodach przed
wysyłką do prawdziwych leadów. Kolejne kroki: moduł wideo (`OpenMontage`)
dopiero po potwierdzeniu konwersji, klonowanie głosu (Instant Voice Cloning,
plan Starter 5 USD) jeśli test na premade voice wypadnie dobrze, orkiestracja
n8n spinająca całość.

`geo citations` (podkomenda pakietu `geo-optimizer-skill`, realne zapytania do
ChatGPT/Perplexity/Anthropic sprawdzające czy marka jest faktycznie cytowana,
wymaga płatnych kluczy API) jest świadomie poza zakresem — dopiero gdy lejek
zacznie działać na sygnałach technicznych z tego modułu.

Ten schemat nie ma jeszcze warstwy API (FastAPI routera) ani migracji (Alembic)
— na tym etapie `Base.metadata.create_all()` wystarcza. Dodać Alembic, gdy
pierwsza zmiana schematu będzie musiała zachować istniejące dane produkcyjne.
