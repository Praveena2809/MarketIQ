"""
Phase 1 regression tests: health, stats, recent research, demo user seeding,
and basic secret non-exposure in API responses.
Run with: venv/bin/python -m pytest tests/test_phase1_regression.py
"""
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import get_settings
from app.core.database import init_db, SessionLocal
from app.models.user import User

client = TestClient(app)
settings = get_settings()


def setup_module(module):
    init_db()


def test_demo_user_seeded():
    db = SessionLocal()
    try:
        demo_user = db.query(User).filter(User.id == settings.DEFAULT_USER_ID).first()
        assert demo_user is not None, "Demo user must be seeded"
        assert demo_user.email == settings.DEFAULT_USER_EMAIL
    finally:
        db.close()


def test_health_endpoint():
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["database"] == "connected"
    assert body["environment"] == settings.ENVIRONMENT
    assert body["gemini_configured"] is True


def test_stats_endpoint():
    res = client.get("/api/stats")
    assert res.status_code == 200
    body = res.json()
    for key in (
        "researches_completed",
        "sources_analyzed",
        "companies_analyzed",
        "trends_detected",
        "insights_synthesized",
        "opportunities_identified",
        "risks_identified",
    ):
        assert key in body
        assert isinstance(body[key], int)
    for key in ("sentiment_counts", "research_type_counts", "source_type_counts"):
        assert key in body
        assert isinstance(body[key], dict)


def test_recent_research_endpoint():
    res = client.get("/api/research/recent")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    for item in data:
        assert "id" in item
        assert "query" in item
        assert "status" in item


def test_root_endpoint():
    res = client.get("/")
    assert res.status_code == 200
    assert res.json()["service"] == "MarketIQ API"


def test_health_does_not_expose_api_key():
    """The Gemini API key must never appear in any API response body."""
    api_key = settings.GEMINI_API_KEY
    assert api_key, "Test environment should configure GEMINI_API_KEY"

    for path in ("/api/health", "/api/stats", "/api/research/recent"):
        res = client.get(path)
        assert res.status_code == 200
        assert api_key not in res.text