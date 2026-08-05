"""Operator dashboard for the outreach/ lead-acquisition system.

Priorytet #1 zostawiony przez poprzednia sesje (STATUS.md): system outreach/
(baza, audyty, mikro-apka, glos) nie mial zadnego frontu do obslugi poza sama
publiczna mikro-apka per-lead (backend/microapp.py) -- wszystko inne szlo
przez CLI (scripts/*.py) i recznie po bazie SQLite. To jest ten front: jeden
widok end-to-end na caly flow ze STRATEGIA_SYSTEM_POZYSKIWANIA_LEADOW.md
(lead -> audyty -> insighty/scoring -> gate/zgoda -> outreach), server-rendered
Python jak microapp.py -- ten sam brak frontend toolchaina, ta sama decyzja.

Routes (montowane w backend/api.py pod "" i "/api", jak wszystko inne):
  GET  /dashboard                        -- lista leadow
  GET  /dashboard/{lead_id}              -- szczegoly jednego leada
  POST /dashboard/{lead_id}/run-audit    -- odpala SEO+AEO/GEO+Senuto(+PageSpeed
                                             jesli klucz jest) synchronicznie
  POST /dashboard/{lead_id}/generate-voice -- buduje i syntetyzuje narracje
  GET  /dashboard/{lead_id}/audio        -- serwuje najnowszy plik audio

Akcje (run-audit, generate-voice) sa za require_api_key, jak /uploads i
/crawl/jobs w backend/api.py -- to same, jedyne mutujace endpointy w tym
routerze. Widoki listy/szczegolow sa otwarte, jak reszta GET-ow w tym API.
"""
import html
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from backend.auth import require_api_key
from outreach import models, repository
from outreach.audit_utils import latest_audits_by_type
from outreach.audits.aeo_geo import run_aeo_geo_audit
from outreach.audits.pagespeed import PageSpeedConfigError, run_pagespeed_audit
from outreach.audits.senuto import load_senuto_row_for_industry
from outreach.audits.seo_onpage import run_onpage_audit
from outreach.db import get_db
from outreach.voice.elevenlabs_tts import (
    DEFAULT_MODEL_ID,
    DEFAULT_VOICE_ID,
    ElevenLabsAPIError,
    ElevenLabsConfigError,
    get_usage,
    synthesize_narration,
)
from outreach.voice.script import build_narration_script

router = APIRouter()

AUDIO_DIR = Path(__file__).resolve().parent.parent / "outreach" / "data" / "audio"

AUDIT_LABELS = {
    "seo": "SEO on-page",
    "pagespeed": "PageSpeed",
    "aeo_geo": "AEO/GEO",
    "senuto": "Senuto (sezonowość)",
    "places": "Google Places",
    "seasonality": "Sezonowość",
}

CONSENT_LABELS = {
    "contact_phone_sms": "Kontakt telefon/SMS",
    "marketing_email": "Marketing e-mail",
    "ai_voice_video": "Głos/wideo AI",
}


def _redirect_to_detail(lead_id: str, message: str, ok: str) -> RedirectResponse:
    return RedirectResponse(f"/dashboard/{lead_id}?msg={quote(message)}&ok={ok}", status_code=303)


def _normalize_url(domain: str) -> str:
    domain = (domain or "").strip()
    if not domain:
        return domain
    if not domain.startswith(("http://", "https://")):
        return f"https://{domain}"
    return domain


def _pipeline_status(lead: models.Lead, audits: dict, has_consent: bool, has_outreach: bool) -> str:
    """Wyliczony na zywo etykieta etapu leada -- Lead nie ma kolumny `status`
    (AGENT.md sekcja 4 ja przewidywala, w praktyce nie zaimplementowana),
    wiec pochodzi z obecnosci powiazanych rekordow, nie z pola w bazie."""
    if has_outreach:
        return "Kontakt wysłany"
    if has_consent:
        return "Zarejestrowany (gate)"
    if audits:
        return "Zaudytowany"
    return "Nowy"


def _badge(text: str, color: str) -> str:
    return f'<span class="badge" style="background:{color}1a;color:{color};border-color:{color}55">{html.escape(text)}</span>'


def _status_badge(status: str) -> str:
    colors = {
        "Nowy": "#94a3b8",
        "Zaudytowany": "#38bdf8",
        "Zarejestrowany (gate)": "#a78bfa",
        "Kontakt wysłany": "#22c55e",
    }
    return _badge(status, colors.get(status, "#94a3b8"))


def _tier_badge(tier: int) -> str:
    colors = {1: "#94a3b8", 2: "#fb923c", 3: "#22c55e"}
    return _badge(f"Tier {tier}", colors.get(tier, "#94a3b8"))


PAGE_HEAD = """
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<meta name="robots" content="noindex, nofollow" />
<style>
  :root { color-scheme: dark; --bg:#070a11; --panel:#111827; --text:#fff7ed; --muted:#cbd5e1; --accent:#fb923c; --border:rgba(251,146,60,.34); }
  * { box-sizing: border-box; }
  body { margin:0; min-height:100vh; font-family:Inter,Segoe UI,Arial,sans-serif; background:radial-gradient(circle at 20% 0%, rgba(251,146,60,.16), transparent 32%), var(--bg); color:var(--text); line-height:1.5; }
  main { width:min(1100px, calc(100vw - 32px)); margin:0 auto; padding:36px 0 96px; }
  a { color:var(--accent); }
  a:focus-visible, .btn:focus-visible, tr td a:focus-visible { outline:3px solid var(--accent); outline-offset:2px; border-radius:4px; }
  .kicker { color:var(--accent); text-transform:uppercase; letter-spacing:.08em; font-size:12px; font-weight:800; }
  h1 { margin:8px 0 6px; font-size:clamp(24px,4vw,32px); }
  .sub { color:var(--muted); font-size:14px; margin:0 0 24px; }
  .card { border:1px solid var(--border); border-radius:14px; background:linear-gradient(135deg, rgba(17,24,39,.96), rgba(5,7,12,.94)); padding:20px; margin-bottom:18px; }
  table { width:100%; border-collapse:collapse; font-size:13px; }
  th { text-align:left; color:var(--muted); font-weight:600; padding:8px 10px; border-bottom:1px solid var(--border); white-space:nowrap; }
  td { padding:10px 10px; border-bottom:1px solid rgba(255,255,255,.06); vertical-align:top; }
  tr:hover td { background:rgba(255,255,255,.02); }
  .badge { display:inline-block; padding:2px 9px; border-radius:999px; font-size:11px; font-weight:700; border:1px solid; white-space:nowrap; }
  .muted { color:var(--muted); }
  .back { display:inline-block; margin-bottom:16px; font-size:13px; }
  .grid2 { display:grid; grid-template-columns:1.4fr 1fr; gap:18px; }
  @media (max-width:820px) { .grid2 { grid-template-columns:1fr; } }
  .kv { display:grid; grid-template-columns:140px 1fr; gap:6px 12px; font-size:13px; }
  .kv dt { color:var(--muted); }
  .kv dd { margin:0; }
  .btn { display:inline-block; border:none; border-radius:999px; background:var(--accent); color:#1a0f05; font-size:13px; font-weight:700; padding:9px 16px; cursor:pointer; text-decoration:none; transition:background .2s ease-out, transform .15s ease-out, opacity .2s; }
  .btn:hover:not([disabled]) { background:#fdba74; }
  .btn:active:not([disabled]) { transform:scale(.97); }
  .btn[disabled] { opacity:.5; cursor:not-allowed; }
  .btn .spinner { display:inline-block; width:12px; height:12px; margin-right:7px; border:2px solid rgba(26,15,5,.35); border-top-color:#1a0f05; border-radius:50%; vertical-align:-2px; animation:btn-spin .7s linear infinite; }
  @keyframes btn-spin { to { transform:rotate(360deg); } }
  .btn-row { display:flex; gap:10px; flex-wrap:wrap; margin-top:12px; }
  .flash { border-radius:10px; padding:10px 14px; font-size:13px; margin-bottom:18px; border:1px solid; }
  .flash.ok { background:rgba(34,197,94,.1); border-color:rgba(34,197,94,.4); color:#86efac; }
  .flash.err { background:rgba(239,68,68,.1); border-color:rgba(239,68,68,.4); color:#fca5a5; }
  .timeline { list-style:none; margin:0; padding:0; font-size:13px; }
  .timeline li { padding:8px 0; border-top:1px solid rgba(255,255,255,.06); }
  .timeline li:first-child { border-top:none; }
  audio { width:100%; margin-top:8px; }
  .empty { color:var(--muted); font-size:13px; }
  @media (prefers-reduced-motion: reduce) { * { transition:none !important; animation:none !important; } }
</style>
"""


def _shell(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="pl">
<head><title>{html.escape(title)} | LeadSeason</title>{PAGE_HEAD}</head>
<body><main>{body}</main></body>
</html>"""


def _flash_html(message: str | None, ok: str | None) -> str:
    if not message:
        return ""
    cls = "ok" if ok == "1" else "err"
    return f'<div class="flash {cls}">{html.escape(message)}</div>'


def _render_list_page(rows: list[dict], message: str | None, ok: str | None) -> str:
    if not rows:
        body_rows = '<tr><td colspan="7" class="empty">Brak leadów w bazie jeszcze. Zasil bazę przez scripts/validate_audit_module.py albo import z LeadSeason.</td></tr>'
    else:
        body_rows = "\n".join(
            f"""<tr>
  <td><a href="/dashboard/{r['id']}">{html.escape(r['company_name'])}</a><div class="muted">{html.escape(r['domain'])}</div></td>
  <td>{html.escape(r['industry'] or '—')}</td>
  <td>{_status_badge(r['status'])}</td>
  <td>{_tier_badge(r['tier'])}</td>
  <td>{r['score']:.0f}</td>
  <td>{html.escape(r['audits_summary']) or '<span class="empty">brak</span>'}</td>
  <td>{_badge('Tak', '#22c55e') if r['has_consent'] else '<span class="muted">Nie</span>'}</td>
</tr>"""
            for r in rows
        )

    return _shell(
        "Dashboard",
        f"""
<div class="kicker">LeadSeason &middot; ai-ops.pl</div>
<h1>Panel operatora — pozyskiwanie leadów</h1>
<p class="sub">{len(rows)} leadów w bazie. Cały flow: lead → audyty → scoring → gate/zgoda → outreach.</p>
{_flash_html(message, ok)}
<div class="card" style="overflow-x:auto">
<table>
<thead><tr><th>Firma / domena</th><th>Branża</th><th>Etap</th><th>Tier</th><th>Score</th><th>Audyty</th><th>Zgoda</th></tr></thead>
<tbody>{body_rows}</tbody>
</table>
</div>
""",
    )


def _render_detail_page(
    lead: models.Lead,
    audits: list[models.AuditResult],
    consents: list[models.ConsentEvent],
    score_events: list[models.LeadScoreEvent],
    visits: list[models.MicroAppVisit],
    narrations: list[models.VoiceNarration],
    status: str,
    message: str | None,
    ok: str | None,
) -> str:
    audits_rows = "\n".join(
        f"""<li><strong>{html.escape(AUDIT_LABELS.get(a.audit_type, a.audit_type))}</strong>
        {f'— {a.score:.0f}/100' if a.score is not None else ''}
        <div class="muted">{html.escape((a.summary_text or '')[:200])}</div>
        <div class="muted">{a.created_at:%Y-%m-%d %H:%M}</div></li>"""
        for a in audits
    ) or '<li class="empty">Brak audytów jeszcze.</li>'

    consents_rows = "\n".join(
        f"""<li><strong>{html.escape(CONSENT_LABELS.get(c.consent_type, c.consent_type))}</strong>
        {'<span class="muted">(wycofana)</span>' if c.revoked_at else ''}
        <div class="muted">{html.escape(c.consent_text)}</div>
        <div class="muted">{c.granted_at:%Y-%m-%d %H:%M} · IP {html.escape(c.ip_address or '—')}</div></li>"""
        for c in consents
    ) or '<li class="empty">Brak zgód jeszcze — lead nie przeszedł gate\'a.</li>'

    score_rows = "\n".join(
        f"""<li>{'+' if e.score_delta >= 0 else ''}{e.score_delta:.0f} — {html.escape(e.reason)}
        <span class="muted">(suma: {e.score_total_after:.0f})</span>
        <div class="muted">{e.created_at:%Y-%m-%d %H:%M}</div></li>"""
        for e in score_events
    ) or '<li class="empty">Brak historii scoringu.</li>'

    visits_rows = "\n".join(
        f"""<li>{html.escape(v.event_type)} <span class="muted">{v.occurred_at:%Y-%m-%d %H:%M}</span></li>"""
        for v in visits[:30]
    ) or '<li class="empty">Lead jeszcze nie odwiedził mikro-apki.</li>'

    if narrations:
        latest_narration = narrations[0]
        audio_block = f"""
<p class="muted">{latest_narration.characters_used} znaków · {html.escape(latest_narration.voice_id)} · {latest_narration.created_at:%Y-%m-%d %H:%M}</p>
{'<audio controls src="/dashboard/' + lead.id + '/audio"></audio>' if latest_narration.audio_path else '<p class="empty">Brak zapisanego pliku audio (dry-run albo błąd zapisu).</p>'}
<p class="muted" style="margin-top:10px">{html.escape(latest_narration.script_text[:400])}{'…' if len(latest_narration.script_text) > 400 else ''}</p>
"""
    else:
        audio_block = '<p class="empty">Jeszcze nie wygenerowano narracji głosowej.</p>'

    slug_link = f'<a href="/audyt/{lead.slug}" target="_blank">/audyt/{html.escape(lead.slug)}</a>' if lead.slug else '<span class="empty">brak slug</span>'

    return _shell(
        f"{lead.company_name}",
        f"""
<a class="back" href="/dashboard">&larr; Wszyscy leadzi</a>
{_flash_html(message, ok)}
<div class="kicker">LeadSeason &middot; ai-ops.pl</div>
<h1>{html.escape(lead.company_name)}</h1>
<p class="sub">{html.escape(lead.domain)} · mikro-apka: {slug_link}</p>

<div class="grid2">
  <div>
    <div class="card">
      <h3 style="margin-top:0">Dane leada</h3>
      <dl class="kv">
        <dt>Etap</dt><dd>{_status_badge(status)}</dd>
        <dt>Tier</dt><dd>{_tier_badge(lead.tier)}</dd>
        <dt>Score</dt><dd>{lead.lead_score:.0f}</dd>
        <dt>Branża</dt><dd>{html.escape(lead.detected_industry or '—')}</dd>
        <dt>Sezon (peak)</dt><dd>{html.escape(lead.season_peak or '—')}</dd>
        <dt>E-mail</dt><dd>{html.escape(lead.contact_email or '—')}</dd>
        <dt>Telefon</dt><dd>{html.escape(lead.contact_phone or '—')}</dd>
        <dt>Źródło</dt><dd>{html.escape(lead.source)}</dd>
        <dt>Utworzono</dt><dd>{lead.created_at:%Y-%m-%d %H:%M}</dd>
      </dl>
      <div class="btn-row">
        <form class="action-form" method="post" action="/dashboard/{lead.id}/run-audit" data-loading-text="Sprawdzanie strony… (do 20 s)">
          <button class="btn" type="submit">Odpal audyt (SEO+AEO/GEO+Senuto)</button>
        </form>
        <form class="action-form" method="post" action="/dashboard/{lead.id}/generate-voice" data-loading-text="Generowanie narracji…">
          <button class="btn" type="submit">Wygeneruj narrację głosową</button>
        </form>
      </div>
    </div>

    <div class="card">
      <h3 style="margin-top:0">Audyty</h3>
      <ul class="timeline">{audits_rows}</ul>
    </div>

    <div class="card">
      <h3 style="margin-top:0">Narracja głosowa</h3>
      {audio_block}
    </div>
  </div>

  <div>
    <div class="card">
      <h3 style="margin-top:0">Zgody (RODO / art. 172)</h3>
      <ul class="timeline">{consents_rows}</ul>
    </div>

    <div class="card">
      <h3 style="margin-top:0">Historia scoringu</h3>
      <ul class="timeline">{score_rows}</ul>
    </div>

    <div class="card">
      <h3 style="margin-top:0">Aktywność w mikro-apce</h3>
      <ul class="timeline">{visits_rows}</ul>
    </div>
  </div>
</div>
<script>
(function () {{
  document.querySelectorAll("form.action-form").forEach(function (form) {{
    form.addEventListener("submit", function () {{
      var button = form.querySelector("button[type=submit]");
      if (!button || button.disabled) return;
      button.disabled = true;
      button.dataset.originalText = button.textContent;
      var loadingText = form.dataset.loadingText || "Przetwarzanie…";
      button.innerHTML = '<span class="spinner" aria-hidden="true"></span>' + loadingText;
    }});
  }});
}})();
</script>
""",
    )


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard_list(request: Request, db: Session = Depends(get_db)):
    leads = repository.list_leads(db)
    rows = []
    for lead in leads:
        audits = latest_audits_by_type(lead)
        has_consent = any(c.revoked_at is None for c in lead.consents)
        has_outreach = len(lead.outreach_events) > 0
        summary = ", ".join(
            f"{AUDIT_LABELS.get(t, t)} {a.score:.0f}" if a.score is not None else AUDIT_LABELS.get(t, t)
            for t, a in audits.items()
        )
        rows.append({
            "id": lead.id,
            "company_name": lead.company_name,
            "domain": lead.domain,
            "industry": lead.detected_industry,
            "status": _pipeline_status(lead, audits, has_consent, has_outreach),
            "tier": lead.tier,
            "score": lead.lead_score,
            "audits_summary": summary,
            "has_consent": has_consent,
        })
    message = request.query_params.get("msg")
    ok = request.query_params.get("ok")
    return HTMLResponse(_render_list_page(rows, message, ok))


@router.get("/dashboard/{lead_id}", response_class=HTMLResponse)
def dashboard_detail(lead_id: str, request: Request, db: Session = Depends(get_db)):
    lead = repository.get_lead(db, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Nie znaleziono leada.")
    audits = sorted(lead.audits, key=lambda a: a.created_at, reverse=True)
    consents = sorted(lead.consents, key=lambda c: c.granted_at, reverse=True)
    score_events = sorted(lead.score_events, key=lambda e: e.created_at, reverse=True)
    visits = sorted(lead.microapp_visits, key=lambda v: v.occurred_at, reverse=True)
    narrations = sorted(lead.voice_narrations, key=lambda n: n.created_at, reverse=True)
    has_consent = any(c.revoked_at is None for c in lead.consents)
    has_outreach = len(lead.outreach_events) > 0
    status = _pipeline_status(lead, latest_audits_by_type(lead), has_consent, has_outreach)
    message = request.query_params.get("msg")
    ok = request.query_params.get("ok")
    return HTMLResponse(
        _render_detail_page(lead, audits, consents, score_events, visits, narrations, status, message, ok)
    )


@router.post("/dashboard/{lead_id}/run-audit", dependencies=[Depends(require_api_key)])
def dashboard_run_audit(lead_id: str, db: Session = Depends(get_db)):
    lead = repository.get_lead(db, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Nie znaleziono leada.")
    url = _normalize_url(lead.domain)

    ran, failed = [], []
    try:
        onpage = run_onpage_audit(url)
        repository.add_audit_result(
            db, lead.id, "seo",
            raw_data=onpage["checks"],
            summary_text="; ".join(onpage["issues"]) or "Brak wykrytych problemów.",
            score=onpage["score"],
        )
        ran.append("SEO on-page")
    except Exception:
        failed.append("SEO on-page")

    try:
        aeo = run_aeo_geo_audit(url)
        repository.add_audit_result(
            db, lead.id, "aeo_geo",
            raw_data=aeo["raw_data"],
            summary_text="; ".join(aeo["issues"][:3]) or "Brak rekomendacji.",
            score=aeo["score"],
        )
        ran.append("AEO/GEO")
    except Exception:
        failed.append("AEO/GEO")

    try:
        ps = run_pagespeed_audit(url)
        repository.add_audit_result(
            db, lead.id, "pagespeed",
            raw_data=ps,
            summary_text=f"Performance {ps['score']}, SEO {ps['scores']['seo']}, A11y {ps['scores']['accessibility']}",
            score=ps["score"],
        )
        ran.append("PageSpeed")
    except PageSpeedConfigError:
        pass  # brak klucza -- pomijamy bez traktowania jako blad
    except Exception:
        failed.append("PageSpeed")

    senuto_row = load_senuto_row_for_industry(lead.detected_industry)
    if senuto_row:
        repository.add_audit_result(db, lead.id, "senuto", raw_data=senuto_row, summary_text="Dopasowanie z macierzy sezonowości Senuto.")
        ran.append("Senuto")

    parts = []
    if ran:
        parts.append(f"Zapisano: {', '.join(ran)}.")
    if failed:
        parts.append(f"Nie udało się: {', '.join(failed)}.")
    if not ran and not failed:
        parts.append("Brak nowych wyników (sprawdź czy domena jest osiągalna).")
    ok = "1" if ran and not failed else ("0" if failed else "1")
    return _redirect_to_detail(lead_id, " ".join(parts), ok)


@router.post("/dashboard/{lead_id}/generate-voice", dependencies=[Depends(require_api_key)])
def dashboard_generate_voice(lead_id: str, db: Session = Depends(get_db)):
    lead = repository.get_lead(db, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Nie znaleziono leada.")

    script_text = build_narration_script(lead)
    try:
        usage = get_usage()
    except ElevenLabsConfigError as exc:
        return _redirect_to_detail(lead_id, str(exc), "0")

    if len(script_text) > usage["characters_remaining"]:
        msg = (
            f"Przerwano: narracja ma {len(script_text)} znaków, a pozostało tylko "
            f"{usage['characters_remaining']} w limicie ElevenLabs."
        )
        return _redirect_to_detail(lead_id, msg, "0")

    try:
        audio_bytes = synthesize_narration(script_text, voice_id=DEFAULT_VOICE_ID)
    except ElevenLabsAPIError as exc:
        return _redirect_to_detail(lead_id, str(exc), "0")

    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    audio_path = AUDIO_DIR / f"{lead.id}.mp3"
    audio_path.write_bytes(audio_bytes)

    repository.record_voice_narration(
        db, lead.id,
        script_text=script_text,
        characters_used=len(script_text),
        voice_id=DEFAULT_VOICE_ID,
        model_id=DEFAULT_MODEL_ID,
        audio_path=str(audio_path),
    )
    msg = f"Wygenerowano narrację ({len(script_text)} znaków)."
    return _redirect_to_detail(lead_id, msg, "1")


@router.get("/dashboard/{lead_id}/audio")
def dashboard_audio(lead_id: str, db: Session = Depends(get_db)):
    lead = repository.get_lead(db, lead_id)
    if lead is None or not lead.voice_narrations:
        raise HTTPException(status_code=404, detail="Brak narracji dla tego leada.")
    latest = sorted(lead.voice_narrations, key=lambda n: n.created_at, reverse=True)[0]
    if not latest.audio_path or not Path(latest.audio_path).exists():
        raise HTTPException(status_code=404, detail="Plik audio nie istnieje na dysku.")
    return FileResponse(latest.audio_path, media_type="audio/mpeg")
