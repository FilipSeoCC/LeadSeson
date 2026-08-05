"""One-off sanity check for the outreach/ lead-acquisition schema.

Creates a temp SQLite DB, runs a full round trip across all tables, and
prints the result. Not a test suite (repo has none) -- a manual smoke check
for STRATEGIA_SYSTEM_POZYSKIWANIA_LEADOW.md sekcja 12, krok 1.

Usage: python scripts/verify_leadgen_schema.py
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

tmp_db = Path(tempfile.gettempdir()) / "leadgen_schema_check.db"
tmp_db.unlink(missing_ok=True)
os.environ["LEADGEN_DATABASE_URL"] = f"sqlite:///{tmp_db}"

from outreach import repository  # noqa: E402
from outreach.db import Base, SessionLocal, engine  # noqa: E402

Base.metadata.create_all(bind=engine)
db = SessionLocal()

lead = repository.create_lead(
    db,
    company_name="Testowa Firma Sp. z o.o.",
    domain="testowa-firma.pl",
    detected_industry="HVAC",
    season_peak="Q4",
    contact_email="kontakt@testowa-firma.pl",
)
assert lead.slug == "testowa-firma", f"expected slugified company name without legal suffix, got {lead.slug!r}"
assert repository.get_lead_by_slug(db, lead.slug).id == lead.id

repository.add_audit_result(db, lead.id, "seo", score=62.5, summary_text="Braki w meta description.")
repository.add_audit_result(
    db, lead.id, "aeo_geo", score=10.0, summary_text="Strona nieobecna w cytowaniach ChatGPT/Perplexity."
)
repository.record_score_event(db, lead.id, 15.0, "registered_via_gate")
consent = repository.record_consent(
    db,
    lead.id,
    "contact_phone_sms",
    consent_text="Zgadzam sie na kontakt telefoniczny/SMS w celu omowienia wynikow audytu.",
    ip_address="203.0.113.5",
)
repository.record_outreach_event(db, lead.id, "email", tier=1, status="sent")
repository.record_microapp_visit(db, lead.id, session_id="sess-1", event_type="gate_submitted")

assert repository.has_valid_consent(db, lead.id, "contact_phone_sms") is True
assert repository.has_valid_consent(db, lead.id, "ai_voice_video") is False

refreshed = repository.get_lead(db, lead.id)
assert refreshed is not None
assert len(refreshed.audits) == 2
assert refreshed.lead_score == 15.0

print(f"Lead: {refreshed.company_name} | score={refreshed.lead_score} | audyty={len(refreshed.audits)}")
print(f"Zgoda SMS/telefon: {consent.consent_type} @ {consent.granted_at}")
print("OK: pelny round-trip po schemacie leadgen zakonczony sukcesem.")

db.close()
engine.dispose()  # release the sqlite file handle before cleanup (Windows locks it otherwise)
try:
    tmp_db.unlink(missing_ok=True)
except OSError:
    pass  # best-effort cleanup of the temp DB, not worth failing the check over
