"""
Phase 10 regression tests: the full-dashboard /api/stats aggregation.

Deterministic: seeds Research, ResearchResult, and Source rows directly (no
external/AI calls). Verifies the additive QuickStats fields — insights /
opportunities / risks counts, sentiment mix, research-type mix, source-type
mix — plus failed-research exclusion, legacy-sentiment fallback, an exact
empty-DB state, backward-compatible response shape, and secret non-exposure.

Numeric assertions use deltas from a before-snapshot so they stay exact even
when the shared test database already contains rows from other modules.

Run with: venv/bin/python -m pytest tests/test_phase10_dashboard.py
"""
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import get_settings
from app.core.database import init_db, SessionLocal
from app.models.research import Research, ResearchStatus, ResearchType
from app.models.research_result import ResearchResult
from app.models.source import Source

client = TestClient(app)
settings = get_settings()


def setup_module(module):
    init_db()


def _stats():
    res = client.get("/api/stats")
    assert res.status_code == 200
    return res.json()


def _dict_count(body, dict_key, label):
    return body.get(dict_key, {}).get(label, 0)


def _seed_research(
    db,
    research_type=ResearchType.MARKET_ANALYSIS,
    status=ResearchStatus.COMPLETED,
    result=None,
    sources=None,
):
    research = Research(
        user_id=settings.DEFAULT_USER_ID,
        query="test query",
        research_type=research_type,
        status=status,
    )
    db.add(research)
    db.flush()
    if result is not None:
        db.add(ResearchResult(research_id=research.id, **result))
    for source in sources or []:
        db.add(Source(research_id=research.id, **source))
    db.commit()
    return research.id


def _cleanup(db, research_ids):
    for research_id in research_ids:
        research = db.get(Research, research_id)
        if research:
            db.delete(research)
    db.commit()


def test_empty_dashboard_aggregates_are_zero():
    db = SessionLocal()
    try:
        db.query(Source).delete()
        db.query(ResearchResult).delete()
        db.query(Research).delete()
        db.commit()
    finally:
        db.close()

    body = _stats()
    assert body["researches_completed"] == 0
    assert body["sources_analyzed"] == 0
    assert body["companies_analyzed"] == 0
    assert body["trends_detected"] == 0
    assert body["insights_synthesized"] == 0
    assert body["opportunities_identified"] == 0
    assert body["risks_identified"] == 0
    assert body["sentiment_counts"] == {}
    assert body["research_type_counts"] == {}
    assert body["source_type_counts"] == {}


def test_stats_response_is_backward_compatible_and_additive():
    body = _stats()
    int_keys = (
        "researches_completed",
        "sources_analyzed",
        "companies_analyzed",
        "trends_detected",
        "insights_synthesized",
        "opportunities_identified",
        "risks_identified",
    )
    for key in int_keys:
        assert key in body
        assert isinstance(body[key], int)
    for key in ("sentiment_counts", "research_type_counts", "source_type_counts"):
        assert key in body
        assert isinstance(body[key], dict)


def test_completed_research_counts_insights_opportunities_risks():
    before = _stats()
    db = SessionLocal()
    research_ids = []
    try:
        research_ids.append(
            _seed_research(
                db,
                research_type=ResearchType.MARKET_ANALYSIS,
                result={
                    "summary": "summary",
                    "insights": [{"finding": "a", "evidence": ["src"]}, {"finding": "b", "evidence": []}],
                    "opportunities": [{"opportunity": "o1", "potential_impact": "high"}],
                    "risks": [{"risk": "r1", "severity": "medium", "mitigation": None}],
                    "trends": [{"trend": "t1", "impact": "high", "description": "d"}],
                    "competitors": [{"company": "Acme", "market_share": None, "strengths": [], "weaknesses": []}],
                    "sentiment": {
                        "sentiments": {"overall": {"label": "positive", "evidence": [], "source_types": [], "summary": "s"}}
                    },
                },
                sources=[
                    {"title": "web source", "source_name": "Web", "source_type": "web"},
                    {"title": "news source", "source_name": "News", "source_type": "news"},
                ],
            )
        )
        after = _stats()
        assert after["researches_completed"] == before["researches_completed"] + 1
        assert after["insights_synthesized"] == before["insights_synthesized"] + 2
        assert after["opportunities_identified"] == before["opportunities_identified"] + 1
        assert after["risks_identified"] == before["risks_identified"] + 1
        assert after["trends_detected"] == before["trends_detected"] + 1
        assert _dict_count(after, "sentiment_counts", "positive") == _dict_count(
            before, "sentiment_counts", "positive"
        ) + 1
        assert _dict_count(after, "research_type_counts", "market_analysis") == _dict_count(
            before, "research_type_counts", "market_analysis"
        ) + 1
        assert _dict_count(after, "source_type_counts", "web") == _dict_count(
            before, "source_type_counts", "web"
        ) + 1
        assert _dict_count(after, "source_type_counts", "news") == _dict_count(
            before, "source_type_counts", "news"
        ) + 1
    finally:
        _cleanup(db, research_ids)
        db.close()


def test_sentiment_aggregation_counts_labels():
    before = _stats()
    before_positive = _dict_count(before, "sentiment_counts", "positive")
    before_mixed = _dict_count(before, "sentiment_counts", "mixed")
    researches = [
        {"status": ResearchStatus.COMPLETED, "research_type": ResearchType.MARKET_ANALYSIS,
         "result": {"sentiment": {"sentiments": {"overall": {"label": "positive"}}}}},
        {"status": ResearchStatus.COMPLETED, "research_type": ResearchType.PRODUCT_ANALYSIS,
         "result": {"sentiment": {"sentiments": {"overall": {"label": "mixed"}}}}},
    ]
    db = SessionLocal()
    research_ids = []
    try:
        for r in researches:
            research_ids.append(
                _seed_research(
                    db,
                    research_type=r["research_type"],
                    status=r["status"],
                    result=r["result"],
                )
            )
        after = _stats()
        assert _dict_count(after, "sentiment_counts", "positive") == before_positive + 1
        assert _dict_count(after, "sentiment_counts", "mixed") == before_mixed + 1
    finally:
        _cleanup(db, research_ids)
        db.close()


def test_legacy_missing_sentiment_falls_back_to_unavailable():
    before = _stats()
    before_unavailable = _dict_count(before, "sentiment_counts", "unavailable")
    db = SessionLocal()
    research_ids = []
    try:
        research_ids.append(
            _seed_research(
                db,
                result={
                    "sentiment": {"market_overview": "no sentiments key at all", "conclusion": "c"},
                    "insights": [],
                },
            )
        )
        research_ids.append(
            _seed_research(
                db,
                research_type=ResearchType.INDUSTRY_TRENDS,
                result={"sentiment": {"sentiments": {"overall": {}}}},
            )
        )
        after = _stats()
        assert _dict_count(after, "sentiment_counts", "unavailable") == before_unavailable + 2
    finally:
        _cleanup(db, research_ids)
        db.close()


def test_research_type_aggregation():
    before = _stats()
    before_competitor = _dict_count(before, "research_type_counts", "competitor_analysis")
    before_product = _dict_count(before, "research_type_counts", "product_analysis")
    db = SessionLocal()
    research_ids = []
    try:
        research_ids.append(
            _seed_research(db, research_type=ResearchType.COMPETITOR_ANALYSIS, result=None)
        )
        research_ids.append(_seed_research(db, research_type=ResearchType.PRODUCT_ANALYSIS, result=None))
        after = _stats()
        assert _dict_count(after, "research_type_counts", "competitor_analysis") == before_competitor + 1
        assert _dict_count(after, "research_type_counts", "product_analysis") == before_product + 1
    finally:
        _cleanup(db, research_ids)
        db.close()


def test_source_type_aggregation():
    before = _stats()
    before_web = _dict_count(before, "source_type_counts", "web")
    before_news = _dict_count(before, "source_type_counts", "news")
    before_document = _dict_count(before, "source_type_counts", "document")
    db = SessionLocal()
    research_ids = []
    try:
        research_ids.append(
            _seed_research(
                db,
                sources=[
                    {"title": "w", "source_name": "W", "source_type": "web"},
                    {"title": "n", "source_name": "N", "source_type": "news"},
                    {"title": "d", "source_name": "D", "source_type": "document"},
                ],
            )
        )
        after = _stats()
        assert _dict_count(after, "source_type_counts", "web") == before_web + 1
        assert _dict_count(after, "source_type_counts", "news") == before_news + 1
        assert _dict_count(after, "source_type_counts", "document") == before_document + 1
    finally:
        _cleanup(db, research_ids)
        db.close()


def test_failed_research_excluded_from_all_aggregates():
    before = _stats()
    db = SessionLocal()
    research_ids = []
    try:
        research_ids.append(
            _seed_research(
                db,
                research_type=ResearchType.COMPETITOR_ANALYSIS,
                status=ResearchStatus.FAILED,
                result=None,
            )
        )
        after = _stats()
        assert after["researches_completed"] == before["researches_completed"]
        assert after["insights_synthesized"] == before["insights_synthesized"]
        assert after["opportunities_identified"] == before["opportunities_identified"]
        assert after["risks_identified"] == before["risks_identified"]
        assert after["sources_analyzed"] == before["sources_analyzed"]
        assert _dict_count(after, "research_type_counts", "competitor_analysis") == _dict_count(
            before, "research_type_counts", "competitor_analysis"
        )
    finally:
        _cleanup(db, research_ids)
        db.close()


def test_secret_never_exposed_in_stats():
    api_key = settings.GEMINI_API_KEY
    news_key = settings.NEWS_API_KEY
    res = client.get("/api/stats")
    assert res.status_code == 200
    if api_key:
        assert api_key not in res.text
    if news_key:
        assert news_key not in res.text
    assert "insights_synthesized" in res.json()