"""Per-lead audit micro-app.

STRATEGIA_SYSTEM_POZYSKIWANIA_LEADOW.md sekcja 7 (krok 4, sekcja 12): jedna
aplikacja z dynamicznym routingiem per-lead zamiast statycznego PDF-a lub
tysiecy recznych stron. Server-rendered -- ten repo nie ma zadnego frontend
toolchaina (patrz LANDING_HTML w backend/api.py, ten sam wzorzec), wiec zamiast
Next.js/React to zwykle HTML+CSS+vanilla JS zwracane przez FastAPI.

Routes (montowane w backend/api.py pod "" i "/api", jak wszystkie inne w tym
pliku):
  GET  /audyt/{slug}        -- strona z progressive disclosure (sekcja 7A/7B)
  POST /audyt/{slug}/track  -- zdarzenia MicroAppVisit (sekcja 7D)
  POST /audyt/{slug}/gate   -- gate ze zgoda (sekcja 7C); zwraca pelny raport
                                dopiero PO zapisaniu zgody -- nic z "zamknietej"
                                czesci raportu nie trafia do klienta wczesniej

Celowo pominiete na tym etapie: double opt-in mailem (wymaga infra wysylki,
ktorej ten backend nie ma -- RESEND_API_KEY zyje w repo ai-ops.pl, nie tutaj).
"""
import html
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from outreach import models, repository
from outreach.audit_utils import latest_audits_by_type
from outreach.db import get_db

router = APIRouter()

CONSENT_TEXT = "Zgadzam się na kontakt telefoniczny/SMS w celu omówienia wyników audytu."
REGISTRATION_SCORE_BONUS = 15.0
REGISTRATION_TIER = 3

AUDIT_LABELS = {
    "seo": "SEO on-page",
    "pagespeed": "Szybkość strony (PageSpeed)",
    "aeo_geo": "Widoczność w AI (ChatGPT/Perplexity/Gemini)",
    "senuto": "Sezonowość (Senuto)",
    "places": "Google Places / GBP",
    "seasonality": "Sezonowość",
}


class GateSubmission(BaseModel):
    session_id: str = Field(min_length=1, max_length=64)
    email: EmailStr
    phone: str = Field(min_length=7, max_length=30)
    consent: bool


class TrackEvent(BaseModel):
    session_id: str = Field(min_length=1, max_length=64)
    event_type: str = Field(min_length=1, max_length=40)
    event_data: dict | None = None


def _pick_hook(lead: models.Lead, audits: dict[str, models.AuditResult]) -> dict:
    """Insight-trigger headline (sekcja 7A) -- konkret, nie generyczne "oto Twoj audyt".

    Priorytet z sekcji 6: AEO/GEO jako potencjalnie mocniejszy trigger niz
    klasyczne SEO dla czesci segmentow -> sprobuj najpierw, potem sezonowosc
    (rdzen LeadSeason), potem SEO on-page, na koncu generyczny fallback.
    """
    aeo = audits.get("aeo_geo")
    if aeo is not None and aeo.score is not None:
        return {
            "headline": f"Widoczność Twojej strony w AI: {aeo.score:.0f}/100",
            "subline": "Sprawdziliśmy, czy ChatGPT, Perplexity i Google AI Overviews w ogóle cytują Twoją stronę.",
            "score": aeo.score,
            "metric_label": "Wynik AEO/GEO",
        }
    if lead.season_peak:
        return {
            "headline": f"Twój sezon ({lead.season_peak}) zaczyna nabierać tempa",
            "subline": "Sprawdziliśmy Twoją widoczność zanim ruszy szczyt sezonu.",
            "score": None,
            "metric_label": None,
        }
    seo = audits.get("seo")
    if seo is not None and seo.score is not None:
        return {
            "headline": f"Twój audyt SEO on-page: {seo.score:.0f}/100",
            "subline": "Znaleźliśmy konkretne braki, które wpływają na Twoją widoczność w Google.",
            "score": seo.score,
            "metric_label": "Wynik SEO on-page",
        }
    return {
        "headline": f"Przygotowaliśmy audyt dla {lead.company_name}",
        "subline": "Zobacz, co sprawdziliśmy i co warto poprawić.",
        "score": None,
        "metric_label": None,
    }


def _score_bar(label: str, score: float) -> str:
    pct = max(0.0, min(100.0, score))
    color = "#22c55e" if pct >= 70 else "#fb923c" if pct >= 40 else "#ef4444"
    return f"""
    <div class="score-bar" role="img" aria-label="{html.escape(label)}: {pct:.0f} na 100">
      <div class="score-bar-label"><span>{html.escape(label)}</span><strong>{pct:.0f}/100</strong></div>
      <div class="score-bar-track"><div class="score-bar-fill" style="width:{pct:.0f}%;background:{color}"></div></div>
    </div>"""


def _locked_report_html(lead: models.Lead, audits: dict[str, models.AuditResult]) -> str:
    sections = []
    for audit_type, audit in audits.items():
        label = AUDIT_LABELS.get(audit_type, audit_type)
        bar = _score_bar(label, audit.score) if audit.score is not None else ""
        summary = html.escape(audit.summary_text or "Brak dodatkowych uwag.")
        sections.append(f'<div class="report-section">{bar}<p class="report-summary">{summary}</p></div>')
    if not sections:
        sections.append('<p class="report-summary">Pełny audyt jest w przygotowaniu — odezwiemy się z wynikami.</p>')
    return "\n".join(sections)


def _render_page(lead: models.Lead, db: Session) -> str:
    audits = latest_audits_by_type(lead, db)
    hook = _pick_hook(lead, audits)
    company = html.escape(lead.company_name)
    hook_bar = _score_bar(hook["metric_label"], hook["score"]) if hook["score"] is not None else ""

    return f"""<!doctype html>
<html lang="pl">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<meta name="robots" content="noindex, nofollow" />
<title>Audyt — {company} | LeadSeason</title>
<style>
  :root {{ color-scheme: dark; --bg:#070a11; --panel:#111827; --text:#fff7ed; --muted:#cbd5e1; --accent:#fb923c; --border:rgba(251,146,60,.34); }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; min-height:100vh; font-family:Inter,Segoe UI,Arial,sans-serif; background:radial-gradient(circle at 20% 0%, rgba(251,146,60,.16), transparent 32%), var(--bg); color:var(--text); line-height:1.55; }}
  main {{ width:min(720px, calc(100vw - 32px)); margin:0 auto; padding:48px 0 96px; }}
  .kicker {{ color:var(--accent); text-transform:uppercase; letter-spacing:.08em; font-size:12px; font-weight:800; }}
  h1 {{ margin:10px 0 12px; font-size:clamp(28px,5vw,40px); line-height:1.12; }}
  .subline {{ color:var(--muted); font-size:17px; margin:0 0 28px; }}
  .card {{ border:1px solid var(--border); border-radius:16px; background:linear-gradient(135deg, rgba(17,24,39,.96), rgba(5,7,12,.94)); padding:24px; margin-bottom:20px; }}
  .score-bar {{ margin-bottom:14px; }}
  .score-bar-label {{ display:flex; justify-content:space-between; font-size:14px; margin-bottom:6px; color:var(--muted); }}
  .score-bar-label strong {{ color:var(--text); }}
  .score-bar-track {{ height:10px; border-radius:999px; background:rgba(255,255,255,.08); overflow:hidden; }}
  .score-bar-fill {{ height:100%; border-radius:999px; transition:width .6s ease-out; }}
  .report-summary {{ color:var(--muted); font-size:14px; margin:0; }}
  .report-section {{ padding:14px 0; border-top:1px solid var(--border); }}
  .report-section:first-child {{ border-top:none; padding-top:0; }}
  #locked {{ display:none; }}
  #reveal-sentinel {{ height:1px; }}
  .gate {{ margin-top:8px; }}
  .gate p.teaser {{ color:var(--muted); font-size:15px; }}
  .gate label {{ display:block; font-size:13px; color:var(--muted); margin:14px 0 6px; }}
  .gate input[type=email], .gate input[type=tel] {{ width:100%; min-height:44px; padding:10px 14px; border-radius:10px; border:1px solid var(--border); background:rgba(255,255,255,.04); color:var(--text); font-size:16px; }}
  .gate input:focus-visible, .gate button:focus-visible {{ outline:3px solid var(--accent); outline-offset:2px; }}
  .consent-row {{ display:flex; align-items:flex-start; gap:10px; margin:18px 0; font-size:13px; color:var(--muted); }}
  .consent-row input {{ margin-top:3px; width:20px; height:20px; flex-shrink:0; accent-color:var(--accent); }}
  .gate button {{ min-height:48px; width:100%; border:none; border-radius:999px; background:var(--accent); color:#1a0f05; font-size:16px; font-weight:700; cursor:pointer; transition:background .2s, transform .15s; }}
  .gate button:hover {{ background:#fdba74; }}
  .gate button:active {{ transform:scale(.98); }}
  .gate button:disabled {{ opacity:.55; cursor:not-allowed; }}
  .error {{ color:#fca5a5; font-size:13px; margin-top:10px; }}
  .error[hidden] {{ display:none; }}
  @media (prefers-reduced-motion: reduce) {{ * {{ transition:none !important; }} }}
</style>
</head>
<body>
<main>
  <div class="kicker">LeadSeason &middot; Audyt</div>
  <h1>{hook["headline"]}</h1>
  <p class="subline">{hook["subline"]}</p>

  <div class="card">
    {hook_bar}
  </div>

  <div id="reveal-sentinel" aria-hidden="true"></div>

  <div id="gate-card" class="card gate" hidden>
    <h2 style="margin-top:0;font-size:20px;">Zobacz pełną analizę</h2>
    <p class="teaser">Podaj kontakt, a odblokujemy pełny raport: wszystkie sprawdzone obszary, konkretne braki i rekomendacje.</p>
    <form id="gate-form" novalidate>
      <label for="email">Adres e-mail</label>
      <input id="email" name="email" type="email" autocomplete="email" required />
      <label for="phone">Numer telefonu</label>
      <input id="phone" name="phone" type="tel" inputmode="tel" autocomplete="tel" placeholder="np. +48 600 000 000" required />
      <label class="consent-row"><input type="checkbox" id="consent" name="consent" required />{CONSENT_TEXT}</label>
      <button type="submit">Odblokuj pełny raport</button>
      <p class="error" id="gate-error" role="alert" hidden></p>
    </form>
  </div>

  <div id="locked" class="card" aria-live="polite"></div>
</main>
<script>
(function () {{
  var SLUG = {lead.slug!r};
  var sessionId = sessionStorage.getItem("leadgen_session");
  if (!sessionId) {{
    sessionId = (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random());
    sessionStorage.setItem("leadgen_session", sessionId);
  }}

  function track(eventType, data) {{
    fetch("/audyt/" + SLUG + "/track", {{
      method: "POST",
      headers: {{ "Content-Type": "application/json" }},
      body: JSON.stringify({{ session_id: sessionId, event_type: eventType, event_data: data || null }}),
      keepalive: true,
    }}).catch(function () {{}});
  }}

  track("page_view", {{ path: location.pathname }});

  var gateCard = document.getElementById("gate-card");
  var gateShown = false;
  var sentinel = document.getElementById("reveal-sentinel");
  var revealTimer = setTimeout(revealGate, 25000);

  var observer = new IntersectionObserver(function (entries) {{
    if (entries[0].isIntersecting) revealGate();
  }}, {{ threshold: 0 }});
  observer.observe(sentinel);

  function revealGate() {{
    if (gateShown) return;
    gateShown = true;
    clearTimeout(revealTimer);
    observer.disconnect();
    gateCard.hidden = false;
    track("gate_shown", null);
  }}

  var form = document.getElementById("gate-form");
  var errorEl = document.getElementById("gate-error");
  var lockedEl = document.getElementById("locked");

  form.addEventListener("submit", function (event) {{
    event.preventDefault();
    errorEl.hidden = true;
    var submitButton = form.querySelector("button[type=submit]");
    submitButton.disabled = true;

    var payload = {{
      session_id: sessionId,
      email: document.getElementById("email").value.trim(),
      phone: document.getElementById("phone").value.trim(),
      consent: document.getElementById("consent").checked,
    }};

    fetch("/audyt/" + SLUG + "/gate", {{
      method: "POST",
      headers: {{ "Content-Type": "application/json" }},
      body: JSON.stringify(payload),
    }})
      .then(function (response) {{
        return response.json().then(function (data) {{ return {{ ok: response.ok, data: data }}; }});
      }})
      .then(function (result) {{
        if (!result.ok) throw new Error((result.data && result.data.detail) || "Nie udało się zapisać zgłoszenia.");
        lockedEl.innerHTML = result.data.report_html;
        lockedEl.style.display = "block";
        gateCard.hidden = true;
        track("gate_submitted", null);
        lockedEl.scrollIntoView({{ behavior: "smooth", block: "start" }});
      }})
      .catch(function (error) {{
        errorEl.textContent = error.message;
        errorEl.hidden = false;
        submitButton.disabled = false;
      }});
  }});
}})();
</script>
</body>
</html>
"""


@router.get("/audyt/{slug}", response_class=HTMLResponse)
def audyt_page(slug: str, db: Session = Depends(get_db)):
    lead = repository.get_lead_by_slug(db, slug)
    if lead is None:
        raise HTTPException(status_code=404, detail="Nie znaleziono audytu dla tego adresu.")
    return HTMLResponse(_render_page(lead, db))


@router.post("/audyt/{slug}/track")
def audyt_track(slug: str, payload: TrackEvent, db: Session = Depends(get_db)):
    lead = repository.get_lead_by_slug(db, slug)
    if lead is None:
        raise HTTPException(status_code=404, detail="Nie znaleziono leada.")
    repository.record_microapp_visit(db, lead.id, payload.session_id, payload.event_type, payload.event_data)
    return {"ok": True}


@router.post("/audyt/{slug}/gate")
def audyt_gate(slug: str, payload: GateSubmission, request: Request, db: Session = Depends(get_db)):
    """Idempotent by design (retries/double-clicks must not duplicate state):

    - consent is recorded (and committed) BEFORE contact PII is ever staged/
      committed, so a failure between the two steps can never leave contact
      info persisted without a backing ConsentEvent
    - has_valid_consent()/lead.tier checks make each side effect a no-op if
      it already happened, so a resubmitted POST doesn't add a second
      ConsentEvent or a second +REGISTRATION_SCORE_BONUS
    """
    if not payload.consent:
        raise HTTPException(status_code=400, detail="Zgoda jest wymagana, żeby odblokować pełny raport.")
    lead = repository.get_lead_by_slug(db, slug)
    if lead is None:
        raise HTTPException(status_code=404, detail="Nie znaleziono leada.")

    if not repository.has_valid_consent(db, lead.id, "contact_phone_sms"):
        repository.record_consent(
            db,
            lead.id,
            "contact_phone_sms",
            consent_text=CONSENT_TEXT,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )

    lead.contact_email = payload.email
    lead.contact_phone = payload.phone
    lead.updated_at = datetime.now(timezone.utc)
    if lead.tier < REGISTRATION_TIER:
        lead.tier = REGISTRATION_TIER
        db.commit()
        repository.record_score_event(db, lead.id, REGISTRATION_SCORE_BONUS, "registered_via_gate")
    else:
        db.commit()

    repository.record_microapp_visit(db, lead.id, payload.session_id, "gate_submitted", None)

    audits = latest_audits_by_type(lead, db)
    return {"ok": True, "report_html": _locked_report_html(lead, audits)}
