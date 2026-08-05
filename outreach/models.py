"""ORM schema for the ai-ops.pl lead acquisition system.

Maps directly onto STRATEGIA_SYSTEM_POZYSKIWANIA_LEADOW.md:
- Lead                 core entity, tier/score fields from sekcja 4 i 7D
- AuditResult          sekcja 2 (SEO/PageSpeed/Places/AEO-GEO/Senuto/sezonowość)
- ConsentEvent         sekcja 7C i 9 (RODO gate, art. 172 zgody SMS/telefon)
- OutreachEvent        sekcja 5/8 (kanały) + sekcja 9 (AI Act disclosure)
- LeadScoreEvent       audit trail tierowania, sekcja 4/7D
- MicroAppVisit        tracking zachowania w mikro-apce, sekcja 7D

Categorical fields (audit_type, channel, status, ...) are plain strings rather
than DB enums — new categories will be added as modules land (sekcja 12) and
SQLite/Postgres enum migrations are more friction than the validation is worth;
allowed values are documented and enforced at the Pydantic layer (schemas.py).
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    company_name: Mapped[str] = mapped_column(String(255))
    domain: Mapped[str] = mapped_column(String(255), index=True)
    # URL slug for the per-lead micro-app (sekcja 7: audyt.ai-ops.pl/nazwa-firmy).
    # Nullable + unique so existing rows can be backfilled (repository.backfill_slugs).
    slug: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True, index=True)
    nip: Mapped[str | None] = mapped_column(String(20), nullable=True)
    detected_industry: Mapped[str | None] = mapped_column(String(120), nullable=True)
    season_peak: Mapped[str | None] = mapped_column(String(120), nullable=True)
    contact_start: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source: Mapped[str] = mapped_column(String(50), default="leadseason_crawl")
    # Publicly discoverable contact used for the first cold touch (e.g. via
    # Hunter.io). Anything beyond this -- phone, SMS, calls -- requires a
    # ConsentEvent (sekcja 7C/9), enforced by repository.has_valid_consent().
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    decision_maker_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tier: Mapped[int] = mapped_column(Integer, default=1)  # 1/2/3, sekcja 4
    lead_score: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    audits: Mapped[list["AuditResult"]] = relationship(back_populates="lead", cascade="all, delete-orphan")
    consents: Mapped[list["ConsentEvent"]] = relationship(back_populates="lead", cascade="all, delete-orphan")
    outreach_events: Mapped[list["OutreachEvent"]] = relationship(back_populates="lead", cascade="all, delete-orphan")
    score_events: Mapped[list["LeadScoreEvent"]] = relationship(back_populates="lead", cascade="all, delete-orphan")
    microapp_visits: Mapped[list["MicroAppVisit"]] = relationship(back_populates="lead", cascade="all, delete-orphan")
    voice_narrations: Mapped[list["VoiceNarration"]] = relationship(back_populates="lead", cascade="all, delete-orphan")


class AuditResult(Base):
    __tablename__ = "audit_results"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"), index=True)
    audit_type: Mapped[str] = mapped_column(String(30))  # seo | pagespeed | places | aeo_geo | senuto | seasonality
    raw_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    summary_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    lead: Mapped["Lead"] = relationship(back_populates="audits")


class ConsentEvent(Base):
    __tablename__ = "consent_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"), index=True)
    consent_type: Mapped[str] = mapped_column(String(40))  # contact_phone_sms | marketing_email | ai_voice_video
    # Exact wording shown to the user at consent time -- required as legal
    # evidence of informed, specific consent (sekcja 7C), not a generic label.
    consent_text: Mapped[str] = mapped_column(Text)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    double_opt_in_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    lead: Mapped["Lead"] = relationship(back_populates="consents")


class OutreachEvent(Base):
    __tablename__ = "outreach_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"), index=True)
    channel: Mapped[str] = mapped_column(String(30))  # email | sms | voice_call | video | phone_manual
    tier: Mapped[int] = mapped_column(Integer)
    content_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ai_generated: Mapped[bool] = mapped_column(Boolean, default=False)
    # AI Act: obowiazek oznaczania tresci AI-generated w UE od 2026-08-02 (sekcja 9).
    ai_disclosed: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    response_classification: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    lead: Mapped["Lead"] = relationship(back_populates="outreach_events")


class LeadScoreEvent(Base):
    __tablename__ = "lead_score_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"), index=True)
    score_delta: Mapped[float] = mapped_column(Float)
    score_total_after: Mapped[float] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    lead: Mapped["Lead"] = relationship(back_populates="score_events")


class MicroAppVisit(Base):
    __tablename__ = "microapp_visits"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"), index=True)
    session_id: Mapped[str] = mapped_column(String(64))
    # page_view | scroll_depth | chart_click | gate_shown | gate_submitted | return_visit
    event_type: Mapped[str] = mapped_column(String(40))
    event_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    lead: Mapped["Lead"] = relationship(back_populates="microapp_visits")


class VoiceNarration(Base):
    """ElevenLabs TTS generation record -- sekcja 3/11: koszt liczy sie w znakach
    (free tier: 10 000/miesiac, bez klonowania), wiec kazda synteza jest
    logowana tutaj, zeby latwo zsumowac zuzycie i nie przekroczyc limitu."""

    __tablename__ = "voice_narrations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"), index=True)
    script_text: Mapped[str] = mapped_column(Text)
    characters_used: Mapped[int] = mapped_column(Integer)
    voice_id: Mapped[str] = mapped_column(String(64))
    model_id: Mapped[str] = mapped_column(String(64))
    audio_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    lead: Mapped["Lead"] = relationship(back_populates="voice_narrations")
