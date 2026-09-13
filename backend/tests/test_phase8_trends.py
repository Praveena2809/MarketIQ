"""
Step 8 trend-research tests: evidence-grounded, qualitative trend extraction
from the existing evidence pool, strict evidence-containment, server-side
source_type derivation, exactly-one-Gemini-call budget, zero additional
web/news/RAG gathering, sanitized impact/direction/as_of, verified-trend
replacement of synthesis defaults, failure-preservation of synthesis defaults,
persistence/back-compat, API round-trips, and secret non-exposure.

Deterministic: every external call (Gemini, web grounding, RAG, news provider)
is mocked. Call-count spies verify the trend pass adds exactly ONE Gemini
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
from app.agents.trend_research_agent import TrendResearchAgent
from app.services.llm import get_llm_service
from app.services.news.news_provider import get_news_provider
from app.services.rag import get_rag_service
from app.services.research.evidence import Evidence, resolve_evidence_source_type
from app.services.research.trend_analysis import (
    TREND_SYSTEM_INSTRUCTION,
    TREND_JSON_SCHEMA,
    MAX_TREND_EVIDENCE_ITEMS,
    MAX_TREND_CHARS,
    MAX_TRENDS,
    VALID_TREND_IMPACT,
    VALID_TREND_DIRECTIONS,
    TrendAnalysisService,
)
from app.services.research.web_search import get_web_search_service
from app.services.research.research_engine import get_research_engine

client = TestClient(app)
settings = get_settings()

FAKE_NEWS_KEY = "test-secret-news-key"

NEWS_SAMPLE_PAYLOAD = {
    "status": "ok",
    "totalResults": 2,
    "articles": [
        {
            "source": {"id": "reuters", "name": "Reuters"},
            "title": "India EV sales hit record in 2026",
            "description": "Electric vehicle registrations grew 40 percent year on year.",
            "url": "https://newsapi.test/articles/india-ev-sales",
            "publishedAt": "2026-09-10T08:30:00Z",
            "content": "Electric vehicle registrations grew 40 percent...",
        },
        {
            "source": {"name": "Economic Times"},
            "title": "Tata Motors expands EV lineup",
            "description": "New models are planned for next year.",
            "url": "https://newsapi.test/articles/tata-motors-ev",
            "publishedAt": "2026-09-08T11:00:00Z",
        },
    ],
}


def _nav_evidence():
    """Real-shaped evidence pool covering web, doc, news, and competitor evidence."""
    return [
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


def _trend_json(trends=None):
    """Default verified trend payload (uses pool IDs from _nav_evidence)."""
    if trends is None:
        trends = [
            {
                "trend": "Agentic AI adoption",
                "impact": "high",
                "description": "Enterprise adoption is accelerating.",
                "direction": "rising",
                "evidence": ["web_1", "news_2", "comp_tata-motors_news_1"],
                "as_of": "2026-09-10T08:30:00Z",
            },
            {
                "trend": "Ola Electric expansion",
                "impact": "medium",
                "description": "Ola Electric growing domestic market share.",
                "direction": "stable",
                "evidence": ["doc_1"],
            },
        ]
    return json.dumps({"trends": trends})


def _pipeline_trend_json():
    """
    Trend payload for the full pipeline: the real news provider emits
    published_at via datetime.isoformat(), e.g. '+00:00' rather than 'Z'.
    as_of mirrors that exact string so validation keeps it (exact match).
    """
    return json.dumps({
        "trends": [
            {
                "trend": "Agentic AI adoption",
                "impact": "high",
                "description": "Enterprise adoption is accelerating.",
                "direction": "rising",
                "evidence": ["web_1", "news_2", "comp_tata-motors_news_1"],
                "as_of": _expected_pipeline_as_of(),
            },
            {
                "trend": "Ola Electric expansion",
                "impact": "medium",
                "description": "Ola Electric growing domestic market share.",
                "direction": "stable",
                "evidence": ["doc_1"],
            },
        ]
    })


def _expected_pipeline_as_of():
    return "2026-09-10T08:30:00+00:00"


def _sentiment_json():
    return json.dumps({
        "overall": {
            "label": "mixed",
            "evidence": ["web_1", "news_2"],
            "summary": "Mixed near-term outlook.",
        },
        "entities": [
            {
                "entity": "Tata Motors",
                "label": "positive",
                "evidence": ["comp_tata-motors_news_1", "news_2"],
                "summary": "Positive outlook driven by EV expansion.",
            },
        ],
    })


def _synthesis_json(evidence_ids=None):
    evidence_ids = evidence_ids or ["web_1", "doc_1"]
    return json.dumps({
        "executive_summary": "The enterprise AI market is expanding quickly.",
        "key_findings": [
            {"finding": "AI adoption is growing.", "evidence": evidence_ids}
        ],
        "market_overview": "A detailed overview grounded in evidence.",
        "trends": [{"trend": "Agentic AI (synthesis default)", "impact": "high", "description": "Falls back when trend pass fails."}],
        "opportunities": [{"opportunity": "Automation", "potential_impact": "high"}],
        "risks": [{"risk": "Regulation", "severity": "medium", "mitigation": "Monitor."}],
        "competitors": [
            {"company": "Tata Motors", "market_share": "N/A", "strengths": ["EV"], "weaknesses": ["Price"]},
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


# --------------------------------------------------------------------------
# Pipeline mock helper
# --------------------------------------------------------------------------
def _patch_trend_pipeline(monkeypatch, trend_payload=None, trend_error=None):
    """Mocks every external service. generate_json dispatches on system_instruction
    to identification, sentiment, trend, or synthesis. Returns a call counter."""
    counters = {"web": 0, "news_get": 0, "rag": 0, "gen_json": 0, "gen_text": 0}

    ws = get_web_search_service()

    def fake_search(query):
        counters["web"] += 1
        return ([_nav_evidence()[0]], ["query"], "")

    monkeypatch.setattr(ws, "search_web", fake_search)

    rag = get_rag_service()

    def fake_retrieve(query, top_k=5, document_ids=None):
        counters["rag"] += 1
        return [
            {"chunk_id": "d_0", "chunk_text": "Tata Motors and Ola Electric are leading EV makers.",
             "document_id": "d1", "chunk_index": 0, "filename": "ev_report.txt",
             "file_type": "txt", "relevance_score": 0.9}
        ]

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
            return json.dumps({"competitors": [{"name": "Tata Motors"}]})
        if "Sentiment Analysis Engine" in si:
            return _sentiment_json()
        if "Trend Analysis Engine" in si:
            if trend_error is not None:
                raise trend_error
            return trend_payload if trend_payload is not None else _pipeline_trend_json()
        return _synthesis_json(evidence_ids=["web_1", "doc_1", "news_2", "comp_tata-motors_news_1"])

    monkeypatch.setattr(llm, "generate_json", fake_generate_json)

    monkeypatch.setattr(settings, "NEWS_API_KEY", FAKE_NEWS_KEY)
    monkeypatch.setattr(settings, "COMPETITOR_FOCUSED_WEB_SEARCH", False)
    provider = get_news_provider()

    def fake_get_json(params):
        counters["news_get"] += 1
        return NEWS_SAMPLE_PAYLOAD

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
# resolve_evidence_source_type — shared provenance helper
# --------------------------------------------------------------------------
class TestEvidenceSourceTypeResolver:
    def test_web_evidence_returns_web(self):
        pool = {e.evidence_id: e for e in _nav_evidence()}
        assert resolve_evidence_source_type("web_1", pool) == "web"

    def test_news_evidence_returns_news(self):
        pool = {e.evidence_id: e for e in _nav_evidence()}
        assert resolve_evidence_source_type("news_2", pool) == "news"

    def test_document_evidence_returns_document(self):
        pool = {e.evidence_id: e for e in _nav_evidence()}
        assert resolve_evidence_source_type("doc_1", pool) == "document"

    def test_competitor_evidence_always_returns_competitor(self):
        pool = {e.evidence_id: e for e in _nav_evidence()}
        assert resolve_evidence_source_type("comp_tata-motors_news_1", pool) == "competitor"

    def test_fabricated_id_returns_none(self):
        pool = {e.evidence_id: e for e in _nav_evidence()}
        assert resolve_evidence_source_type("fake_9", pool) is None

    def test_unknown_id_returns_none(self):
        assert resolve_evidence_source_type("x", {}) is None


# --------------------------------------------------------------------------
# TrendAnalysisService: prompt / budget / schema
# --------------------------------------------------------------------------
class TestTrendServiceUnit:
    def test_empty_evidence_no_gemini_call(self, monkeypatch):
        called = {"called": False}

        def should_not_be_called(prompt, **kw):
            called["called"] = True
            return "{}"

        monkeypatch.setattr(get_llm_service(), "generate_json", should_not_be_called)
        svc = TrendAnalysisService()
        trends, warning, success = svc.analyze("q", [])
        assert called["called"] is False
        assert trends == []
        assert success is False
        assert "insufficient evidence" in warning.lower()

    def test_prompt_includes_query_and_evidence_ids(self, monkeypatch):
        captured = {}

        def spy(prompt, **kw):
            captured["prompt"] = prompt
            captured["schema"] = kw.get("schema")
            captured["si"] = kw.get("system_instruction")
            return _trend_json()

        monkeypatch.setattr(get_llm_service(), "generate_json", spy)
        svc = TrendAnalysisService()
        svc.analyze("Indian EV market", _nav_evidence())

        assert 'Indian EV market' in captured["prompt"]
        for eid in ["web_1", "doc_1", "news_2", "comp_tata-motors_news_1"]:
            assert f"[Evidence ID: {eid}]" in captured["prompt"]
        assert captured["schema"] == TREND_JSON_SCHEMA
        assert "Trend Analysis Engine" in (captured["si"] or "")
        assert MAX_TREND_EVIDENCE_ITEMS == 40

    def test_successful_verification_server_derived_source_types(self, monkeypatch):
        """comp_tata-motors_news_1 → 'competitor' (not 'news')."""
        monkeypatch.setattr(get_llm_service(), "generate_json", lambda **kw: _trend_json())
        svc = TrendAnalysisService()
        trends, warning, success = svc.analyze("q", _nav_evidence())
        assert warning is None
        assert success is True
        assert len(trends) == 2
        t1 = trends[0]
        assert t1.trend == "Agentic AI adoption"
        assert t1.impact == "high"
        assert t1.direction == "rising"
        assert t1.evidence == ["web_1", "news_2", "comp_tata-motors_news_1"]
        # source_types derived server-side: comp → competitor, not news
        assert set(t1.source_types) == {"competitor", "news", "web"}
        assert t1.as_of == "2026-09-10T08:30:00Z"

    def test_source_types_never_trusted_from_model(self, monkeypatch):
        """Model-provided source_types field is ignored entirely."""
        payload = json.dumps({
            "trends": [{
                "trend": "Test trend",
                "impact": "low",
                "evidence": ["web_1"],
                "source_types": ["web", "news", "document", "competitor"],
                "direction": "stable",
            }]
        })
        monkeypatch.setattr(get_llm_service(), "generate_json", lambda **kw: payload)
        svc = TrendAnalysisService()
        trends, _, _ = svc.analyze("q", _nav_evidence())
        assert trends[0].source_types == ["web"]

    def test_impact_sanitization(self, monkeypatch):
        payload = json.dumps({
            "trends": [
                {"trend": "A", "impact": "critical", "evidence": ["web_1"]},
                {"trend": "B", "impact": "HIGH", "evidence": ["web_1"]},
                {"trend": "C", "impact": 5, "evidence": ["web_1"]},
                {"trend": "D", "impact": None, "evidence": ["web_1"]},
            ]
        })
        monkeypatch.setattr(get_llm_service(), "generate_json", lambda **kw: payload)
        svc = TrendAnalysisService()
        trends, _, _ = svc.analyze("q", _nav_evidence())
        impacts = {t.trend: t.impact for t in trends}
        assert impacts["A"] == "medium"   # invalid → medium
        assert impacts["B"] == "high"     # case-insensitive match
        assert impacts["C"] == "medium"   # not a string → medium
        assert impacts["D"] == "medium"   # None → medium

    def test_direction_sanitization(self, monkeypatch):
        payload = json.dumps({
            "trends": [
                {"trend": "A", "impact": "high", "evidence": ["web_1"], "direction": "Rising"},
                {"trend": "B", "impact": "high", "evidence": ["web_1"], "direction": "hot"},
                {"trend": "C", "impact": "high", "evidence": ["web_1"], "direction": 3},
                {"trend": "D", "impact": "high", "evidence": ["web_1"], "direction": ""},
            ]
        })
        monkeypatch.setattr(get_llm_service(), "generate_json", lambda **kw: payload)
        svc = TrendAnalysisService()
        trends, _, _ = svc.analyze("q", _nav_evidence())
        directions = {t.trend: t.direction for t in trends}
        assert directions["A"] == "rising"
        assert directions["B"] == ""   # invalid → ""
        assert directions["C"] == ""   # not a string → ""
        assert directions["D"] == ""   # empty → ""

    def test_as_of_validation_exact_match_on_news_published_at(self, monkeypatch):
        """as_of survives only when it exactly matches a cited news published_at."""
        payload = json.dumps({
            "trends": [
                {
                    "trend": "Matched date",
                    "impact": "high",
                    "evidence": ["comp_tata-motors_news_1"],
                    "as_of": "2026-09-10T08:30:00Z",
                },
                {
                    "trend": "Web only with date",
                    "impact": "high",
                    "evidence": ["web_1"],
                    "as_of": "2026-09-10T08:30:00Z",
                },
                {
                    "trend": "Mismatched date",
                    "impact": "high",
                    "evidence": ["news_2"],
                    "as_of": "2026-09-10T08:30:00Z",
                },
            ]
        })
        monkeypatch.setattr(get_llm_service(), "generate_json", lambda **kw: payload)
        svc = TrendAnalysisService()
        trends, _, _ = svc.analyze("q", _nav_evidence())
        as_ofs = {t.trend: t.as_of for t in trends}
        # comp_tata-motors_news_1 has published_at=2026-09-10T08:30:00Z → kept
        assert as_ofs["Matched date"] == "2026-09-10T08:30:00Z"
        # web_1 is not news → None
        assert as_ofs["Web only with date"] is None
        # news_2 published_at=2026-09-08T11:00:00Z ≠ 2026-09-10T08:30:00Z → None
        assert as_ofs["Mismatched date"] is None

    def test_fabricated_evidence_ids_dropped(self, monkeypatch):
        payload = json.dumps({
            "trends": [
                {"trend": "A", "impact": "high", "evidence": ["web_1", "fake_9"]},
                {"trend": "All fabricated", "impact": "high", "evidence": ["fake_9", "fake_10"]},
            ]
        })
        monkeypatch.setattr(get_llm_service(), "generate_json", lambda **kw: payload)
        svc = TrendAnalysisService()
        trends, warning, success = svc.analyze("q", _nav_evidence())
        assert len(trends) == 1
        assert trends[0].evidence == ["web_1"]

    def test_all_trends_dropped_is_successful_empty_determination(self, monkeypatch):
        """Every trend citing only fabricated IDs → zero verified trends; this is
        a SUCCESSFUL determination (no evidence-supported trends), not a failure."""
        payload = json.dumps({
            "trends": [
                {"trend": "A", "impact": "high", "evidence": ["fake_9", "fake_10"]},
                {"trend": "B", "impact": "high", "evidence": ["made_up_1"]},
            ]
        })
        monkeypatch.setattr(get_llm_service(), "generate_json", lambda **kw: payload)
        svc = TrendAnalysisService()
        trends, warning, success = svc.analyze("q", _nav_evidence())
        assert trends == []
        assert success is True
        assert warning is not None and "no evidence-supported trends" in warning.lower()

    def test_trend_without_evidence_dropped(self, monkeypatch):
        payload = json.dumps({
            "trends": [
                {"trend": "No evidence key", "impact": "high"},
                {"trend": "", "impact": "high", "evidence": ["web_1"]},
            ]
        })
        monkeypatch.setattr(get_llm_service(), "generate_json", lambda **kw: payload)
        svc = TrendAnalysisService()
        trends, warning, success = svc.analyze("q", _nav_evidence())
        # name-only trend dropped (no evidence); empty-name trend also dropped.
        # A verified empty result is a successful determination, not a failure.
        assert trends == []
        assert success is True
        assert warning is not None and "no evidence-supported trends" in warning.lower()

    def test_malformed_json_returns_empty_with_warning(self, monkeypatch):
        monkeypatch.setattr(get_llm_service(), "generate_json", lambda **kw: "this is not json")
        svc = TrendAnalysisService()
        trends, warning, success = svc.analyze("q", _nav_evidence())
        assert trends == []
        assert success is False
        assert warning is not None and "malformed" in warning.lower()

    def test_wrong_shape_returns_empty_with_warning(self, monkeypatch):
        monkeypatch.setattr(get_llm_service(), "generate_json", lambda **kw: '{"foo": 1}')
        svc = TrendAnalysisService()
        trends, warning, success = svc.analyze("q", _nav_evidence())
        assert trends == []
        assert success is False
        assert warning is not None and "malformed" in warning.lower()

    def test_generic_exception_fails_soft(self, monkeypatch):
        def boom(prompt, **kw): raise RuntimeError("boom")
        monkeypatch.setattr(get_llm_service(), "generate_json", boom)
        svc = TrendAnalysisService()
        trends, warning, success = svc.analyze("q", _nav_evidence())
        assert trends == []
        assert success is False
        assert "trend analysis unavailable" in warning.lower()

    def test_quota_exhausted_specific_warning(self, monkeypatch):
        def boom(prompt, **kw): raise RuntimeError("RESOURCE_EXHAUSTED: 429 quota")
        monkeypatch.setattr(get_llm_service(), "generate_json", boom)
        svc = TrendAnalysisService()
        trends, warning, success = svc.analyze("q", _nav_evidence())
        assert trends == []
        assert success is False
        assert "RESOURCE_EXHAUSTED" in warning
        assert "quota" in warning.lower()

    def test_max_trends_cap(self, monkeypatch):
        payload = json.dumps({
            "trends": [
                {"trend": f"Trend {i}", "impact": "high", "evidence": ["web_1"]}
                for i in range(12)
            ]
        })
        monkeypatch.setattr(get_llm_service(), "generate_json", lambda **kw: payload)
        svc = TrendAnalysisService()
        trends, _, _ = svc.analyze("q", _nav_evidence())
        assert len(trends) == MAX_TRENDS == 8

    def test_prompt_truncates_excess_evidence(self, monkeypatch):
        large_pool = [
            Evidence(evidence_id=f"web_{i}", source_type="web",
                     title=f"Source {i}", content="x" * 200, url=f"https://e{i}.com")
            for i in range(60)
        ]
        captured = {}
        def spy(prompt, **kw):
            captured["prompt"] = prompt
            return json.dumps({"trends": []})
        monkeypatch.setattr(get_llm_service(), "generate_json", spy)
        svc = TrendAnalysisService()
        svc.analyze("q", large_pool)
        # Only first 40 evidence IDs appear in the prompt
        assert "[Evidence ID: web_0]" in captured["prompt"]
        assert "[Evidence ID: web_39]" in captured["prompt"]
        assert "[Evidence ID: web_40]" not in captured["prompt"]


# --------------------------------------------------------------------------
# TrendResearchAgent
# --------------------------------------------------------------------------
class TestTrendResearchAgent:
    def test_returns_trends_and_no_extra_calls(self, monkeypatch):
        ws = get_web_search_service()
        monkeypatch.setattr(ws, "search_web", lambda q: ([], [], ""))
        rag = get_rag_service()
        monkeypatch.setattr(rag, "retrieve", lambda q, top_k=5, document_ids=None: [])
        gen_text_called = {"n": 0}
        llm = get_llm_service()
        monkeypatch.setattr(llm, "generate_text", lambda **kw: (gen_text_called.__setitem__("n", gen_text_called["n"]+1) or "q"))
        gen_json_called = {"n": 0}
        monkeypatch.setattr(llm, "generate_json", lambda **kw: (
            gen_json_called.__setitem__("n", gen_json_called["n"]+1) or _trend_json()
        ))
        monkeypatch.setattr(settings, "NEWS_API_KEY", "")
        monkeypatch.setattr(settings, "COMPETITOR_FOCUSED_WEB_SEARCH", False)

        agent = TrendResearchAgent()
        result = agent.execute_trend_research("Indian EV market", _nav_evidence())

        assert result.trends and len(result.trends) == 2
        assert result.success is True
        assert result.warning is None
        assert len(result.notes) == 0
        # No web/news/RAG/embedding calls
        assert gen_json_called["n"] == 1  # exactly 1 Gemini call
        assert gen_text_called["n"] == 0

    def test_failure_returns_empty_with_warning(self, monkeypatch):
        monkeypatch.setattr(get_llm_service(), "generate_json",
                            lambda **kw: (_ for _ in ()).throw(RuntimeError("boom")))
        agent = TrendResearchAgent()
        result = agent.execute_trend_research("q", _nav_evidence())
        assert result.trends == []
        assert result.success is False
        assert result.warning is not None
        assert result.notes[0] == result.warning

    def test_empty_determination_is_successful(self, monkeypatch):
        """A verified zero-trend result is success=True (authoritative empty)."""
        monkeypatch.setattr(
            get_llm_service(), "generate_json",
            lambda **kw: json.dumps({"trends": [{"trend": "X", "impact": "high", "evidence": ["fake_9"]}]}),
        )
        agent = TrendResearchAgent()
        result = agent.execute_trend_research("q", _nav_evidence())
        assert result.trends == []
        assert result.success is True
        assert result.warning is not None


# --------------------------------------------------------------------------
# ResearchAgent pipeline integration
# --------------------------------------------------------------------------
class TestResearchAgentTrendPipeline:
    def test_verified_trends_replace_synthesis_defaults(self, monkeypatch):
        counters = _patch_trend_pipeline(monkeypatch)
        agent = ResearchAgent()
        report, all_evidence = agent.execute_research("Analyze the Indian EV market", document_ids=["d1"])

        assert counters["gen_json"] == 5  # identification + synthesis + sentiment + trend + insight
        assert counters["web"] == 1
        assert counters["news_get"] == 2
        assert counters["rag"] == 2

        # Verified trends replaced synthesis defaults.
        assert report.trends and len(report.trends) == 2
        assert report.trends[0].trend == "Agentic AI adoption"
        assert report.trends[0].evidence == ["web_1", "news_2", "comp_tata-motors_news_1"]
        assert set(report.trends[0].source_types) == {"competitor", "news", "web"}
        assert report.trends[0].direction == "rising"

        # Every cited evidence ID exists in the supplied pool.
        pool = {e.evidence_id for e in all_evidence}
        for t in report.trends:
            assert set(t.evidence) <= pool

        # Sentiment still attached.
        assert report.sentiment is not None
        assert report.sentiment.overall.label == "mixed"

    def test_trend_failure_preserves_synthesis_trends(self, monkeypatch):
        counters = _patch_trend_pipeline(monkeypatch, trend_error=RuntimeError("boom"))
        agent = ResearchAgent()
        captured = {}
        orig_generate_report = agent.synthesis_agent.generate_report

        def wrap_generate_report(query, **kw):
            captured["warning_notes"] = kw.get("warning_notes")
            return orig_generate_report(query, **kw)

        monkeypatch.setattr(agent.synthesis_agent, "generate_report", wrap_generate_report)
        report, _ = agent.execute_research("Analyze the Indian EV market", document_ids=["d1"])

        assert counters["gen_json"] == 5  # trend call still attempted
        # Synthesis-produced default preserved.
        assert report.trends and len(report.trends) == 1
        assert report.trends[0].trend == "Agentic AI (synthesis default)"
        assert report.trends[0].evidence == []  # synthesis default has no evidence
        assert "Trend analysis unavailable" in (captured["warning_notes"] or "")

    def test_successful_zero_verified_replaces_synthesis_with_empty(self, monkeypatch):
        """
        Regression: a SUCCESSFUL trend pass that verifiably finds zero
        evidence-supported trends (model returned only fabricated IDs)
        REPLACES the synthesis-produced trends with [] rather than
        preserving them.
        """
        bad_payload = json.dumps({
            "trends": [
                {"trend": "Phantom trend", "impact": "high", "evidence": ["fake_9"]}
            ]
        })
        counters = _patch_trend_pipeline(monkeypatch, trend_payload=bad_payload)
        agent = ResearchAgent()
        captured = {}
        orig_generate_report = agent.synthesis_agent.generate_report

        def wrap_generate_report(query, **kw):
            captured["warning_notes"] = kw.get("warning_notes")
            return orig_generate_report(query, **kw)

        monkeypatch.setattr(agent.synthesis_agent, "generate_report", wrap_generate_report)
        report, _ = agent.execute_research("Analyze the Indian EV market", document_ids=["d1"])

        assert counters["gen_json"] == 5
        # Successful zero-trend determination wins over the synthesis default.
        assert report.trends == []
        assert not any(getattr(t, "trend", "") == "Agentic AI (synthesis default)" for t in report.trends)
        # Honest note about the empty evidence-supported set is still surfaced.
        assert "No evidence-supported trends" in (captured["warning_notes"] or "")

    def test_competitor_evidence_consumed_by_trend_pass(self, monkeypatch):
        def check_competitor_in_trend(prompt, **kw):
            si = kw.get("system_instruction") or ""
            if "Trend Analysis Engine" in si:
                assert "comp_tata-motors_news_1" in prompt
            return _trend_json() if "Trend" in si else _synthesis_json(
                evidence_ids=["web_1", "doc_1", "news_2", "comp_tata-motors_news_1"])
        _patch_trend_pipeline(monkeypatch)
        monkeypatch.setattr(get_llm_service(), "generate_json", check_competitor_in_trend)
        agent = ResearchAgent()
        report, _ = agent.execute_research("Analyze the Indian EV market", document_ids=["d1"])
        # Trend items cite comp evidence, confirming pool was passed through.
        assert any("comp_tata-motors_news_1" in t.evidence for t in report.trends)


# --------------------------------------------------------------------------
# ResearchEngine persistence / back-compat
# --------------------------------------------------------------------------
class TestTrendPersistence:
    def test_engine_persists_trend_evidence_fields(self, monkeypatch):
        counters = _patch_trend_pipeline(monkeypatch)
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
            assert counters["gen_json"] == 5
            result = db.get(ResearchResult, record.result.id) if record.result else None
            assert result is not None
            # DB round-trip: evidence, source_types, direction, as_of preserved.
            trend = result.trends[0]
            assert trend["trend"] == "Agentic AI adoption"
            assert trend["evidence"] == ["web_1", "news_2", "comp_tata-motors_news_1"]
            assert set(trend["source_types"]) == {"competitor", "news", "web"}
            assert trend["direction"] == "rising"
            # Published date from news.isoformat() (e.g. "+00:00").
            assert trend["as_of"] == _expected_pipeline_as_of()
            # Back-compat: sentiment field present.
            sentiment = result.sentiment or {}
            assert sentiment.get("market_overview")
        finally:
            _cleanup_research(db, record.id)
            db.close()

    def test_engine_trend_quota_failure_preserves_defaults_and_warns(self, monkeypatch):
        counters = _patch_trend_pipeline(
            monkeypatch,
            trend_error=RuntimeError("RESOURCE_EXHAUSTED: 429 quota"),
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
            research_type_str="competitor_analysis",
            document_ids=["d1"],
        )
        try:
            assert record.status == ResearchStatus.COMPLETED
            assert counters["gen_json"] == 5
            result = db.get(ResearchResult, record.result.id) if record.result else None
            assert result is not None
            # Synthesis defaults preserved; empty additive fields (no fabrication).
            trend = result.trends[0]
            assert trend["trend"] == "Agentic AI (synthesis default)"
            assert trend["evidence"] == []
            # The honest quota note is surfaced to the synthesis step, verbatim.
            assert captured["warning_notes"] and "quota" in (captured["warning_notes"] or "").lower()
            assert "RESOURCE_EXHAUSTED" in (captured["warning_notes"] or "")
        finally:
            _cleanup_research(db, record.id)
            db.close()


# --------------------------------------------------------------------------
# API round-trip
# --------------------------------------------------------------------------
class TestTrendApiRoundTrip:
    def test_api_post_get_trend_provenance(self, monkeypatch):
        _patch_trend_pipeline(monkeypatch)
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
            trends = body["result"]["trends"]
            assert len(trends) == 2
            t1 = trends[0]
            assert t1["trend"] == "Agentic AI adoption"
            assert t1["evidence"] == ["web_1", "news_2", "comp_tata-motors_news_1"]
            assert set(t1["source_types"]) == {"competitor", "news", "web"}
            assert t1["direction"] == "rising"
            # Exact as_of preserved when model echoes published_at from the prompt.
            assert t1["as_of"] == _expected_pipeline_as_of()

            # Provenance containment: every cited trend evidence ID appears in
            # the evidence-id universe exposed by the API.
            cited = set()
            for t in trends:
                cited |= set(t.get("evidence", []))
            known = set()
            for kf in body["result"]["key_findings"]:
                known |= set(kf.get("evidence", []))
            for c in body["result"]["competitors"]:
                known |= set(c.get("evidence", []))
            assert cited <= known

            # GET round-trip matches.
            get = client.get(f"/api/research/{research_id}")
            assert get.status_code == 200
            got = get.json()
            assert got["result"]["trends"][0]["evidence"] == ["web_1", "news_2", "comp_tata-motors_news_1"]
        finally:
            db = SessionLocal()
            try:
                _cleanup_research(db, research_id)
            finally:
                db.close()

    def test_old_trend_records_remain_compatible(self):
        """Pre-Step-8 records (no evidence/source_types/direction/as_of) render safely."""
        db = SessionLocal()
        research = Research(
            user_id=settings.DEFAULT_USER_ID,
            query="legacy query",
            status=ResearchStatus.COMPLETED,
        )
        db.add(research)
        db.commit()
        db.refresh(research)
        try:
            result = ResearchResult(
                research_id=research.id,
                summary="legacy",
                insights=[],
                trends=[{"trend": "Legacy", "impact": "medium", "description": "Pre-Step-8."}],
                opportunities=[],
                risks=[],
                competitors=[],
            )
            db.add(result)
            db.commit()
            get = client.get(f"/api/research/{research.id}")
            assert get.status_code == 200
            trend = get.json()["result"]["trends"][0]
            assert trend["trend"] == "Legacy"
            assert trend["evidence"] == []
            assert trend["source_types"] == []
            assert trend["direction"] == ""
            assert trend.get("as_of") is None
        finally:
            _cleanup_research(db, research.id)
            db.close()


# --------------------------------------------------------------------------
# Secret safety
# --------------------------------------------------------------------------
class TestSecretSafety:
    def test_no_secret_in_api_output(self, monkeypatch):
        _patch_trend_pipeline(monkeypatch)
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
        finally:
            db = SessionLocal()
            try:
                _cleanup_research(db, body["research_id"])
            finally:
                db.close()
