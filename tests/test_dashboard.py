# -*- coding: utf-8 -*-
"""Dashboard tests run against an isolated in-memory SQLite DB (FastAPI
dependency override), never the real outreach/data/leadgen.db dev database."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api import app
from outreach import models, repository
from outreach.db import Base, get_db


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def _override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    yield TestClient(app), TestSession
    app.dependency_overrides.pop(get_db, None)


def _seed_lead(TestSession, **overrides):
    db = TestSession()
    fields = {"company_name": "Testowa Firma", "domain": "https://testowa-firma.pl", "source": "test"}
    fields.update(overrides)
    lead = repository.create_lead(db, **fields)
    db.close()
    return lead.id


def test_dashboard_list_empty(client):
    web, _ = client
    resp = web.get("/dashboard")
    assert resp.status_code == 200
    assert "Brak leadów" in resp.text


def test_dashboard_list_shows_seeded_lead(client):
    web, TestSession = client
    _seed_lead(TestSession)
    resp = web.get("/dashboard")
    assert resp.status_code == 200
    assert "Testowa Firma" in resp.text
    assert "Nowy" in resp.text  # brak audytów/zgód/outreachu -> etap "Nowy"


def test_dashboard_detail_404_for_unknown_lead(client):
    web, _ = client
    resp = web.get("/dashboard/does-not-exist")
    assert resp.status_code == 404


def test_dashboard_detail_reflects_audit_and_consent(client):
    web, TestSession = client
    lead_id = _seed_lead(TestSession)
    db = TestSession()
    repository.add_audit_result(db, lead_id, "seo", score=88.0, summary_text="Brak wykrytych problemow.")
    repository.record_consent(db, lead_id, "contact_phone_sms", consent_text="Zgoda testowa.")
    db.close()

    resp = web.get(f"/dashboard/{lead_id}")
    assert resp.status_code == 200
    assert "SEO on-page" in resp.text
    assert "88" in resp.text
    assert "Zarejestrowany (gate)" in resp.text


def test_dashboard_audio_404_without_narration(client):
    web, TestSession = client
    lead_id = _seed_lead(TestSession)
    resp = web.get(f"/dashboard/{lead_id}/audio")
    assert resp.status_code == 404
