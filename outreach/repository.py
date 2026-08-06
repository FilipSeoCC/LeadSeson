"""CRUD helpers for the outreach/ schema.

has_valid_consent() is the compliance gate from sekcja 9 of
STRATEGIA_SYSTEM_POZYSKIWANIA_LEADOW.md: SMS and voice-call outreach (art. 172
Prawa telekomunikacyjnego) must not fire without a live consent record. Any
future sender for those channels should call this before dispatch, not
re-implement the check.
"""
import sys
from pathlib import Path

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import models
from .slug import slugify_company_name

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bulk_crawler import domain_key  # noqa: E402


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
    """_unique_slug()'s pre-check is a fast path, not a guarantee: two concurrent
    calls for the same company_name can both see a candidate slug as free before
    either commits. If the pre-checked slug still collides at INSERT time, roll
    back and pick a fresh one against the now-updated DB state instead of
    letting the IntegrityError crash the request; a caller-supplied slug is
    trusted as intentional and re-raised instead of silently changed.
    """
    if fields.get("domain"):
        fields["domain"] = domain_key(fields["domain"])

    explicit_slug = fields.get("slug")
    company_name = fields.get("company_name", "")
    candidate_slug = explicit_slug or _unique_slug(db, company_name)

    attempts_left = 5
    while True:
        lead = models.Lead(**{**fields, "slug": candidate_slug})
        db.add(lead)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            attempts_left -= 1
            if explicit_slug or attempts_left <= 0:
                raise
            candidate_slug = _unique_slug(db, company_name)
            continue
        db.refresh(lead)
        return lead


def list_leads(db: Session, limit: int = 500) -> list[models.Lead]:
    return (
        db.query(models.Lead)
        .order_by(models.Lead.updated_at.desc())
        .limit(limit)
        .all()
    )


def get_lead(db: Session, lead_id: str) -> models.Lead | None:
    return db.get(models.Lead, lead_id)


def get_lead_by_domain(db: Session, domain: str) -> models.Lead | None:
    """Compares against the same domain_key() form create_lead() now stores,
    so https://example.pl/, example.pl, and https://www.example.pl/oferta
    all resolve to the same Lead instead of creating duplicates."""
    return db.query(models.Lead).filter(models.Lead.domain == domain_key(domain)).first()


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


def backfill_domains(db: Session) -> int:
    """One-time cleanup for Lead rows created before get_lead_by_domain()/
    create_lead() started normalizing via domain_key(). Collapses any now-
    duplicate domain_key values onto the oldest row (keeps its id/slug/audit
    history) and re-points child rows before deleting the newer duplicates,
    so no ConsentEvent/AuditResult/etc. is silently lost. Returns count of
    Lead rows updated in place (not counting duplicates removed)."""
    updated = 0
    seen_by_key: dict[str, models.Lead] = {}
    for lead in db.query(models.Lead).order_by(models.Lead.created_at.asc()).all():
        normalized = domain_key(lead.domain)
        canonical = seen_by_key.get(normalized)
        if canonical is None:
            if lead.domain != normalized:
                lead.domain = normalized
                updated += 1
            seen_by_key[normalized] = lead
            continue
        for child_model in (models.AuditResult, models.ConsentEvent, models.OutreachEvent, models.LeadScoreEvent, models.MicroAppVisit, models.VoiceNarration):
            db.query(child_model).filter(child_model.lead_id == lead.id).update(
                {child_model.lead_id: canonical.id}, synchronize_session=False
            )
        db.delete(lead)
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

    # Atomic "SET lead_score = lead_score + delta" at the DB level, not a Python
    # read-modify-write -- two concurrent calls for the same lead_id (e.g. a
    # gate retry racing the original request) would otherwise both read the
    # same starting value and the second commit would silently drop one
    # increment even though both LeadScoreEvent audit rows got inserted.
    db.query(models.Lead).filter(models.Lead.id == lead_id).update(
        {models.Lead.lead_score: models.Lead.lead_score + score_delta},
        synchronize_session=False,
    )
    db.refresh(lead)

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
