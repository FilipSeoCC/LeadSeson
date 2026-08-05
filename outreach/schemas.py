"""Pydantic Create/Read schemas for the outreach/ API layer.

Literal types are the single source of truth for allowed categorical values
(audit_type, consent_type, channel, status) -- models.py stores them as plain
strings, validation happens here.
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

AuditType = Literal["seo", "pagespeed", "places", "aeo_geo", "senuto", "seasonality"]
ConsentType = Literal["contact_phone_sms", "marketing_email", "ai_voice_video"]
OutreachChannel = Literal["email", "sms", "voice_call", "video", "phone_manual"]
OutreachStatus = Literal["queued", "sent", "delivered", "opened", "clicked", "replied", "bounced", "failed"]
MicroAppEventType = Literal["page_view", "scroll_depth", "chart_click", "gate_shown", "gate_submitted", "return_visit"]


class LeadCreate(BaseModel):
    company_name: str
    domain: str
    nip: str | None = None
    detected_industry: str | None = None
    season_peak: str | None = None
    contact_start: str | None = None
    source: str = "leadseason_crawl"
    contact_email: str | None = None
    contact_phone: str | None = None
    decision_maker_name: str | None = None


class LeadRead(LeadCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tier: int
    lead_score: float
    created_at: datetime
    updated_at: datetime


class AuditResultCreate(BaseModel):
    audit_type: AuditType
    raw_data: dict | None = None
    summary_text: str | None = None
    score: float | None = None


class AuditResultRead(AuditResultCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    lead_id: str
    created_at: datetime


class ConsentEventCreate(BaseModel):
    consent_type: ConsentType
    consent_text: str
    ip_address: str | None = None
    user_agent: str | None = None


class ConsentEventRead(ConsentEventCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    lead_id: str
    granted_at: datetime
    double_opt_in_confirmed_at: datetime | None = None
    revoked_at: datetime | None = None


class OutreachEventCreate(BaseModel):
    channel: OutreachChannel
    tier: int
    content_ref: str | None = None
    ai_generated: bool = False
    ai_disclosed: bool = False
    status: OutreachStatus = "queued"


class OutreachEventRead(OutreachEventCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    lead_id: str
    sent_at: datetime | None = None
    responded_at: datetime | None = None
    response_classification: str | None = None
    created_at: datetime


class LeadScoreEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    lead_id: str
    score_delta: float
    score_total_after: float
    reason: str
    created_at: datetime


class MicroAppVisitCreate(BaseModel):
    session_id: str
    event_type: MicroAppEventType
    event_data: dict | None = None


class MicroAppVisitRead(MicroAppVisitCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    lead_id: str
    occurred_at: datetime
