# Status projektu — dla każdego agenta podejmującego pracę

Ten plik to bieżący stan repo, aktualizowany przez każdego agenta (Claude/Codex/inny), który tu pracuje. Cel: żeby kolejna sesja nie musiała odtwarzać kontekstu od zera i nie nadepnęła na coś, co już zrobił ktoś inny.

**Ostatnia aktualizacja:** 2026-08-06, Claude (Claude Code) — Krok 6 (infrastruktura wysyłki, `outreach/send/`) ZROBIONY i wypchnięty (`e60f747`). Zweryfikowany REALNĄ wysyłką przez Resend na własny adres usera (nie na realnego leada). Dev DB wyczyszczona z danych testowych "Andruszkiewicz Aleksander" (artefakt jakości danych z CSV). Pełny zestaw testów: 37/37 przechodzi.

## Kontekst: co to jest to repo

Dwa flow żyją w tym repo, jeden nadrzędny nad drugim:

- **`STRATEGIA_SYSTEM_POZYSKIWANIA_LEADOW.md`** — GŁÓWNY, nadrzędny flow: system pozyskiwania klientów dla ai-ops.pl (audyt → AI → głos/wideo → outreach → konwersja), opisany w sekcji 12 jako kolejność kroków 1-13. **To jest właściwy cel tego repo obecnie.**
- Oryginalne narzędzie LeadSeason (crawler + taksonomia branż + Q4 Customer Care pipeline dla WeNet — `bulk_crawler.py`, `bulk_app.py`, `backend/data_service.py`) — to tylko **poboczny wątek sezonowości**, jeden z sygnałów wykorzystywanych WEWNĄTRZ większego flow ze STRATEGII, nie odwrotnie.

## ✅ Zrobione (kroki 1-5 sekcji 12 STRATEGIA_SYSTEM_POZYSKIWANIA_LEADOW.md)

Wszystko w module `outreach/` + `backend/microapp.py` + `scripts/*.py`, zwalidowane na realnych domenach klientów WeNet (nie na atrapach):

1. **Baza danych** (`outreach/models.py`, `repository.py`, `schemas.py`) — Lead, AuditResult, ConsentEvent, OutreachEvent, LeadScoreEvent, MicroAppVisit, VoiceNarration. SQLite lokalnie, Postgres przez `LEADGEN_DATABASE_URL`.
2. **Moduł audytu** (`outreach/audits/`) — SEO on-page (własna implementacja, zamiennik `seonaut` bo brak Dockera/Go), PageSpeed Insights (wymaga `GOOGLE_PAGESPEED_API_KEY`), Senuto matrix loader.
3. **AEO/GEO** (`outreach/audits/aeo_geo.py`) — cytowalność w AI przez pakiet PyPI `geo-optimizer-skill`, bez kluczy API.
4. **Mikro-apka per-lead** (`backend/microapp.py`, `/audyt/{slug}`) — progressive disclosure + gate ze zgodą RODO, zweryfikowane end-to-end w realnej przeglądarce.
5. **Moduł głosu** (`outreach/voice/`) — narracja audytu + ElevenLabs TTS, zweryfikowane realną syntezą audio (klucz w `.env`, gitignored).

Commit: `3705eb7` na `main` (obejmuje też niepowiązane zmiany sprzed tej sesji: SSRF guard w `bulk_crawler.py`, X-API-Key auth w `backend/api.py`, ujednolicenie pipeline'ów Q4 w `data_service.py`, nowe kategorie branż w `config/`).

## ✅ Priorytet #1 ZROBIONY (2026-08-05): panel operatora / dashboard

`backend/dashboard.py`, zamontowany w `backend/api.py` (`/dashboard` + `/api/dashboard`), server-rendered Python jak `microapp.py` (decyzja usera: ten stack, nie Streamlit, nie Next.js — spójność z resztą repo, zero nowego toolchaina).

- `GET /dashboard` — lista wszystkich leadów: firma/domena, branża, **wyliczony na żywo etap pipeline'u** (Nowy → Zaudytowany → Zarejestrowany (gate) → Kontakt wysłany — `Lead` nie ma kolumny `status`, mimo że AGENT.md ją przewidywał; liczy się obecność powiązanych rekordów, nie pole w bazie), tier, score, skróty ostatnich audytów, ✅/— zgody.
- `GET /dashboard/{lead_id}` — pełna historia: audyty (typ/score/podsumowanie/data), zgody RODO/art.172, historia scoringu, aktywność w mikro-apce, narracja głosowa z odtwarzaczem (`<audio>`, serwowane przez `GET /dashboard/{lead_id}/audio`).
- `POST /dashboard/{lead_id}/run-audit` — SEO on-page + AEO/GEO + Senuto zawsze, PageSpeed jeśli jest klucz; za `require_api_key` (przeniesiony do `backend/auth.py`, żeby uniknąć circular importu z `backend/api.py`).
- `POST /dashboard/{lead_id}/generate-voice` — ElevenLabs, gracefully pomija z komunikatem flash jeśli brak klucza/limit przekroczony.
- Zweryfikowane end-to-end w realnej przeglądarce na PRAWDZIWYCH danych z wcześniejszych sesji (leady z `scripts/validate_audit_module.py`, w tym jeden zarejestrowany przez gate z prawdziwą narracją audio 574KB) — działa. Testy: `tests/test_dashboard.py` (5, izolowana in-memory SQLite przez `dependency_overrides`).
- **Odkryte przy tej okazji, wizualnie**: lead `hts.com.pl` ma 3x zduplikowany `ConsentEvent` + 3x `+15` scoringu z tego samego gate'a — to dokładnie bug idempotencji z `backend/microapp.py::audyt_gate()` opisany w sekcji "🟡 Priorytet #2" poniżej, teraz widoczny na własne oczy, nie tylko w code review.

## ✅ Priorytet #2 ZROBIONY (2026-08-05): findings z `/code-review` (commit `3705eb7`)

9 z 10 potwierdzonych (CONFIRMED) problemów naprawionych w `81588b9`, 1 okazał się już nieaktualny. Wszystkie zweryfikowane realnym testem (nie tylko czytaniem kodu), pełny zestaw testów (37) przechodzi.

**Bezpieczeństwo — NAPRAWIONE:**
- `outreach/audits/seo_onpage.py` — teraz fetchuje przez `bulk_crawler.fetch_url()` (rewaliduje `is_safe_url()` na każdym hopie przekierowania) zamiast `requests.get(allow_redirects=True)`. Zweryfikowane atakiem: mockowy serwer przekierowujący na `169.254.169.254` — teraz blokowany.

**Integralność danych / RODO — NAPRAWIONE:**
- `backend/microapp.py::audyt_gate()` — zgoda zapisywana PRZED PII, `has_valid_consent()`/`lead.tier` jako idempotency-guard. Zweryfikowane: 3x submit → 1 zgoda, 1 zdarzenie scoringu, score=15 (nie 45). Wyczyszczono istniejące duplikaty na `hts.com.pl` w dev DB.
- `outreach/repository.py::create_lead()` — retry na `IntegrityError` przy kolizji sluga.
- `outreach/repository.py::record_score_event()` — atomowy SQL `UPDATE` zamiast odczyt-modyfikacja-zapis w Pythonie.
- `outreach/repository.py::get_lead_by_domain()`/`create_lead()` — normalizacja przez `bulk_crawler.domain_key()`. Dodano `backfill_domains()`, uruchomione na dev DB (8 leadów, 0 kolizji).
- `outreach/audits/senuto.py` — dopasowanie przez `normalize_key()` (NFKD) zamiast `.strip().lower()`. Zweryfikowane: "Księgowość" dopasowuje "Ksiegowosc".

**Kod sprzed tej sesji — NAPRAWIONE / już nieaktualne:**
- `backend/data_service.py::q4_summary()` — przywrócony priorytet `domain_key` nad `domain`.
- `bulk_crawler.py::fetch_url()` — opisowy błąd `"Too many redirects (>N)"` zamiast `ok=False, error=""`. Zweryfikowane mockiem pętli przekierowań.
- `bulk_app.py`'s `q4_exclusion_window` + `today` — **już nieaktualne**: merge z drugą sesją wyeliminował osobną funkcję `q4_exclusion_window()`, `today` jest teraz bezpośrednim parametrem `build_q4_customer_care_base_from_leads()` i działa poprawnie (zweryfikowane bezpośrednim testem).

**Wydajność — NAPRAWIONE:**
- `outreach/audit_utils.py::latest_audits_by_type()` — przyjmuje opcjonalny `db: Session`, wtedy odpytuje tylko najnowszy wiersz per `audit_type` (subquery z `max(created_at)`) zamiast ładować całą historię audytów. Przełączone wszystkie 5 miejsc wywołania (`backend/microapp.py` x3, `backend/dashboard.py` x2, `outreach/voice/script.py`). Zweryfikowane: identyczny wynik jak stara ścieżka.

## ✅ Krok 6 ZROBIONY (2026-08-06): infrastruktura wysyłki (`outreach/send/`)

- `email.py` — klient Resend (`RESEND_API_KEY`, ten sam dostawca co `startupai`).
- `outreach_email.py` — buduje temat/HTML z tego samego `pick_hook()` co mikro-apka (przeniesiony do `outreach/audit_utils.py`, żeby oba kanały nie rozjechały się w treści), dołącza narrację głosową jeśli istnieje, zawsze loguje próbę jako `OutreachEvent`.
- `scripts/send_outreach_email.py --slug ... --to ... [--dry-run]` + akcja w dashboardzie (pole na adres, nie wypełnione automatycznie — to infrastruktura testowa, nie masowa wysyłka).
- **Zweryfikowane REALNĄ wysyłką** przez Resend na własny adres użytkownika (Resend id potwierdzone), nie na realnego leada — sekcja 9 (RODO/cold-mail) wciąż wymaga osobnej decyzji przed wysyłką do prawdziwych firm.
- Przy okazji wyczyszczono dev DB z 8 leadów testowych o błędnej nazwie "Andruszkiewicz Aleksander" (artefakt danych z `output/full_test_50.csv` — pole `company` trzymało nazwisko właściciela konta, nie nazwę firmy) i utworzono jednego czystego leada testowego (`HTS Klimatyzacja`, domena hts.com.pl) do weryfikacji.

**Drobna, nienaprawiona usterka treści** (nie w logice, w copy): nagłówek dla ścieżki SEO w `pick_hook()` (`outreach/audit_utils.py`) mówi "Znaleźliśmy konkretne braki" nawet przy wyniku 100/100 bez żadnych problemów — kosmetyczne, do poprawy przy okazji.

## Jak kontynuować

1. Sprawdź `git status`/`git log` — repo jest aktywnie współdzielone z innymi sesjami/agentami.
2. Kroki 1-6 + dashboard + wszystkie code-review findings są gotowe i na origin/main. Kolejny naturalny krok: moduł wideo (`OpenMontage`, dopiero po potwierdzeniu konwersji), klonowanie głosu (Instant Voice Cloning, plan Starter 5 USD), orkiestracja n8n — nierozpoczęte. Realna kampania wysyłkowa na prawdziwych leadach wymaga osobnej decyzji usera o zakresie/zgodach (sekcja 9).
3. Nie commituj/pushuj bez wyraźnej prośby użytkownika.
