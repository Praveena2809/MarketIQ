"""
Phase 11 regression tests: the research-history list API (GET /api/research/history).

Deterministic: truncates the research tables at module start, seeds Research
rows directly (no external/AI calls), and cleans up after each test. Verifies
row shape, updated_at DESC ordering, limit/offset pagination, query-param
bounds, route ordering (history must be registered before /{research_id}),
failed-record inclusion, /api/research/recent regression, and secret
non-exposure.

Run with: venv/bin/python -m pytest tests/test_phase11_history.py
"""
from datetime import datetime, timezone, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.core.config import get_settings
from app.core.database import init_db, SessionLocal
from app.models.research import Research, ResearchStatus, ResearchType
from app.models.research_result import ResearchResult
from app.models.source import Source

client = TestClient(app)
settings = get_settings()

CARD_KEYS = ("id", "query", "research_type", "status", "updated_at")


def setup_module(module):
    init_db()
    db = SessionLocal()
    try:
        # Exact pagination assertions need a known-empty research table, so
        # clear leftover rows from prior runs/modules at module start.
        db.query(Source).delete()
        db.query(ResearchResult).delete()
        db.query(Research).delete()
        db.commit()
    finally:
        db.close()


def _seed(
    db,
    query="history test query",
    research_type=ResearchType.MARKET_ANALYSIS,
    status=ResearchStatus.COMPLETED,
    updated_at=None,
    with_result=False,
):
    research = Research(
        user_id=settings.DEFAULT_USER_ID,
        query=query,
        research_type=research_type,
        status=status,
    )
    if updated_at is not None:
        research.updated_at = updated_at
    db.add(research)
    db.flush()
    if with_result:
        db.add(ResearchResult(research_id=research.id, summary="history summary"))
    db.commit()
    return research.id


def _cleanup(db, research_ids):
    for research_id in research_ids:
        research = db.get(Research, research_id)
        if research:
            db.delete(research)
    db.commit()


def test_history_empty_db_returns_empty_list():
    res = client.get("/api/research/history")
    assert res.status_code == 200
    assert res.json() == []


def test_history_row_shape():
    db = SessionLocal()
    research_ids = []
    try:
        research_ids.append(_seed(db, query="shape query", with_result=True))
        body = client.get("/api/research/history?limit=10").json()
        assert len(body) == 1
        item = body[0]
        for key in CARD_KEYS:
            assert key in item
        assert item["query"] == "shape query"
        assert item["research_type"] == "market_analysis"
        assert item["status"] == "completed"
    finally:
        _cleanup(db, research_ids)
        db.close()


def test_history_orders_by_updated_at_desc():
    db = SessionLocal()
    research_ids = []
    try:
        now = datetime.now(timezone.utc)
        research_ids.append(_seed(db, query="oldest", updated_at=now - timedelta(hours=3)))
        research_ids.append(_seed(db, query="middle", updated_at=now - timedelta(hours=2)))
        research_ids.append(_seed(db, query="newest", updated_at=now - timedelta(hours=1)))
        body = client.get("/api/research/history?limit=10").json()
        assert [r["query"] for r in body] == ["newest", "middle", "oldest"]
    finally:
        _cleanup(db, research_ids)
        db.close()


def test_history_pagination_limit_and_offset():
    db = SessionLocal()
    research_ids = []
    try:
        now = datetime.now(timezone.utc)
        research_ids = [_seed(db, query=f"page {i}", updated_at=now + timedelta(minutes=i)) for i in range(7)]
        page1 = client.get("/api/research/history?limit=3&offset=0").json()
        page2 = client.get("/api/research/history?limit=3&offset=3").json()
        page3 = client.get("/api/research/history?limit=3&offset=6").json()
        beyond = client.get("/api/research/history?limit=3&offset=9").json()

        assert len(page1) == 3
        assert len(page2) == 3
        assert len(page3) == 1
        assert beyond == []

        covered = [r["id"] for r in page1 + page2 + page3]
        assert len(covered) == len(set(covered)) == len(research_ids)
        assert set(covered) == set(research_ids)
        # Pages are globally newest-first.
        assert page1[0]["query"] == "page 6"
        assert page3[0]["query"] == "page 0"
    finally:
        _cleanup(db, research_ids)
        db.close()


def test_history_bounds_rejected():
    assert client.get("/api/research/history?limit=0").status_code == 422
    assert client.get("/api/research/history?limit=101").status_code == 422
    assert client.get("/api/research/history?offset=-1").status_code == 422


def test_history_route_not_research_id():
    res = client.get("/api/research/history")
    assert res.status_code == 200
    assert isinstance(res.json(), list)
    # The dynamic /{research_id} route is registered after /history and still
    # 404s on unknown ids (not shadowed).
    assert client.get("/api/research/does-not-exist").status_code == 404


def test_history_includes_failed_without_result():
    db = SessionLocal()
    research_ids = []
    try:
        research_ids.append(
            _seed(db, query="failed run", status=ResearchStatus.FAILED, with_result=False)
        )
        body = client.get("/api/research/history?limit=10").json()
        assert len(body) == 1
        assert body[0]["query"] == "failed run"
        assert body[0]["status"] == "failed"
    finally:
        _cleanup(db, research_ids)
        db.close()


def test_recent_endpoint_regression():
    res = client.get("/api/research/recent")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    for item in data:
        assert "id" in item
        assert "query" in item
        assert "status" in item
        assert "updated_at" in item


def test_secret_never_exposed_in_history():
    api_key = settings.GEMINI_API_KEY
    news_key = settings.NEWS_API_KEY
    for params in ("", "?limit=25&offset=0", "?limit=1&offset=100"):
        res = client.get(f"/api/research/history{params}")
        assert res.status_code == 200
        if api_key:
            assert api_key not in res.text
        if news_key:
            assert news_key not in res.text
        if params:
            assert isinstance(res.json(), list)