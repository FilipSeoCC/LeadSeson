"""Outreach email content + send orchestration.

STRATEGIA_SYSTEM_POZYSKIWANIA_LEADOW.md sekcja 12: "test wysylki (mail+audio,
mala proba) -> walidacja konwersji przed inwestycja w wideo". Sekcja 4 opisuje
tierowanie (Tier 1 = sam tekst, Tier 2 = audio klonowanym glosem) -- ten modul
dolacza automatycznie najnowsza narracje glosowa jesli istnieje dla leada,
zamiast czekac na osobny etap tierowania logiki wysylkowej.

AI Act (sekcja 9): tresc maila jest generowana (szablon + insight-trigger z
audytow) i moze zawierac audio TTS -- oznaczone jawnie w tresci maila oraz
ai_generated=True/ai_disclosed=True na OutreachEvent.
"""
import os

from sqlalchemy.orm import Session

from .. import models, repository
from ..audit_utils import latest_audits_by_type, pick_hook
from .email import ResendAPIError, ResendConfigError, send_email

MICROAPP_BASE_URL = os.getenv("MICROAPP_BASE_URL", "http://localhost:8010")
DEFAULT_TIER = 1
AI_DISCLOSURE_NOTE = "Ta wiadomość i towarzyszący jej audyt zostały przygotowane przy wsparciu narzędzi AI."


def build_outreach_email(lead: models.Lead, db: Session | None = None) -> dict:
    """Buduje temat i treść HTML maila outreachowego (nie wysyła)."""
    audits = latest_audits_by_type(lead, db)
    hook = pick_hook(lead, audits)
    audyt_url = f"{MICROAPP_BASE_URL}/audyt/{lead.slug}"

    html_body = f"""\
<div style="font-family:Arial,Helvetica,sans-serif;font-size:15px;color:#1f2937;line-height:1.6;max-width:560px;margin:0 auto;">
  <p>Dzień dobry,</p>
  <p><strong>{hook["headline"]}</strong><br>{hook["subline"]}</p>
  <p>Pełny raport z konkretnymi rekomendacjami czeka pod linkiem:</p>
  <p><a href="{audyt_url}" style="display:inline-block;background:#fb923c;color:#1a0f05;padding:10px 22px;border-radius:999px;text-decoration:none;font-weight:bold;">Zobacz audyt — {lead.company_name}</a></p>
  <p style="color:#6b7280;font-size:12px;margin-top:24px;">{AI_DISCLOSURE_NOTE}</p>
</div>"""
    return {"subject": hook["headline"], "html_body": html_body, "audyt_url": audyt_url}


def send_outreach_email_for_lead(
    db: Session, lead: models.Lead, to_email: str, tier: int = DEFAULT_TIER
) -> models.OutreachEvent:
    """Buduje i wysyła mail outreachowy, zawsze zapisuje OutreachEvent (status
    sent/failed) jako log próby kontaktu -- caller sprawdza event.status,
    zamiast łapać wyjątki, żeby wiedzieć czy się udało."""
    content = build_outreach_email(lead, db)
    narrations = sorted(lead.voice_narrations, key=lambda n: n.created_at, reverse=True)
    latest_narration = narrations[0] if narrations else None
    attachment_path = latest_narration.audio_path if latest_narration and latest_narration.audio_path else None
    if attachment_path and not os.path.exists(attachment_path):
        attachment_path = None

    try:
        result = send_email(
            to_email=to_email,
            subject=content["subject"],
            html_body=content["html_body"],
            attachment_path=attachment_path,
            attachment_filename="audyt-narracja.mp3" if attachment_path else None,
        )
        status = "sent"
        content_ref = result.get("id")
    except (ResendConfigError, ResendAPIError) as exc:
        status = "failed"
        content_ref = str(exc)

    event = repository.record_outreach_event(
        db,
        lead.id,
        channel="email",
        tier=tier,
        content_ref=content_ref,
        ai_generated=True,
        ai_disclosed=True,
        status=status,
    )
    if status == "sent":
        event.sent_at = models._now()
        db.commit()
        db.refresh(event)
    return event
