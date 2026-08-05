"""CRUD helpers for the outreach/ schema.

has_valid_consent() is the compliance gate from sekcja 9 of
STRATEGIA_SYSTEM_POZYSKIWANIA_LEADOW.md: SMS and voice-call outreach (art. 172
Prawa telekomunikacyjnego) must not fire without a live consent record. Any
future sender for those channels should call this before dispatch, not
re-implement the check.
"""
from sqlalchemy.orm import Session

from . import models
from .slug import slugify_company_name


def _unique_slug(db: Session, company_name: str, exclude_lead_id: str | None = None) -> str:
    base = slugify_company_name(company_name)
    slug = base
    suffix = 2
    while True:
        query = db.query(models.Lead).filter(models.Lead.slug == slug)
        if exclude_lead_id:
            query = query.filter(models.Lead.id != exclude_lead_id)
        if query.first() is None:
            return slug
        slug = f"{base}-{suffix}"
        suffix += 1


def create_lead(db: Session, **fields) -> models.Lead:
    if not fields.get("slug"):
        fields["slug"] = _unique_slug(db, fields.get("company_name", ""))
    lead = models.Lead(**fields)
    db.add(lead)
    db.commit()
    db.refresh(lead)
    return lead


def get_lead(db: Session, lead_id: str) -> models.Lead | None:
    return db.get(models.Lead, lead_id)


def get_lead_by_domain(db: Session, domain: str) -> models.Lead | None:
    return db.query(models.Lead).filter(models.Lead.domain == domain).first()


def get_lead_by_slug(db: Session, slug: str) -> models.Lead | None:
    return db.query(models.Lead).filter(models.Lead.slug == slug).first()


def backfill_slugs(db: Session) -> int:
    """Assign a slug to any Lead created before the slug column existed. Returns count updated.

    Flushes after each assignment: _unique_slug()'s uniqueness query runs against
    this same session (autoflush=False, see db.py), so without an explicit flush
    it would not see slugs assigned earlier in this same loop and could hand out
    duplicates before the final commit.
    """
    updated = 0
    for lead in db.query(models.Lead).filter(models.Lead.slug.is_(None)).all():
        lead.slug = _unique_slug(db, lead.company_name, exclude_lead_id=lead.id)
        db.flush()
        updated += 1
    if updated:
        db.commit()
    return updated


def add_audit_result(db: Session, lead_id: str, audit_type: str, **fields) -> models.AuditResult:
    audit = models.AuditResult(lead_id=lead_id, audit_type=audit_type, **fields)
    db.add(audit)
    db.commit()
    db.refresh(audit)
    return audit


def record_consent(db: Session, lead_id: str, consent_type: str, consent_text: str, **fields) -> models.ConsentEvent:
    consent = models.ConsentEvent(lead_id=lead_id, consent_type=consent_type, consent_text=consent_text, **fields)
    db.add(consent)
    db.commit()
    db.refresh(consent)
    return consent


def revoke_consent(db: Session, consent_id: str) -> models.ConsentEvent | None:
    consent = db.get(models.ConsentEvent, consent_id)
    if consent is None:
        return None
    consent.revoked_at = models._now()
    db.commit()
    db.refresh(consent)
    return consent


def has_valid_consent(db: Session, lead_id: str, consent_type: str) -> bool:
    """Sekcja 9: SMS/telefon wymagaja zgody z art. 172 -- sprawdz przed wysylka."""
    consent = (
        db.query(models.ConsentEvent)
        .filter(models.ConsentEvent.lead_id == lead_id, models.ConsentEvent.consent_type == consent_type)
        .order_by(models.ConsentEvent.granted_at.desc())
        .first()
    )
    return consent is not None and consent.revoked_at is None


def record_outreach_event(db: Session, lead_id: str, channel: str, tier: int, **fields) -> models.OutreachEvent:
    event = models.OutreachEvent(lead_id=lead_id, channel=channel, tier=tier, **fields)
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def record_score_event(db: Session, lead_id: str, score_delta: float, reason: str) -> models.LeadScoreEvent:
    lead = get_lead(db, lead_id)
    if lead is None:
        raise ValueError(f"Nieznany lead_id: {lead_id}")
    lead.lead_score += score_delta
    event = models.LeadScoreEvent(
        lead_id=lead_id,
        score_delta=score_delta,
        score_total_after=lead.lead_score,
        reason=reason,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def record_microapp_visit(
    db: Session, lead_id: str, session_id: str, event_type: str, event_data: dict | None = None
) -> models.MicroAppVisit:
    visit = models.MicroAppVisit(lead_id=lead_id, session_id=session_id, event_type=event_type, event_data=event_data)
    db.add(visit)
    db.commit()
    db.refresh(visit)
    return visit


def record_voice_narration(
    db: Session, lead_id: str, script_text: str, characters_used: int, voice_id: str, model_id: str,
    audio_path: str | None = None,
) -> models.VoiceNarration:
    narration = models.VoiceNarration(
        lead_id=lead_id,
        script_text=script_text,
        characters_used=characters_used,
        voice_id=voice_id,
        model_id=model_id,
        audio_path=audio_path,
    )
    db.add(narration)
    db.commit()
    db.refresh(narration)
    return narration


def total_voice_characters_used(db: Session) -> int:
    """Suma znakow wyslanych do ElevenLabs do tej pory -- porównaj z darmowym
    limitem (10 000/mies., sekcja 3) przed kolejna synteza."""
    from sqlalchemy import func

    total = db.query(func.sum(models.VoiceNarration.characters_used)).scalar()
    return int(total or 0)
