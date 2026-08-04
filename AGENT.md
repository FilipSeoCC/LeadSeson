# AGENT.md — Specyfikacja dla agenta-developera LeadSeason Acquisition

> Ten plik jest instrukcją dla agenta AI pełniącego rolę developera projektu.
> Kontekst biznesowy i uzasadnienie decyzji: `STRATEGIA_SYSTEM_POZYSKIWANIA_LEADOW.md`.
> Ten plik opisuje **co i jak zbudować**. Tamten opisuje **dlaczego**.

---

## 0. Rola agenta

Jesteś głównym developerem systemu pozyskiwania leadów nadbudowanego na istniejącym repo LeadSeason (moduł sezonowości).

**Zasady pracy:**
- Buduj przyrostowo, faza po fazie. Nie zaczynaj fazy N+1 przed działającą fazą N.
- Każda faza kończy się działającym, testowalnym artefaktem — nie szkieletem.
- Preferuj integrację gotowego OSS nad pisaniem od zera, ale **czytaj licencje** (patrz §9).
- Wszystkie sekrety w `.env`, nigdy w repo. Rozszerzaj istniejący `.env.example`.
- Kod i komentarze po angielsku. Treści generowane dla klienta (audyty, maile, narracja) po polsku.
- Po każdej fazie: aktualizuj `README.md` i dopisz sekcję do `CHANGELOG.md`.

---

## 1. Cel systemu

Zautomatyzowany pipeline: **dane o firmie → audyt AI → mikro-aplikacja → outreach → kwalifikacja leada**.

Kluczowy insight architektoniczny: **produktem końcowym nie jest PDF ani wideo, tylko spersonalizowana mikro-aplikacja pod unikalnym URL-em**, która sama kwalifikuje leada przez tracking zachowania i gate rejestracyjny.

---

## 2. Architektura docelowa

```
┌─────────────────────────────────────────────────────────┐
│  INGEST          Lista firm (CSV / Places / scraper)     │
└────────────────────────┬────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────┐
│  COLLECTORS      seonaut · PageSpeed · Senuto MCP        │
│  (Faza 1–2)      GEO/AEO · Places · Playwright shots     │
└────────────────────────┬────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────┐
│  CORE DB         leads · audits · insights · events      │
│  (Faza 0)        Postgres + Prisma/SQLAlchemy            │
└────────────────────────┬────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────┐
│  INSIGHT ENGINE  Claude API → ranking + narracja         │
│  (Faza 3)        seasonality_matrix.py (istniejący)      │
└────────────────────────┬────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────┐
│  MICRO-APP       Next.js /audyt/[slug]                   │
│  (Faza 4)        hook → progressive disclosure → gate    │
└────────────────────────┬────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────┐
│  OUTREACH        SES mail + ElevenLabs audio             │
│  (Faza 5–6)      tracking → scoring → tier 1/2/3         │
└────────────────────────┬────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────┐
│  VIDEO + ORCH    OpenMontage · n8n · IMAP monitor        │
│  (Faza 7–8)                                              │
└─────────────────────────────────────────────────────────┘
```

---

## 3. Stack — decyzje wiążące

| Warstwa | Wybór | Uzasadnienie |
|---|---|---|
| Baza | **PostgreSQL** | JSONB pod surowe payloady z API, relacje pod eventy |
| Backend | **Python 3.11 + FastAPI** | Zgodność z istniejącym repo (`bulk_app.py`, `taxonomy.py`) |
| ORM | **SQLAlchemy + Alembic** | Migracje wersjonowane |
| Mikro-apka | **Next.js 14 (App Router) + TypeScript** | SSR pod dynamiczne `/audyt/[slug]`, SEO-safe, łatwy deploy |
| Wykresy | **Recharts** (front) / **matplotlib** (PDF) | Recharts = interaktywność, matplotlib = statyczny render |
| Styling | **Tailwind CSS** | Szybkość, spójność |
| Kolejka | **Celery + Redis** | Collectory są długie (crawl + Lighthouse), nie mogą blokować requestu |
| PDF | **WeasyPrint** | HTML→PDF, ten sam szablon co mikro-apka |
| LLM | **Claude API (Sonnet)** | Narracja audytu, klasyfikacja odpowiedzi |
| TTS | **ElevenLabs** (Starter→Creator) | ~2,40 zł/audyt, pomijalne |
| Mail | **Amazon SES** | ~0,10 USD/1000 |
| Orkiestracja | **n8n** (self-hosted) | Dopiero faza 8, nie na starcie |

---

## 4. Schemat bazy danych (Faza 0 — buduj to pierwsze)

```sql
-- Firma / lead
leads (
  id, slug UNIQUE, company_name, domain, nip,
  industry_code,           -- FK do taxonomy.py
  city, lat, lng,
  contact_email, contact_phone, contact_name,
  status,                  -- new|collecting|audited|sent|engaged|registered|contacted|won|lost
  tier,                    -- 1|2|3
  score INT DEFAULT 0,
  consent_marketing BOOL DEFAULT false,
  consent_phone BOOL DEFAULT false,
  consent_timestamp, consent_ip,
  created_at, updated_at
)

-- Surowe dane z każdego collectora
audit_raw (
  id, lead_id FK, collector,   -- seonaut|pagespeed|senuto|geo|places|screenshots
  payload JSONB, collected_at, status, error_msg
)

-- Przetworzone insighty (to co trafia do apki)
insights (
  id, lead_id FK,
  type,        -- seasonality|aeo|technical|local|competitive
  severity,    -- critical|warning|info
  headline,    -- nagłówek-hak, max 90 znaków
  body,        -- narracja
  metric_value, metric_unit,
  chart_data JSONB,
  rank INT,    -- kolejność wyświetlania; rank=1 to główny hook
  verified_by_human BOOL DEFAULT false
)

-- Tracking zachowania w mikro-apce
events (
  id, lead_id FK, session_id,
  event_type,  -- page_view|scroll_depth|chart_click|gate_shown|gate_submit|pdf_download|return_visit
  metadata JSONB, ip, user_agent, created_at
)

-- Historia outreachu
outreach (
  id, lead_id FK, channel,  -- email|sms|voice|video
  variant, subject, body, asset_url,
  sent_at, opened_at, clicked_at, replied_at,
  reply_classification      -- positive|negative|auto|question
)
```

**Indeksy:** `leads.slug`, `leads.status`, `events.lead_id`, `events.created_at`.

`slug` = `slugify(company_name)` + 4-znakowy hash domeny (unikalność + brak enumeracji cudzych audytów).

---

## 5. Fazy implementacji

### FAZA 0 — Fundament
- Schemat bazy + migracje Alembic
- FastAPI skeleton, healthcheck, `.env.example`
- `docker-compose.yml`: postgres + redis + api
- Model `Lead` z CRUD + import CSV
- **Definition of done:** można zaimportować 10 firm z CSV i odpytać je przez API

### FAZA 1 — Collectory podstawowe
Każdy collector = osobny moduł w `collectors/`, wspólny interfejs:

```python
class BaseCollector(ABC):
    name: str
    @abstractmethod
    async def collect(self, lead: Lead) -> dict: ...
    # zapisuje do audit_raw, nigdy nie rzuca wyjątkiem w górę —
    # zapisuje status='error' i error_msg
```

Kolejność:
1. `PageSpeedCollector` — Google PSI API, mobile + desktop, Core Web Vitals. Najprostszy, zacznij tu.
2. `SeonautCollector` — **`StJudeWasHere/seonaut` (MIT, Go)**. Uruchom jako osobny kontener w compose, odpytuj przez jego API/DB. Nie przepisuj na Pythona.
3. `SenutoCollector` — istniejące MCP. Widoczność, słowa kluczowe, konkurencja. Wykorzystaj `get_domain_statistics`, `get_competitors`, `get_keywords`.
4. `PlacesCollector` — Google Places API, dane GBP: rating, liczba recenzji, kategoria, zdjęcia, godziny.

**Definition of done:** dla 10 firm testowych każdy collector zwraca wypełniony `audit_raw`.

### FAZA 2 — Warstwa AEO/GEO (kluczowy różnicownik)
Integracja **`Auriti-Labs/geo-optimizer-skill`** (Python + MCP).

Sprawdzane:
- Czy domena jest cytowana w odpowiedziach ChatGPT / Perplexity / Gemini na kluczowe zapytania branżowe
- Obecność i poprawność `llms.txt`
- Schema markup / dane strukturalne
- Struktura treści pod ekstrakcję przez modele (nagłówki, FAQ, jednoznaczne odpowiedzi)

Zapytania testowe generuj z `taxonomy.py` + lokalizacji leada, np. `"najlepszy {branża} {miasto}"`, `"gdzie zrobić {usługa} w {miasto}"`.

**Output:** insight typu `aeo` z metryką „cytowalność X/10 zapytań" — to ma być mocny nagłówek-hak.

**Definition of done:** dla firmy testowej system zwraca konkretną liczbę: w ilu zapytaniach AI wymienia tę firmę, a w ilu konkurencję.

### FAZA 3 — Insight Engine
1. Agregacja `audit_raw` → jeden znormalizowany kontekst JSON
2. Wpięcie istniejącego `seasonality_matrix.py` → insight `seasonality` (ile tygodni do szczytu sezonu, luka widoczności)
3. Claude API: kontekst → 3–5 insightów z `headline`, `body`, `severity`, `chart_data`
4. Ranking: `rank=1` dostaje najmocniejszy hak — priorytet **AEO > sezonowość > krytyczne błędy techniczne > lokalne**
5. Flaga `verified_by_human` + prosty panel do zatwierdzania (może być CLI w tej fazie)

**Prompt engineering — twarde reguły dla LLM:**
- Zakaz halucynacji: każda liczba musi pochodzić z `audit_raw`, nigdy z modelu. Jeśli brak danych → pomiń insight, nie zgaduj.
- Nagłówek max 90 znaków, konkret + liczba, nigdy generyk („Twoja strona ma problemy" = źle)
- Ton: ostrzeżenie przed stratą, nie sprzedaż
- Porównanie do konkurencji zamsze gdy dostępne dane

**Definition of done:** dla 10 firm generuje się po 3–5 sensownych, niehalucynowanych insightów.

### FAZA 4 — Mikro-aplikacja
Next.js, route `/audyt/[slug]`, SSR z API.

Struktura strony:
```
[SEKCJA 1 — OTWARTA]
  Nagłówek = insights[rank=1].headline
  Jeden wykres (najmocniejszy)
  Krótka narracja
  ↓ scroll
[SEKCJA 2 — OTWARTA]
  Drugi insight, wykres
  ↓ scroll  → tu triggeruje gate
[GATE]
  „Zobacz pełną analizę (X błędów, plan naprawczy, porównanie do 3 konkurentów)"
  Formularz: email* / telefon* / checkbox zgody (odznaczony, konkretna treść celu)
  Wszystkie pola w jednym kroku
[SEKCJA 3+ — ZA GATE'EM]
  Pozostałe insighty, pełne rekomendacje, przycisk „Pobierz PDF"
```

Trigger gate'a: `IntersectionObserver` na sekcji 2 **lub** 25 s na stronie — co nastąpi pierwsze.

Tracking: każdy `event_type` z §4 leci POST-em do `/api/events`. Bez zewnętrznej analityki — własne dane, własny scoring.

Po submicie gate'a: double opt-in mailem, `consent_*` + IP + timestamp do bazy, `status='registered'`, `tier=3`.

**Design:** ciemne tło, jeden mocny akcent kolorystyczny, duża typografia nagłówków, wykresy jako bohater strony. Ma wyglądać jak narzędzie diagnostyczne, nie jak folder reklamowy agencji.

**Definition of done:** działający URL z pełnym flow i zapisem eventów.

### FAZA 5 — Scoring i tierowanie
```
+10  otwarcie maila
+25  wejście w mikro-apkę
+15  scroll >50%
+20  klik w wykres
+40  powrót (druga sesja)
+100 rejestracja w gate'cie
+60  pobranie PDF
```
- Tier 1: <25 — tylko mail tekstowy
- Tier 2: 25–99 — dogranie audio
- Tier 3: ≥100 — wideo + kontakt osobisty

Przeliczanie przy każdym evencie (trigger DB lub Celery task).

### FAZA 6 — Outreach: mail + głos
- **Mail (SES):** szablony Jinja2, wariant A/B, link do mikro-apki z `?src=mail&s={session}`. Nagłówek maila = `insights[rank=1].headline` (spójność hak→strona).
- **Głos (ElevenLabs):** `eleven_multilingual_v2`, głos sklonowany. Narracja 2–3 min ≈ 2700 znaków ≈ 0,60 USD. Generuj **on-demand dla Tier 2+**, nie dla całej listy. Cache w S3/lokalnie.
- Audio osadzone w mikro-apce jako odtwarzacz + link w mailu.
- **Oznaczaj audio jako wygenerowane przez AI** (wymóg AI Act od 2 sierpnia 2026).

**Definition of done:** kampania testowa na 20–50 firm z pełnym trackingiem.

### FAZA 7 — Wideo
Baza: **`calesthio/OpenMontage`** (ffmpeg + ElevenLabs + Remotion, 12 pipeline'ów).

Pipeline: Playwright screenshoty (strona, SERP, mapa, wykres) → Ken Burns → overlaye z podświetleniem błędów → sync z audio z Fazy 6 → MP4 60–90 s.

Generuj **wyłącznie dla Tier 3**. Hostuj samodzielnie z thumbnailem w mailu (nie załącznik).

### FAZA 8 — Orkiestracja i domknięcie
- n8n: harmonogram collectorów, retry, alerty
- IMAP monitor + Claude do klasyfikacji odpowiedzi → `outreach.reply_classification`
- Trigger-based re-audyt: cykliczne sprawdzanie zmian (spadek widoczności, nowa recenzja, zmiana cytowalności AEO) → automatyczny nowy insight → nowy dotyk
- Free konto: klient wraca śledzić swoje metryki w czasie

---

## 6. Skille wymagane od agenta

| Obszar | Konkretnie |
|---|---|
| Backend | Python 3.11, FastAPI, async/await, SQLAlchemy 2.0, Alembic, Celery |
| Frontend | Next.js 14 App Router, TypeScript, Tailwind, Recharts, IntersectionObserver |
| Dane | PostgreSQL + JSONB, projektowanie schematów, indeksowanie |
| Integracje API | REST, OAuth, rate limiting, retry z backoffem, obsługa limitów darmowych tierów |
| Scraping | Playwright (headless, screenshoty), parsowanie HTML, obchodzenie prostych blokad |
| LLM | Prompt engineering pod ustrukturyzowany output JSON, walidacja anty-halucynacyjna, Claude API |
| Media | ffmpeg, moviepy, ElevenLabs API, podstawy montażu |
| DevOps | Docker Compose, zmienne środowiskowe, deploy (Vercel dla front, VPS dla backendu) |
| Go (pomocniczo) | Na tyle, by uruchomić i odpytać `seonaut` — bez przepisywania |
| Domenowo | SEO techniczne, Core Web Vitals, local SEO/GBP, AEO/GEO, sezonowość zapytań |

---

## 7. Repozytoria do wykorzystania

| Repo | Licencja | Rola | Sposób użycia |
|---|---|---|---|
| `StJudeWasHere/seonaut` | MIT | Crawler SEO | Osobny kontener w compose, integracja przez API |
| `Auriti-Labs/geo-optimizer-skill` | — | AEO/GEO | Import jako moduł Python / MCP |
| `calesthio/OpenMontage` | — | Wideo | Pipeline jako referencja, adaptacja pod audyt |
| `omkarcloud/google-maps-scraper` | MIT | Dane GBP + sourcing | Ostrożnie — patrz §9 |
| `seo-skills/seo-audit-skill` | — | 108 reguł audytowych | Źródło listy reguł, nie kodu |
| `zubair-trabzada/ai-marketing-claude` | — | Generowanie raportów | Referencja promptów i struktury PDF |

**Zawsze:** sprawdź plik LICENSE przed wpięciem kodu do produkcji. Brak licencji = brak prawa użycia, niezależnie od tego, że repo jest publiczne.

---

## 8. Metryki sukcesu

Mierz na każdym etapie lejka osobno — nie jedną liczbą:

| Metryka | Cel roboczy | Benchmark |
|---|---|---|
| Delivery rate | >95% | — |
| Open rate | >40% | — |
| Klik w mikro-apkę | >15% | — |
| Scroll do gate'a | >50% wejść | — |
| Rejestracja w gate'cie | >20% oglądających | cel „20%" najsensowniej umieścić tutaj |
| Reply rate | 6–15% | audyt-led benchmark; 20% to sufit kategorii |
| Rozmowa z odpowiedzi | 20–25% | — |
| Close rate | ~30% | — |

Planuj ekonomię na 10% reply, nie 20% — patrz §11 dokumentu strategii.

---

## 9. Ograniczenia i obszary ryzyka

Nie są to formalności do odhaczenia — mają realny wpływ na architekturę:

- **Zgody:** system zbiera telefon/mail przez gate. Zapisuj `consent_timestamp` + `consent_ip` + treść zgody. Bez tego cała warstwa SMS/telefon jest nieużywalna.
- **Oznaczanie AI:** audio i wideo muszą być oznaczone jako AI-generated (AI Act, obowiązuje od 2 sierpnia 2026).
- **Scraping Map Google:** narusza ToS Google. Bezpieczniej używać oficjalnego Places API do audytu konkretnej firmy niż scrapera do masowego budowania bazy. Jeśli używasz scrapera — rate limiting i mała skala.
- **Cold mail:** opt-out w każdej wiadomości, osobna domena wysyłkowa (nie główna), warmup przed skalowaniem.
- **Deliverability > wolumen:** spalona domena kończy projekt. Startuj od 20–50 maili dziennie.

---

## 10. Kolejność startu — pierwsze 3 kroki

1. `docker-compose.yml` + schemat bazy + migracje (Faza 0)
2. `PageSpeedCollector` end-to-end na jednej domenie testowej
3. Statyczny prototyp mikro-apki z hardkodowanymi danymi — żeby zobaczyć, czy format przekonuje, zanim podłączysz pełny pipeline

Punkt 3 jest ważniejszy niż się wydaje: cała wartość systemu zależy od tego, czy mikro-apka wywołuje reakcję. Lepiej to zweryfikować na zmyślonych danych w tydzień, niż po dwóch miesiącach budowy collectorów.
