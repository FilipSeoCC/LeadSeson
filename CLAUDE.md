# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

LeadSeason generates a seasonal lead list for Customer Care at WeNet: it crawls client websites from a CRM export, classifies each client's industry, matches that industry to a seasonality window, and ranks clients for Q4 sales contact (upsell/cross-sell). Business rationale and target export schema are in `PLAN_CUSTOMER_CARE_LEADSEASON.md` — read it before changing Q4 ranking/scoring logic.

## Commands

Install deps: `pip install -r requirements.txt` (Playwright also needs `playwright install chromium` if using `--places`/browser fallback).

Run the CLI crawler:
```powershell
python bulk_crawler.py --input sample_input.xml --output output/results.csv --workers 12
python bulk_crawler.py --input clients.xml --output output/test.csv --limit 500   # first N records only
python bulk_crawler.py --input clients.xml --output output/results.csv --force    # ignore domain cache
```

Run the Streamlit app (primary UI, day-to-day operational tool): `START_BULK_APP.bat` → http://localhost:8510

Run the FastAPI backend (separate from the Streamlit app, see Architecture below): `START_BACKEND.bat` → http://127.0.0.1:8010, docs at `/docs`

There is no test suite, linter, or build step in this repo.

## Architecture

**Two independent runtimes that do NOT share code paths for Q4 ranking:**

1. **`bulk_app.py`** (Streamlit, ~3500 lines) — the actual tool people use. Monolith: UI, parsing, scoring, and rendering all live in one file. Its Q4 pipeline (`build_seasonal_leads` → `build_q4_customer_care_base_from_leads`, around line 927+) reads industry/seasonality from a **Senuto-derived Excel matrix** at `output/leadseason_macierz_sezonowosci_senuto.xlsx` (built from live Senuto MCP keyword queries inside the app's "Zasilenie danych → Sezonowość" view, not from `config/`), using Polish column names (`kwartaly_szczytu`, `confidence_sezonowosci`, `score_gotowosci`, `branza_glowna`/`podbranza` or `ai_branza_glowna`/`ai_podbranza`).

2. **`backend/api.py` + `backend/data_service.py`** (FastAPI) — a separate, only partially-connected pipeline. `q4_action_frame()`/`q4_summary()` in `data_service.py` compute Q4 ranking from a rule-based classifier's output columns (`q4_priority`, `seasonality_confidence`, `classification_confidence`), sourced from `config/leadseason_seasonality_matrix.csv` via `seasonality_matrix.py`'s `enrich_with_seasonality()`. This backend exposes `lead_reason`/`call_script`/`recommended_product` — columns the plan requires for the Customer Care export — but **the Streamlit frontend does not call this backend at all**; they run as unrelated processes.

Before touching Q4 scoring logic, know which of the two you're changing — a fix in one does not apply to the other. Unifying them is open (tracked as a known gap, not yet decided which implementation is canonical).

**Data flow (both pipelines share this crawl stage):**
```
XML/XLSX/CSV (CRM2/KartaAccount export)
  → bulk_crawler.py: parse_input_records → dedupe by domain → fetch_url/fetch_url_browser (Playwright fallback)
  → parse_metadata (title, meta, h1-h3, schema.org, offer links, body text sample)
  → taxonomy.py: classify_detailed (rule-based industry classifier)
  → optional places_enrichment.py (Google Places/GMB category, requires GOOGLE_PLACES_API_KEY)
  → optional ai_classification.py (manual Claude-in-the-loop pass, see CLAUDE_CLASSIFICATION_WORKFLOW.md)
  → seasonality_matrix.py / bulk_app.py's Senuto matrix (branch above)
  → output CSV/XLSX + <name>.summary.json
```

**`config/leadseason_taxonomy.csv`** (industry taxonomy, keyed by `branza_glowna`) and **`config/leadseason_seasonality_matrix.csv`** (seasonality by `google_type`/`leadseason_industry`) are the canonical curated reference data for the rule-based classifier + backend path. Keep `leadseason_industry` values in the matrix as exact matches to a `branza_glowna` value in the taxonomy — there is no automatic validation of this, so a typo or new industry added to one file silently stops matching the other. If you add a new industry to the seasonality matrix, add a corresponding row to the taxonomy in the same change.

**`scripts/`** (`build_category_quality_report.py`, `verify_hierarchy_gap_with_llm_pass.py`, `build_senuto_groups.py`) are one-off analysis scripts used to build/audit the config CSVs during past sessions. Despite the "llm_pass" name, `verify_hierarchy_gap_with_llm_pass.py` runs a hardcoded keyword ruleset, not an actual LLM call. Some scripts reference paths from prior Claude Code sessions that no longer exist — treat them as reference/history, not as a reproducible pipeline to re-run as-is.

**Vercel deployment** (`vercel.json` → `api/index.py` → `backend.api.app`) only serves the FastAPI backend, not the Streamlit app. Be aware the backend's crawl job (`POST /crawl/jobs`, using `BackgroundTasks`) and its filesystem-based cache/output/upload directories assume a persistent local disk and long-running process — neither holds on Vercel's serverless runtime, so crawling does not work there today.

**Security note:** `bulk_crawler.py`'s `is_safe_url()` blocks the crawler from hitting private/loopback/link-local addresses and cloud metadata endpoints (SSRF). Preserve this check if you touch `fetch_url`/`fetch_url_browser` — domains crawled come directly from user-uploaded CRM files.

## outreach/ — lead acquisition system (ai-ops.pl)

A third, separate subsystem living in this repo: the database layer for the
customer-acquisition pipeline described in `STRATEGIA_SYSTEM_POZYSKIWANIA_LEADOW.md`
(audyt → AI → głos/wideo → outreach → konwersja), built on top of the LeadSeason
seasonality module. It does **not** read from or write to `backend/data_service.py`'s
CSV/XLSX Q4 pipeline — independent SQLAlchemy store (SQLite by default, `LEADGEN_DATABASE_URL`
env var for Postgres). See `outreach/README.md` for the schema and `python -m outreach.init_db`
to bootstrap it. Covers steps 1-6 of the strategy doc's section 12 rollout order: schema,
`outreach/audits/` (on-page SEO, PageSpeed, AEO/GEO via the real `geo-optimizer-skill` PyPI
package, Senuto matrix loader -- validated against real domains via
`scripts/validate_audit_module.py`), `backend/microapp.py` (server-rendered per-lead audit
page at `/audyt/{slug}` with progressive disclosure + consent gate, mounted into this app's
router), `outreach/voice/` (ElevenLabs TTS narration, validated with a real synthesis --
see outreach/README.md for the full flow and a documented gotcha about stale voice_ids), and
`outreach/send/` (Resend email client + outreach message builder, attaches the latest voice
narration when one exists, always logs an OutreachEvent even on failure). `pick_hook()` --
the insight-trigger headline logic -- lives in `outreach/audit_utils.py`, shared by the
micro-app and the outreach email so they never show a different hook for the same lead.
PageSpeed needs `GOOGLE_PAGESPEED_API_KEY` (keyless quota is 0/day as of 2026). AEO/GEO
audits take ~15-20s/domain (no API key needed) -- `geo citations` (paid live citation checks
against ChatGPT/Perplexity APIs) is out of scope. ElevenLabs needs `ELEVENLABS_API_KEY` with
"Voices: Read" permission enabled on the key (off by default) for `list_voices()`/`get_usage()`
to work; TTS itself works on the free tier (10k chars/month) as long as `voice_id` comes from
`list_voices()` for that account rather than a hardcoded example ID. Before extending it,
check which step you're implementing.

A `leadseason-backend` entry (uvicorn on :8010) was added to the root-level
`.claude/launch.json` (one directory above this repo, shared across all of Filip's local
projects) to preview this app.

**`backend/dashboard.py`** — operator dashboard for the `outreach/` system, at `/dashboard`
(list of every Lead: company/domain, industry, a *derived* pipeline stage, tier, score, latest
audit scores, consent yes/no) and `/dashboard/{lead_id}` (full history: audits, consents,
score events, micro-app visits, voice narration with an inline player). Server-rendered,
same reasoning as `backend/microapp.py` (no frontend toolchain). `Lead` has no `status`
column (AGENT.md sekcja 4 specified one; never implemented) — the dashboard computes a
stage label live from which related rows exist (audits → consents → outreach_events) rather
than trusting a stored field that could drift. Two POST actions run synchronously and are
gated by `require_api_key` (now in `backend/auth.py`, shared with `backend/api.py` to avoid
a circular import): "Odpal audyt" (SEO on-page + AEO/GEO + Senuto row lookup, PageSpeed only
if `GOOGLE_PAGESPEED_API_KEY` is set) and "Wygeneruj narrację głosową" (ElevenLabs, skipped
gracefully with a flash message if `ELEVENLABS_API_KEY` is missing or the free-tier quota
would be exceeded), and "Wyślij mail outreachowy" (Resend, requires `RESEND_API_KEY`, operator
types the recipient address -- **not pre-filled for cold outreach**, this is test
infrastructure per STRATEGIA_SYSTEM_POZYSKIWANIA_LEADOW.md sekcja 12 krok 6, not a bulk-send
tool). Tests: `tests/test_dashboard.py`, isolated in-memory SQLite via FastAPI
`dependency_overrides` on `outreach.db.get_db` — never touches the real dev
`outreach/data/leadgen.db`.
