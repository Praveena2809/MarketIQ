"""
Step 5 news-research tests: provider parsing/provenance, query handling, recency,
graceful unavailability, evidence normalization, source persistence, research
pipeline integration, API regression, and secret non-exposure.

Deterministic: every external call (provider HTTP, Gemini) is mocked. News
articles in fixtures carry explicit fake-but-real-shaped URLs so assertions can
verify provenance is preserved exactly, never fabricated.
"""
import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import get_settings
from app.core.database import init_db, SessionLocal
from app.models.research import Research, ResearchStatus
from app.models.research_result import ResearchResult
from app.models.source import Source
from app.agents.news_research_agent import NewsResearchAgent
from app.agents.research_agent import ResearchAgent
from app.services.llm import get_llm_service
from app.services.news.news_provider import NewsAPIProvider, get_news_provider, _parse_published_at
from app.services.rag import get_rag_service
from app.services.research.evidence import Evidence
from app.services.research.source_tracker import SourceTracker
from app.services.research.synthesis import get_synthesis_service
from app.services.research.research_engine import get_research_engine
from app.services.research.web_search import get_web_search_service

client = TestClient(app)
settings = get_settings()

SAMPLE_PAYLOAD = {
    "status": "ok",
    "totalResults": 3,
    "articles": [
        {
            "source": {"id": "reuters", "name": "Reuters"},
            "author": "Fake Author",
            "title": "India EV sales hit record in 2026",
            "description": "Electric vehicle registrations in India grew 40 percent year on year.",
            "url": "https://newsapi.test/articles/india-ev-sales",
            "urlToImage": "https://newsapi.test/img/india-ev.jpg",
            "publishedAt": "2026-09-10T08:30:00Z",
            "content": "Electric vehicle registrations grew 40 percent...",
        },
        {
            "source": {"id": None, "name": "Economic Times"},
            "author": "",
            "title": "Tata Motors expands EV lineup",
            "description": "New models are planned for next year.",
            "url": "https://newsapi.test/articles/tata-motors-ev",
            "publishedAt": "2026-09-08T11:00:00Z",
        },
        {
            "source": {"name": "Local Gazette"},
            "author": "",
            "title": "Article without URL must never become evidence",
            "description": "This item has no URL and must be dropped.",
            "url": "",
            "publishedAt": "2026-09-01T10:00:00Z",
        },
    ],
}

FAKE_NEWS_KEY = "test-secret-news-key"


def _valid_synthesis_json(evidence_ids=None):
    evidence_ids = evidence_ids or ["web_1", "doc_1"]
    return json.dumps({
        "executive_summary": "The enterprise AI market is expanding quickly.",
        "key_findings": [
            {"finding": "AI adoption is growing.", "evidence": evidence_ids}
        ],
        "market_overview": "A detailed overview grounded in evidence.",
        "trends": [{"trend": "Agentic AI", "impact": "high", "description": "Rising interest."}],
        "opportunities": [{"opportunity": "Automation", "potential_impact": "high"}],
        "risks": [{"risk": "Regulation", "severity": "medium", "mitigation": "Monitor."}],
        "competitors": [{"company": "Acme Corp", "market_share": "N/A", "strengths": ["X"], "weaknesses": ["Y"]}],
        "conclusion": "A supported conclusion.",
        "source_ids": evidence_ids,
    })


def _cleanup_research(db, research_id):
    research = db.get(Research, research_id)
    if research:
        db.delete(research)
        db.commit()


def setup_module(module):
    init_db()


# --------------------------------------------------------------------------
# Phase 1-3 regressions folded into Step 5
# --------------------------------------------------------------------------
def test_phase1_2_3_regressions():
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"
    assert res.json()["database"] == "connected"

    res = client.get("/api/stats")
    assert res.status_code == 200
    assert "researches_completed" in res.json()

    res = client.get("/api/research/recent")
    assert res.status_code == 200
    assert isinstance(res.json(), list)


# --------------------------------------------------------------------------
# Provider response parsing & provenance
# --------------------------------------------------------------------------
def test_provider_parses_real_articles(monkeypatch):
    monkeypatch.setattr(settings, "NEWS_API_KEY", FAKE_NEWS_KEY)
    provider = NewsAPIProvider()
    monkeypatch.setattr(provider, "_get_json", lambda params: SAMPLE_PAYLOAD)

    articles, warning = provider.fetch_recent("electric vehicle India")

    assert warning == ""
    # The no-URL article is dropped - provenance is required.
    assert len(articles) == 2
    assert articles[0].title == "India EV sales hit record in 2026"
    assert articles[0].url == "https://newsapi.test/articles/india-ev-sales"
    assert articles[0].source_name == "Reuters"
    assert articles[0].description == "Electric vehicle registrations in India grew 40 percent year on year."
    assert articles[0].published_at is not None
    assert articles[0].published_at.tzinfo is not None
    assert articles[1].source_name == "Economic Times"


def test_provider_drops_articles_without_url(monkeypatch):
    monkeypatch.setattr(settings, "NEWS_API_KEY", FAKE_NEWS_KEY)
    provider = NewsAPIProvider()
    monkeypatch.setattr(provider, "_get_json", lambda params: SAMPLE_PAYLOAD)
    articles, _ = provider.fetch_recent("q")
    urls = [a.url for a in articles]
    assert "" not in urls
    assert "https://newsapi.test/articles/india-ev-sales" in urls


def test_provider_non_ok_status_returns_empty(monkeypatch):
    monkeypatch.setattr(settings, "NEWS_API_KEY", FAKE_NEWS_KEY)
    provider = NewsAPIProvider()
    monkeypatch.setattr(provider, "_get_json", lambda params: {
        "status": "error", "code": "unexpectedError", "message": "provider hiccup"
    })
    articles, warning = provider.fetch_recent("q")
    assert articles == []
    assert warning


def test_provider_requires_api_key(monkeypatch):
    monkeypatch.setattr(settings, "NEWS_API_KEY", "")
    provider = NewsAPIProvider()
    articles, warning = provider.fetch_recent("electric vehicle India")
    assert articles == []
    assert "NEWS_API_KEY" in warning
    assert "not configured" in warning.lower()


def test_provider_quota_failure_graceful(monkeypatch):
    monkeypatch.setattr(settings, "NEWS_API_KEY", FAKE_NEWS_KEY)
    provider = NewsAPIProvider()

    def boom(params):
        raise ValueError("News provider returned HTTP 429: Rate limit exceeded")

    monkeypatch.setattr(provider, "_get_json", boom)
    articles, warning = provider.fetch_recent("q")
    assert articles == []
    assert "429" in warning or "Rate limit" in warning


# --------------------------------------------------------------------------
# Publication date handling
# --------------------------------------------------------------------------
def test_published_at_parsing():
    assert _parse_published_at("2026-09-10T08:30:00Z") is not None
    assert _parse_published_at("2026-09-10T08:30:00+05:30") is not None
    assert _parse_published_at("not-a-date") is None
    assert _parse_published_at("") is None
    assert _parse_published_at(None) is None


def test_malformed_published_date_persists_as_none(monkeypatch):
    monkeypatch.setattr(settings, "NEWS_API_KEY", FAKE_NEWS_KEY)
    payload = json.loads(json.dumps(SAMPLE_PAYLOAD))
    payload["articles"][0]["publishedAt"] = "bogus-date"
    provider = NewsAPIProvider()
    monkeypatch.setattr(provider, "_get_json", lambda params: payload)
    articles, _ = provider.fetch_recent("q")
    assert articles[0].published_at is None


# --------------------------------------------------------------------------
# Query handling & recency
# --------------------------------------------------------------------------
def test_news_agent_derives_focused_query_via_llm(monkeypatch):
    monkeypatch.setattr(settings, "NEWS_API_KEY", FAKE_NEWS_KEY)
    llm = get_llm_service()
    monkeypatch.setattr(llm, "generate_text", lambda prompt, **kw: "electric vehicle India")

    captured = {}
    provider = get_news_provider()

    def fake_fetch(q):
        captured["q"] = q
        return ([], "")  # empty is fine for the query-probe

    monkeypatch.setattr(provider, "fetch_recent", fake_fetch)
    agent = NewsResearchAgent()
    _, _ = agent.gather_news_evidence("Analyze the Indian electric vehicle market for the next 12 months")
    assert captured["q"] == "electric vehicle India"


def test_news_query_fallback_without_llm(monkeypatch):
    monkeypatch.setattr(settings, "NEWS_API_KEY", FAKE_NEWS_KEY)
    llm = get_llm_service()
    monkeypatch.setattr(llm, "is_configured", lambda: False)

    captured = {}
    provider = get_news_provider()

    def fake_fetch(q):
        captured["q"] = q
        return ([], "")

    monkeypatch.setattr(provider, "fetch_recent", fake_fetch)
    agent = NewsResearchAgent()
    agent.gather_news_evidence("  Analyze \n the Indian   electric vehicle market  ")
    assert captured["q"]
    assert "\n" not in captured["q"]
    assert "  " not in captured["q"].replace("Analyze", "Analyze")  # whitespace collapsed


def test_focused_query_wrappers_stripped(monkeypatch):
    monkeypatch.setattr(settings, "NEWS_API_KEY", FAKE_NEWS_KEY)
    llm = get_llm_service()
    monkeypatch.setattr(llm, "generate_text", lambda prompt, **kw: 'Search query: "India EV market"')

    captured = {}
    provider = get_news_provider()
    monkeypatch.setattr(provider, "fetch_recent", lambda q: (captured.update(q=q) or [], ""))
    # fetch_recent returns a tuple; use a small wrapper instead
    monkeypatch.setattr(provider, "fetch_recent", (lambda q: ([], "")) if False else None)

    def fake_fetch(q):
        captured["q"] = q
        return ([], "")

    monkeypatch.setattr(provider, "fetch_recent", fake_fetch)
    agent = NewsResearchAgent()
    agent.gather_news_evidence("India electric vehicle market")
    assert captured["q"] == "India EV market"


def test_news_recency_and_limits_in_request_params(monkeypatch):
    monkeypatch.setattr(settings, "NEWS_API_KEY", FAKE_NEWS_KEY)
    provider = NewsAPIProvider()
    captured = {}

    def fake_get(params):
        captured.update(params)
        return SAMPLE_PAYLOAD

    monkeypatch.setattr(provider, "_get_json", fake_get)
    provider.fetch_recent("electric vehicle India")

    assert captured["q"] == "electric vehicle India"
    assert captured["sortBy"] == "publishedAt"
    assert captured["language"] == settings.NEWS_LANGUAGE
    assert captured["pageSize"] == str(settings.NEWS_RESULTS_PER_QUERY)
    assert captured["from"]
    assert len(captured["from"]) == 10  # YYYY-MM-DD


# --------------------------------------------------------------------------
# Evidence normalization (real metadata only, never fabricated)
# --------------------------------------------------------------------------
def test_news_evidence_normalization_preserves_provenance(monkeypatch):
    monkeypatch.setattr(settings, "NEWS_API_KEY", FAKE_NEWS_KEY)
    provider = get_news_provider()
    monkeypatch.setattr(provider, "_get_json", lambda params: SAMPLE_PAYLOAD)

    agent = NewsResearchAgent()
    evidence, warning = agent.gather_news_evidence("Analyze the Indian electric vehicle market")

    assert warning is None
    # No-URL article removed; bounded to config max.
    assert len(evidence) <= settings.NEWS_RESULTS_PER_QUERY
    assert len(evidence) == 2

    first = evidence[0]
    assert first.evidence_id == "news_1"
    assert first.source_type == "news"
    # Provenance must match the provider exactly - no invented title/url.
    assert first.title == "India EV sales hit record in 2026"
    assert first.url == "https://newsapi.test/articles/india-ev-sales"
    assert first.publisher == "Reuters"
    assert first.published_at == "2026-09-10T08:30:00+00:00"
    assert first.content == "Electric vehicle registrations in India grew 40 percent year on year."

    second = evidence[1]
    assert second.publisher == "Economic Times"
    assert second.url == "https://newsapi.test/articles/tata-motors-ev"


def test_news_agent_handles_provider_failure_honestly(monkeypatch):
    monkeypatch.setattr(settings, "NEWS_API_KEY", FAKE_NEWS_KEY)
    provider = get_news_provider()
    monkeypatch.setattr(provider, "fetch_recent", lambda q: ([], "No recent news articles found for this query."))

    agent = NewsResearchAgent()
    evidence, warning = agent.gather_news_evidence("electric vehicles india")
    assert evidence == []
    assert warning == "No recent news articles found for this query."


def test_news_agent_missing_key_returns_no_evidence(monkeypatch):
    monkeypatch.setattr(settings, "NEWS_API_KEY", "")
    agent = NewsResearchAgent()
    evidence, warning = agent.gather_news_evidence("Analyze the Indian electric vehicle market")
    assert evidence == []
    assert warning is not None
    assert "not configured" in warning.lower()


# --------------------------------------------------------------------------
# Secret non-exposure
# --------------------------------------------------------------------------
def test_news_api_key_never_leaks_in_warning(monkeypatch):
    monkeypatch.setattr(settings, "NEWS_API_KEY", FAKE_NEWS_KEY)
    provider = NewsAPIProvider()

    def boom(params):
        raise ValueError(f"connection failed using key {FAKE_NEWS_KEY}")

    monkeypatch.setattr(provider, "_get_json", boom)
    articles, warning = provider.fetch_recent("q")
    assert articles == []
    assert FAKE_NEWS_KEY not in warning
    assert "[REDACTED]" in warning


def test_sanitize_redacts_key(monkeypatch):
    monkeypatch.setattr(settings, "NEWS_API_KEY", FAKE_NEWS_KEY)
    provider = NewsAPIProvider()
    cleaned = provider._sanitize(f"quota exceeded for {FAKE_NEWS_KEY} on host")
    assert FAKE_NEWS_KEY not in cleaned
    assert "[REDACTED]" in cleaned


# --------------------------------------------------------------------------
# Source persistence
# --------------------------------------------------------------------------
def test_news_source_persistence():
    db = SessionLocal()
    research = Research(user_id=settings.DEFAULT_USER_ID, query="q", status=ResearchStatus.RUNNING)
    db.add(research)
    db.commit()
    db.refresh(research)
    try:
        evidence = Evidence(
            evidence_id="news_1",
            source_type="news",
            title="India EV sales hit record in 2026",
            content="Electric vehicle registrations grew.",
            url="https://newsapi.test/articles/india-ev-sales",
            publisher="Reuters",
            published_at="2026-09-10T08:30:00Z",
            relevance_score=0.95,
        )
        saved = SourceTracker.save_sources(db, research.id, [evidence])
        assert len(saved) == 1
        row = saved[0]
        assert row.source_type == "news"
        assert row.url == "https://newsapi.test/articles/india-ev-sales"
        assert row.source_name == "Reuters"
        assert row.title == "India EV sales hit record in 2026"
        assert row.published_at is not None
        assert row.is_mock is False
        assert row.relevance == 0.95
    finally:
        _cleanup_research(db, research.id)
        db.close()


def test_news_source_url_required_by_tracker():
    db = SessionLocal()
    research = Research(user_id=settings.DEFAULT_USER_ID, query="q", status=ResearchStatus.RUNNING)
    db.add(research)
    db.commit()
    db.refresh(research)
    try:
        fake = Evidence(
            evidence_id="news_fake",
            source_type="news",
            title="Fabricated headline",
            content="x",
            url=None,
            publisher="Fake Publisher",
        )
        saved = SourceTracker.save_sources(db, research.id, [fake])
        assert saved == []
    finally:
        _cleanup_research(db, research.id)
        db.close()


# --------------------------------------------------------------------------
# Synthesis integration
# --------------------------------------------------------------------------
def test_synthesis_prompt_includes_news_evidence(monkeypatch):
    captured = {}

    def fake_generate_json(prompt, **kwargs):
        captured["prompt"] = prompt
        return _valid_synthesis_json(["web_1", "doc_1"])

    llm = get_llm_service()
    monkeypatch.setattr(llm, "generate_json", fake_generate_json)

    service = get_synthesis_service()
    news = [
        Evidence(
            evidence_id="news_1",
            source_type="news",
            title="India EV sales hit record",
            content="Electric vehicle registrations grew.",
            url="https://newsapi.test/articles/india-ev-sales",
            publisher="Reuters",
            published_at="2026-09-10T08:30:00Z",
        )
    ]
    report = service.synthesize("q", [], [], news)

    assert "NEWS EVIDENCE" in captured["prompt"]
    assert "news_1" in captured["prompt"]
    assert "Reuters" in captured["prompt"]
    assert "https://newsapi.test/articles/india-ev-sales" in captured["prompt"]
    assert report is not None


def test_synthesis_fallback_counts_news_evidence(monkeypatch):
    llm = get_llm_service()
    monkeypatch.setattr(llm, "generate_json", lambda prompt, **kw: "this is not json")

    service = get_synthesis_service()
    news = [
        Evidence(
            evidence_id="news_1",
            source_type="news",
            title="T",
            url="https://newsapi.test/a",
            content="c",
        )
    ]
    report = service.synthesize("q", [], [], news)
    assert "news_1" in report.source_ids
    assert report.executive_summary


# --------------------------------------------------------------------------
# Research pipeline integration
# --------------------------------------------------------------------------
def _patch_research_pipeline(monkeypatch):
    ws = get_web_search_service()
    monkeypatch.setattr(
        ws,
        "search_web",
        lambda query: (
            [Evidence(evidence_id="web_1", source_type="web", title="Web Source",
                      url="https://website.example.com/x", content="web content")],
            ["query"],
            "",
        ),
    )

    rag = get_rag_service()
    monkeypatch.setattr(
        rag,
        "retrieve",
        lambda query, top_k=5, document_ids=None: [
            {"chunk_id": "d_0", "chunk_text": "Doc chunk content.", "document_id": "doc_x",
             "chunk_index": 0, "filename": "docx.txt", "file_type": "txt", "relevance_score": 0.9}
        ],
    )

    llm = get_llm_service()
    monkeypatch.setattr(llm, "generate_text", lambda prompt, **kw: "electric vehicle India")
    monkeypatch.setattr(llm, "generate_json", lambda prompt, **kw: _valid_synthesis_json(["web_1", "doc_1", "news_1"]))

    monkeypatch.setattr(settings, "NEWS_API_KEY", FAKE_NEWS_KEY)
    provider = get_news_provider()
    monkeypatch.setattr(provider, "_get_json", lambda params: SAMPLE_PAYLOAD)


def test_research_engine_includes_news_sources(monkeypatch):
    _patch_research_pipeline(monkeypatch)

    db = SessionLocal()
    engine = get_research_engine()
    record = engine.run_research(
        db,
        user_id=settings.DEFAULT_USER_ID,
        query="Analyze the Indian electric vehicle market",
        research_type_str="market_analysis",
    )
    try:
        assert record.status == ResearchStatus.COMPLETED
        sources = db.query(Source).filter(Source.research_id == record.id).all()
        types = {s.source_type for s in sources}
        assert types == {"web", "document", "news"}

        news_rows = [s for s in sources if s.source_type == "news"]
        assert len(news_rows) == 2
        assert news_rows[0].url == "https://newsapi.test/articles/india-ev-sales"
        assert news_rows[0].published_at is not None

        result = db.get(ResearchResult, record.result.id) if record.result else None
        assert result is not None
        # News sources are persisted with real provenance (title/url/date).
        assert any(s.published_at is not None for s in news_rows)
    finally:
        _cleanup_research(db, record.id)
        db.close()


def test_news_warning_propagates_when_unavailable(monkeypatch):
    _patch_research_pipeline(monkeypatch)
    provider = get_news_provider()
    monkeypatch.setattr(provider, "fetch_recent", lambda q: ([], "News research unavailable (quota)."))

    db = SessionLocal()
    engine = get_research_engine()
    record = engine.run_research(
        db,
        user_id=settings.DEFAULT_USER_ID,
        query="Analyze the Indian electric vehicle market",
    )
    try:
        assert record.status == ResearchStatus.COMPLETED
        sources = db.query(Source).filter(Source.research_id == record.id).all()
        types = {s.source_type for s in sources}
        assert "news" not in types  # no fabricated news persisted
        assert "web" in types and "document" in types
    finally:
        _cleanup_research(db, record.id)
        db.close()


def test_research_api_regression_with_news(monkeypatch):
    _patch_research_pipeline(monkeypatch)

    post = client.post("/api/research", json={"query": "Analyze the Indian electric vehicle market"})
    assert post.status_code == 201, post.text
    body = post.json()
    research_id = body["research_id"]
    try:
        assert body["status"] == "completed"
        assert body["result"]["executive_summary"]
        types = {s["source_type"] for s in body["sources"]}
        assert types == {"web", "document", "news"}

        get = client.get(f"/api/research/{research_id}")
        assert get.status_code == 200
        assert get.json()["research_id"] == research_id
        # The synthesized result must reference news evidence distinctly.
        news_ids = [s["id"] for s in get.json()["sources"] if s["source_type"] == "news"]
        assert news_ids
    finally:
        db = SessionLocal()
        try:
            _cleanup_research(db, research_id)
        finally:
            db.close()


def test_secrets_never_exposed_with_news_configured(monkeypatch):
    _patch_research_pipeline(monkeypatch)
    assert settings.NEWS_API_KEY == FAKE_NEWS_KEY

    for path in ("/api/health", "/api/stats", "/api/research/recent"):
        res = client.get(path)
        assert res.status_code == 200
        assert FAKE_NEWS_KEY not in res.text

    post = client.post("/api/research", json={"query": "electric vehicle market"})
    assert post.status_code == 201, post.text
    body = post.json()
    try:
        assert FAKE_NEWS_KEY not in post.text
        get_res = client.get(f"/api/research/{body['research_id']}")
        assert FAKE_NEWS_KEY not in get_res.text
    finally:
        db = SessionLocal()
        try:
            _cleanup_research(db, body["research_id"])
        finally:
            db.close()