"""Shared helpers for reading audit results off a Lead.

Used by backend/microapp.py (rendering the report), backend/dashboard.py, and
outreach/voice/script.py (building the narration) -- kept in one place so all
three stay in sync.
"""
from sqlalchemy import func
from sqlalchemy.orm import Session

from . import models


def latest_audits_by_type(lead: models.Lead, db: Session | None = None) -> dict[str, models.AuditResult]:
    """Returns the newest AuditResult per audit_type for this lead.

    Pass `db` when available: this is called on the public hot path (every
    GET /audyt/{slug} page view, plus the dashboard) and querying only the
    rows actually needed avoids loading a lead's entire audit history --
    including large raw_data JSON blobs from aeo_geo/pagespeed -- just to
    keep the newest row per type. Without `db`, falls back to scanning the
    already-loaded lead.audits relationship (e.g. right after add_audit_result()
    in the same request, before a fresh query would see it without a flush).
    """
    if db is not None:
        latest_per_type = (
            db.query(models.AuditResult.audit_type, func.max(models.AuditResult.created_at).label("max_created_at"))
            .filter(models.AuditResult.lead_id == lead.id)
            .group_by(models.AuditResult.audit_type)
            .subquery()
        )
        rows = (
            db.query(models.AuditResult)
            .join(
                latest_per_type,
                (models.AuditResult.audit_type == latest_per_type.c.audit_type)
                & (models.AuditResult.created_at == latest_per_type.c.max_created_at)
                & (models.AuditResult.lead_id == lead.id),
            )
            .all()
        )
        return {row.audit_type: row for row in rows}

    latest: dict[str, models.AuditResult] = {}
    for audit in lead.audits:
        current = latest.get(audit.audit_type)
        if current is None or audit.created_at >= current.created_at:
            latest[audit.audit_type] = audit
    return latest


def pick_hook(lead: models.Lead, audits: dict[str, models.AuditResult]) -> dict:
    """Insight-trigger headline (sekcja 7A) -- konkret, nie generyczne "oto Twoj audyt".

    Priorytet z sekcji 6: AEO/GEO jako potencjalnie mocniejszy trigger niz
    klasyczne SEO dla czesci segmentow -> sprobuj najpierw, potem sezonowosc
    (rdzen LeadSeason), potem SEO on-page, na koncu generyczny fallback.

    Shared by backend/microapp.py (mikro-apka) and outreach/send/ (temat i
    naglowek maila outreachowego) -- ten sam hak, dwa kanaly.
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
