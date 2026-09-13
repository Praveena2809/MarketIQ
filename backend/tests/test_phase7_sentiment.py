"""
Step 7 sentiment-research tests: categorical + qualitative sentiment driven by
the existing evidence pool, strict evidence-containment, server-side
source_type derivation, exactly-one-Gemini-call budget, zero additional
web/news/RAG gathering, per-company sentiment for identified competitors,
graceful Gemini/quota/malformed-JSON failure, persistence/back-compat, API
round-trips, and secret non-exposure.

Deterministic: every external call (Gemini, web grounding, RAG, news provider)
is mocked. Call-count spies verify the sentiment pass adds exactly ONE Gemini
generate_json call and zero other external calls.
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
from app.agents.research_agent import ResearchAgent
from app.agents.sentiment_research_agent import SentimentResearchAgent
from app.services.llm import get_llm_service
from app.services.news.news_provider import get_news_provider
from app.services.rag import get_rag_service
from app.services.research.evidence import Evidence
from app.services.research.sentiment_analysis import (
    VALID_SENTIMENT_LABELS,
    SENTIMENT_SYSTEM_INSTRUCTION,
    SENTIMENT_JSON_SCHEMA,
    SentimentAnalysisService,
)
from app.services.research.web_search import get_web_search_service
from app.services.research.research_engine import get_research_engine

client = TestClient(app)
settings = get_settings()

FAKE_NEWS_KEY = "test-secret-news-key"

SAMPLE_PAYLOAD = {
    "status": "ok",
    "totalResults": 2,
    "articles": [
        {
            "source": {"id": "reuters", "name": "Reuters"},
            "author": "Fake Author",
            "title": "India EV sales hit record in 2026",
            "description": "Electric vehicle registrations in India grew 40 percent year on year.",
            "url": "https://newsapi.test/articles/india-ev-sales",
            "publishedAt": "2026-09-10T08:30:00Z",
            "content": "Electric vehicle registrations grew 40 percent...",
        },
        {
            "source": {"name": "Economic Times"},
            "author": "",
            "title": "Tata Motors expands EV lineup",
            "description": "New models are planned for next year.",
            "url": "https://newsapi.test/articles/tata-motors-ev",
            "publishedAt": "2026-09-08T11:00:00Z",
        },
    ],
}


def _nav_evidence():
    """Real-shaped web/document/news evidence pool covering two companies."""
    eta = [
        Evidence(
            evidence_id="web_1",
            source_type="web",
            title="Tata Motors EV Overview",
            url="https://example.com/tata-ev",
            content="Tata Motors is accelerating its electric vehicle lineup in India.",
        ),
        Evidence(
            evidence_id="doc_1",
            source_type="document",
            title="Document Source: ev_report.txt",
            content="Tata Motors and Ola Electric are among the leading EV makers.",
            filename="ev_report.txt",
            document_id="d1",
            chunk_index=0,
        ),
        Evidence(
            evidence_id="news_2",
            source_type="news",
            title="Tata Motors expands EV lineup",
            url="https://newsapi.test/articles/tata-motors-ev",
            content="New models are planned for next year.",
            publisher="Economic Times",
            published_at="2026-09-08T11:00:00Z",
        ),
        Evidence(
            evidence_id="comp_tata-motors_news_1",
            source_type="news",
            title="India EV sales hit record in 2026",
            url="https://newsapi.test/articles/india-ev-sales",
            content="Electric vehicle registrations grew 40 percent year on year.",
            publisher="Reuters",
            published_at="2026-09-10T08:30:00Z",
        ),
    ]
    return eta


def _sentiment_json():
    return json.dumps({
        "overall": {
            "label": "mixed",
            "evidence": ["web_1", "news_2"],
            "summary": "Mixed near-term outlook with positive momentum.",
        },
        "entities": [
            {
                "entity": "Tata Motors",
                "label": "positive",
                "evidence": ["comp_tata-motors_news_1", "news_2"],
                "summary": "Positive outlook driven by EV expansion.",
            },
            {
                "entity": "FakeCorp Inc",  # never identified -> must be dropped
                "label": "negative",
                "evidence": ["fake_9"],  # fabricated id -> never verified
                "summary": "Fabricated sentiment.",
            },
        ],
    })


def _valid_synthesis_json(evidence_ids=None):
    evidence_ids = evidence_ids or ["web_1", "news_1"]
    return json.dumps({
        "executive_summary": "The Indian EV market is expanding quickly.",
        "key_findings": [
            {"finding": "EV adoption is growing.", "evidence": evidence_ids}
        ],
        "market_overview": "A detailed overview grounded in evidence.",
        "trends": [{"trend": "EV adoption", "impact": "high", "description": "Rising interest."}],
        "opportunities": [{"opportunity": "Automation", "potential_impact": "high"}],
        "risks": [{"risk": "Regulation", "severity": "medium", "mitigation": "Monitor."}],
        "competitors": [
            {
                "company": "Tata Motors",
                "market_share": "N/A",
                "strengths": ["Expanding EV lineup"],
                "weaknesses": [],
                "evidence": ["comp_tata-motors_news_1"],
            }
        ],
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


def _patch_sentiment_pipeline(monkeypatch, sentiment_payload=None, sentiment_error=None):
    """Mocks every external service. generate_json dispatches on the agent:
    identification, sentiment, or synthesis. Returns a call counter dict."""
    counters = {"web": 0, "news_get": 0, "rag": 0, "gen_json": 0, "gen_text": 0}

    ws = get_web_search_service()

    def fake_search(query):
        counters["web"] += 1
        return ([_nav_evidence()[0]], ["query"], "")

    monkeypatch.setattr(ws, "search_web", fake_search)

    rag = get_rag_service()

    def fake_retrieve(query, top_k=5, document_ids=None):
        counters["rag"] += 1
        return [{"chunk_id": "d_0",
                 "chunk_text": "Tata Motors and Ola Electric are among the leading EV makers.",
                 "document_id": "d1", "chunk_index": 0, "filename": "ev_report.txt",
                 "file_type": "txt", "relevance_score": 0.9}]

    monkeypatch.setattr(rag, "retrieve", fake_retrieve)

    llm = get_llm_service()

    def fake_generate_text(prompt, **kw):
        counters["gen_text"] += 1
        return "electric vehicle India"

    monkeypatch.setattr(llm, "generate_text", fake_generate_text)

    def fake_generate_json(prompt, **kw):
        counters["gen_json"] += 1
        si = kw.get("system_instruction") or ""
        if "Competitor Identification Engine" in si:
            return '{"competitors": [{"name": "Tata Motors"}]}'
        if "Sentiment Analysis Engine" in si:
            if sentiment_error is not None:
                raise sentiment_error
            return sentiment_payload if sentiment_payload is not None else _sentiment_json()
        return _valid_synthesis_json(evidence_ids=["web_1", "doc_1", "news_1", "news_2"])

    monkeypatch.setattr(llm, "generate_json", fake_generate_json)

    monkeypatch.setattr(settings, "NEWS_API_KEY", FAKE_NEWS_KEY)
    monkeypatch.setattr(settings, "COMPETITOR_FOCUSED_WEB_SEARCH", False)
    provider = get_news_provider()

    def fake_get_json(params):
        counters["news_get"] += 1
        return SAMPLE_PAYLOAD

    monkeypatch.setattr(provider, "_get_json", fake_get_json)
    return counters


# --------------------------------------------------------------------------
# Phase 1-6 regression smoke
# --------------------------------------------------------------------------
def test_phase1_6_regressions():
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"

    res = client.get("/api/stats")
    assert res.status_code == 200
    assert "researches_completed" in res.json()

    res = client.get("/api/research/recent")
    assert res.status_code == 200
    assert isinstance(res.json(), list)


# --------------------------------------------------------------------------
# Sentiment service: prompt, schema, call budget
# --------------------------------------------------------------------------
def test_sentiment_prompt_includes_pool_and_entities(monkeypatch):
    captured = {}
    llm = get_llm_service()

    def fake_generate_json(prompt, **kw):
        captured["prompt"] = prompt
        captured["schema"] = kw.get("schema")
        captured["si"] = kw.get("system_instruction")
        return _sentiment_json()

    monkeypatch.setattr(llm, "generate_json", fake_generate_json)

    svc = SentimentAnalysisService()
    schema, warning = svc.analyze(
        "Analyze the Indian EV market",
        _nav_evidence(),
        eligible_entities=["Tata Motors", "Ola Electric"],
    )

    assert warning is None
    assert schema.overall.label == "mixed"
    assert schema.entities[0].entity == "Tata Motors"

    prompt = captured["prompt"]
    assert "ENTITIES TO SCORE: Tata Motors, Ola Electric" in prompt
    assert "web_1" in prompt
    assert "comp_tata-motors_news_1" in prompt
    assert "https://example.com/tata-ev" in prompt
    # Structured-output schema is passed for deterministic JSON.
    assert isinstance(captured["schema"], dict)
    assert captured["schema"]["required"] == ["overall"]
    assert "Sentiment Analysis Engine" in (captured["si"] or "")


def test_sentiment_is_single_llm_call_no_external_calls(monkeypatch):
    calls = {"gen_json": 0, "web": 0, "news": 0, "rag": 0}
    llm = get_llm_service()
    monkeypatch.setattr(llm, "generate_json", lambda prompt, **kw: (
        calls.__setitem__("gen_json", calls["gen_json"] + 1) or _sentiment_json()
    ))
    ws = get_web_search_service()
    monkeypatch.setattr(ws, "search_web", lambda q: (
        calls.__setitem__("web", calls["web"] + 1) or ([], [], "")))
    provider = get_news_provider()
    monkeypatch.setattr(provider, "fetch_recent", lambda q: (
        calls.__setitem__("news", calls["news"] + 1) or ([], "")))
    rag = get_rag_service()
    monkeypatch.setattr(rag, "retrieve", lambda query, top_k=5, document_ids=None: (
        calls.__setitem__("rag", calls["rag"] + 1) or []))

    svc = SentimentAnalysisService()
    schema, _ = svc.analyze("Analyze the Indian EV market", _nav_evidence(),
                            eligible_entities=["Tata Motors"])
    assert schema.overall.label == "mixed"
    assert calls["gen_json"] == 1
    assert calls["web"] == 0 and calls["news"] == 0 and calls["rag"] == 0


def test_sentiment_empty_evidence_returns_early(monkeypatch):
    gen_calls = {"n": 0}
    llm = get_llm_service()
    monkeypatch.setattr(llm, "generate_json", lambda prompt, **kw: (
        gen_calls.__setitem__("n", gen_calls["n"] + 1) or "{}"))

    svc = SentimentAnalysisService()
    schema, warning = svc.analyze("q", [])
    assert gen_calls["n"] == 0
    assert schema.overall.label == "unavailable"
    assert schema.overall.evidence == []
    assert warning and "insufficient evidence" in warning.lower()


def test_sentiment_llm_failure_fails_soft(monkeypatch):
    llm = get_llm_service()
    monkeypatch.setattr(llm, "generate_json",
                        lambda prompt, **kw: (_ for _ in ()).throw(RuntimeError("boom")))
    svc = SentimentAnalysisService()
    schema, warning = svc.analyze("q", _nav_evidence())
    assert schema.overall.label == "unavailable"
    assert schema.entities == []
    assert warning and "Sentiment analysis unavailable" in warning


def test_sentiment_quota_error_is_not_rewritten(monkeypatch):
    llm = get_llm_service()
    monkeypatch.setattr(llm, "generate_json", lambda prompt, **kw: (
        (_ for _ in ()).throw(Exception("429 RESOURCE_EXHAUSTED, quota"))))
    svc = SentimentAnalysisService()
    schema, warning = svc.analyze("q", _nav_evidence())
    assert schema.overall.label == "unavailable"
    assert "unavailable" in schema.overall.label
    # The quota error is surfaced honestly, not hidden or rewritten.
    assert "quota" in warning.lower()
    assert "RESOURCE_EXHAUSTED" in warning


def test_sentiment_malformed_json_fails_soft(monkeypatch):
    llm = get_llm_service()
    monkeypatch.setattr(llm, "generate_json", lambda prompt, **kw: "this is not json")
    svc = SentimentAnalysisService()
    schema, warning = svc.analyze("q", _nav_evidence())
    assert schema.overall.label == "unavailable"
    assert warning and "malformed" in warning


# --------------------------------------------------------------------------
# Containment, source-type derivation, labels, entities
# --------------------------------------------------------------------------
def test_sentiment_containment_drops_fabricated_ids(monkeypatch):
    llm = get_llm_service()
    monkeypatch.setattr(llm, "generate_json", lambda prompt, **kw: json.dumps({
        "overall": {"label": "mixed", "evidence": ["web_1", "fake_9", "web_99"], "summary": "s"},
        "entities": [],
    }))
    svc = SentimentAnalysisService()
    schema, _ = svc.analyze("q", _nav_evidence())
    assert sorted(schema.overall.evidence) == ["web_1"]
    assert "fake_9" not in schema.overall.evidence
    assert schema.overall.source_types == ["web"]


def test_sentiment_source_types_derived_server_side(monkeypatch):
    llm = get_llm_service()
    monkeypatch.setattr(llm, "generate_json", lambda prompt, **kw: json.dumps({
        "overall": {
            "label": "positive",
            # Model-provided "source_types" are ignored; they are derived from
            # the verified Evidence IDs server-side.
            "source_types": ["fake_model_tag"],
            "evidence": ["web_1", "doc_1", "news_2", "comp_tata-motors_news_1"],
            "summary": "s",
        },
        "entities": [],
    }))
    svc = SentimentAnalysisService()
    schema, _ = svc.analyze("q", _nav_evidence())
    # web_1 -> web, doc_1 -> document, news_2 -> news,
    # comp_* -> competitor: the four distinctions are preserved.
    assert schema.overall.source_types == sorted(["web", "document", "news", "competitor"])
    assert "fake_model_tag" not in schema.overall.source_types


def test_sentiment_invalid_label_normalized_to_unavailable(monkeypatch):
    llm = get_llm_service()
    monkeypatch.setattr(llm, "generate_json", lambda prompt, **kw: json.dumps({
        "overall": {"label": "Bullish!", "evidence": ["web_1"], "summary": "s"},
        "entities": [],
    }))
    svc = SentimentAnalysisService()
    schema, _ = svc.analyze("q", _nav_evidence())
    assert schema.overall.label == "unavailable"
    assert "bullish" not in schema.overall.label.lower()


def test_sentiment_entities_filtered_to_identified(monkeypatch):
    llm = get_llm_service()
    monkeypatch.setattr(llm, "generate_json", lambda prompt, **kw: _sentiment_json())
    svc = SentimentAnalysisService()
    schema, _ = svc.analyze(
        "q", _nav_evidence(), eligible_entities=["Tata Motors", "Ola Electric"])

    # FakeCorp Inc was neither identified nor in the pool -> dropped entirely.
    assert [e.entity for e in schema.entities] == ["Tata Motors"]
    # Tata Motors keeps only verified evidence with server-side source types.
    entity = schema.entities[0]
    assert entity.label == "positive"
    assert sorted(entity.evidence) == ["comp_tata-motors_news_1", "news_2"]
    assert entity.source_types == sorted(["competitor", "news"])


def test_sentiment_entities_dropped_without_valid_evidence(monkeypatch):
    llm = get_llm_service()
    monkeypatch.setattr(llm, "generate_json", lambda prompt, **kw: json.dumps({
        "overall": {"label": "neutral", "evidence": ["web_1"], "summary": "s"},
        "entities": [
            {"entity": "Tata Motors", "label": "negative",
             "evidence": ["fake_id"], "summary": "No verifiable backing."},
        ],
    }))
    svc = SentimentAnalysisService()
    schema, _ = svc.analyze("q", _nav_evidence(), eligible_entities=["Tata Motors"])
    assert schema.entities == []


def test_sentiment_unknown_entities_blocked_when_no_identifications(monkeypatch):
    llm = get_llm_service()
    monkeypatch.setattr(llm, "generate_json", lambda prompt, **kw: json.dumps({
        "overall": {"label": "neutral", "evidence": ["web_1"], "summary": "s"},
        "entities": [
            {"entity": "Random Corp", "label": "positive",
             "evidence": ["web_1"], "summary": "Not an identified competitor."},
        ],
    }))
    svc = SentimentAnalysisService()
    schema, _ = svc.analyze("q", _nav_evidence(), eligible_entities=None)
    assert schema.entities == []


def test_sentiment_overall_with_no_valid_evidence_collapses(monkeypatch):
    llm = get_llm_service()
    monkeypatch.setattr(llm, "generate_json", lambda prompt, **kw: json.dumps({
        "overall": {"label": "positive", "evidence": ["made_up_1"], "summary": "s"},
        "entities": [],
    }))
    svc = SentimentAnalysisService()
    schema, _ = svc.analyze("q", _nav_evidence())
    assert schema.overall.label == "unavailable"
    assert schema.overall.evidence == []


def test_sentiment_label_whitelist():
    assert VALID_SENTIMENT_LABELS == {"positive", "neutral", "negative", "mixed", "unavailable"}


# --------------------------------------------------------------------------
# Sentiment agent: thin orchestration, no gathering
# --------------------------------------------------------------------------
def test_agent_no_external_gathering(monkeypatch):
    calls = {"gen_json": 0, "web": 0, "news": 0, "rag": 0}
    llm = get_llm_service()
    monkeypatch.setattr(llm, "generate_json", lambda prompt, **kw: (
        calls.__setitem__("gen_json", calls["gen_json"] + 1) or _sentiment_json()))
    ws = get_web_search_service()
    monkeypatch.setattr(ws, "search_web", lambda q: (
        calls.__setitem__("web", calls["web"] + 1) or ([], [], "")))
    provider = get_news_provider()
    monkeypatch.setattr(provider, "fetch_recent", lambda q: (
        calls.__setitem__("news", calls["news"] + 1) or ([], "")))
    rag = get_rag_service()
    monkeypatch.setattr(rag, "retrieve", lambda query, top_k=5, document_ids=None: (
        calls.__setitem__("rag", calls["rag"] + 1) or []))

    agent = SentimentResearchAgent()
    result = agent.execute_sentiment_analysis(
        "Analyze the Indian EV market", _nav_evidence(),
        competitors=["Tata Motors"],
    )
    assert result.sentiment.overall.label == "mixed"
    assert result.warning is None
    assert result.notes == []
    assert calls["gen_json"] == 1
    assert calls["web"] == 0 and calls["news"] == 0 and calls["rag"] == 0


def test_agent_surfaces_warning_note(monkeypatch):
    llm = get_llm_service()
    monkeypatch.setattr(llm, "generate_json",
                        lambda prompt, **kw: (_ for _ in ()).throw(RuntimeError("boom")))
    agent = SentimentResearchAgent()
    result = agent.execute_sentiment_analysis("q", _nav_evidence(), competitors=[])
    assert result.sentiment.overall.label == "unavailable"
    assert result.warning and "Sentiment analysis unavailable" in result.warning
    assert result.notes[0] == result.warning


# --------------------------------------------------------------------------
# Pipeline integration
# --------------------------------------------------------------------------
def test_research_agent_sentiment_adds_single_call(monkeypatch):
    counters = _patch_sentiment_pipeline(monkeypatch)
    agent = ResearchAgent()
    report, all_evidence = agent.execute_research(
        "Analyze the Indian EV market", document_ids=["d1"])

    # Sentiment adds exactly ONE Gemini call on top of identification + synthesis.
    assert counters["gen_json"] == 3
    # Zero additional web/news/RAG gathering beyond the once-each initial passes.
    assert counters["web"] == 1
    assert counters["news_get"] == 2  # query-level + one focused competitor
    assert counters["rag"] == 2       # query-level + one focused competitor

    # Report carries the categorical sentiment (additive optional field).
    assert report.sentiment is not None
    assert report.sentiment.overall.label == "mixed"
    assert [e.entity for e in report.sentiment.entities] == ["Tata Motors"]

    # Competition evidence is consumed by the sentiment pass.
    cited_comp = {rid for e in report.sentiment.entities for rid in e.evidence}
    assert "comp_tata-motors_news_1" in cited_comp

    # Every cited evidence ID exists in the supplied evidence pool.
    pool = {e.evidence_id for e in all_evidence}
    cited = set(report.sentiment.overall.evidence) | cited_comp
    assert cited <= pool


def test_research_engine_persists_sentiments_and_backcompat_fields(monkeypatch):
    counters = _patch_sentiment_pipeline(monkeypatch)
    db = SessionLocal()
    engine = get_research_engine()
    record = engine.run_research(
        db,
        user_id=settings.DEFAULT_USER_ID,
        query="Analyze the Indian EV market",
        research_type_str="competitor_analysis",
        document_ids=["d1"],
    )
    try:
        assert record.status == ResearchStatus.COMPLETED
        assert counters["gen_json"] == 3
        result = db.get(ResearchResult, record.result.id) if record.result else None
        assert result is not None
        sentiment = result.sentiment or {}
        # market_overview / conclusion backward compatibility preserved.
        assert sentiment.get("market_overview")
        assert sentiment.get("conclusion")
        sentiments = sentiment.get("sentiments")
        assert sentiments is not None
        assert sentiments["overall"]["label"] == "mixed"
        assert sentiments["entities"][0]["entity"] == "Tata Motors"
        assert "comp_tata-motors_news_1" in sentiments["entities"][0]["evidence"]
    finally:
        _cleanup_research(db, record.id)
        db.close()


def test_research_engine_graceful_when_sentiment_fails(monkeypatch):
    _patch_sentiment_pipeline(
        monkeypatch,
        sentiment_error=Exception("429 RESOURCE_EXHAUSTED, quota"),
    )
    db = SessionLocal()
    engine = get_research_engine()
    sent_agent = engine.research_agent.synthesis_agent
    orig_generate_report = sent_agent.generate_report
    captured = {}

    def wrap_generate_report(query, **kw):
        captured["warning_notes"] = kw.get("warning_notes")
        return orig_generate_report(query, **kw)

    monkeypatch.setattr(sent_agent, "generate_report", wrap_generate_report)

    record = engine.run_research(
        db,
        user_id=settings.DEFAULT_USER_ID,
        query="Analyze the Indian EV market",
    )
    try:
        # A sentiment failure never fails the research job.
        assert record.status == ResearchStatus.COMPLETED
        result = db.get(ResearchResult, record.result.id)
        sentiments = (result.sentiment or {}).get("sentiments")
        assert sentiments["overall"]["label"] == "unavailable"
        assert sentiments["entities"] == []
        # The honest quota note is surfaced to the synthesis step, verbatim.
        assert captured["warning_notes"] and "quota" in (captured["warning_notes"] or "").lower()
        assert "RESOURCE_EXHAUSTED" in (captured["warning_notes"] or "")
    finally:
        _cleanup_research(db, record.id)
        db.close()


# --------------------------------------------------------------------------
# API round-trips and backward compatibility
# --------------------------------------------------------------------------
def test_api_post_get_sentiment_roundtrip(monkeypatch):
    _patch_sentiment_pipeline(monkeypatch)

    post = client.post("/api/research", json={
        "query": "Analyze the Indian EV market",
        "research_type": "competitor_analysis",
        "document_ids": ["d1"],
    })
    assert post.status_code == 201, post.text
    body = post.json()
    research_id = body["research_id"]
    try:
        assert body["status"] == "completed"
        sentiment = body["result"]["sentiment"]
        assert sentiment is not None
        assert sentiment["overall"]["label"] == "mixed"
        assert sorted(sentiment["overall"]["source_types"]) == ["news", "web"]
        assert sentiment["entities"][0]["entity"] == "Tata Motors"
        assert sentiment["entities"][0]["label"] == "positive"
        assert sorted(sentiment["entities"][0]["source_types"]) == ["competitor", "news"]

        # Provenance: every cited sentiment evidence ID also appears among the
        # report's own evidence references (key findings + competitor evidence) -
        # the only evidence-id universe the API exposes.
        cited = set(sentiment["overall"]["evidence"])
        for e in sentiment["entities"]:
            cited |= set(e["evidence"])
        known = set()
        for kf in body["result"]["key_findings"]:
            known |= set(kf.get("evidence", []))
        for c in body["result"]["competitors"]:
            known |= set(c.get("evidence", []))
        assert cited <= known

        get = client.get(f"/api/research/{research_id}")
        assert get.status_code == 200
        got = get.json()
        assert got["result"]["sentiment"]["overall"]["label"] == "mixed"
        assert got["result"]["sentiment"]["entities"][0]["evidence"]
    finally:
        db = SessionLocal()
        try:
            _cleanup_research(db, research_id)
        finally:
            db.close()


def test_api_old_sentiment_records_remain_compatible():
    db = SessionLocal()
    research = Research(user_id=settings.DEFAULT_USER_ID, query="legacy query",
                        status=ResearchStatus.COMPLETED)
    db.add(research)
    db.commit()
    db.refresh(research)
    try:
        # A pre-Step-7 record: sentiment only holds market_overview + conclusion.
        db.add(ResearchResult(
            research_id=research.id,
            summary="legacy summary",
            insights=[],
            risks=[],
            opportunities=[],
            trends=[],
            competitors=[],
            sentiment={"market_overview": "legacy overview", "conclusion": "legacy conclusion"},
        ))
        db.commit()

        res = client.get(f"/api/research/{research.id}")
        assert res.status_code == 200
        r = res.json()["result"]
        # Backward compatibility: prose fields preserved, sentiment additive None.
        assert r["market_overview"] == "legacy overview"
        assert r["conclusion"] == "legacy conclusion"
        assert r["sentiment"] is None
    finally:
        _cleanup_research(db, research.id)
        db.close()


def test_secrets_never_exposed_sentiment_flow(monkeypatch):
    _patch_sentiment_pipeline(monkeypatch)

    for path in ("/api/health", "/api/stats", "/api/research/recent"):
        res = client.get(path)
        assert res.status_code == 200
        assert FAKE_NEWS_KEY not in res.text
        if settings.GEMINI_API_KEY:
            assert settings.GEMINI_API_KEY not in res.text

    post = client.post("/api/research", json={"query": "electric vehicle market"})
    assert post.status_code == 201, post.text
    body = post.json()
    try:
        assert FAKE_NEWS_KEY not in post.text
        if settings.GEMINI_API_KEY:
            assert settings.GEMINI_API_KEY not in post.text
        get_res = client.get(f"/api/research/{body['research_id']}")
        assert FAKE_NEWS_KEY not in get_res.text
        if settings.GEMINI_API_KEY:
            assert settings.GEMINI_API_KEY not in get_res.text
        assert body["result"]["sentiment"] is not None
    finally:
        db = SessionLocal()
        try:
            _cleanup_research(db, body["research_id"])
        finally:
            db.close()