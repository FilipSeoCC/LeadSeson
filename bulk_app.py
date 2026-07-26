import json
import tempfile
import subprocess
import sys
from datetime import date
from io import BytesIO
from pathlib import Path

import pandas as pd
import streamlit as st

from ai_classification import build_ai_batch, jsonl_bytes, merge_ai_results, read_ai_results
from bulk_crawler import DEFAULT_WORKERS, parse_input_records, run_bulk
from seasonality_matrix import enrich_with_seasonality


APP_NAME = "LeadSeason"
BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"
CACHE_DIR = BASE_DIR / ".leadseason_cache"
TEMPLATE_PATH = BASE_DIR / "templates" / "leadflame_bulk_upload_template_from_kartaaccount.xlsx"
TEMPLATE_DOWNLOAD_NAME = "wzor_pliku_leadseason.xlsx"
SAMPLE_100_XLSX_PATH = BASE_DIR / "templates" / "przykladowy_plik_100_rekordow_leadseason.xlsx"
SAMPLE_XML_PATH = BASE_DIR / "templates" / "leadflame_bulk_upload_sample_from_kartaaccount.xml"
CATEGORY_REPORT_PATH = OUTPUT_DIR / "leadseason_kategoryzacja_ai_places_500.xlsx"
CATEGORY_REPORT_CSV_PATH = OUTPUT_DIR / "leadseason_kategoryzacja_ai_places_500.csv"
CATEGORY_REPORT_SCRIPT = BASE_DIR / "scripts" / "build_category_quality_report.py"
SENUTO_GROUPS_PATH = OUTPUT_DIR / "leadseason_grupy_branze_do_senuto.xlsx"
SENUTO_GROUPS_CSV_PATH = OUTPUT_DIR / "leadseason_grupy_branze_do_senuto.csv"
SENUTO_GROUPS_SCRIPT = BASE_DIR / "scripts" / "build_senuto_groups.py"
SENUTO_MATRIX_PATH = OUTPUT_DIR / "leadseason_macierz_sezonowosci_senuto.xlsx"
MAXUN_EXPERIMENT_PATH = OUTPUT_DIR / "leadseason_maxun_experiment_candidates.xlsx"
MAXUN_EXPERIMENT_CSV_PATH = OUTPUT_DIR / "leadseason_maxun_experiment_candidates.csv"
MAXUN_EXPERIMENT_JSONL_PATH = OUTPUT_DIR / "leadseason_maxun_experiment_candidates.jsonl"
MAXUN_RESULTS_PATH = OUTPUT_DIR / "leadseason_maxun_experiment_results.xlsx"
MAXUN_RESCUE_PATH = OUTPUT_DIR / "leadseason_maxun_crawl_rescue_candidates.xlsx"
MAXUN_RESCUE_CSV_PATH = OUTPUT_DIR / "leadseason_maxun_crawl_rescue_candidates.csv"
MAXUN_RESCUE_JSONL_PATH = OUTPUT_DIR / "leadseason_maxun_crawl_rescue_candidates.jsonl"
MAXUN_RESCUE_RESULTS_PATH = OUTPUT_DIR / "leadseason_maxun_crawl_rescue_results.xlsx"

OUTPUT_MIME_TYPES = {
    ".csv": "text/csv",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".json": "application/json",
}

Q4_VALUES = {"HIGH", "MEDIUM_HIGH"}
CRAWL_STATUS_PL = {
    "OK": "OK - pobrano stronę",
    "ERROR": "Błąd pobrania",
    "UNKNOWN": "Nieznany",
    "Brak danych": "Brak danych",
}
SITE_HEALTH_STATUS_PL = {
    "OK": "OK - dane użyteczne",
    "FETCH_ERROR": "Błąd pobrania strony",
    "BLOCKED": "Blokada / weryfikator",
    "PLACEHOLDER": "Strona techniczna / placeholder",
    "INACTIVE": "Strona nieaktywna",
    "PARKED": "Domena zaparkowana",
    "NO_SIGNAL": "Za mało treści",
    "UNKNOWN": "Nieznany",
    "Brak danych": "Brak danych",
}
PLACES_STATUS_PL = {
    "OK": "OK - dopasowano GMB",
    "NOT_FOUND": "Nie znaleziono w Google",
    "NO_API_KEY": "Brak klucza API",
    "ERROR": "Błąd API",
    "LOW_CONFIDENCE": "Niska pewność dopasowania",
    "AMBIGUOUS": "Kilka możliwych dopasowań",
    "SKIPPED": "Pominięto",
    "Brak danych": "Brak danych",
}
CATEGORY_BUCKET_PL = {
    "AI_PLUS_PLACES": "AI + Google zgodne",
    "WYSOKA_PEWNOSC_AI": "Wysoka pewność AI",
    "SREDNIA_AI": "Średnia pewność AI",
    "NISKA_PEWNOSC_AI": "Niska pewność AI",
    "DO_WERYFIKACJI": "Do ręcznej weryfikacji",
    "BRAK_SYGNALU": "Brak sygnału",
    "Brak danych": "Brak danych",
}


def map_status(value, mapping):
    text = str(value or "").strip()
    return mapping.get(text, text or "Brak danych")

CLAUDE_PROMPT = """
Jesteś analitykiem danych dla WeNet i weryfikujesz branże klientów MŚP do procesu LeadSeason.

Dostaniesz plik JSONL. Każda linia to jeden rekord klienta z danymi ze strony WWW:
- domena,
- title,
- meta description,
- H1/H2/H3,
- linki ofertowe,
- próbka tekstu strony,
- obecna klasyfikacja, jeśli istnieje.

Zadanie:
1. Rozpoznaj branżę główną klienta.
2. Rozpoznaj podbranżę.
3. Rozpoznaj główną usługę lub typ działalności.
4. Określ model: B2B, B2C albo Mieszany.
5. Oceń pewność klasyfikacji od 0 do 100.
6. Podaj krótkie evidence z danych wejściowych.

Zwróć wynik jako JSONL: jedna linia odpowiedzi na jedną linię wejścia.
Nie dodawaj komentarzy poza JSONL.

Wymagany schemat:
{
  "record_key": "taki sam jak w wejściu",
  "branza_glowna": "string",
  "podbranza": "string",
  "usluga_glowna": "string",
  "model_b2b_b2c": "B2B | B2C | Mieszany | Nieokreślona",
  "confidence": 0,
  "new_category_flag": "ISTNIEJACA | NOWA_BRANZA | NOWA_PODBRANZA | NOWA_USLUGA | BRAK_SYGNALU",
  "evidence": "krótki argument z danych wejściowych",
  "manual_review": false
}

Jeśli dane są puste albo strona nie mówi jasno czym zajmuje się firma, ustaw:
- branza_glowna: "Nieokreślona"
- confidence: 0-30
- new_category_flag: "BRAK_SYGNALU"
- manual_review: true
"""

SENUTO_MCP_PROMPT = """
Jesteś analitykiem sezonowości dla LeadSeason. Masz dostęp do Senuto przez MCP/API.

Dostaniesz plik JSONL. Każda linia to jedna grupa branżowa z polami:
- branza_glowna, podbranza, usluga_glowna, model_b2b_b2c,
- liczba_rekordow i liczba_domen w bazie,
- reprezentatywne_domeny,
- reprezentatywne_frazy.

Zadanie dla każdej linii:
1. Sprawdź sezonowość w Senuto dla reprezentatywnych domen i/lub fraz branżowych.
2. Nie klasyfikuj ponownie branży. Użyj branży/podbranży/usługi z wejścia.
3. Wyznacz miesiące szczytu popytu, start sezonu i koniec sezonu.
4. Oceń, czy sezonowość jest wyraźna: "tak", "nie" albo "hipoteza".
5. Nadaj confidence_sezonowosci 0-100:
   - 80-100: kilka domen/fraz potwierdza podobny wzorzec,
   - 60-79: jest sensowny sygnał, ale próba jest mniejsza,
   - 30-59: hipoteza z częściowych danych,
   - 0-29: brak danych albo sygnał zbyt słaby.
6. Jeśli Senuto nie ma danych, ustaw status "BRAK_DANYCH", confidence 0-30 i nie wymyślaj sezonu.

Zwróć JSONL: jedna linia odpowiedzi na jedną linię wejścia, bez komentarzy poza JSONL.

Wymagany schemat odpowiedzi:
{
  "branza_glowna": "string",
  "podbranza": "string",
  "usluga_glowna": "string",
  "model_b2b_b2c": "B2B | B2C | Mieszany | Nieokreślona",
  "liczba_rekordow": 0,
  "liczba_domen": 0,
  "domen_z_danymi_senuto": 0,
  "reprezentatywne_domeny": "domena1.pl | domena2.pl",
  "reprezentatywne_frazy": "fraza1 | fraza2",
  "senuto_query_type": "domain | keyword | mixed",
  "senuto_queries_used": "co dokładnie sprawdzono w Senuto",
  "sezon_peak_miesiace": "np. październik | listopad | grudzień",
  "sezon_start_miesiac": "np. wrzesień",
  "sezon_end_miesiac": "np. grudzień",
  "czy_sezonowosc_wyrazna": "tak | nie | hipoteza",
  "confidence_sezonowosci": 0,
  "senuto_evidence": "krótki opis sygnału: wolumeny/trend/miesiące/domeny",
  "status": "OK | BRAK_DANYCH | DO_WERYFIKACJI"
}
"""

MAXUN_EXPERIMENT_PROMPT = """
Cel eksperymentu: sprawdzić, czy Maxun poprawia jakość klasyfikacji branży dla rekordów niepewnych w LeadSeason.

Dostaniesz JSONL. Każda linia to jeden rekord klienta, który w obecnym procesie ma niską pewność branży,
brak sygnału albo wymaga ręcznej weryfikacji.

Dla każdego rekordu uruchom Maxun jako scrape/crawl strony:
1. Wejdź na url z pola `url`.
2. Zbierz LLM-ready Markdown albo czysty tekst z home page i najważniejszych podstron ofertowych.
3. Preferuj podstrony: oferta, usługi, produkty, o firmie, realizacje, sklep, kontakt.
4. Nie klikaj formularzy i nie loguj się.
5. Jeśli strona jest pusta, zaparkowana, blokuje bota albo nie działa, oznacz to w `maxun_status`.

Zwróć JSONL: jedna linia odpowiedzi na jedną linię wejścia.

Wymagany schemat:
{
  "record_key": "taki sam jak w wejściu",
  "domain_key": "domena.pl",
  "url": "https://domena.pl",
  "maxun_status": "OK | EMPTY | BLOCKED | ERROR | NOT_FOUND",
  "maxun_pages_crawled": 0,
  "maxun_title": "string",
  "maxun_meta_description": "string",
  "maxun_markdown": "najważniejsza treść strony w markdown/tekście",
  "maxun_offer_terms": "krótkie frazy ofertowe oddzielone |",
  "maxun_evidence": "krótki opis co znaleziono albo czemu się nie udało"
}
"""


st.set_page_config(page_title=APP_NAME, page_icon="LS", layout="wide")

st.markdown(
    """
<style>
:root {
  --bg: #070a11;
  --bg-soft: #0d1320;
  --bg-elevated: rgba(17,24,39,.88);
  --surface-strong: #05070c;
  --surface-strong-2: #111827;
  --text: #fff7ed;
  --text-secondary: #d6d3d1;
  --text-muted: #a8a29e;
  --on-dark: #f9fafb;
  --on-dark-muted: #cbd5e1;
  --border: rgba(251,146,60,.18);
  --border-strong: rgba(251,146,60,.34);
  --accent: #fb923c;
  --accent-hover: #f97316;
  --accent-soft: rgba(251,146,60,.12);
  --accent-border: rgba(251,146,60,.34);
  --blue: #60a5fa;
  --blue-soft: rgba(96,165,250,.12);
  --green: #34d399;
  --green-soft: rgba(52,211,153,.12);
  --red: #f87171;
  --red-soft: rgba(248,113,113,.12);
  --shadow: 0 12px 32px rgba(0,0,0,.34);
  --shadow-soft: 0 1px 2px rgba(0,0,0,.24);
  --radius: 10px;
  --radius-sm: 8px;
}
html, body, .stApp {
  font-family: Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif !important;
}
.stApp {
  background:
    radial-gradient(circle at 20% 0%, rgba(251,146,60,.12), transparent 30%),
    linear-gradient(180deg, rgba(255,122,24,.08) 0%, rgba(255,122,24,.02) 28%, var(--bg) 100%),
    var(--bg) !important;
}
.block-container { padding-top: 1.25rem !important; padding-bottom: 2rem !important; max-width: 1540px !important; }
h1, h2, h3, h4, p, label, .stMarkdown, span, div { letter-spacing: 0; }
h1 { color: var(--text); font-size: 1.8rem !important; font-weight: 760 !important; line-height: 1.12 !important; margin-bottom: 0 !important; }
h2, h3 { color: var(--text) !important; font-weight: 720 !important; }
h3 { font-size: 1.05rem !important; }
p, label, .stCaption, [data-testid="stCaptionContainer"] { color: var(--text-secondary) !important; }
[data-testid="stHeader"] {
  background: rgba(7,10,17,.96) !important;
  border-bottom: 1px solid rgba(255,255,255,.06);
}
#MainMenu { visibility: hidden; }
[data-testid="stSidebar"] {
  background: var(--surface-strong);
  border-right: 1px solid rgba(255,255,255,.08);
}
[data-testid="stSidebar"] * { color: var(--on-dark-muted) !important; }
[data-testid="stSidebar"] h1 { font-size: 1.28rem !important; color: var(--on-dark) !important; font-weight: 800 !important; }
[data-testid="stSidebar"] div[role="radiogroup"] { gap: 2px; }
[data-testid="stSidebar"] div[role="radiogroup"] label {
  min-height: 44px;
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  transition: background .18s ease, color .18s ease, box-shadow .18s ease;
  border: 1px solid transparent;
}
[data-testid="stSidebar"] div[role="radiogroup"] label:hover {
  background: rgba(255,255,255,.08);
  border-color: rgba(255,255,255,.12);
}
[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) {
  background: var(--accent);
  border-color: rgba(255,255,255,.18);
  box-shadow: 0 8px 22px rgba(217,119,6,.24);
}
[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) * { color: #fff !important; }
[data-testid="stMetric"] {
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 12px 14px;
  box-shadow: var(--shadow-soft);
  min-height: 92px;
  position: relative;
  overflow: hidden;
}
[data-testid="stMetric"]::before {
  content: "";
  position: absolute;
  left: 0;
  top: 0;
  width: 3px;
  height: 100%;
  background: var(--accent);
}
[data-testid="stMetricValue"] { color: var(--text) !important; font-weight: 760 !important; font-size: 1.45rem !important; white-space: normal !important; overflow-wrap: break-word !important; font-variant-numeric: tabular-nums; }
[data-testid="stMetricLabel"] { color: var(--text-secondary) !important; font-size: .78rem !important; font-weight: 650 !important; }
.topbar {
  padding: 18px 22px;
  border: 1px solid var(--border-strong);
  border-radius: var(--radius);
  background: linear-gradient(135deg, rgba(17,24,39,.98), rgba(5,7,12,.92));
  box-shadow: var(--shadow);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  flex-wrap: wrap;
}
.kicker {
  color: var(--accent);
  font-size: 12px;
  font-weight: 800;
  text-transform: uppercase;
  letter-spacing: .06em;
}
.topbar h1 { color: var(--on-dark) !important; }
.topbar p {
  margin: 6px 0 0;
  max-width: 820px;
  color: var(--on-dark-muted) !important;
  font-size: 14px;
}
.status-row { display: flex; gap: 8px; flex-wrap: wrap; }
.status-pill {
  border: 1px solid var(--accent-border);
  border-radius: 999px;
  padding: 7px 11px;
  color: #ffedd5;
  background: rgba(124,45,18,.22);
  font-size: 12px;
  font-weight: 700;
}
.panel {
  padding: 16px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--bg-elevated);
  box-shadow: var(--shadow-soft);
}
.mini-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  margin-top: 4px;
}
.mini-card {
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: rgba(7,10,17,.44);
  padding: 11px 12px;
  min-height: 78px;
}
.mini-card strong { color: var(--text); }
.mini-card span { display: block; margin-top: 4px; color: var(--text-secondary); font-size: 12px; line-height: 1.4; }
.hero-pipeline {
  margin: 0 0 18px;
  padding: 22px;
  border: 1px solid var(--border-strong);
  border-radius: var(--radius);
  background:
    radial-gradient(circle at 82% 18%, rgba(251,146,60,.16), transparent 28%),
    linear-gradient(135deg, rgba(17,24,39,.98), rgba(5,7,12,.96));
  box-shadow: var(--shadow);
}
.hero-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.05fr) minmax(420px, .95fr);
  gap: 18px;
  align-items: stretch;
}
.hero-copy h2 {
  margin: 8px 0 8px !important;
  font-size: 1.72rem !important;
  line-height: 1.14 !important;
  color: var(--on-dark) !important;
}
.hero-copy p {
  margin: 0;
  max-width: 760px;
  color: var(--on-dark-muted) !important;
  line-height: 1.55;
}
.hero-stat-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  margin-top: 18px;
}
.hero-stat {
  min-height: 84px;
  padding: 12px;
  border: 1px solid rgba(251,146,60,.22);
  border-radius: var(--radius-sm);
  background: rgba(7,10,17,.58);
}
.hero-stat strong {
  display: block;
  color: var(--on-dark) !important;
  font-size: 1.42rem;
  line-height: 1.1;
  font-variant-numeric: tabular-nums;
}
.hero-stat span {
  display: block;
  margin-top: 7px;
  color: var(--on-dark-muted) !important;
  font-size: 12px;
  line-height: 1.35;
}
.pipeline-card {
  padding: 14px;
  border: 1px solid rgba(255,255,255,.08);
  border-radius: var(--radius);
  background: rgba(7,10,17,.52);
}
.pipeline-card h3 {
  margin: 0 0 12px !important;
  color: var(--on-dark) !important;
  font-size: .98rem !important;
}
.pipeline-steps {
  display: grid;
  gap: 8px;
}
.pipeline-step {
  display: grid;
  grid-template-columns: 32px minmax(0, 1fr);
  gap: 10px;
  align-items: start;
  padding: 10px;
  border: 1px solid rgba(255,255,255,.08);
  border-radius: var(--radius-sm);
  background: rgba(255,255,255,.035);
}
.pipeline-num {
  width: 28px;
  height: 28px;
  display: inline-grid;
  place-items: center;
  border-radius: 999px;
  background: var(--accent);
  color: #111827 !important;
  font-weight: 820;
  font-size: 12px;
}
.pipeline-step strong {
  display: block;
  color: var(--on-dark) !important;
  font-size: 13px;
}
.pipeline-step span {
  display: block;
  margin-top: 3px;
  color: var(--on-dark-muted) !important;
  font-size: 12px;
  line-height: 1.38;
}
.lead-row-now { border-left: 3px solid var(--accent); }
.hint {
  border-left: 3px solid var(--accent);
  padding: 12px 14px;
  background: var(--accent-soft);
  color: var(--text) !important;
  border-radius: var(--radius-sm);
  border-top: 1px solid var(--accent-border);
  border-right: 1px solid var(--accent-border);
  border-bottom: 1px solid var(--accent-border);
}
.hint * { color: var(--text) !important; }
.badge {
  display: inline-block;
  padding: 3px 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  background: var(--accent-soft);
  color: var(--accent);
}
.badge.dim { background: var(--border); color: var(--text-secondary); }
[data-testid="stDataFrame"], [data-testid="stTable"] {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
  font-variant-numeric: tabular-nums;
  box-shadow: var(--shadow-soft);
}
[data-baseweb="select"] > div {
  border: 1px solid var(--border) !important;
  border-radius: var(--radius-sm) !important;
  background: var(--bg-elevated) !important;
  box-shadow: inset 0 1px 0 rgba(255,255,255,.05);
  min-height: 44px;
}
[data-baseweb="select"] span,
[data-baseweb="select"] input,
input,
textarea {
  color: var(--text) !important;
  caret-color: var(--accent) !important;
}
[data-baseweb="select"] svg {
  color: var(--text-secondary) !important;
  fill: var(--text-secondary) !important;
}
[data-baseweb="select"] > div:focus-within {
  border-color: var(--accent) !important;
  box-shadow: 0 0 0 3px var(--accent-soft) !important;
}
[data-baseweb="tag"] {
  background: var(--accent-soft) !important;
  border: 1px solid var(--accent-border) !important;
  border-radius: 999px !important;
  color: var(--accent) !important;
  font-weight: 600 !important;
}
[data-baseweb="tag"] span {
  color: var(--accent) !important;
}
[data-baseweb="popover"] {
  border-radius: 14px !important;
  box-shadow: 0 18px 50px rgba(0,0,0,.16) !important;
}
[role="option"][aria-selected="true"] {
  background: var(--accent-soft) !important;
  color: var(--accent) !important;
  font-weight: 650 !important;
}
[role="option"][aria-selected="true"]::after {
  content: "✓";
  margin-left: auto;
  color: var(--accent);
  font-weight: 800;
}
[data-testid="stCheckbox"] label {
  align-items: center;
  gap: 10px;
}
[data-testid="stCheckbox"] label span {
  color: var(--text-secondary) !important;
}
[data-testid="stCheckbox"] input[type="checkbox"] {
  accent-color: var(--accent);
}
div.stButton > button, div.stDownloadButton > button {
  border-radius: 980px;
  border: 1px solid rgba(251,146,60,.55);
  background: linear-gradient(135deg, #f97316, #f59e0b);
  color: #111827;
  font-weight: 720;
  min-height: 44px;
  padding: 0.55rem 1.05rem;
  transition: background .18s ease, box-shadow .18s ease, transform .18s ease;
}
div.stButton > button:hover, div.stDownloadButton > button:hover {
  background: linear-gradient(135deg, #fb923c, #fbbf24);
  color: #020617;
  box-shadow: 0 8px 22px rgba(217,119,6,.22);
  transform: translateY(-1px);
}
div.stButton > button:focus, div.stDownloadButton > button:focus {
  outline: 3px solid var(--accent-soft) !important;
  outline-offset: 2px !important;
}
[data-testid="stTabs"] button { font-weight: 720; min-height: 44px; }
[data-testid="stTabs"] button[aria-selected="true"] { color: var(--accent) !important; }
input, textarea { border-radius: var(--radius-sm) !important; }
hr { border-color: var(--border) !important; }
@media (prefers-reduced-motion: reduce) {
  * { transition: none !important; animation: none !important; }
}
@media (max-width: 760px) {
  .mini-grid { grid-template-columns: 1fr; }
  .hero-layout { grid-template-columns: 1fr; }
  .hero-stat-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .topbar { padding: 16px; }
  [data-testid="stMetric"] { min-height: 84px; }
}
</style>
""",
    unsafe_allow_html=True,
)


def render_header(subtitle):
    st.markdown(
        f"""
<div class="topbar">
  <div>
    <div class="kicker">Customer Care lead operations</div>
    <h1>LeadSeason</h1>
    <p>{subtitle}</p>
  </div>
  <div class="status-row">
    <div class="status-pill">Import</div>
    <div class="status-pill">Crawler WWW</div>
    <div class="status-pill">Google Places</div>
    <div class="status-pill">LLM</div>
    <div class="status-pill">Senuto</div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )
    st.write("")


def fmt_int(value):
    try:
        return f"{int(value):,}".replace(",", " ")
    except (TypeError, ValueError):
        return "0"


def render_q4_pipeline_hero(df, source_label):
    data = df
    total = len(data)
    unique_domains = data["domain_key"].replace("Brak danych", pd.NA).dropna().nunique() if total and "domain_key" in data else 0
    q4_df = data[data["q4_priority"].astype(str).isin(Q4_VALUES)] if total and "q4_priority" in data else pd.DataFrame()
    q4_domains = q4_df["domain_key"].replace("Brak danych", pd.NA).dropna().nunique() if not q4_df.empty and "domain_key" in q4_df else 0
    high_rows = int(q4_df["q4_priority"].astype(str).eq("HIGH").sum()) if not q4_df.empty and "q4_priority" in q4_df else 0
    q4_mrr = q4_df["_mrr_num"].sum() if not q4_df.empty and "_mrr_num" in q4_df else 0
    usable = int(data["usable_for_llm"].astype(str).str.lower().isin(["true", "1", "tak", "yes"]).sum()) if total and "usable_for_llm" in data else 0
    usable_pct = metric_percent(usable, total) if total else "0.0%"

    st.markdown(
        f"""
<div class="hero-pipeline">
  <div class="hero-layout">
    <div class="hero-copy">
      <div class="kicker">LeadSeason pipeline</div>
      <h2>Od pliku klientów do listy domen, do których warto uderzać przed Q4.</h2>
      <p>
        Wrzucasz bazę zgodną ze wzorem. Aplikacja crawluje strony, dokłada Google Places/GMB,
        przygotowuje paczkę dla LLM do weryfikacji branż, mapuje grupy branżowe na sezonowość
        i zwraca bazę operacyjną dla Customer Care.
      </p>
      <div class="hero-stat-grid">
        <div class="hero-stat"><strong>{fmt_int(q4_df.shape[0])}</strong><span>rekordów z sezonowością Q4</span></div>
        <div class="hero-stat"><strong>{fmt_int(q4_domains)}</strong><span>unikalnych domen Q4</span></div>
        <div class="hero-stat"><strong>{fmt_int(high_rows)}</strong><span>priorytet HIGH</span></div>
        <div class="hero-stat"><strong>{fmt_int(q4_mrr)}</strong><span>MRR w segmencie Q4</span></div>
      </div>
    </div>
    <div class="pipeline-card">
      <h3>Jak działa docelowy proces</h3>
      <div class="pipeline-steps">
        <div class="pipeline-step"><div class="pipeline-num">1</div><div><strong>Import bazy</strong><span>NIP, domena, id klienta/detail, opiekun, pakiet i wartość umowy.</span></div></div>
        <div class="pipeline-step"><div class="pipeline-num">2</div><div><strong>Crawl WWW + zdrowie strony</strong><span>Title, meta, nagłówki, oferta, tekst strony i status czy dane nadają się dla LLM.</span></div></div>
        <div class="pipeline-step"><div class="pipeline-num">3</div><div><strong>Google Places/GMB</strong><span>Typ biznesu, nazwa, telefon, adres i sygnał potwierdzający branżę.</span></div></div>
        <div class="pipeline-step"><div class="pipeline-num">4</div><div><strong>LLM kategoryzuje branżę</strong><span>Branża, podbranża, usługa, B2B/B2C, confidence i rekordy do ręcznej weryfikacji.</span></div></div>
        <div class="pipeline-step"><div class="pipeline-num">5</div><div><strong>Senuto i output akcyjny</strong><span>Mapowanie sezonowości na grupy branżowe i lista klientów/domen do działań.</span></div></div>
      </div>
    </div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )
    st.caption(f"Aktywne źródło danych: {source_label}. Użyteczne strony dla LLM: {usable_pct}.")


def render_overview_tab():
    st.markdown(
        "Jedna ścieżka pracy: import bazy → crawl WWW → Google Places → weryfikacja LLM → grupy branżowe → sezonowość Senuto. "
        "Uruchamiasz to raz na jakiś czas, żeby odświeżyć dane pod widokiem **Plan działania**."
    )

    st.markdown("### Aktywna baza dla planu działania")
    st.caption("Tu wybierasz, jaki plik zasila widok Plan działania. Bez wyboru apka sama bierze najnowszy plik z 'pełna' w nazwie.")
    source_choice = st.radio(
        "Źródło danych",
        ["Automatycznie", "Wybierz plik z folderu output", "Wgraj plik XLSX/CSV/JSON"],
        horizontal=True,
        key="active_leads_source_choice",
    )
    if source_choice == "Wybierz plik z folderu output":
        output_files = [
            path for path in sorted(OUTPUT_DIR.glob("*"), key=lambda item: item.stat().st_mtime, reverse=True)
            if path.suffix.lower() in [".xlsx", ".csv", ".json"] and not path.name.endswith(".summary.json")
        ] if OUTPUT_DIR.exists() else []
        if output_files:
            selected_file = st.selectbox("Plik z output", output_files, format_func=lambda path: path.name, key="active_leads_output_file")
            if st.button("Ustaw jako aktywną bazę"):
                st.session_state["active_leads_df"] = load_output_path(selected_file, selected_file.stat().st_mtime)
                st.session_state["active_leads_label"] = selected_file.name
                st.success(f"Ustawiono aktywną bazę: {selected_file.name}")
        else:
            st.info("Brak plików w folderze output.")
    elif source_choice == "Wgraj plik XLSX/CSV/JSON":
        uploaded = st.file_uploader("Wrzuć bazę klientów", type=["xlsx", "xls", "csv", "json"], key="active_leads_upload")
        if uploaded:
            st.session_state["active_leads_df"] = load_dataframe_from_file(uploaded)
            st.session_state["active_leads_label"] = uploaded.name
            st.success(f"Ustawiono aktywną bazę: {uploaded.name}")
    else:
        st.session_state.pop("active_leads_df", None)
        st.session_state.pop("active_leads_label", None)

    active_label = st.session_state.get("active_leads_label")
    if active_label:
        st.caption(f"Aktywna baza (ręcznie wybrana): **{active_label}**")
    else:
        st.caption("Aktywna baza: automatyczny wybór najnowszego pliku z 'pełna' w nazwie.")

    metrics, category_data = load_category_report_frames()
    senuto_data = load_senuto_groups_frame()
    senuto_matrix = load_senuto_matrix_frame()
    active_df, _ = auto_pick_dataset()
    active_df = prepare_dashboard_frame(active_df) if not active_df.empty else active_df
    category_metrics, _, _, _ = build_category_metrics(category_data)
    season_metrics, _, _, _ = build_seasonality_metrics(senuto_matrix, category_data)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Jakość kategoryzacji", "gotowe" if not category_data.empty else "brak")
    c2.metric("Domeny w badaniu", category_data["domain_key"].nunique() if not category_data.empty and "domain_key" in category_data else 0)
    c3.metric("Pokrycie AI", f"{metric_value(metrics, 'pokrycie_ai_pct')}%" if not metrics.empty else "0%")
    c4.metric("Grupy do Senuto", len(senuto_data) if not senuto_data.empty else 0)
    c5, c6, c7, c8 = st.columns(4)
    c5.metric("AI + Places", category_metrics.get("ai_places_domains", 0), pct(category_metrics.get("ai_places_domains", 0), category_metrics.get("domains", 0)))
    c6.metric("Do ręcznej weryfikacji", category_metrics.get("review_domains", 0))
    c7.metric("Domeny z sezonowością", season_metrics.get("matched_domains", 0))
    c8.metric("Domeny z Q4", season_metrics.get("q4_domains", 0))

    st.markdown("### Status procesu")
    pipeline = pd.DataFrame(build_pipeline_status(active_df, category_data, senuto_data, senuto_matrix))
    st.dataframe(
        pipeline,
        width="stretch",
        hide_index=True,
        column_config={
            "etap": st.column_config.TextColumn("Etap"),
            "status": st.column_config.TextColumn("Status"),
            "metryka": st.column_config.TextColumn("Co mamy"),
        },
    )

    left, right = st.columns([1.05, 1])
    with left:
        st.markdown("### Co robi aplikacja")
        st.markdown(
            """
<div class="panel">
  <div class="mini-grid">
    <div class="mini-card"><strong>Wejście</strong><span>Plik zgodny ze wzorem: NIP, domena, id klienta, detail i opcjonalnie opiekun/pakiet.</span></div>
    <div class="mini-card"><strong>Dane z WWW</strong><span>Title, meta description, nagłówki, linki ofertowe i próbka treści strony.</span></div>
    <div class="mini-card"><strong>GMB/Places</strong><span>Nazwa firmy, typ Google, telefon, adres, strona i confidence dopasowania.</span></div>
    <div class="mini-card"><strong>LLM</strong><span>Weryfikacja branży, podbranży, usługi i modelu B2B/B2C.</span></div>
    <div class="mini-card"><strong>Senuto</strong><span>Grupy branżowe zamiast pojedynczych domen, żeby badać sezonowość skalowalnie.</span></div>
    <div class="mini-card"><strong>Output</strong><span>Raport jakości, rekordy do weryfikacji i plik grup do uzupełnienia sezonowością.</span></div>
  </div>
</div>
""",
            unsafe_allow_html=True,
        )
    with right:
        st.markdown("### Najbliższe akcje")
        st.markdown(
            """
<div class="hint">
1. Wgraj bazę w widoku Import i enrichment.  
2. Pobierz paczkę dla LLM w widoku Klasyfikacja branż.  
3. Zaimportuj wynik LLM i sprawdź Jakość kategoryzacji.  
4. Przygotuj grupy i import sezonowości w widoku Sezonowość.
5. Wróć do Planu działania i wybierz cel pracy.
</div>
""",
            unsafe_allow_html=True,
        )
        st.write("")
        if TEMPLATE_PATH.exists():
            st.download_button("Pobierz wzór pliku wejściowego", TEMPLATE_PATH.read_bytes(), file_name=TEMPLATE_DOWNLOAD_NAME, mime=OUTPUT_MIME_TYPES[".xlsx"], width="stretch")
        if CATEGORY_REPORT_PATH.exists():
            st.download_button("Pobierz aktualny raport branż", CATEGORY_REPORT_PATH.read_bytes(), file_name=CATEGORY_REPORT_PATH.name, mime=OUTPUT_MIME_TYPES[".xlsx"], width="stretch")


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


def months_between(today, target):
    return (target.year - today.year) * 12 + (target.month - today.month)


NIEOKRESLONA_VALUES = {"", "nieokreślona", "brak danych"}


def build_seasonal_leads(df, matrix, today=None):
    if df.empty or matrix.empty:
        return pd.DataFrame()
    has_ai = "ai_branza_glowna" in df.columns and "ai_podbranza" in df.columns
    has_rule = "branza_glowna" in df.columns and "podbranza" in df.columns
    if not has_ai and not has_rule:
        return pd.DataFrame()

    matrix_by_key = {}
    for _, row in matrix.iterrows():
        key = (str(row.get("branza_glowna") or "").strip(), str(row.get("podbranza") or "").strip())
        matrix_by_key[key] = row

    today = today or date.today()
    current_idx = today.month - 1
    optional_cols = {
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


def build_action_plan(df, action_type, target_limit=100):
    if df.empty:
        return pd.DataFrame()
    plan = df.copy()
    plan["_rank_score"] = 0
    plan["_rank_score"] += (12 - pd.to_numeric(plan.get("miesiecy_do_szczytu", 99), errors="coerce").fillna(99).clip(0, 12)) * 8
    plan["_rank_score"] += pd.to_numeric(plan.get("confidence_sezonowosci", 0), errors="coerce").fillna(0) * 0.6
    plan["_rank_score"] += pd.to_numeric(plan.get("mrr", 0), errors="coerce").fillna(0).clip(0, 1000) / 50
    if "miesiecy_do_konca_umowy" in plan:
        renewal = pd.to_numeric(plan["miesiecy_do_konca_umowy"], errors="coerce")
        plan["_rank_score"] += renewal.between(0, 3).fillna(False).astype(int) * 25

    if action_type == "Teraz: sezon w 0-1 mies.":
        plan = plan[plan["miesiecy_do_szczytu"].le(1)]
        action_label = "Kontakt teraz"
    elif action_type == "Plan Q4":
        plan = plan[plan["sezon_peak_miesiace"].astype(str).str.contains("październik|listopad|grudzień", case=False, na=False)]
        action_label = "Plan Q4"
    elif action_type == "Tylko potwierdzone":
        plan = plan[(plan["czy_sezonowosc_wyrazna"].eq("tak")) & (pd.to_numeric(plan["confidence_sezonowosci"], errors="coerce").fillna(0) >= 70)]
        action_label = "Potwierdzona sezonowość"
    elif action_type == "Do walidacji":
        plan = plan[(plan["okno_kontaktu"].eq("Brak danych sezonowości")) | (pd.to_numeric(plan["confidence_sezonowosci"], errors="coerce").fillna(0) < 60)]
        action_label = "Walidacja danych"
    else:
        action_label = "Segment wybrany ręcznie"

    plan = plan.sort_values("_rank_score", ascending=False).head(int(target_limit or 100)).copy()
    plan["plan_dzialania"] = action_label
    plan["status_realizacji"] = "DO_ZAPLANOWANIA"
    plan["owner_planu"] = plan.get("account_owner", "")
    plan["ranking"] = range(1, len(plan) + 1)
    plan["powod_wyboru"] = plan.apply(
        lambda row: f"{row.get('okno_kontaktu', '')}; sezon: {row.get('sezon_peak_miesiace', '')}; confidence: {row.get('confidence_sezonowosci', 0)}",
        axis=1,
    )
    return plan.drop(columns=["_rank_score"], errors="ignore")


def add_lead_readiness(leads):
    if leads.empty:
        return leads
    data = leads.copy()
    season_conf = pd.to_numeric(data.get("confidence_sezonowosci", 0), errors="coerce").fillna(0).clip(0, 100)
    branch_conf = pd.to_numeric(data.get("branza_confidence", 0), errors="coerce").fillna(0).clip(0, 100)
    months_to_peak = pd.to_numeric(data.get("miesiecy_do_szczytu", 99), errors="coerce").fillna(99)
    mrr = pd.to_numeric(data.get("mrr", 0), errors="coerce").fillna(0)
    renewal = pd.to_numeric(data.get("miesiecy_do_konca_umowy", 99), errors="coerce").fillna(99)

    has_domain = data.get("domain_key", "").astype(str).str.strip().ne("")
    has_season = data.get("okno_kontaktu", "").astype(str).ne("Brak danych sezonowości")
    strong_season = data.get("czy_sezonowosc_wyrazna", "").astype(str).str.lower().eq("tak")
    llm_branch = data.get("branza_zrodlo", "").astype(str).str.contains("LLM", case=False, na=False)

    score = (
        branch_conf * 0.25
        + season_conf * 0.35
        + has_season.astype(int) * 15
        + strong_season.astype(int) * 10
        + llm_branch.astype(int) * 5
        + has_domain.astype(int) * 5
        + (mrr.gt(0)).astype(int) * 5
    ).clip(0, 100).round().astype(int)
    data["score_gotowosci"] = score
    data["jakosc_rekordu"] = pd.cut(
        score,
        bins=[-1, 39, 64, 79, 100],
        labels=["Słaba", "Do sprawdzenia", "Dobra", "Gotowy"],
    ).astype(str)

    data["segment_operacyjny"] = "Do walidacji danych"
    data.loc[has_season & months_to_peak.le(1) & score.ge(65), "segment_operacyjny"] = "Kontakt teraz"
    data.loc[has_season & months_to_peak.between(2, 3) & score.ge(60), "segment_operacyjny"] = "Plan 30-90 dni"
    data.loc[has_season & data.get("kwartaly_szczytu", "").astype(str).str.contains("Q4", na=False) & score.ge(55), "segment_operacyjny"] = "Plan Q4"
    data.loc[has_season & score.lt(60), "segment_operacyjny"] = "Hipoteza do potwierdzenia"
    data.loc[~has_season, "segment_operacyjny"] = "Brak sezonowości"
    data.loc[renewal.between(0, 3) & score.ge(50), "segment_operacyjny"] = "Odnowienia umów"
    return data


def action_goal_to_filter(leads, goal):
    if leads.empty:
        return leads
    data = leads.copy()
    if goal == "Kontakt teraz":
        return data[data["segment_operacyjny"].eq("Kontakt teraz")]
    if goal == "Plan 30-90 dni":
        return data[data["segment_operacyjny"].eq("Plan 30-90 dni")]
    if goal == "Plan Q4":
        return data[data["kwartaly_szczytu"].astype(str).str.contains("Q4", na=False)]
    if goal == "Odnowienia umów":
        renewal = pd.to_numeric(data.get("miesiecy_do_konca_umowy", 99), errors="coerce").fillna(99)
        return data[renewal.between(0, 3)]
    if goal == "Do walidacji":
        return data[data["segment_operacyjny"].isin(["Do walidacji danych", "Hipoteza do potwierdzenia", "Brak sezonowości"])]
    return data


def build_pipeline_status(df, category_data, senuto_groups, senuto_matrix):
    total = len(df) if not df.empty else 0
    domains = df["domain_key"].replace("", pd.NA).dropna().nunique() if total and "domain_key" in df else 0
    crawl_ok = int(df["crawl_status"].eq("OK").sum()) if total and "crawl_status" in df else 0
    usable_pages = int(df["usable_for_llm"].astype(str).str.lower().isin(["true", "1", "tak", "yes"]).sum()) if total and "usable_for_llm" in df else crawl_ok
    places_ok = int(df["places_status"].eq("OK").sum()) if total and "places_status" in df else 0
    category_domains = category_data["domain_key"].nunique() if not category_data.empty and "domain_key" in category_data else 0
    senuto_ok = int(senuto_matrix["status"].eq("OK").sum()) if not senuto_matrix.empty and "status" in senuto_matrix else 0

    return [
        {"etap": "Baza klientów", "status": "gotowe" if total else "brak", "metryka": f"{total} rekordów / {domains} domen"},
        {"etap": "Crawl WWW", "status": "gotowe" if crawl_ok else "wymaga akcji", "metryka": f"{crawl_ok} stron OK / {usable_pages} użytecznych dla LLM"},
        {"etap": "Google Places/GMB", "status": "gotowe" if places_ok else "opcjonalne", "metryka": f"{places_ok} dopasowań"},
        {"etap": "Klasyfikacja branż LLM", "status": "gotowe" if category_domains else "wymaga akcji", "metryka": f"{category_domains} domen z raportem"},
        {"etap": "Grupy do Senuto", "status": "gotowe" if not senuto_groups.empty else "wymaga akcji", "metryka": f"{len(senuto_groups)} grup"},
        {"etap": "Macierz sezonowości", "status": "gotowe" if senuto_ok else "wymaga akcji", "metryka": f"{senuto_ok} grup OK"},
    ]


def enrich_with_category_report(df):
    if "ai_branza_glowna" in df.columns:
        return df, 0
    if "domain_key" not in df.columns or not CATEGORY_REPORT_PATH.exists():
        return df, 0
    _, category_data = load_category_report_frames()
    if category_data.empty or "domain_key" not in category_data.columns:
        return df, 0
    merge_cols = [c for c in ["domain_key", "ai_branza_glowna", "ai_podbranza", "ai_usluga_glowna", "ai_model_b2b_b2c", "ai_confidence"] if c in category_data.columns]
    lookup = category_data[merge_cols].drop_duplicates("domain_key")
    merged = df.merge(lookup, on="domain_key", how="left")
    joined_cols = [c for c in merge_cols if c != "domain_key"]
    merged[joined_cols] = merged[joined_cols].fillna("")
    matched = int(merged["ai_branza_glowna"].ne("").sum()) if "ai_branza_glowna" in merged else 0
    return merged, matched


def auto_pick_dataset():
    if "active_leads_df" in st.session_state and not st.session_state["active_leads_df"].empty:
        return st.session_state["active_leads_df"], st.session_state.get("active_leads_label", "wybrane w Zasileniu danych")
    if "bulk_results" in st.session_state and not st.session_state["bulk_results"].empty:
        return st.session_state["bulk_results"], "ostatni wynik z sesji"
    output_files = [
        path for path in sorted(OUTPUT_DIR.glob("*"), key=lambda item: item.stat().st_mtime, reverse=True)
        if path.suffix.lower() in [".xlsx", ".csv", ".json"] and not path.name.endswith(".summary.json")
    ] if OUTPUT_DIR.exists() else []
    if not output_files:
        return pd.DataFrame(), ""
    default_file = next((path for path in output_files if "pelna" in path.name.lower()), output_files[0])
    return load_output_path(default_file, default_file.stat().st_mtime), default_file.name


def render_leads_view():
    render_header("Plan działania: wybierz cel operacyjny, zawęź segment i pobierz kolejkę pracy dla opiekunów.")

    df, source_label = auto_pick_dataset()
    matrix = load_senuto_matrix_frame()

    if df.empty:
        st.info("Brak danych. Wybierz bazę klientów w widoku Zasilenie danych → Status procesu.")
        return
    if matrix.empty:
        st.info(f"Brak jeszcze macierzy sezonowości (`{SENUTO_MATRIX_PATH.name}`). Zbuduj ją w widoku Zasilenie danych → Sezonowość.")
        return

    df, matched_from_report = enrich_with_category_report(df)

    leads = add_lead_readiness(build_seasonal_leads(df, matrix))
    if leads.empty:
        st.warning(
            "Ta baza nie ma jeszcze kolumn branży (`ai_branza_glowna`/`ai_podbranza` albo `branza_glowna`/`podbranza`). "
            "Wgraj wynik po klasyfikacji LLM albo zmień bazę w widoku Zasilenie danych → Status procesu."
        )
        return

    caption_bits = [f"Źródło: {source_label}", f"{len(leads)} klientów"]
    if matched_from_report:
        caption_bits.append(f"branża dociągnięta z {CATEGORY_REPORT_PATH.name} dla {matched_from_report}/{len(df)} rekordów")
    st.caption(" · ".join(caption_bits))

    has_mrr = "mrr" in leads and leads["mrr"].sum() > 0
    has_renewal = "miesiecy_do_konca_umowy" in leads and leads["miesiecy_do_konca_umowy"].notna().any()
    ready_now = int(leads["segment_operacyjny"].eq("Kontakt teraz").sum())
    plan_soon = int(leads["segment_operacyjny"].eq("Plan 30-90 dni").sum())
    q4_count = int(leads["kwartaly_szczytu"].astype(str).str.contains("Q4", na=False).sum())
    validation_count = int(leads["segment_operacyjny"].isin(["Do walidacji danych", "Hipoteza do potwierdzenia", "Brak sezonowości"]).sum())
    avg_score = int(pd.to_numeric(leads["score_gotowosci"], errors="coerce").fillna(0).mean()) if not leads.empty else 0

    st.markdown("### Co chcesz zrobić z bazą?")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Kontakt teraz", ready_now)
    c2.metric("Plan 30-90 dni", plan_soon)
    c3.metric("Piki Q4", q4_count)
    c4.metric("Do walidacji", validation_count)
    c5.metric("Śr. gotowość", f"{avg_score}/100")

    action_goal = st.radio(
        "Cel pracy",
        ["Kontakt teraz", "Plan 30-90 dni", "Plan Q4", "Odnowienia umów", "Do walidacji", "Cała baza"],
        horizontal=True,
        index=0,
    )
    view = action_goal_to_filter(leads, action_goal)

    total = len(view)
    no_data = int(view["okno_kontaktu"].eq("Brak danych sezonowości").sum())
    now_count = int(view["miesiecy_do_szczytu"].eq(0).sum())
    soon_count = int(view["miesiecy_do_szczytu"].le(1).sum())

    s1, s2, s3, s4 = st.columns(4)
    s1.metric("Rekordy w celu", total)
    s2.metric("Z sezonowością", total - no_data)
    s3.metric("Szczyt 0-1 mies.", soon_count)
    s4.metric("Szczyt teraz", now_count)

    if has_mrr or has_renewal:
        m1, m2, m3 = st.columns(3)
        if has_mrr:
            m1.metric("MRR w celu", f"{view['mrr'].sum():,.0f} zł".replace(",", " "))
            m2.metric("MRR gotowy teraz", f"{view.loc[view['segment_operacyjny'].eq('Kontakt teraz'), 'mrr'].sum():,.0f} zł".replace(",", " "))
        if has_renewal:
            renewing_soon = view["miesiecy_do_konca_umowy"].between(0, 3)
            m3.metric("Umowy do 3 mies.", int(renewing_soon.sum()))

    st.markdown("### Doprecyzuj segment")
    filters_col, table_col = st.columns([0.75, 1.65])
    with filters_col:
        action_type_map = {
            "Kontakt teraz": "Teraz: sezon w 0-1 mies.",
            "Plan Q4": "Plan Q4",
            "Do walidacji": "Do walidacji",
            "Plan 30-90 dni": "Własny segment",
            "Odnowienia umów": "Własny segment",
            "Cała baza": "Własny segment",
        }
        action_type = action_type_map.get(action_goal, "Własny segment")
        target_limit = st.number_input("Limit planu", min_value=10, max_value=1000, value=100, step=10)
        owners = sorted({o for o in view["account_owner"].astype(str) if o}) if "account_owner" in view else []
        selected_owners = st.multiselect("Opiekun", owners, default=[], placeholder="Wszyscy opiekunowie") if owners else []
        branze = sorted({b for b in view["branza_glowna"].astype(str) if b})
        selected_branze = st.multiselect("Branża", branze, default=[], placeholder="Wszystkie branże")
        quality_options = ["Gotowy", "Dobra", "Do sprawdzenia", "Słaba"]
        selected_quality = st.multiselect("Jakość rekordu", quality_options, default=[], placeholder="Wszystkie poziomy")
        st.caption("Wpisz, żeby wyszukać. Puste pole oznacza brak ograniczenia.")
        default_window = 3 if action_goal in ["Kontakt teraz", "Plan 30-90 dni"] else 12
        window = st.slider("Szczyt w ciągu (miesięcy)", 0, 12, default_window)
        only_strong = st.checkbox("Tylko wyraźna sezonowość", value=False)
        hide_no_data = st.checkbox("Ukryj rekordy bez danych sezonowości", value=action_goal != "Do walidacji")
        renewal_window = 12
        if has_renewal:
            renewal_window = st.slider("Koniec umowy w ciągu (miesięcy, 12 = bez limitu)", 0, 12, 12)

    filtered = view.copy()
    if owners and selected_owners:
        filtered = filtered[filtered["account_owner"].isin(selected_owners)]
    if selected_branze:
        filtered = filtered[filtered["branza_glowna"].isin(selected_branze)]
    if selected_quality:
        filtered = filtered[filtered["jakosc_rekordu"].isin(selected_quality)]
    if hide_no_data:
        filtered = filtered[filtered["okno_kontaktu"] != "Brak danych sezonowości"]
    if action_goal == "Do walidacji" and not hide_no_data:
        filtered = filtered[(filtered["miesiecy_do_szczytu"] <= window) | filtered["okno_kontaktu"].eq("Brak danych sezonowości")]
    else:
        filtered = filtered[filtered["miesiecy_do_szczytu"] <= window]
    if only_strong:
        filtered = filtered[filtered["czy_sezonowosc_wyrazna"] == "tak"]
    if has_renewal and renewal_window < 12:
        filtered = filtered[filtered["miesiecy_do_konca_umowy"].fillna(999) <= renewal_window]

    action_plan = build_action_plan(filtered, action_type, target_limit)
    p1, p2, p3, p4 = st.columns(4)
    p1.metric("Rekordy w segmencie", len(filtered))
    p2.metric("Do planu", len(action_plan))
    p3.metric("Unikalne domeny", action_plan["domain_key"].nunique() if "domain_key" in action_plan else 0)
    p4.metric("MRR w planie", f"{action_plan['mrr'].sum():,.0f} zł".replace(",", " ") if "mrr" in action_plan and not action_plan.empty else "0 zł")

    with table_col:
        st.markdown("### Kolejka pracy")
        display_cols = [
            col for col in [
                "ranking", "status_realizacji", "owner_planu", "score_gotowosci", "jakosc_rekordu",
                "company", "domain_key", "branza_glowna", "podbranza", "plan_dzialania", "okno_kontaktu",
                "sezon_peak_miesiace", "confidence_sezonowosci", "mrr", "end_date",
                "miesiecy_do_konca_umowy", "service", "seo_basket", "powod_wyboru",
            ] if col in action_plan.columns
        ]
        plan_config = {
            "ranking": st.column_config.NumberColumn("#"),
            "mrr": st.column_config.NumberColumn("MRR", format="%.0f zł"),
            "score_gotowosci": st.column_config.ProgressColumn("Gotowość", min_value=0, max_value=100, format="%d"),
            "confidence_sezonowosci": st.column_config.NumberColumn("Pewność sezonu", format="%d"),
            "miesiecy_do_konca_umowy": st.column_config.NumberColumn("Mies. do końca umowy"),
            "status_realizacji": st.column_config.SelectboxColumn(
                "Status",
                options=["DO_ZAPLANOWANIA", "W_TRAKCIE", "ZROBIONE", "ODŁOŻONE", "DO_WERYFIKACJI"],
            ),
        }
        st.data_editor(
            action_plan[display_cols],
            width="stretch",
            height=520,
            column_config=plan_config,
            hide_index=True,
            disabled=[col for col in display_cols if col != "status_realizacji"],
            key=f"action_plan_editor_{action_goal}",
        )

    st.markdown("### Podsumowanie segmentu")
    group_options = [col for col in ["branza_glowna", "segment_operacyjny", "okno_kontaktu", "priorytet_kontaktu", "account_owner", "service", "seo_basket"] if col in filtered.columns]
    if group_options:
        group_by = st.selectbox("Grupuj wg", group_options, index=0)
        summary = filtered.groupby(group_by).size().rename("liczba_klientow").reset_index()
        if has_mrr:
            summary["suma_mrr"] = filtered.groupby(group_by)["mrr"].sum().values
        summary = summary.sort_values("liczba_klientow", ascending=False)
        col_a, col_b = st.columns([1, 1])
        with col_a:
            if not summary.empty:
                st.bar_chart(summary.set_index(group_by)["liczba_klientow"])
        with col_b:
            summary_config = {"liczba_klientow": st.column_config.NumberColumn("Klienci", format="%d")}
            if "suma_mrr" in summary:
                summary_config["suma_mrr"] = st.column_config.NumberColumn("Suma MRR", format="%.0f zł")
            st.dataframe(summary, width="stretch", height=300, column_config=summary_config, hide_index=True)
    else:
        summary = pd.DataFrame()

    st.download_button(
        "Pobierz plan działania XLSX",
        xlsx_bytes({"Plan działania": action_plan, "Segment": filtered, "Podsumowanie": summary}),
        file_name="leadseason_plan_dzialania.xlsx",
        mime=OUTPUT_MIME_TYPES[".xlsx"],
        width="stretch",
    )


def clean_number(value):
    text = str(value or "").strip().replace("\xa0", "").replace(" ", "")
    text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return 0.0


def load_dataframe_from_file(uploaded_file):
    suffix = Path(uploaded_file.name).suffix.lower()
    payload = uploaded_file.getvalue()
    if suffix in [".xlsx", ".xls"]:
        return pd.read_excel(BytesIO(payload), dtype=str, keep_default_na=False)
    if suffix == ".csv":
        return pd.read_csv(BytesIO(payload), sep=None, engine="python", dtype=str, keep_default_na=False, encoding="utf-8-sig")
    if suffix == ".json":
        data = json.loads(payload.decode("utf-8-sig"))
        if isinstance(data, dict):
            for key in ["rows", "data", "records", "items"]:
                if isinstance(data.get(key), list):
                    data = data[key]
                    break
        return pd.DataFrame(data)
    raise ValueError("Obsługiwane są XLSX, CSV i JSON.")


@st.cache_data(show_spinner=False, ttl=600)
def load_latest_output():
    candidates = sorted(
        [path for path in OUTPUT_DIR.glob("*") if path.suffix.lower() in [".xlsx", ".csv", ".json"]],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for path in candidates:
        if path.name.endswith(".summary.json"):
            continue
        try:
            if path.suffix.lower() == ".xlsx":
                return pd.read_excel(path, dtype=str, keep_default_na=False), path
            if path.suffix.lower() == ".csv":
                return pd.read_csv(path, sep=None, engine="python", dtype=str, keep_default_na=False, encoding="utf-8-sig"), path
            data = json.loads(path.read_text(encoding="utf-8"))
            return pd.DataFrame(data), path
        except Exception:
            continue
    return pd.DataFrame(), None


@st.cache_data(show_spinner=False, ttl=600)
def load_output_path(path, cache_stamp=None):
    path = Path(path)
    CACHE_DIR.mkdir(exist_ok=True)
    sheet = None
    if path.suffix.lower() == ".xlsx":
        workbook = pd.ExcelFile(path)
        sheet = "kategoryzacja_500" if "kategoryzacja_500" in workbook.sheet_names else workbook.sheet_names[0]
    cache_key = f"{path.stem}_{path.stat().st_mtime_ns}_{sheet or 'file'}".replace(" ", "_")
    cache_path = CACHE_DIR / f"{cache_key}.pkl"
    if cache_path.exists():
        try:
            return pd.read_pickle(cache_path)
        except Exception:
            cache_path.unlink(missing_ok=True)

    if path.suffix.lower() == ".xlsx":
        df = pd.read_excel(path, sheet_name=sheet, dtype=str, keep_default_na=False)
        df.to_pickle(cache_path)
        return df
    if path.suffix.lower() == ".csv":
        df = pd.read_csv(path, sep=None, engine="python", dtype=str, keep_default_na=False, encoding="utf-8-sig")
        df.to_pickle(cache_path)
        return df
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        for key in ["rows", "data", "records", "items"]:
            if isinstance(data.get(key), list):
                data = data[key]
                break
    df = pd.DataFrame(data)
    df.to_pickle(cache_path)
    return df


def ensure_operational_columns(df):
    if df.empty:
        return df
    if "q4_priority" in df.columns and df["q4_priority"].fillna("").astype(str).str.strip().ne("").any():
        return df
    rows = []
    seasonality_cache = {}
    for _, row in df.iterrows():
        item = row.to_dict()
        missing = not item.get("q4_priority") or item.get("q4_priority") == "DO_WERYFIKACJI"
        if missing:
            cache_key = (
                str(item.get("places_primary_type") or ""),
                str(item.get("places_types") or ""),
                str(item.get("detected_industry") or ""),
            )
            if cache_key not in seasonality_cache:
                seasonality_cache[cache_key] = enrich_with_seasonality(item)
            item.update(seasonality_cache[cache_key])
        rows.append(item)
    return pd.DataFrame(rows)


def prepare_dashboard_frame(df):
    df = ensure_operational_columns(df.copy())
    if "monthly_value" in df:
        df["_mrr_num"] = df["monthly_value"].map(clean_number)
    elif "mrr" in df:
        df["_mrr_num"] = df["mrr"].map(clean_number)
    else:
        df["_mrr_num"] = 0.0
    for col in ["detected_industry", "q4_priority", "account_owner", "crawl_status", "domain_key", "site_health_status"]:
        if col not in df:
            df[col] = ""
        df[col] = df[col].fillna("").astype(str).replace("", "Brak danych")
    df["crawl_status_pl"] = df["crawl_status"].map(CRAWL_STATUS_PL).fillna(df["crawl_status"])
    df["site_health_status_pl"] = df["site_health_status"].map(SITE_HEALTH_STATUS_PL).fillna(df["site_health_status"])
    if "places_status" in df:
        df["places_status"] = df["places_status"].fillna("").astype(str).replace("", "Brak danych")
        df["places_status_pl"] = df["places_status"].map(PLACES_STATUS_PL).fillna(df["places_status"])
    return df


def xlsx_bytes(sheets):
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for name, frame in sheets.items():
            safe_name = name[:31]
            frame.to_excel(writer, sheet_name=safe_name, index=False)
    return buffer.getvalue()


def get_dashboard_source_frame(key_prefix="source"):
    source = st.radio(
        "Źródło danych",
        ["Wybierz plik z folderu output", "Wgraj gotowy wynik XLSX/CSV/JSON", "Ostatni wynik z aplikacji"],
        horizontal=True,
        key=f"{key_prefix}_source",
    )
    df = pd.DataFrame()
    source_label = ""
    if source == "Ostatni wynik z aplikacji" and "bulk_results" in st.session_state:
        df = st.session_state["bulk_results"]
        source_label = "session"
    elif source == "Wgraj gotowy wynik XLSX/CSV/JSON":
        uploaded = st.file_uploader("Wrzuć wynik ETL/crawlera", type=["xlsx", "xls", "csv", "json"], key=f"{key_prefix}_upload")
        if uploaded:
            st.caption(f"Wybrany plik: {uploaded.name}")
            if st.button("Zastosuj plik", key=f"{key_prefix}_apply_upload"):
                df = load_dataframe_from_file(uploaded)
                source_label = uploaded.name
                st.session_state[f"{key_prefix}_resolved_df"] = df
                st.session_state[f"{key_prefix}_resolved_label"] = source_label
    else:
        output_files = [
            path for path in sorted(OUTPUT_DIR.glob("*"), key=lambda item: item.stat().st_mtime, reverse=True)
            if path.suffix.lower() in [".xlsx", ".csv", ".json"] and not path.name.endswith(".summary.json")
        ] if OUTPUT_DIR.exists() else []
        if output_files:
            default_index = next((idx for idx, path in enumerate(output_files) if "pelna" in path.name.lower()), 0)
            selected_file = st.selectbox("Plik z output", output_files, index=default_index, format_func=lambda path: path.name, key=f"{key_prefix}_output_file")
            st.caption(f"Wybrany plik: {selected_file.name}")
            if st.button("Zastosuj źródło", key=f"{key_prefix}_apply_output"):
                df = load_output_path(selected_file, selected_file.stat().st_mtime)
                source_label = selected_file.name
                st.session_state[f"{key_prefix}_resolved_df"] = df
                st.session_state[f"{key_prefix}_resolved_label"] = source_label
    return df, source_label


def resolve_dashboard_source_frame(key_prefix="source"):
    if f"{key_prefix}_resolved_df" in st.session_state:
        return st.session_state[f"{key_prefix}_resolved_df"], st.session_state.get(f"{key_prefix}_resolved_label", "session")

    source = st.session_state.get(f"{key_prefix}_source", "Wybierz plik z folderu output")
    if source == "Ostatni wynik z aplikacji" and "bulk_results" in st.session_state:
        return st.session_state["bulk_results"], "session"

    auto_df, auto_path = auto_pick_dataset()
    if not auto_df.empty:
        return auto_df, Path(auto_path).name if auto_path else "auto"
    latest_df, latest_path = load_latest_output()
    return latest_df, latest_path.name if latest_path else ""


def render_sources_view():
    st.caption("Pliki startowe, próbki i lokalne artefakty do pracy z bazą.")
    left, right = st.columns([1.1, 1])
    with left:
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.markdown("### Pliki wsadowe")
        st.markdown(
            """
<div class="mini-grid">
  <div class="mini-card"><strong>Wzór pliku</strong><span>Pełny szablon z kolumnami do importu.</span></div>
  <div class="mini-card"><strong>Test 100</strong><span>Mały wsad do szybkiego sprawdzenia crawla.</span></div>
  <div class="mini-card"><strong>XML</strong><span>Alternatywny format dla integracji.</span></div>
</div>
""",
            unsafe_allow_html=True,
        )
        st.write("")
        if TEMPLATE_PATH.exists():
            st.download_button("Pobierz wzór pliku", TEMPLATE_PATH.read_bytes(), file_name=TEMPLATE_DOWNLOAD_NAME, mime=OUTPUT_MIME_TYPES[".xlsx"], width="stretch")
        if SAMPLE_100_XLSX_PATH.exists():
            st.download_button("Pobierz przykład 100 rekordów", SAMPLE_100_XLSX_PATH.read_bytes(), file_name=SAMPLE_100_XLSX_PATH.name, mime=OUTPUT_MIME_TYPES[".xlsx"], width="stretch")
        if SAMPLE_XML_PATH.exists():
            st.download_button("Pobierz przykład XML", SAMPLE_XML_PATH.read_bytes(), file_name="leadseason_sample.xml", mime="application/xml", width="stretch")
        st.markdown("</div>", unsafe_allow_html=True)
    with right:
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.markdown("### Ostatnie wyniki lokalne")
        outputs = sorted(OUTPUT_DIR.glob("*"), key=lambda path: path.stat().st_mtime, reverse=True)[:12] if OUTPUT_DIR.exists() else []
        if outputs:
            st.dataframe(
                pd.DataFrame(
                    [{"plik": item.name, "MB": round(item.stat().st_size / 1024 / 1024, 2)} for item in outputs]
                ),
                width="stretch",
                height=330,
            )
        else:
            st.info("Brak wyników w folderze output.")
        st.markdown("</div>", unsafe_allow_html=True)


def render_generator_view():
    st.caption("Import i enrichment: wrzuć bazę, pobierz dane ze stron WWW i dociągnij sygnały Google Places/GMB.")
    left, right = st.columns([1.1, 1])

    with left:
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.markdown("### 1. Wgraj bazę klientów")
        uploaded = st.file_uploader("Wrzuć plik wsadowy", type=["xml", "xlsx", "xls", "csv"], key="generator_upload")
        st.caption("Minimum: `id`, `detail_id`, `nip`, `domain`. Dodatkowe pola typu opiekun, MRR i pakiet wzbogacają dashboard.")
        st.markdown('<div class="hint">Ten krok tworzy bazę techniczną dla LLM: dane CRM + crawl WWW + opcjonalnie Google Places/GMB.</div>', unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with right:
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.markdown("### 2. Ustaw enrichment")
        workers = st.slider("Równoległe domeny", min_value=1, max_value=40, value=DEFAULT_WORKERS)
        timeout = st.slider("Timeout na domenę", min_value=5, max_value=45, value=15)
        limit = st.number_input("Limit rekordów testowych", min_value=0, value=0, step=100)
        force = st.checkbox("Ignoruj cache domen", value=False)
        st.checkbox(
            "Druga runda dla blokad WWW",
            value=True,
            disabled=True,
            help="Crawler automatycznie robi wolniejszy retry i browser fallback dla stron z weryfikatorem/anti-botem.",
        )
        use_places = st.checkbox("Dociągnij dane Google Places/GMB", value=False)
        places_api_key = ""
        if use_places:
            places_api_key = st.text_input("Google Places API key", type="password")
        output_format = st.selectbox("Format eksportu", ["xlsx", "csv", "json"], index=0)
        st.markdown("</div>", unsafe_allow_html=True)

    if not uploaded:
        return

    tmp_dir = Path(tempfile.mkdtemp(prefix="leadseason_bulk_"))
    suffix = Path(uploaded.name).suffix or ".xml"
    input_path = tmp_dir / f"input{suffix}"
    input_path.write_bytes(uploaded.getvalue())

    try:
        records = parse_input_records(input_path)
        unique_domains = len({row["domain_key"] for row in records if row["domain_key"]})
        st.markdown("### Kontrola wsadu")
        c1, c2, c3 = st.columns(3)
        c1.metric("Rekordy", len(records))
        c2.metric("Unikalne domeny", unique_domains)
        c3.metric("Mniej wejść dzięki deduplikacji", f"{max(len(records) - unique_domains, 0):,}".replace(",", " "))
        st.dataframe(pd.DataFrame(records[: min(20, len(records))]), width="stretch", height=250)

        if st.button("Uruchom crawl i enrichment", type="primary", width="stretch"):
            output_path = tmp_dir / f"leadseason_results.{output_format}"
            with st.spinner("Pobieram dane: crawl WWW, metadane, treść strony i Google Places/GMB..."):
                rows = run_bulk(
                    input_xml=input_path,
                    output_path=output_path,
                    cache_dir=BASE_DIR / "cache" / "domains",
                    workers=workers,
                    timeout=timeout,
                    force=force,
                    limit=int(limit or 0),
                    use_places=use_places,
                    places_api_key=places_api_key,
                    places_cache_dir=BASE_DIR / "cache" / "places",
                )
            df = prepare_dashboard_frame(pd.DataFrame(rows))
            st.session_state["bulk_results"] = df
            st.session_state["bulk_output_path"] = output_path
            st.session_state["bulk_summary_path"] = output_path.with_suffix(".summary.json")
            st.success(f"Gotowe: {len(df)} rekordów. Teraz przejdź do Klasyfikacji branż.")
            render_results_tabs(df, output_path, st.session_state.get("bulk_summary_path"))
    except Exception as exc:
        st.error(str(exc))


def metric_percent(part, total):
    if not total:
        return "0%"
    return f"{part / total * 100:.1f}%"


def valid_signal_mask(series):
    norm = series.fillna("").astype(str).str.strip().str.lower()
    return norm.ne("") & ~norm.isin(["brak danych", "nieokreślona", "nieokreslona", "nan", "do weryfikacji", "-"])


def current_industry_mask(df):
    if df.empty:
        return pd.Series(dtype=bool)
    masks = []
    for col in ["branza_glowna", "ai_branza_glowna"]:
        if col in df:
            masks.append(valid_signal_mask(df[col]))
    if "classification_confidence" in df:
        masks.append(pd.to_numeric(df["classification_confidence"], errors="coerce").fillna(0).gt(0))
    if "industry_confidence" in df:
        masks.append(pd.to_numeric(df["industry_confidence"], errors="coerce").fillna(0).gt(0))
    if not masks:
        return pd.Series(False, index=df.index)
    result = masks[0].copy()
    for mask in masks[1:]:
        result = result | mask
    return result.reindex(df.index, fill_value=False)


def top_counts(df, column, limit=12):
    if column not in df or df.empty:
        return pd.DataFrame(columns=[column, "liczba"])
    series = df[column].fillna("").replace("", "Brak danych").value_counts().head(limit)
    return series.rename_axis(column).reset_index(name="liczba")


def render_dashboard_view():
    df, source_label = resolve_dashboard_source_frame("dashboard")
    if df.empty:
        st.info("Wgraj plik albo najpierw przelicz bazę w widoku Import i enrichment.")
        with st.expander("Źródło danych i konfiguracja dashboardu", expanded=True):
            get_dashboard_source_frame("dashboard")
        return

    df = prepare_dashboard_frame(df)
    render_q4_pipeline_hero(df, source_label)
    with st.expander("Źródło danych i konfiguracja dashboardu", expanded=False):
        configured_df, configured_label = get_dashboard_source_frame("dashboard")
        if not configured_df.empty and configured_label != source_label:
            st.info("Źródło zostało zmienione. Dashboard odświeży się automatycznie po zmianie wyboru.")
    st.caption("Dashboard operacyjny: wielkość bazy, branże, Q4, opiekunowie, MRR i jakość danych.")
    st.caption(f"Źródło: {source_label}")

    total = len(df)
    unique_clients = df["id"].replace("", pd.NA).dropna().nunique() if "id" in df else 0
    unique_domains = df["domain_key"].replace("Brak danych", pd.NA).dropna().nunique()
    q4_df = df[df["q4_priority"].astype(str).isin(Q4_VALUES)]
    review_df = df[df["q4_priority"].astype(str).eq("DO_WERYFIKACJI")]
    ok_rows = int((df["crawl_status"] == "OK").sum()) if "crawl_status" in df else 0
    bad_health_values = ["FETCH_ERROR", "BLOCKED", "PLACEHOLDER", "INACTIVE", "PARKED", "NO_SIGNAL"]
    bad_site_df = df[df["site_health_status"].astype(str).isin(bad_health_values)] if "site_health_status" in df else pd.DataFrame()
    usable_for_llm = int(df["usable_for_llm"].astype(str).str.lower().isin(["true", "1", "tak", "yes"]).sum()) if "usable_for_llm" in df else ok_rows
    retry_saved = int(df["crawl_retry_reason"].astype(str).str.contains("improved site health", case=False, na=False).sum()) if "crawl_retry_reason" in df else 0
    industry_ready_mask = current_industry_mask(df)
    detected_rows = int(industry_ready_mask.sum())
    industry_review_rows = max(total - detected_rows, 0)
    mrr_sum = df["_mrr_num"].sum()
    mrr_coverage = int((df["_mrr_num"] > 0).sum())

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Rekordy", f"{total:,}".replace(",", " "))
    c2.metric("Klienci", f"{unique_clients:,}".replace(",", " "))
    c3.metric("Domeny", f"{unique_domains:,}".replace(",", " "))
    c4.metric("Rekordy sezonowe", f"{len(q4_df):,}".replace(",", " "), metric_percent(len(q4_df), total))
    c5.metric("MRR w bazie", f"{mrr_sum:,.0f}".replace(",", " ") if mrr_sum else "Brak danych", metric_percent(mrr_coverage, total))

    c6, c7, c8, c9, c10, c11 = st.columns(6)
    c6.metric("Crawl OK", metric_percent(ok_rows, total), f"{ok_rows} rekordów")
    c7.metric("Strony użyteczne", metric_percent(usable_for_llm, total), f"{usable_for_llm} dla LLM")
    c8.metric("Strony niedziałające", metric_percent(len(bad_site_df), total), f"{len(bad_site_df)} rekordów")
    c9.metric("Uratowane retry", retry_saved)
    c10.metric("Branża przypisana", metric_percent(detected_rows, total), f"{detected_rows} po aktualnym pipeline")
    c11.metric("Branża do AI/weryfikacji", metric_percent(industry_review_rows, total), f"{industry_review_rows} rekordów")

    filters_col, table_col = st.columns([.8, 1.4])
    with filters_col:
        st.markdown("### Filtry")
        priorities = sorted([item for item in df["q4_priority"].dropna().unique() if str(item)])
        selected_priorities = st.multiselect("Priorytet", priorities, default=[], placeholder="Wszystkie priorytety")
        owners = sorted([item for item in df["account_owner"].dropna().unique() if str(item)])
        selected_owners = st.multiselect("Opiekun", owners, default=[], placeholder="Wszyscy opiekunowie")
        industries = sorted([item for item in df["detected_industry"].dropna().unique() if str(item)])
        selected_industries = st.multiselect("Branża", industries, default=[], placeholder="Wszystkie branże")
        health_options = (
            df[["site_health_status", "site_health_status_pl"]]
            .drop_duplicates()
            .sort_values("site_health_status_pl")
            .to_dict(orient="records")
        )
        selected_health_labels = st.multiselect(
            "Zdrowie strony",
            [item["site_health_status_pl"] for item in health_options],
            default=[],
            placeholder="Wszystkie statusy",
        )
        selected_health = [
            item["site_health_status"]
            for item in health_options
            if item["site_health_status_pl"] in selected_health_labels
        ]
        st.caption("Wpisz, żeby zawęzić listę. Pusty wybór oznacza wszystkie wartości.")

    filtered = df.copy()
    if selected_priorities:
        filtered = filtered[filtered["q4_priority"].isin(selected_priorities)]
    if selected_owners:
        filtered = filtered[filtered["account_owner"].isin(selected_owners)]
    if selected_industries:
        filtered = filtered[filtered["detected_industry"].isin(selected_industries)]
    if selected_health:
        filtered = filtered[filtered["site_health_status"].isin(selected_health)]

    with table_col:
        st.markdown("### Co analizujesz")
        analysis_section = st.radio(
            "Sekcja",
            ["Branże", "Opiekunowie", "Pakiety", "Jakość danych", "Niedziałające strony", "Tabela", "Eksport"],
            horizontal=True,
            label_visibility="collapsed",
            key="dashboard_analysis_section",
        )
        st.caption(f"Po filtrach: {len(filtered):,} rekordów".replace(",", " "))

    if analysis_section == "Branże":
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("#### Top branże")
            industry_counts = top_counts(filtered, "detected_industry", 15)
            st.bar_chart(industry_counts.set_index("detected_industry"))
        with col_b:
            st.markdown("#### Priorytety Q4")
            priority_counts = top_counts(filtered, "q4_priority", 10)
            st.bar_chart(priority_counts.set_index("q4_priority"))

    elif analysis_section == "Opiekunowie":
        owner_summary = (
            filtered.groupby("account_owner", dropna=False)
            .agg(
                rekordy=("id", "count"),
                q4=("q4_priority", lambda s: int(s.isin(Q4_VALUES).sum())),
                mrr=("_mrr_num", "sum"),
                domeny=("domain_key", "nunique"),
            )
            .reset_index()
            .sort_values(["q4", "mrr"], ascending=False)
        )
        st.dataframe(owner_summary, width="stretch", height=420)

    elif analysis_section == "Pakiety":
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("#### Pakiety / usługi")
            if "service" in filtered:
                service_counts = top_counts(filtered, "service", 15)
                st.bar_chart(service_counts.set_index("service"))
            else:
                st.info("Brak kolumny `service`.")
        with col_b:
            st.markdown("#### Koszyk SEO / dostęp")
            if "seo_basket" in filtered:
                basket_counts = top_counts(filtered, "seo_basket", 12)
                st.bar_chart(basket_counts.set_index("seo_basket"))
            elif "access_type" in filtered:
                access_counts = top_counts(filtered, "access_type", 12)
                st.bar_chart(access_counts.set_index("access_type"))
            else:
                st.info("Brak kolumn `seo_basket` / `access_type`.")

    elif analysis_section == "Jakość danych":
        status_counts = top_counts(filtered, "crawl_status_pl", 10)
        health_counts = top_counts(filtered, "site_health_status_pl", 10)
        places_counts = top_counts(filtered, "places_status_pl", 10) if "places_status_pl" in filtered else pd.DataFrame()
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            st.markdown("#### Status crawla")
            st.bar_chart(status_counts.set_index("crawl_status_pl"))
        with col_b:
            st.markdown("#### Zdrowie strony")
            if not health_counts.empty:
                st.bar_chart(health_counts.set_index("site_health_status_pl"))
                st.dataframe(health_counts, width="stretch", hide_index=True)
            else:
                st.info("Brak kolumny `site_health_status` w tym pliku.")
        with col_c:
            st.markdown("#### Status Google Places")
            if not places_counts.empty:
                st.bar_chart(places_counts.set_index("places_status_pl"))
                st.dataframe(places_counts, width="stretch", hide_index=True)
            else:
                st.info(
                    "Brak danych Google Places/GMB w tym outputcie. Ten plik został przeliczony bez etapu Places "
                    "albo bez klucza API. Uruchom ponownie import z opcją `Dociągnij dane Google Places/GMB`."
                )

    elif analysis_section == "Niedziałające strony":
        st.markdown("### Strony niedziałające lub nieużyteczne")
        bad_filtered = filtered[filtered["site_health_status"].astype(str).isin(bad_health_values)] if "site_health_status" in filtered else pd.DataFrame()
        reason_counts = top_counts(bad_filtered, "site_health_status_pl", 10)
        col_a, col_b = st.columns([0.9, 1.4])
        with col_a:
            if not reason_counts.empty:
                st.bar_chart(reason_counts.set_index("site_health_status_pl"))
                st.dataframe(reason_counts, width="stretch", hide_index=True)
            else:
                st.success("W aktualnym filtrze nie ma niedziałających stron.")
        with col_b:
            bad_cols = [
                col for col in [
                    "account_owner", "id", "company", "domain_key", "crawl_status_pl",
                    "site_health_status_pl", "site_health_reason", "http_status", "final_url",
                    "title", "detected_industry",
                ] if col in bad_filtered.columns
            ]
            st.dataframe(bad_filtered[bad_cols], width="stretch", height=420, hide_index=True)

    elif analysis_section == "Tabela":
        st.markdown("### Przekrój po filtrach")
        display_cols = [
            col for col in [
                "account_owner", "id", "nip", "company", "domain_key", "detected_industry",
                "site_health_status_pl", "site_health_reason", "q4_priority", "season_peak", "contact_start",
            ] if col in filtered.columns
        ]
        st.dataframe(filtered[display_cols].head(500), width="stretch", height=460)
        if len(filtered) > 500:
            st.caption("Tabela pokazuje pierwsze 500 rekordów dla szybkości. Pełny zakres pobierzesz w eksporcie.")

    elif analysis_section == "Eksport":
        q4_export = filtered[filtered["q4_priority"].isin(Q4_VALUES)]
        review_export = filtered[filtered["q4_priority"].eq("DO_WERYFIKACJI")]
        owner_summary = (
            filtered.groupby("account_owner", dropna=False)
            .agg(
                rekordy=("id", "count"),
                q4=("q4_priority", lambda s: int(s.isin(Q4_VALUES).sum())),
                mrr=("_mrr_num", "sum"),
                domeny=("domain_key", "nunique"),
            )
            .reset_index()
            .sort_values(["q4", "mrr"], ascending=False)
        )
        export_payload = xlsx_bytes(
            {
                "Dashboard filtered": filtered,
                "Rekordy sezonowe": q4_export,
                "Do weryfikacji": review_export,
                "Niedziałające strony": bad_site_df,
                "Opiekunowie": owner_summary,
            }
        )
        st.download_button(
            "Pobierz dashboard jako XLSX",
            export_payload,
            file_name="leadseason_dashboard_operacyjny.xlsx",
            mime=OUTPUT_MIME_TYPES[".xlsx"],
            width="stretch",
        )


def render_claude_view():
    st.caption("Klasyfikacja branż: eksport danych po crawlu, import klasyfikacji LLM i kontrola rekordów niepewnych.")
    df, source_label = get_dashboard_source_frame("claude")
    if df.empty:
        st.info("Wybierz plik wynikowy albo przelicz bazę w widoku Import i enrichment.")
        return

    df = prepare_dashboard_frame(df)
    eligible_mask = df.apply(lambda row: (
                            str(row.get("detected_industry") or "").strip().lower() in ["", "brak danych"]
                            or str(row.get("detected_industry") or "").strip().lower().startswith("nieokre"))
                            and str(row.get("crawl_status") or "") == "OK"
                            and str(row.get("site_health_status") or "OK") == "OK"
                            and str(row.get("usable_for_llm", True)).lower() not in ["false", "0", "nie", "no"]
                            and bool(str(row.get("body_text_sample") or row.get("title") or "").strip()), axis=1)
    eligible_count = int(eligible_mask.sum())
    total = len(df)
    st.caption(f"Źródło: {source_label}")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Rekordy w bazie", total)
    c2.metric("Do LLM", eligible_count, f"{eligible_count / total * 100:.1f}%" if total else "0%")
    c3.metric("Nieokreślona", int(df["detected_industry"].eq("Nieokreślona").sum()))
    c4.metric("Crawl OK", int(df["crawl_status"].eq("OK").sum()))

    tab_export, tab_import, tab_prompt = st.tabs(["Eksport dla LLM", "Import klasyfikacji", "Prompt"])

    with tab_export:
        st.markdown("### Paczka danych dla LLM")
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            only_unclassified = st.checkbox("Tylko Nieokreślona + crawl OK", value=True)
        with col_b:
            start = st.number_input("Offset", min_value=0, value=0, step=100)
        with col_c:
            limit = st.number_input("Limit batcha", min_value=1, max_value=1000, value=100, step=50)

        records = build_ai_batch(df, only_unclassified=only_unclassified, limit=int(limit), start=int(start))
        st.metric("Rekordy w paczce", len(records))
        if records:
            preview = pd.DataFrame([{"record_key": item["record_key"], **item["context"]} for item in records[:20]])
            st.dataframe(preview, width="stretch", height=260)
            st.download_button(
                "Pobierz JSONL dla LLM",
                jsonl_bytes(records),
                file_name=f"leadseason_claude_batch_{int(start)}_{int(limit)}.jsonl",
                mime="application/jsonl",
                width="stretch",
            )

    with tab_import:
        st.markdown("### Scal zweryfikowaną kategoryzację z bazą")
        result_file = st.file_uploader("Wrzuć wynik LLM JSONL/JSON/XLSX/CSV", type=["jsonl", "json", "xlsx", "xls", "csv"], key="claude_results_upload")
        if result_file:
            try:
                results_df = read_ai_results(result_file)
                merged, stats = merge_ai_results(df, results_df)
                merged = prepare_dashboard_frame(merged)
                st.session_state["bulk_results"] = merged
                st.success(f"Scalono {stats['updated']} z {stats['input_results']} wyników LLM.")
                st.dataframe(
                    merged[
                        [col for col in [
                            "id", "detail_id", "domain_key", "detected_industry", "industry_confidence",
                            "branza_glowna", "podbranza", "usluga_glowna", "model_b2b_b2c", "classification_source",
                        ] if col in merged.columns]
                    ].head(200),
                    width="stretch",
                    height=360,
                )
                st.download_button(
                    "Pobierz bazę po LLM jako XLSX",
                    xlsx_bytes({"Po Claude": merged}),
                    file_name="leadseason_po_claude.xlsx",
                    mime=OUTPUT_MIME_TYPES[".xlsx"],
                    width="stretch",
                )
            except Exception as exc:
                st.error(str(exc))

    with tab_prompt:
        st.markdown("### Instrukcja dla LLM")
        st.code(CLAUDE_PROMPT, language="markdown")


def render_maxun_experiment_view():
    st.caption("Eksperyment Maxun: sprawdź, czy browserowy scrape/crawl poprawia rekordy z niepewną branżą.")
    _, category_data = load_category_report_frames()
    active_df, active_label = auto_pick_dataset()
    active_df = prepare_dashboard_frame(active_df) if not active_df.empty else active_df

    tab_rescue, tab_batch, tab_import, tab_prompt = st.tabs(["Ratunek crawla ERROR", "Paczka testowa branż", "Import wyników", "Instrukcja"])

    with tab_rescue:
        st.markdown("### Druga runda: Maxun dla błędów crawla i stron bez sygnału")
        st.markdown(
            """
<div class="hint">
Ten etap bierze domeny, których nasz szybki crawler nie ogarnął albo zebrał za mało sygnału.
Maxun/Chrome ma wejść wolniej, poczekać na weryfikatory i zebrać tekst do LLM. To jest ratunek jakości,
nie główna metoda dla całej bazy.
</div>
""",
            unsafe_allow_html=True,
        )
        if active_df.empty:
            st.info("Brak aktywnej bazy. Najpierw wybierz albo przelicz plik w dashboardzie/zasileniu danych.")
        else:
            rescue_limit = st.number_input("Limit domen do ratunku", min_value=10, max_value=500, value=100, step=10, key="maxun_rescue_limit")
            wait_after = st.slider("Opóźnienie po wejściu na stronę", min_value=5, max_value=45, value=18, step=1, key="maxun_rescue_wait")
            rescue = select_maxun_crawl_rescue_candidates(active_df, limit=int(rescue_limit), wait_after=int(wait_after))
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Kandydaci", len(rescue))
            c2.metric("Unikalne domeny", rescue["domain_key"].nunique() if "domain_key" in rescue else 0)
            c3.metric("Błąd pobrania", int(rescue["crawl_status"].astype(str).eq("ERROR").sum()) if "crawl_status" in rescue else 0)
            c4.metric("Źródło", active_label or "auto")
            view_cols = [
                "domain_key", "url", "crawl_status_pl", "site_health_status_pl", "site_health_reason",
                "http_status", "error", "title", "company", "account_owner", "rescue_reason",
            ]
            st.dataframe(rescue[[col for col in view_cols if col in rescue.columns]], width="stretch", height=360, hide_index=True)
            records = build_maxun_crawl_rescue_records(rescue, wait_after=int(wait_after))
            col_a, col_b, col_c = st.columns(3)
            with col_a:
                if st.button("Zapisz paczkę ratunkową", type="primary", width="stretch"):
                    save_maxun_crawl_rescue_batch(rescue, wait_after=int(wait_after))
                    st.success(f"Zapisano `{MAXUN_RESCUE_PATH.name}` oraz JSONL.")
            with col_b:
                if records:
                    st.download_button(
                        "Pobierz JSONL ratunkowy",
                        jsonl_bytes(records),
                        file_name=MAXUN_RESCUE_JSONL_PATH.name,
                        mime="application/jsonl",
                        width="stretch",
                    )
            with col_c:
                if MAXUN_RESCUE_PATH.exists():
                    st.download_button(
                        "Pobierz paczkę XLSX",
                        MAXUN_RESCUE_PATH.read_bytes(),
                        file_name=MAXUN_RESCUE_PATH.name,
                        mime=OUTPUT_MIME_TYPES[".xlsx"],
                        width="stretch",
                    )

    with tab_batch:
        if category_data.empty:
            st.info("Brak raportu kategoryzacji. Najpierw zbuduj lub wgraj raport w widoku Jakość kategoryzacji.")
        else:
            st.markdown("### Kandydaci do testu Maxun")
            st.markdown(
                """
<div class="hint">
Wybieramy domeny, gdzie obecny proces ma niski confidence, bucket do weryfikacji, brak branży albo słaby sygnał Places.
Maxun ma zebrać bogatszy materiał ze strony, a potem LLM może ponownie zweryfikować branżę.
</div>
""",
                unsafe_allow_html=True,
            )
            limit = st.number_input("Limit kandydatów", min_value=5, max_value=200, value=50, step=5)
            candidates = select_maxun_experiment_candidates(category_data, limit=int(limit))
            c1, c2, c3 = st.columns(3)
            c1.metric("Kandydaci", len(candidates))
            c2.metric("Unikalne domeny", candidates["domain_key"].nunique() if "domain_key" in candidates else 0)
            c3.metric("Nieokreślone", int(candidates["ai_branza_glowna"].astype(str).str.lower().isin(["nieokreślona", "nieokreslona", ""]).sum()) if "ai_branza_glowna" in candidates else 0)

            view_cols = [
                "domain_key", "company", "url", "ai_branza_glowna", "ai_podbranza",
                "ai_confidence", "category_quality_bucket", "places_status", "places_match_confidence", "powod_eksperymentu",
            ]
            st.dataframe(candidates[[col for col in view_cols if col in candidates.columns]], width="stretch", height=360)

            if st.button("Zapisz paczkę eksperymentu", type="primary", width="stretch"):
                save_maxun_experiment_batch(candidates)
                st.success(f"Zapisano paczkę: `{MAXUN_EXPERIMENT_PATH.name}`, CSV i JSONL.")

            col_a, col_b, col_c = st.columns(3)
            records = build_maxun_experiment_records(candidates)
            with col_a:
                if records:
                    st.download_button(
                        "Pobierz JSONL do Maxun",
                        jsonl_bytes(records),
                        file_name=MAXUN_EXPERIMENT_JSONL_PATH.name,
                        mime="application/jsonl",
                        width="stretch",
                    )
            with col_b:
                st.download_button(
                    "Pobierz instrukcję",
                    MAXUN_EXPERIMENT_PROMPT.encode("utf-8"),
                    file_name="leadseason_instrukcja_maxun_experiment.txt",
                    mime="text/plain",
                    width="stretch",
                )
            with col_c:
                if MAXUN_EXPERIMENT_PATH.exists():
                    st.download_button(
                        "Pobierz paczkę XLSX",
                        MAXUN_EXPERIMENT_PATH.read_bytes(),
                        file_name=MAXUN_EXPERIMENT_PATH.name,
                        mime=OUTPUT_MIME_TYPES[".xlsx"],
                        width="stretch",
                    )

    with tab_import:
        st.markdown("### Wynik eksperymentu")
        st.caption("Wgraj JSONL/JSON/CSV/XLSX zwrócony przez Maxun albo przez Claude korzystającego z Maxun MCP.")
        uploaded = st.file_uploader("Wrzuć wynik Maxun", type=["jsonl", "json", "xlsx", "xls", "csv"], key="maxun_results_upload")
        if not uploaded and MAXUN_RESULTS_PATH.exists():
            workbook = pd.ExcelFile(MAXUN_RESULTS_PATH)
            summary = pd.read_excel(workbook, sheet_name="metryki", dtype=str, keep_default_na=False) if "metryki" in workbook.sheet_names else pd.DataFrame()
            comparison = pd.read_excel(workbook, sheet_name="porownanie", dtype=str, keep_default_na=False) if "porownanie" in workbook.sheet_names else pd.DataFrame()
            st.success(f"Pokazuję ostatni zapisany eksperyment: `{MAXUN_RESULTS_PATH.name}`.")
            if not summary.empty:
                metric_cols = st.columns(min(4, len(summary)))
                for idx, row in summary.head(4).iterrows():
                    metric_cols[idx % len(metric_cols)].metric(str(row.get("metryka", "")), str(row.get("wartosc", "")))
                st.dataframe(summary, width="stretch", hide_index=True)
            if not comparison.empty:
                st.dataframe(comparison.head(100), width="stretch", height=430)
            st.download_button(
                "Pobierz raport eksperymentu XLSX",
                MAXUN_RESULTS_PATH.read_bytes(),
                file_name=MAXUN_RESULTS_PATH.name,
                mime=OUTPUT_MIME_TYPES[".xlsx"],
                width="stretch",
            )
        if uploaded:
            try:
                raw = read_maxun_results(uploaded)
                normalized = normalize_maxun_results(raw)
                candidates = select_maxun_experiment_candidates(category_data, limit=200)
                comparison = compare_maxun_experiment(candidates, normalized)
                with pd.ExcelWriter(MAXUN_RESULTS_PATH, engine="openpyxl") as writer:
                    normalized.to_excel(writer, sheet_name="wyniki_maxun", index=False)
                    comparison.to_excel(writer, sheet_name="porownanie", index=False)
                ok_count = int(normalized["maxun_status"].eq("OK").sum()) if not normalized.empty else 0
                signal_count = int(comparison["czy_maxun_dodal_sygnal"].sum()) if not comparison.empty else 0
                c1, c2, c3 = st.columns(3)
                c1.metric("Wyniki", len(normalized))
                c2.metric("Maxun OK", ok_count)
                c3.metric("Dodał sygnał", signal_count)
                st.dataframe(comparison.head(100), width="stretch", height=430)
                st.download_button(
                    "Pobierz raport eksperymentu XLSX",
                    MAXUN_RESULTS_PATH.read_bytes(),
                    file_name=MAXUN_RESULTS_PATH.name,
                    mime=OUTPUT_MIME_TYPES[".xlsx"],
                    width="stretch",
                )
            except Exception as exc:
                st.error(str(exc))

    with tab_prompt:
        st.markdown("### Instrukcja dla Maxun / Claude z Maxun MCP")
        st.code(MAXUN_EXPERIMENT_PROMPT, language="markdown")


@st.cache_data(show_spinner=False, ttl=600)
def load_category_report_frames():
    if not CATEGORY_REPORT_PATH.exists():
        return pd.DataFrame(), pd.DataFrame()
    metrics = pd.read_excel(CATEGORY_REPORT_PATH, sheet_name="metryki", dtype=str, keep_default_na=False)
    data = pd.read_excel(CATEGORY_REPORT_PATH, sheet_name="kategoryzacja_500", dtype=str, keep_default_na=False)
    return metrics, data


def metric_value(metrics, name, default="0"):
    if metrics.empty or "metryka" not in metrics or "wartosc" not in metrics:
        return default
    rows = metrics[metrics["metryka"].eq(name)]
    if rows.empty:
        return default
    value = rows.iloc[0]["wartosc"]
    return str(value).replace(".0", "")


@st.cache_data(show_spinner=False, ttl=600)
def load_senuto_groups_frame():
    if not SENUTO_GROUPS_PATH.exists():
        return pd.DataFrame()
    workbook = pd.ExcelFile(SENUTO_GROUPS_PATH)
    sheet = "grupy_do_senuto" if "grupy_do_senuto" in workbook.sheet_names else workbook.sheet_names[0]
    return pd.read_excel(workbook, sheet_name=sheet, dtype=str, keep_default_na=False)


@st.cache_data(show_spinner=False, ttl=600)
def load_senuto_matrix_frame():
    if not SENUTO_MATRIX_PATH.exists():
        return pd.DataFrame()
    return pd.read_excel(SENUTO_MATRIX_PATH, dtype=str, keep_default_na=False)


SENUTO_MATRIX_COLUMNS = [
    "branza_glowna",
    "podbranza",
    "usluga_glowna",
    "model_b2b_b2c",
    "liczba_rekordow",
    "liczba_domen",
    "domen_z_danymi_senuto",
    "reprezentatywne_domeny",
    "reprezentatywne_frazy",
    "senuto_query_type",
    "senuto_queries_used",
    "sezon_peak_miesiace",
    "sezon_start_miesiac",
    "sezon_end_miesiac",
    "czy_sezonowosc_wyrazna",
    "confidence_sezonowosci",
    "senuto_evidence",
    "status",
]


def build_senuto_mcp_batch(groups, limit=50, only_pending=True, skip_unknown=True):
    if groups.empty:
        return []
    work = groups.copy()
    matrix = load_senuto_matrix_frame()
    checked_keys = set()
    if only_pending and not matrix.empty and {"branza_glowna", "podbranza", "usluga_glowna"}.issubset(matrix.columns):
        checked_keys = set(zip(
            matrix["branza_glowna"].astype(str).str.strip(),
            matrix["podbranza"].astype(str).str.strip(),
            matrix["usluga_glowna"].astype(str).str.strip(),
        ))
    if checked_keys and {"ai_branza_glowna", "ai_podbranza", "ai_usluga_glowna"}.issubset(work.columns):
        work["_key"] = list(zip(
            work["ai_branza_glowna"].astype(str).str.strip(),
            work["ai_podbranza"].astype(str).str.strip(),
            work["ai_usluga_glowna"].astype(str).str.strip(),
        ))
        work = work[~work["_key"].isin(checked_keys)]
    if skip_unknown and "ai_branza_glowna" in work:
        branch = work["ai_branza_glowna"].astype(str).str.strip().str.lower()
        work = work[~branch.isin(["", "nieokreślona", "nieokreslona", "brak danych", "brak sygnalu", "brak_sygnału"])]
    if "liczba_rekordow" in work:
        work["_records_num"] = as_number(work["liczba_rekordow"])
        work = work.sort_values("_records_num", ascending=False)
    if limit:
        work = work.head(int(limit))

    records = []
    for _, row in work.iterrows():
        records.append(
            {
                "group_key": " | ".join(
                    [
                        str(row.get("ai_branza_glowna") or "").strip(),
                        str(row.get("ai_podbranza") or "").strip(),
                        str(row.get("ai_usluga_glowna") or "").strip(),
                    ]
                ),
                "task": "senuto_seasonality_for_industry_group",
                "instruction": "Use Senuto MCP/API to return one JSON object in expected_output_schema. Do not invent seasonality when Senuto has no data.",
                "context": {
                    "branza_glowna": row.get("ai_branza_glowna", ""),
                    "podbranza": row.get("ai_podbranza", ""),
                    "usluga_glowna": row.get("ai_usluga_glowna", ""),
                    "model_b2b_b2c": row.get("ai_model_b2b_b2c", ""),
                    "liczba_rekordow": row.get("liczba_rekordow", ""),
                    "liczba_domen": row.get("liczba_domen", ""),
                    "reprezentatywne_domeny": row.get("reprezentatywne_domeny", ""),
                    "reprezentatywne_frazy": row.get("proponowane_frazy_senuto", ""),
                    "places_primary_types": row.get("places_primary_types", ""),
                },
                "expected_output_schema": {col: "string or number" for col in SENUTO_MATRIX_COLUMNS},
                "quality_rules": [
                    "Keep industry labels from input unchanged.",
                    "Set status=OK only when Senuto data supports the seasonality signal.",
                    "Set status=BRAK_DANYCH when no useful domain/keyword data exists.",
                    "Use pipe-separated month names when several months peak.",
                ],
            }
        )
    return records


def read_senuto_results(uploaded_file):
    name = uploaded_file.name.lower()
    payload = uploaded_file.getvalue()
    if name.endswith(".jsonl"):
        rows = []
        for line in payload.decode("utf-8-sig").splitlines():
            line = line.strip()
            if line:
                item = json.loads(line)
                if isinstance(item, dict) and "result" in item and isinstance(item["result"], dict):
                    item = item["result"]
                rows.append(item)
        return pd.DataFrame(rows)
    if name.endswith(".json"):
        data = json.loads(payload.decode("utf-8-sig"))
        if isinstance(data, dict):
            for key in ["rows", "data", "records", "items", "results"]:
                if isinstance(data.get(key), list):
                    data = data[key]
                    break
            if isinstance(data, dict):
                data = [data]
        return pd.DataFrame(data)
    if name.endswith(".csv"):
        return pd.read_csv(BytesIO(payload), sep=None, engine="python", dtype=str, keep_default_na=False, encoding="utf-8-sig")
    workbook = pd.ExcelFile(BytesIO(payload))
    sheet = "macierz_sezonowosci" if "macierz_sezonowosci" in workbook.sheet_names else workbook.sheet_names[0]
    return pd.read_excel(workbook, sheet_name=sheet, dtype=str, keep_default_na=False)


def normalize_senuto_matrix(results):
    if results.empty:
        return pd.DataFrame(columns=SENUTO_MATRIX_COLUMNS)
    df = results.copy()
    aliases = {
        "ai_branza_glowna": "branza_glowna",
        "ai_podbranza": "podbranza",
        "ai_usluga_glowna": "usluga_glowna",
        "ai_model_b2b_b2c": "model_b2b_b2c",
        "proponowane_frazy_senuto": "reprezentatywne_frazy",
        "status_senuto": "status",
    }
    df = df.rename(columns={old: new for old, new in aliases.items() if old in df.columns and new not in df.columns})
    for col in SENUTO_MATRIX_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df = df[SENUTO_MATRIX_COLUMNS].copy()
    df["status"] = df["status"].replace("", "DO_SPRAWDZENIA")
    for col in ["liczba_rekordow", "liczba_domen", "domen_z_danymi_senuto", "confidence_sezonowosci"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    for col in ["branza_glowna", "podbranza", "usluga_glowna", "model_b2b_b2c", "status"]:
        df[col] = df[col].astype(str).str.strip()
    df["status"] = df["status"].str.upper().replace("", "DO_SPRAWDZENIA")
    df = df.drop_duplicates(["branza_glowna", "podbranza", "usluga_glowna"], keep="last")
    return df


def save_senuto_matrix(matrix, merge_existing=True):
    output = matrix.copy()
    if merge_existing and SENUTO_MATRIX_PATH.exists():
        existing = load_senuto_matrix_frame()
        existing = normalize_senuto_matrix(existing)
        output = pd.concat([existing, output], ignore_index=True)
        output = output.drop_duplicates(["branza_glowna", "podbranza", "usluga_glowna"], keep="last")
    SENUTO_MATRIX_PATH.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(SENUTO_MATRIX_PATH, engine="openpyxl") as writer:
        output.to_excel(writer, sheet_name="macierz_sezonowosci", index=False)
    output.to_csv(SENUTO_MATRIX_PATH.with_suffix(".csv"), index=False, encoding="utf-8-sig")
    return output


def select_maxun_experiment_candidates(category_data, limit=50):
    if category_data.empty:
        return pd.DataFrame()
    df = category_data.copy()
    for col in [
        "domain_key", "domain", "company", "ai_branza_glowna", "ai_podbranza",
        "ai_usluga_glowna", "ai_confidence", "category_quality_bucket",
        "places_status", "places_match_confidence", "title", "meta_description", "ai_evidence",
    ]:
        if col not in df.columns:
            df[col] = ""
    conf = pd.to_numeric(df["ai_confidence"], errors="coerce").fillna(0)
    places_conf = pd.to_numeric(df["places_match_confidence"], errors="coerce").fillna(0)
    bucket = df["category_quality_bucket"].astype(str)
    branch = df["ai_branza_glowna"].astype(str).str.strip().str.lower()
    uncertain_mask = (
        conf.lt(70)
        | bucket.isin(["DO_WERYFIKACJI", "SREDNIA_AI", "NISKA_PEWNOSC_AI"])
        | branch.isin(["", "nieokreślona", "nieokreslona", "brak danych"])
        | places_conf.lt(60)
    )
    work = df[uncertain_mask].copy()
    work["_uncertainty_score"] = 0
    work["_uncertainty_score"] += (100 - conf).clip(0, 100)
    work["_uncertainty_score"] += bucket.isin(["DO_WERYFIKACJI", "NISKA_PEWNOSC_AI"]).astype(int) * 35
    work["_uncertainty_score"] += branch.isin(["", "nieokreślona", "nieokreslona", "brak danych"]).astype(int) * 50
    work["_uncertainty_score"] += places_conf.lt(60).astype(int) * 15
    if "domain_key" in work:
        work = work.drop_duplicates("domain_key", keep="first")
    work = work.sort_values("_uncertainty_score", ascending=False).head(int(limit or 50)).copy()
    work["record_key"] = work.apply(lambda row: str(row.get("domain_key") or row.name), axis=1)
    work["url"] = work["domain"].where(work["domain"].astype(str).str.startswith(("http://", "https://")), "https://" + work["domain_key"].astype(str))
    work["powod_eksperymentu"] = work.apply(
        lambda row: "; ".join(
            item for item in [
                f"AI confidence {row.get('ai_confidence', '')}",
                f"bucket {row.get('category_quality_bucket', '')}",
                "brak branży" if str(row.get("ai_branza_glowna", "")).strip().lower() in ["", "nieokreślona", "nieokreslona"] else "",
                f"Places {row.get('places_status', '')}/{row.get('places_match_confidence', '')}",
            ] if item
        ),
        axis=1,
    )
    return work.drop(columns=["_uncertainty_score"], errors="ignore")


def select_maxun_crawl_rescue_candidates(df, limit=100, wait_after=18):
    if df.empty:
        return pd.DataFrame()
    work = df.copy()
    for col in [
        "domain_key", "domain", "company", "account_owner", "crawl_status",
        "site_health_status", "site_health_reason", "http_status", "error",
        "title", "meta_description", "final_url", "site_text_chars",
    ]:
        if col not in work.columns:
            work[col] = ""
    crawl_status = work["crawl_status"].astype(str).str.upper()
    health = work["site_health_status"].astype(str).str.upper()
    text_chars = pd.to_numeric(work["site_text_chars"], errors="coerce").fillna(0)
    rescue_mask = (
        crawl_status.eq("ERROR")
        | health.isin(["FETCH_ERROR", "BLOCKED", "NO_SIGNAL"])
        | (crawl_status.eq("OK") & health.isin(["BLOCKED", "NO_SIGNAL"]) & text_chars.lt(1000))
    )
    rescue = work[rescue_mask].copy()
    if rescue.empty:
        return rescue
    rescue["domain_key"] = rescue["domain_key"].where(rescue["domain_key"].astype(str).str.strip().ne(""), rescue["domain"].astype(str))
    rescue = rescue.drop_duplicates("domain_key", keep="first")
    status_rank = crawl_status.reindex(rescue.index).map({"ERROR": 100, "OK": 20}).fillna(10)
    health_rank = health.reindex(rescue.index).map({"FETCH_ERROR": 80, "BLOCKED": 70, "NO_SIGNAL": 60}).fillna(0)
    rescue["_rescue_score"] = status_rank + health_rank + (1000 - text_chars.reindex(rescue.index).clip(0, 1000)) / 25
    rescue["url"] = rescue["domain"].where(
        rescue["domain"].astype(str).str.startswith(("http://", "https://")),
        "https://" + rescue["domain_key"].astype(str).str.replace(r"^https?://", "", regex=True).str.strip("/"),
    )
    rescue["wait_after_seconds"] = int(wait_after)
    rescue["crawl_status_pl"] = rescue["crawl_status"].map(CRAWL_STATUS_PL).fillna(rescue["crawl_status"])
    rescue["site_health_status_pl"] = rescue["site_health_status"].map(SITE_HEALTH_STATUS_PL).fillna(rescue["site_health_status"])
    rescue["rescue_reason"] = rescue.apply(
        lambda row: "; ".join(
            item for item in [
                f"crawl_status={row.get('crawl_status', '')}" if row.get("crawl_status") else "",
                f"site_health={row.get('site_health_status', '')}" if row.get("site_health_status") else "",
                f"reason={row.get('site_health_reason', '')}" if row.get("site_health_reason") else "",
                f"error={row.get('error', '')}" if row.get("error") else "",
                f"text_chars={row.get('site_text_chars', '')}" if str(row.get("site_text_chars", "")).strip() else "",
            ] if item
        ),
        axis=1,
    )
    rescue["record_key"] = rescue["domain_key"].astype(str)
    return rescue.sort_values("_rescue_score", ascending=False).head(int(limit or 100)).drop(columns=["_rescue_score"], errors="ignore")


def build_maxun_crawl_rescue_records(candidates, wait_after=18):
    records = []
    for _, row in candidates.iterrows():
        records.append(
            {
                "record_key": str(row.get("record_key") or row.get("domain_key") or ""),
                "task": "maxun_rescue_failed_crawl",
                "instruction": (
                    "Open the page in a real browser, wait before extraction, then collect LLM-ready content. "
                    "This is a second-pass rescue for pages where the fast crawler returned ERROR, BLOCKED or NO_SIGNAL."
                ),
                "url": row.get("url", ""),
                "wait_after_seconds": int(row.get("wait_after_seconds") or wait_after or 18),
                "preferred_pages": ["home", "oferta", "uslugi", "produkty", "o-nas", "kontakt"],
                "context": {
                    "domain_key": row.get("domain_key", ""),
                    "company": row.get("company", ""),
                    "account_owner": row.get("account_owner", ""),
                    "crawl_status": row.get("crawl_status", ""),
                    "site_health_status": row.get("site_health_status", ""),
                    "site_health_reason": row.get("site_health_reason", ""),
                    "http_status": row.get("http_status", ""),
                    "error": row.get("error", ""),
                    "current_title": row.get("title", ""),
                    "current_meta_description": row.get("meta_description", ""),
                    "reason": row.get("rescue_reason", ""),
                },
                "expected_output_schema": {
                    "record_key": "string",
                    "domain_key": "string",
                    "url": "string",
                    "maxun_status": "OK | EMPTY | BLOCKED | ERROR | NOT_FOUND",
                    "maxun_pages_crawled": "number",
                    "maxun_title": "string",
                    "maxun_meta_description": "string",
                    "maxun_markdown": "LLM-ready content after browser wait",
                    "maxun_offer_terms": "short offer/service phrases separated by |",
                    "maxun_evidence": "what changed vs fast crawler",
                },
            }
        )
    return records


def save_maxun_crawl_rescue_batch(candidates, wait_after=18):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    candidates.to_csv(MAXUN_RESCUE_CSV_PATH, index=False, encoding="utf-8-sig")
    with pd.ExcelWriter(MAXUN_RESCUE_PATH, engine="openpyxl") as writer:
        candidates.to_excel(writer, sheet_name="kandydaci_rescue", index=False)
        pd.DataFrame(build_maxun_crawl_rescue_records(candidates, wait_after=wait_after)).to_excel(writer, sheet_name="jsonl_preview", index=False)
    MAXUN_RESCUE_JSONL_PATH.write_bytes(jsonl_bytes(build_maxun_crawl_rescue_records(candidates, wait_after=wait_after)))
    return MAXUN_RESCUE_PATH


def build_maxun_experiment_records(candidates):
    records = []
    for _, row in candidates.iterrows():
        records.append(
            {
                "record_key": str(row.get("record_key") or row.get("domain_key") or ""),
                "task": "maxun_scrape_uncertain_industry_record",
                "instruction": "Use Maxun scrape/crawl to collect LLM-ready content for industry re-classification. Return expected_output_schema only.",
                "url": row.get("url", ""),
                "context": {
                    "domain_key": row.get("domain_key", ""),
                    "company": row.get("company", ""),
                    "current_branza_glowna": row.get("ai_branza_glowna", ""),
                    "current_podbranza": row.get("ai_podbranza", ""),
                    "current_usluga_glowna": row.get("ai_usluga_glowna", ""),
                    "current_ai_confidence": row.get("ai_confidence", ""),
                    "current_quality_bucket": row.get("category_quality_bucket", ""),
                    "current_title": row.get("title", ""),
                    "current_meta_description": row.get("meta_description", ""),
                    "reason": row.get("powod_eksperymentu", ""),
                },
                "expected_output_schema": {
                    "record_key": "string",
                    "domain_key": "string",
                    "url": "string",
                    "maxun_status": "OK | EMPTY | BLOCKED | ERROR | NOT_FOUND",
                    "maxun_pages_crawled": "number",
                    "maxun_title": "string",
                    "maxun_meta_description": "string",
                    "maxun_markdown": "string",
                    "maxun_offer_terms": "string",
                    "maxun_evidence": "string",
                },
            }
        )
    return records


def save_maxun_experiment_batch(candidates):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    candidates.to_csv(MAXUN_EXPERIMENT_CSV_PATH, index=False, encoding="utf-8-sig")
    with pd.ExcelWriter(MAXUN_EXPERIMENT_PATH, engine="openpyxl") as writer:
        candidates.to_excel(writer, sheet_name="kandydaci", index=False)
        pd.DataFrame(build_maxun_experiment_records(candidates)).to_excel(writer, sheet_name="jsonl_preview", index=False)
    MAXUN_EXPERIMENT_JSONL_PATH.write_bytes(jsonl_bytes(build_maxun_experiment_records(candidates)))
    return MAXUN_EXPERIMENT_PATH


def read_maxun_results(uploaded_file):
    name = uploaded_file.name.lower()
    payload = uploaded_file.getvalue()
    if name.endswith(".jsonl"):
        rows = []
        for line in payload.decode("utf-8-sig").splitlines():
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            if isinstance(item, dict) and "result" in item and isinstance(item["result"], dict):
                item = item["result"]
            rows.append(item)
        return pd.DataFrame(rows)
    if name.endswith(".json"):
        data = json.loads(payload.decode("utf-8-sig"))
        if isinstance(data, dict):
            for key in ["rows", "data", "records", "items", "results"]:
                if isinstance(data.get(key), list):
                    data = data[key]
                    break
            if isinstance(data, dict):
                data = [data]
        return pd.DataFrame(data)
    if name.endswith(".csv"):
        return pd.read_csv(BytesIO(payload), sep=None, engine="python", dtype=str, keep_default_na=False, encoding="utf-8-sig")
    workbook = pd.ExcelFile(BytesIO(payload))
    sheet = "wyniki_maxun" if "wyniki_maxun" in workbook.sheet_names else workbook.sheet_names[0]
    return pd.read_excel(workbook, sheet_name=sheet, dtype=str, keep_default_na=False)


def normalize_maxun_results(results):
    columns = [
        "record_key", "domain_key", "url", "maxun_status", "maxun_pages_crawled",
        "maxun_title", "maxun_meta_description", "maxun_markdown", "maxun_offer_terms", "maxun_evidence",
    ]
    if results.empty:
        return pd.DataFrame(columns=columns)
    df = results.copy()
    aliases = {"status": "maxun_status", "markdown": "maxun_markdown", "title": "maxun_title", "text": "maxun_markdown"}
    df = df.rename(columns={old: new for old, new in aliases.items() if old in df.columns and new not in df.columns})
    for col in columns:
        if col not in df.columns:
            df[col] = ""
    df = df[columns].copy()
    df["maxun_status"] = df["maxun_status"].replace("", "DO_SPRAWDZENIA").astype(str).str.upper()
    df["maxun_pages_crawled"] = pd.to_numeric(df["maxun_pages_crawled"], errors="coerce").fillna(0).astype(int)
    df["maxun_text_len"] = df["maxun_markdown"].astype(str).str.len()
    return df.drop_duplicates(["record_key", "domain_key"], keep="last")


def compare_maxun_experiment(candidates, results):
    if candidates.empty or results.empty:
        return pd.DataFrame()
    base_cols = [
        "record_key", "domain_key", "company", "ai_branza_glowna", "ai_podbranza",
        "ai_usluga_glowna", "ai_confidence", "category_quality_bucket", "powod_eksperymentu",
    ]
    left = candidates[[col for col in base_cols if col in candidates.columns]].copy()
    merged = left.merge(results, on=["record_key", "domain_key"], how="left")
    ai_conf = pd.to_numeric(merged.get("ai_confidence", 0), errors="coerce").fillna(0)
    text_len = pd.to_numeric(merged.get("maxun_text_len", 0), errors="coerce").fillna(0)
    pages = pd.to_numeric(merged.get("maxun_pages_crawled", 0), errors="coerce").fillna(0)
    status_ok = merged.get("maxun_status", "").astype(str).eq("OK")
    merged["maxun_signal_score"] = (status_ok.astype(int) * 35 + text_len.clip(0, 6000) / 100 + pages.clip(0, 5) * 5).clip(0, 100).round().astype(int)
    merged["czy_maxun_dodal_sygnal"] = merged["maxun_signal_score"].ge(50)
    merged["hipoteza_wplywu"] = merged.apply(
        lambda row: "wysoki potencjał poprawy" if row["czy_maxun_dodal_sygnal"] and float(row.get("ai_confidence") or 0) < 70 else (
            "dodatkowy materiał do LLM" if row["czy_maxun_dodal_sygnal"] else "brak poprawy z Maxun"
        ),
        axis=1,
    )
    merged["ai_confidence_before"] = ai_conf
    return merged


def as_number(series, default=0):
    return pd.to_numeric(series, errors="coerce").fillna(default)


def pct(part, total):
    if not total:
        return "0.0%"
    return f"{part / total * 100:.1f}%"


def q_bucket(value):
    try:
        score = float(value)
    except (TypeError, ValueError):
        score = 0
    if score >= 80:
        return "wysoka"
    if score >= 60:
        return "średnia"
    if score > 0:
        return "niska"
    return "brak"


def quality_score(row):
    score = 0
    if str(row.get("crawl_status") or "") == "OK":
        score += 20
    if str(row.get("places_status") or "") == "OK":
        score += 20
    if str(row.get("category_quality_bucket") or "") == "AI_PLUS_PLACES":
        score += 25
    score += min(float(pd.to_numeric(row.get("ai_confidence") or 0, errors="coerce") or 0), 100) * 0.35
    return int(round(min(score, 100)))


def build_category_metrics(data):
    if data.empty:
        return {}, pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    df = data.copy()
    total_rows = len(df)
    total_domains = df["domain_key"].replace("", pd.NA).dropna().nunique() if "domain_key" in df else total_rows
    if "ai_confidence" in df:
        df["_ai_conf"] = as_number(df["ai_confidence"])
    else:
        df["_ai_conf"] = 0
    if "places_match_confidence" in df:
        df["_places_conf"] = as_number(df["places_match_confidence"])
    else:
        df["_places_conf"] = 0
    df["_quality_score"] = df.apply(quality_score, axis=1)
    df["_quality_band"] = df["_quality_score"].map(q_bucket)

    ai_filled = df.get("ai_branza_glowna", pd.Series("", index=df.index)).astype(str).str.strip().ne("") & ~df.get("ai_branza_glowna", pd.Series("", index=df.index)).astype(str).str.lower().eq("nieokreślona")
    service_filled = df.get("ai_usluga_glowna", pd.Series("", index=df.index)).astype(str).str.strip().ne("")
    places_ok = df.get("places_status", pd.Series("", index=df.index)).astype(str).eq("OK")
    places_strong = places_ok & df["_places_conf"].ge(70)
    ai_places = df.get("category_quality_bucket", pd.Series("", index=df.index)).astype(str).eq("AI_PLUS_PLACES")
    review = df.get("category_quality_bucket", pd.Series("", index=df.index)).astype(str).isin(["DO_WERYFIKACJI", "NISKA_PEWNOSC_AI"])

    metrics = {
        "rows": total_rows,
        "domains": total_domains,
        "branches": df.get("ai_branza_glowna", pd.Series(dtype=str)).replace("", pd.NA).dropna().nunique(),
        "subbranches": df.get("ai_podbranza", pd.Series(dtype=str)).replace("", pd.NA).dropna().nunique(),
        "services": df.get("ai_usluga_glowna", pd.Series(dtype=str)).replace("", pd.NA).dropna().nunique(),
        "ai_domains": df[ai_filled]["domain_key"].nunique() if "domain_key" in df else int(ai_filled.sum()),
        "service_domains": df[service_filled]["domain_key"].nunique() if "domain_key" in df else int(service_filled.sum()),
        "places_domains": df[places_ok]["domain_key"].nunique() if "domain_key" in df else int(places_ok.sum()),
        "places_strong_domains": df[places_strong]["domain_key"].nunique() if "domain_key" in df else int(places_strong.sum()),
        "ai_places_domains": df[ai_places]["domain_key"].nunique() if "domain_key" in df else int(ai_places.sum()),
        "review_domains": df[review]["domain_key"].nunique() if "domain_key" in df else int(review.sum()),
        "avg_quality": round(df["_quality_score"].mean(), 1),
        "avg_ai_conf": round(df["_ai_conf"].mean(), 1),
    }
    branch_table = (
        df.groupby("ai_branza_glowna", dropna=False)
        .agg(
            rekordy=("domain_key", "size"),
            domeny=("domain_key", "nunique"),
            podbranze=("ai_podbranza", "nunique"),
            uslugi=("ai_usluga_glowna", "nunique"),
            srednia_pewnosc_ai=("_ai_conf", "mean"),
            ai_plus_places=("category_quality_bucket", lambda s: int(s.eq("AI_PLUS_PLACES").sum())),
            do_weryfikacji=("category_quality_bucket", lambda s: int(s.isin(["DO_WERYFIKACJI", "NISKA_PEWNOSC_AI"]).sum())),
            jakosc=("_quality_score", "mean"),
        )
        .reset_index()
        .sort_values("domeny", ascending=False)
    )
    for col in ["srednia_pewnosc_ai", "jakosc"]:
        branch_table[col] = branch_table[col].round(1)

    quality_table = df["_quality_band"].value_counts().rename_axis("poziom_jakosci").reset_index(name="rekordy")
    model_table = df.get("ai_model_b2b_b2c", pd.Series("", index=df.index)).replace("", "Brak danych").value_counts().rename_axis("model").reset_index(name="rekordy")
    return metrics, branch_table, quality_table, model_table


def build_seasonality_metrics(matrix, category_data):
    if matrix.empty:
        return {}, pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    m = matrix.copy()
    m["_confidence"] = as_number(m.get("confidence_sezonowosci", pd.Series(0, index=m.index)))
    ok = m.get("status", pd.Series("", index=m.index)).astype(str).eq("OK")
    clear = m.get("czy_sezonowosc_wyrazna", pd.Series("", index=m.index)).astype(str).eq("tak")
    hypothesis = ok & m["_confidence"].between(1, 69)
    confirmed = ok & clear & m["_confidence"].ge(70)

    matched_domains = 0
    q4_domains = 0
    if not category_data.empty and {"ai_branza_glowna", "ai_podbranza", "domain_key"}.issubset(category_data.columns):
        checked_keys = set(zip(m[ok]["branza_glowna"].astype(str).str.strip(), m[ok]["podbranza"].astype(str).str.strip()))
        q4_keys = set()
        q4_tokens = {"paz", "lis", "gru"}
        for _, row in m[ok].iterrows():
            months = [part.strip() for part in str(row.get("sezon_peak_miesiace") or "").split(",")]
            if any(month in q4_tokens for month in months):
                q4_keys.add((str(row.get("branza_glowna") or "").strip(), str(row.get("podbranza") or "").strip()))
        cat = category_data.copy()
        cat["_key"] = list(zip(cat["ai_branza_glowna"].astype(str).str.strip(), cat["ai_podbranza"].astype(str).str.strip()))
        matched_domains = cat[cat["_key"].isin(checked_keys)]["domain_key"].replace("", pd.NA).dropna().nunique()
        q4_domains = cat[cat["_key"].isin(q4_keys)]["domain_key"].replace("", pd.NA).dropna().nunique()

    metrics = {
        "groups_checked": len(m),
        "groups_ok": int(ok.sum()),
        "groups_no_data": int(m.get("status", pd.Series("", index=m.index)).astype(str).eq("BRAK_DANYCH").sum()),
        "groups_confirmed": int(confirmed.sum()),
        "groups_hypothesis": int(hypothesis.sum()),
        "groups_clear": int(clear.sum()),
        "avg_confidence": round(m["_confidence"].mean(), 1),
        "matched_domains": matched_domains,
        "q4_domains": q4_domains,
    }

    month_rows = []
    quarter_map = {"sty": "Q1", "lut": "Q1", "mar": "Q1", "kwi": "Q2", "maj": "Q2", "cze": "Q2", "lip": "Q3", "sie": "Q3", "wrz": "Q3", "paz": "Q4", "lis": "Q4", "gru": "Q4"}
    for _, row in m[ok].iterrows():
        domains = float(pd.to_numeric(row.get("liczba_domen") or 0, errors="coerce") or 0)
        for month in [part.strip() for part in str(row.get("sezon_peak_miesiace") or "").split(",") if part.strip()]:
            month_rows.append({"miesiac": MONTH_NAMES_PL.get(month, month), "kwartal": quarter_map.get(month, ""), "grupy": 1, "domeny": domains})
    month_table = pd.DataFrame(month_rows)
    if not month_table.empty:
        month_table = month_table.groupby(["kwartal", "miesiac"], as_index=False).agg(grupy=("grupy", "sum"), domeny=("domeny", "sum"))
    quarter_table = month_table.groupby("kwartal", as_index=False).agg(grupy=("grupy", "sum"), domeny=("domeny", "sum")) if not month_table.empty else pd.DataFrame()
    confidence_table = m["_confidence"].map(q_bucket).value_counts().rename_axis("confidence").reset_index(name="grupy")
    return metrics, month_table, quarter_table, confidence_table


def render_category_view():
    st.caption("Jakość kategoryzacji: pokrycie branż, zgodność z Google Places/GMB i rekordy do ręcznej weryfikacji.")

    left, right = st.columns([1, 1])
    with left:
        st.markdown(
            """
<div class="hint">
Tu oceniasz jakość branż po procesie enrichment + LLM. Google Places/GMB jest drugim sygnałem,
a stare reguły są tylko punktem porównania.
</div>
""",
            unsafe_allow_html=True,
        )
    with right:
        if st.button("Odśwież raport 500 domen", width="stretch", disabled=not CATEGORY_REPORT_SCRIPT.exists()):
            try:
                result = subprocess.run(
                    [sys.executable, str(CATEGORY_REPORT_SCRIPT)],
                    cwd=str(BASE_DIR),
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                if result.returncode == 0:
                    st.success("Raport kategoryzacji został przeliczony.")
                else:
                    st.error(result.stderr or result.stdout or "Nie udało się przeliczyć raportu.")
            except Exception as exc:
                st.error(str(exc))

    metrics, data = load_category_report_frames()
    if data.empty:
        st.info("Nie ma jeszcze raportu. Uruchom skrypt `scripts/build_category_quality_report.py` albo odśwież raport po wygenerowaniu plików Claude/Places.")
        return

    category_metrics, branch_quality, quality_table, model_table = build_category_metrics(data)
    data_display = data.copy()
    if "places_status" in data_display:
        data_display["places_status_pl"] = data_display["places_status"].map(PLACES_STATUS_PL).fillna(data_display["places_status"])
    if "category_quality_bucket" in data_display:
        data_display["category_quality_bucket_pl"] = data_display["category_quality_bucket"].map(CATEGORY_BUCKET_PL).fillna(data_display["category_quality_bucket"])
    domains_count = data["domain_key"].nunique() if "domain_key" in data else len(data)
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Rekordy CRM", metric_value(metrics, "rekordy_w_probce", str(len(data))))
    c2.metric("Domeny", domains_count)
    c3.metric("Pokrycie AI", f"{metric_value(metrics, 'pokrycie_ai_pct')}%")
    c4.metric("Places OK", f"{metric_value(metrics, 'places_ok_pct')}%")
    c5.metric("Do weryfikacji", metric_value(metrics, "do_weryfikacji"))

    c6, c7, c8, c9, c10 = st.columns(5)
    c6.metric("Branże główne", category_metrics.get("branches", 0))
    c7.metric("Podbranże", category_metrics.get("subbranches", 0))
    c8.metric("Usługi", category_metrics.get("services", 0))
    c9.metric("AI + Places", category_metrics.get("ai_places_domains", 0), pct(category_metrics.get("ai_places_domains", 0), category_metrics.get("domains", 0)))
    c10.metric("Śr. jakość", category_metrics.get("avg_quality", 0))

    quality_counts = data_display["category_quality_bucket_pl"].value_counts().rename_axis("status").reset_index(name="liczba") if "category_quality_bucket_pl" in data_display else pd.DataFrame()
    branch_counts = data["ai_branza_glowna"].value_counts().rename_axis("branza_glowna").reset_index(name="liczba") if "ai_branza_glowna" in data else pd.DataFrame()
    subbranch_counts = data["ai_podbranza"].value_counts().rename_axis("podbranza").reset_index(name="liczba") if "ai_podbranza" in data else pd.DataFrame()
    places_counts = data_display["places_primary_type"].value_counts().rename_axis("places_primary_type").reset_index(name="liczba") if "places_primary_type" in data_display else pd.DataFrame()
    review = data[data["category_quality_bucket"].isin(["DO_WERYFIKACJI", "NISKA_PEWNOSC_AI"])] if "category_quality_bucket" in data else pd.DataFrame()

    tab_main, tab_branches, tab_places, tab_review, tab_export = st.tabs(["Przegląd", "Branże", "Google Places", "Do weryfikacji", "Eksport"])

    with tab_main:
        st.markdown("### Jakość klasyfikacji")
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            st.markdown("#### Status jakości")
            st.dataframe(quality_counts, width="stretch", height=180)
        with col_b:
            st.markdown("#### Score jakości")
            st.dataframe(quality_table, width="stretch", height=180)
        with col_c:
            st.markdown("#### Model B2B/B2C")
            st.dataframe(model_table, width="stretch", height=180)
        preview_cols = [
            "company",
            "domain_key",
            "detected_industry",
            "ai_branza_glowna",
            "ai_podbranza",
            "ai_usluga_glowna",
            "ai_confidence",
            "places_name",
            "places_primary_type",
            "places_match_confidence",
            "category_quality_bucket",
        ]
        preview_cols = ["places_status_pl" if col == "places_status" else col for col in preview_cols]
        preview_cols = ["category_quality_bucket_pl" if col == "category_quality_bucket" else col for col in preview_cols]
        st.dataframe(data_display[[col for col in preview_cols if col in data_display.columns]].head(250), width="stretch", height=430)

    with tab_branches:
        col_a, col_b = st.columns([1.2, 1])
        with col_a:
            st.markdown("### Branże główne: liczność i jakość")
            st.dataframe(branch_quality, width="stretch", height=430)
        with col_b:
            st.markdown("### Podbranże")
            st.dataframe(subbranch_counts, width="stretch", height=430)

    with tab_places:
        st.markdown("### Typy z Google Places")
        if "places_status" not in data_display:
            st.info("Ten raport nie ma kolumn Google Places. Przelicz bazę z opcją `Dociągnij dane Google Places/GMB` albo zbuduj raport po imporcie `places_500.csv`.")
        else:
            places_status_counts = top_counts(data_display, "places_status_pl", 10)
            st.dataframe(places_status_counts, width="stretch", height=180, hide_index=True)
            st.dataframe(places_counts, width="stretch", height=260)
            places_cols = ["company", "domain_key", "places_status_pl", "places_name", "places_primary_type", "places_types", "places_match_confidence", "places_website"]
            st.dataframe(data_display[[col for col in places_cols if col in data_display.columns]], width="stretch", height=380)

    with tab_review:
        st.markdown("### Rekordy wymagające ręcznego spojrzenia")
        st.dataframe(review, width="stretch", height=460)

    with tab_export:
        if CATEGORY_REPORT_PATH.exists():
            st.download_button(
                "Pobierz raport XLSX",
                CATEGORY_REPORT_PATH.read_bytes(),
                file_name=CATEGORY_REPORT_PATH.name,
                mime=OUTPUT_MIME_TYPES[".xlsx"],
                width="stretch",
            )
        if CATEGORY_REPORT_CSV_PATH.exists():
            st.download_button(
                "Pobierz czysty CSV",
                CATEGORY_REPORT_CSV_PATH.read_bytes(),
                file_name=CATEGORY_REPORT_CSV_PATH.name,
                mime=OUTPUT_MIME_TYPES[".csv"],
                width="stretch",
            )


def render_senuto_view():
    st.caption("Sezonowość: realne dane Senuto per grupa branżowa, sprawdzone zamiast domena po domenie.")

    matrix = load_senuto_matrix_frame()
    groups = load_senuto_groups_frame()
    _, category_data = load_category_report_frames()

    tab_matrix, tab_export_mcp, tab_import_mcp, tab_pending, tab_prompt = st.tabs([
        "Wyniki sezonowości",
        "Eksport MCP/API",
        "Import wyników",
        "Grupy do sprawdzenia",
        "Instrukcja Senuto",
    ])

    with tab_matrix:
        if matrix.empty:
            st.info(
                f"Brak jeszcze pliku `{SENUTO_MATRIX_PATH.name}`. To jest wynik realnych zapytań do Senuto "
                "(get_keywords, dane miesięczne) zagregowanych per grupa branża + podbranża."
            )
        else:
            ok = matrix[matrix.get("status", "").eq("OK")] if "status" in matrix else matrix
            brak = matrix[matrix.get("status", "").eq("BRAK_DANYCH")] if "status" in matrix else pd.DataFrame()
            wyrazna = matrix[matrix.get("czy_sezonowosc_wyrazna", "").eq("tak")] if "czy_sezonowosc_wyrazna" in matrix else pd.DataFrame()
            season_metrics, month_table, quarter_table, confidence_table = build_seasonality_metrics(matrix, category_data)

            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("Grupy sprawdzone", len(matrix))
            c2.metric("Z danymi", len(ok))
            c3.metric("Potwierdzone", season_metrics.get("groups_confirmed", 0))
            c4.metric("Hipotezy", season_metrics.get("groups_hypothesis", 0))
            c5.metric("Brak danych", len(brak))
            c6, c7, c8, c9 = st.columns(4)
            c6.metric("Domeny z sezonowością", season_metrics.get("matched_domains", 0))
            c7.metric("Domeny z pikiem Q4", season_metrics.get("q4_domains", 0))
            c8.metric("Wyraźna sezonowość", len(wyrazna))
            c9.metric("Śr. confidence", season_metrics.get("avg_confidence", 0))

            st.markdown(
                """
<div class="hint">
Te dane pochodzą z realnych zapytań do Senuto (comiesięczne wolumeny wyszukiwań, nie szacunki) dla domen
reprezentatywnych każdej grupy. Traktuj to jako sygnał na poziomie branży, nie pojedynczego klienta —
`confidence_sezonowosci` mówi, ile domen faktycznie miało dane.
</div>
""",
                unsafe_allow_html=True,
            )
            st.write("")

            display_cols = [
                "branza_glowna", "podbranza", "liczba_rekordow", "domen_z_danymi_senuto",
                "reprezentatywne_domeny", "sezon_peak_miesiace", "sezon_start_miesiac", "sezon_end_miesiac",
                "czy_sezonowosc_wyrazna", "confidence_sezonowosci", "status",
            ]
            view = matrix[[col for col in display_cols if col in matrix.columns]]
            col_months, col_quarters, col_conf = st.columns([1.1, .9, .8])
            with col_months:
                st.markdown("### Piki po miesiącach")
                if not month_table.empty:
                    st.bar_chart(month_table.set_index("miesiac")["domeny"])
                    st.caption("Wartość `domeny` to suma sygnałów z grup, nie deduplikacja globalna między miesiącami.")
                    st.dataframe(month_table, width="stretch", height=190)
                else:
                    st.info("Brak miesięcy peak.")
            with col_quarters:
                st.markdown("### Piki po kwartałach")
                if not quarter_table.empty:
                    st.bar_chart(quarter_table.set_index("kwartal")["domeny"])
                    st.caption("Jedna grupa może mieć peak w kilku miesiącach, więc kwartał pokazuje intensywność sezonową.")
                    st.dataframe(quarter_table, width="stretch", height=190)
                else:
                    st.info("Brak danych kwartalnych.")
            with col_conf:
                st.markdown("### Confidence")
                st.dataframe(confidence_table, width="stretch", height=260)
            st.markdown("### Macierz sezonowości (dane realne z Senuto)")
            st.dataframe(view, width="stretch", height=520)

            st.download_button(
                "Pobierz macierz sezonowości XLSX",
                SENUTO_MATRIX_PATH.read_bytes(),
                file_name=SENUTO_MATRIX_PATH.name,
                mime=OUTPUT_MIME_TYPES[".xlsx"],
                width="stretch",
            )

    with tab_export_mcp:
        st.markdown("### Paczka grup do Senuto MCP/API")
        st.markdown(
            """
<div class="hint">
Ten krok buduje kontrolowany wsad dla Claude z MCP Senuto albo dla przyszłego klienta API. To jest brakujący element procesu:
aplikacja przygotowuje grupy, narzędzie Senuto zbiera dane, a wynik wraca do aplikacji jako macierz sezonowości.
</div>
""",
            unsafe_allow_html=True,
        )
        if groups.empty:
            st.info("Brak grup branżowych. Najpierw przelicz grupy w zakładce `Grupy do sprawdzenia`.")
        else:
            current_checked = 0 if matrix.empty else len(matrix)
            total_groups = len(groups)
            pending_count = max(total_groups - current_checked, 0)
            c1, c2, c3 = st.columns(3)
            c1.metric("Grupy branżowe", total_groups)
            c2.metric("Już w macierzy", current_checked)
            c3.metric("Do sprawdzenia", pending_count)

            col_a, col_b, col_c = st.columns(3)
            with col_a:
                mcp_limit = st.number_input("Limit grup w paczce", min_value=1, max_value=500, value=50, step=10)
            with col_b:
                only_pending = st.checkbox("Tylko grupy bez sezonowości", value=True)
            with col_c:
                skip_unknown = st.checkbox("Pomiń nierozpoznane branże", value=True)
            senuto_records = build_senuto_mcp_batch(
                groups,
                limit=int(mcp_limit),
                only_pending=only_pending,
                skip_unknown=skip_unknown,
            )
            st.metric("Grupy w paczce", len(senuto_records))
            if senuto_records:
                preview = pd.DataFrame([{"group_key": item["group_key"], **item["context"]} for item in senuto_records[:20]])
                st.dataframe(preview, width="stretch", height=280)
                st.download_button(
                    "Pobierz JSONL dla Senuto MCP/API",
                    jsonl_bytes(senuto_records),
                    file_name=f"leadseason_senuto_mcp_batch_{int(mcp_limit)}.jsonl",
                    mime="application/jsonl",
                    width="stretch",
                )
                st.download_button(
                    "Pobierz instrukcję dla Claude/Senuto",
                    SENUTO_MCP_PROMPT.encode("utf-8"),
                    file_name="leadseason_instrukcja_senuto_mcp.txt",
                    mime="text/plain",
                    width="stretch",
                )
            else:
                st.success("Nie ma grup do eksportu przy tych ustawieniach.")

    with tab_import_mcp:
        st.markdown("### Import wyniku z Senuto MCP/API")
        st.caption("Obsługiwane formaty: JSONL, JSON, XLSX, CSV. Import normalizuje kolumny i zapisuje standardową macierz sezonowości aplikacji.")
        merge_existing = st.checkbox("Dopisz lub zaktualizuj istniejącą macierz", value=True)
        senuto_upload = st.file_uploader("Wrzuć wynik Senuto", type=["jsonl", "json", "xlsx", "xls", "csv"], key="senuto_results_upload")
        if senuto_upload:
            try:
                raw_results = read_senuto_results(senuto_upload)
                normalized = normalize_senuto_matrix(raw_results)
                ok_rows = len(normalized[normalized["status"].eq("OK")]) if "status" in normalized else 0
                no_data_rows = len(normalized[normalized["status"].eq("BRAK_DANYCH")]) if "status" in normalized else 0
                c1, c2, c3 = st.columns(3)
                c1.metric("Wiersze w imporcie", len(normalized))
                c2.metric("OK", ok_rows)
                c3.metric("Brak danych", no_data_rows)
                st.dataframe(normalized.head(100), width="stretch", height=360)
                if st.button("Zapisz jako macierz sezonowości aplikacji", type="primary", width="stretch"):
                    saved = save_senuto_matrix(normalized, merge_existing=merge_existing)
                    st.success(f"Zapisano `{SENUTO_MATRIX_PATH.name}` i CSV obok. Wiersze w macierzy: {len(saved)}.")
            except Exception as exc:
                st.error(str(exc))

    with tab_pending:
        st.markdown(
            """
<div class="hint">
Ten widok to wsad roboczy: grupy branżowe wyliczone z raportu branż, jeszcze bez sprawdzonej sezonowości.
Kliknij przycisk, żeby przeliczyć grupy na nowo po aktualizacji raportu branż.
</div>
""",
            unsafe_allow_html=True,
        )
        if st.button("Przelicz grupy branżowe", disabled=not SENUTO_GROUPS_SCRIPT.exists()):
            try:
                result = subprocess.run(
                    [sys.executable, str(SENUTO_GROUPS_SCRIPT)],
                    cwd=str(BASE_DIR),
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                if result.returncode == 0:
                    st.success("Wygenerowano grupy branżowe do Senuto.")
                else:
                    st.error(result.stderr or result.stdout or "Nie udało się wygenerować grup.")
            except Exception as exc:
                st.error(str(exc))

        if groups.empty:
            st.info("Nie ma jeszcze pliku grup. Najpierw wygeneruj raport branż, potem kliknij `Przelicz grupy branżowe`.")
        else:
            checked_keys = set()
            if not matrix.empty and "branza_glowna" in matrix and "podbranza" in matrix:
                checked_keys = set(zip(matrix["branza_glowna"], matrix["podbranza"]))
            groups = groups.copy()
            if "ai_branza_glowna" in groups and "ai_podbranza" in groups:
                groups["_juz_sprawdzone"] = list(zip(groups["ai_branza_glowna"], groups["ai_podbranza"]))
                groups["_juz_sprawdzone"] = groups["_juz_sprawdzone"].map(lambda key: "tak" if key in checked_keys else "nie")
                remaining = groups[groups["_juz_sprawdzone"].eq("nie")]
            else:
                remaining = groups

            c1, c2 = st.columns(2)
            c1.metric("Grupy łącznie", len(groups))
            c2.metric("Jeszcze bez sezonowości", len(remaining))

            columns = [
                "ai_branza_glowna", "ai_podbranza", "ai_usluga_glowna", "ai_model_b2b_b2c",
                "liczba_rekordow", "liczba_domen", "reprezentatywne_domeny", "proponowane_frazy_senuto",
                "places_primary_types",
            ]
            view = remaining[[col for col in columns if col in remaining.columns]]
            st.markdown("### Grupy jeszcze bez sprawdzonej sezonowości")
            st.dataframe(view, width="stretch", height=460)

            col_a, col_b = st.columns(2)
            with col_a:
                if SENUTO_GROUPS_PATH.exists():
                    st.download_button(
                        "Pobierz wszystkie grupy XLSX",
                        SENUTO_GROUPS_PATH.read_bytes(),
                        file_name=SENUTO_GROUPS_PATH.name,
                        mime=OUTPUT_MIME_TYPES[".xlsx"],
                        width="stretch",
                    )
            with col_b:
                if SENUTO_GROUPS_CSV_PATH.exists():
                    st.download_button(
                        "Pobierz wszystkie grupy CSV",
                        SENUTO_GROUPS_CSV_PATH.read_bytes(),
                        file_name=SENUTO_GROUPS_CSV_PATH.name,
                        mime=OUTPUT_MIME_TYPES[".csv"],
                        width="stretch",
                    )

    with tab_prompt:
        st.markdown("### Metoda: jak liczymy sezonowość per grupa")
        st.markdown(
            """
<div class="hint">
W obecnej wersji aplikacja nie łączy się bezpośrednio z Senuto MCP, bo ten dostęp jest po stronie Claude.
Dlatego funkcja jest wbudowana jako etap pipeline: eksport paczki → Senuto MCP/API → import macierzy.
Gdy pojawi się stały dostęp API, ten sam schemat danych można podpiąć bez zmiany dashboardu.
</div>
""",
            unsafe_allow_html=True,
        )
        st.code(
            SENUTO_MCP_PROMPT
            + """

Metoda agregacji w aplikacji:
Cel: sezonowość dla grup branżowych (branża główna + podbranża), nie dla pojedynczych klientów.

1. Z raportu branż grupujemy rekordy po (branża główna, podbranża).
2. Dla 1-5 reprezentatywnych domen z grupy pobieramy z Senuto (get_keywords,
   detail_level=extended) słowa kluczowe wraz z miesięcznym rozkładem wyszukiwań (trends).
3. Sumujemy miesięczne wolumeny wszystkich słów kluczowych i domen w grupie.
4. Miesiąc = peak, gdy wolumen >= 110% średniej; low, gdy <= 90% średniej.
5. confidence_sezonowosci rośnie z liczbą domen, które faktycznie miały dane w Senuto.

Domeny bez żadnych słów kluczowych w Senuto (nowe/niszowe strony) są pomijane,
a grupa dostaje status BRAK_DANYCH zamiast zmyślonej sezonowości.
""".strip(),
            language="markdown",
        )


def render_results_tabs(df, output_path=None, summary_path=None):
    q4_df = df[df.get("q4_priority", "").astype(str).isin(Q4_VALUES)] if "q4_priority" in df else pd.DataFrame()
    review_df = df[df.get("q4_priority", "").astype(str).eq("DO_WERYFIKACJI")] if "q4_priority" in df else pd.DataFrame()
    st.markdown("### Wyniki generatora")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Rekordy", len(df))
    c2.metric("Rekordy sezonowe", len(q4_df))
    c3.metric("Do weryfikacji", len(review_df))
    c4.metric("Branże przypisane", int(current_industry_mask(df).sum()))

    tab_q4, tab_all, tab_review, tab_export = st.tabs(["Sezonowe", "Wszystkie rekordy", "Do weryfikacji", "Eksport"])
    q4_cols = [
        "account_owner", "id", "detail_id", "nip", "company", "domain_key",
        "detected_industry", "q4_priority", "season_peak", "contact_start", "seasonality_confidence",
    ]
    view_cols = [
        "id", "detail_id", "nip", "domain_key", "crawl_status", "detected_industry",
        "industry_confidence", "places_primary_type", "places_industry_hint", "places_match_confidence",
        "q4_priority", "season_peak", "contact_start",
    ]
    with tab_q4:
        existing = [col for col in q4_cols if col in q4_df.columns]
        st.dataframe(q4_df[existing] if existing else q4_df, width="stretch", height=420)
    with tab_all:
        existing = [col for col in view_cols if col in df.columns]
        st.dataframe(df[existing] if existing else df, width="stretch", height=420)
    with tab_review:
        existing = [col for col in view_cols if col in review_df.columns]
        st.dataframe(review_df[existing] if existing else review_df, width="stretch", height=360)
    with tab_export:
        sheets = {"Wszystkie rekordy": df, "Sezonowe": q4_df, "Do weryfikacji": review_df}
        st.download_button("Pobierz wynik operacyjny XLSX", xlsx_bytes(sheets), file_name="leadseason_wynik_operacyjny.xlsx", mime=OUTPUT_MIME_TYPES[".xlsx"], width="stretch")
        if output_path and Path(output_path).exists():
            st.download_button("Pobierz surowy wynik", Path(output_path).read_bytes(), file_name=Path(output_path).name, mime=OUTPUT_MIME_TYPES.get(Path(output_path).suffix.lower(), "application/octet-stream"), width="stretch")
        if summary_path and Path(summary_path).exists():
            st.download_button("Pobierz podsumowanie JSON", Path(summary_path).read_bytes(), file_name=Path(summary_path).name, mime="application/json", width="stretch")


def render_pipeline_admin_view():
    render_header("Zasilenie danych: wrzuć bazę, uruchom crawl i przygotuj klasyfikację branż.")
    tabs = st.tabs([
        "Status procesu", "Import i crawl", "Klasyfikacja LLM",
    ])
    with tabs[0]:
        render_overview_tab()
    with tabs[1]:
        render_generator_view()
    with tabs[2]:
        render_claude_view()


def render_quality_center_view():
    render_header("Jakość danych: sprawdź strony WWW, kategoryzację, sezonowość i eksperymenty poprawy sygnału.")
    tabs = st.tabs(["Jakość kategoryzacji", "Sezonowość", "Eksperyment Maxun", "Dashboard jakości"])
    with tabs[0]:
        render_category_view()
    with tabs[1]:
        render_senuto_view()
    with tabs[2]:
        render_maxun_experiment_view()
    with tabs[3]:
        render_dashboard_view()


def main():
    with st.sidebar:
        st.title("LeadSeason")
        page = st.radio(
            "Widok",
            ["Dashboard", "Plan działania", "Zasilenie danych", "Jakość danych", "Eksporty"],
            index=0,
        )
        st.caption("Prosty proces: zobacz bazę, wybierz plan, zasil dane, sprawdź jakość, pobierz pliki.")

    if page == "Dashboard":
        render_header("Dashboard: ocena bazy klientów, branż, sezonowości i jakości danych.")
        render_dashboard_view()
    elif page == "Plan działania":
        render_leads_view()
    elif page == "Zasilenie danych":
        render_pipeline_admin_view()
    elif page == "Jakość danych":
        render_quality_center_view()
    else:
        render_header("Eksporty: wzory plików, próbki i artefakty do dalszej pracy.")
        render_sources_view()


if __name__ == "__main__":
    main()
