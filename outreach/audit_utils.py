"""Shared helpers for reading audit results off a Lead.

Used by backend/microapp.py (rendering the report) and outreach/voice/script.py
(building the narration) -- kept in one place so both stay in sync.
"""
from . import models


def latest_audits_by_type(lead: models.Lead) -> dict[str, models.AuditResult]:
    latest: dict[str, models.AuditResult] = {}
    for audit in lead.audits:
        current = latest.get(audit.audit_type)
        if current is None or audit.created_at >= current.created_at:
            latest[audit.audit_type] = audit
    return latest
