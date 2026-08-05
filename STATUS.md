# Status projektu — dla każdego agenta podejmującego pracę

Ten plik to bieżący stan repo, aktualizowany przez każdego agenta (Claude/Codex/inny), który tu pracuje. Cel: żeby kolejna sesja nie musiała odtwarzać kontekstu od zera i nie nadepnęła na coś, co już zrobił ktoś inny.

**Ostatnia aktualizacja:** 2026-08-05, Claude (Claude Code) — dashboard operatora dodany, patrz sekcja poniżej.

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

## 🟡 Priorytet #2: naprawić findings z `/code-review` (commit `3705eb7`) — jeszcze NIE naprawione

High-effort review (8 kątów + weryfikacja), 10 potwierdzonych (CONFIRMED) problemów. Nieposortowane wg pliku:

**Bezpieczeństwo (najwyższy priorytet z tej listy):**
- **`outreach/audits/seo_onpage.py:56,122`** — SSRF przez przekierowanie HTTP. `requests.get(..., allow_redirects=True)` nie rewaliduje `is_safe_url()` na każdym hopie przekierowania (w przeciwieństwie do `bulk_crawler.fetch_url()` w tym samym commicie, który to robi poprawnie manualną pętlą). Crawlowana domena może przekierować na `169.254.169.254` (cloud metadata) albo `localhost` i moduł to wykona bez drugiego sprawdzenia.

**Integralność danych / RODO (`backend/microapp.py`, `outreach/repository.py`):**
- `backend/microapp.py` `audyt_gate()` (~linia 299) — brak idempotencji: ponowny submit formularza duplikuje `ConsentEvent` i dodaje `+15` do `lead_score` za każdym razem. `db.commit()` (linia 311) zapisuje `tier`/PII PRZED zapisaniem zgody (linia 313) — błąd bazy w tym oknie zostawia dane kontaktowe bez zgody.
- `outreach/repository.py` `_unique_slug()`/`create_lead()` (~linia 15) — race condition check-then-insert, dwa równoczesne requesty dla tej samej nazwy firmy mogą crashnąć na `IntegrityError`.
- `outreach/repository.py` `record_score_event()` (~linia 114) — odczyt-modyfikacja-zapis bez blokady, równoczesne wywołania mogą zgubić inkrement wyniku.
- `outreach/repository.py` `get_lead_by_domain()`/`create_lead()` (~linia 39) — brak normalizacji domeny (istnieją `normalize_domain()` w `bulk_crawler.py` i `_normalize_domain()` w `data_service.py`, nieużyte) → duplikaty leadów dla tej samej firmy pod różnymi wariantami URL.
- `outreach/audits/senuto.py:35` — dopasowanie branży przez `.strip().lower()` zamiast kanonicznego `normalize_key()` (NFKD, usuwa polskie diakrytyki) z `seasonality_matrix.py`/`taxonomy.py` → ciche brak-dopasowania przy różnicach w akcentach.

**W kodzie sprzed tej sesji (nie napisane przeze mnie, ale w tym samym commicie):**
- `backend/data_service.py:254` — `q4_summary()` liczy unikalne domeny po surowym polu `domain` zamiast kanonicznego `domain_key`, zawyżając liczniki per branża.
- `bulk_app.py:1087` — `q4_exclusion_window()` wywoływane bez argumentów wewnątrz `build_q4_customer_care_base_from_leads`, więc parametr `today` przekazany do `build_seasonal_leads` nie dociera do okna wykluczeń kontraktów.
- `bulk_crawler.py:573` — gdy pętla przekierowań wyczerpie `MAX_REDIRECTS=5`, `fetch_url()` zwraca `ok=False` z pustym `error=""` (bo `response.ok` jest `True` dla 3xx) — brak diagnostyki dlaczego się nie udało.

**Wydajność:**
- `outreach/audit_utils.py:9` `latest_audits_by_type()` — ładuje CAŁĄ historię audytów leada (razem z dużymi blobami `raw_data` JSON) przy każdym wejściu na `/audyt/{slug}` — publiczny hot path.

## Jak kontynuować

1. Sprawdź `git status`/`git log` — może ktoś już to naprawił.
2. Zdecyduj z userem: dashboard najpierw, czy najpierw poprawki (zwłaszcza SSRF) przed kolejnym pushem.
3. Nie commituj/pushuj bez wyraźnej prośby użytkownika.
