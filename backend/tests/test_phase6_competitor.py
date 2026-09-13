"""
Step 6 competitor-research tests: evidence-only identification, strict
evidence-containment, bounded/zero focused gathering, re-tagged per-competitor
evidence, competitor-grounded synthesis, source provenance/dedupe, pipeline
integration, API regression, secret non-exposure, and phase 1-5 smoke.

Deterministic: every external call (Gemini, web grounding, RAG, news provider)
is mocked. Call-count spies verify the minimal-call budget for the initial
web/news/document passes (exactly once) and for focused per-competitor passes.
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
from app.agents.competitor_research_agent import CompetitorResearchAgent
from app.agents.research_agent import ResearchAgent
from app.services.llm import get_llm_service
from app.services.news.news_provider import get_news_provider
from app.services.rag import get_rag_service
from app.services.research.competitor_identification import (
    CompetitorIdentificationService,
    _parse_names,
)
from app.services.research.evidence import Evidence
from app.services.research.source_tracker import SourceTracker
from app.services.research.synthesis import get_synthesis_service
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
    """Real-shaped web/document evidence whose text mentions two companies."""
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
    ]


def _valid_synthesis_json(evidence_ids=None, competitors=None):
    evidence_ids = evidence_ids or ["web_1", "doc_1"]
    if competitors is None:
        competitors = [
            {"company": "Acme Corp", "market_share": "N/A", "strengths": ["X"], "weaknesses": ["Y"]}
        ]
    return json.dumps({
        "executive_summary": "The enterprise AI market is expanding quickly.",
        "key_findings": [
            {"finding": "AI adoption is growing.", "evidence": evidence_ids}
        ],
        "market_overview": "A detailed overview grounded in evidence.",
        "trends": [{"trend": "Agentic AI", "impact": "high", "description": "Rising interest."}],
        "opportunities": [{"opportunity": "Automation", "potential_impact": "high"}],
        "risks": [{"risk": "Regulation", "severity": "medium", "mitigation": "Monitor."}],
        "competitors": competitors,
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


def _patch_full_pipeline(monkeypatch):
    """Mocks every external service and returns a call counter dict."""
    counters = {"web": 0, "news_get": 0, "rag": 0, "gen_json": 0, "gen_text": 0}

    ws = get_web_search_service()

    def fake_search(query):
        counters["web"] += 1
        return ([_nav_evidence()[0]], ["query"], "")

    monkeypatch.setattr(ws, "search_web", fake_search)

    rag = get_rag_service()

    def fake_retrieve(query, top_k=5, document_ids=None):
        counters["rag"] += 1
        return [{"chunk_id": "d_0", "chunk_text": "Tata Motors and Ola Electric are among the leading EV makers.",
                 "document_id": "d1", "chunk_index": 0, "filename": "ev_report.txt",
                 "file_type": "txt", "relevance_score": 0.9}]

    monkeypatch.setattr(rag, "retrieve", fake_retrieve)

    llm = get_llm_service()
    # Used by the news agent to derive focused queries (query-level and focused).
    monkeypatch.setattr(llm, "generate_text", lambda prompt, **kw: "electric vehicle India")

    def fake_generate_json(prompt, **kw):
        counters["gen_json"] += 1
        return _valid_synthesis_json(
            evidence_ids=["web_1", "doc_1", "news_1"],
            competitors=[{
                "company": "Tata Motors",
                "market_share": "N/A",
                "strengths": ["Expanding EV lineup"],
                "weaknesses": [],
                "evidence": ["comp_tata-motors_news_1"],
            }],
        )

    monkeypatch.setattr(llm, "generate_json", fake_generate_json)

    monkeypatch.setattr(settings, "NEWS_API_KEY", FAKE_NEWS_KEY)
    provider = get_news_provider()

    def fake_get_json(params):
        counters["news_get"] += 1
        return SAMPLE_PAYLOAD

    monkeypatch.setattr(provider, "_get_json", fake_get_json)
    return counters


# --------------------------------------------------------------------------
# Phase 1-3-5 regression smoke
# --------------------------------------------------------------------------
def test_phase1_2_3_5_regressions():
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
# Identification: evidence-only, no external calls
# --------------------------------------------------------------------------
def test_identification_uses_existing_evidence_only(monkeypatch):
    captured = {}
    llm = get_llm_service()

    def fake_generate_json(prompt, **kw):
        captured["prompt"] = prompt
        captured["schema"] = kw.get("schema")
        captured["si"] = kw.get("system_instruction")
        return json.dumps({"competitors": [{"name": "Tata Motors"}, {"name": "Ola Electric"}]})

    monkeypatch.setattr(llm, "generate_json", fake_generate_json)

    # Prove identification never touches external services.
    news_calls = {"n": 0}
    provider = get_news_provider()
    monkeypatch.setattr(provider, "fetch_recent",
                        lambda q: (news_calls.__setitem__("n", news_calls["n"] + 1) or ([], "")))
    web_calls = {"w": 0}
    ws = get_web_search_service()
    monkeypatch.setattr(ws, "search_web",
                        lambda q: (web_calls.__setitem__("w", web_calls["w"] + 1) or ([], [], "")))

    svc = CompetitorIdentificationService()
    names, warning = svc.identify("Analyze the Indian EV market", _nav_evidence())

    assert names == ["Tata Motors", "Ola Electric"]
    assert warning is None
    assert news_calls["n"] == 0 and web_calls["w"] == 0
    # Prompt consumes only the provided evidence pool.
    assert "https://example.com/tata-ev" in captured["prompt"]
    assert "web_1" in captured["prompt"]
    assert "Tata Motors and Ola Electric" in captured["prompt"]
    # Structured-output schema is passed for deterministic JSON.
    assert isinstance(captured["schema"], dict)
    assert captured["schema"]["required"] == ["competitors"]
    assert "Competitor Identification Engine" in (captured["si"] or "")


def test_identification_containment_filters_unverified_names(monkeypatch):
    llm = get_llm_service()
    monkeypatch.setattr(llm, "generate_json", lambda prompt, **kw: json.dumps({
        "competitors": [
            {"name": "Tata Motors"},
            {"name": "FakeCorp Inc"},        # never mentioned in evidence
            {"name": "Ola Electric"},        # duplicated below
            {"name": "Ola Electric"},
        ]
    }))
    svc = CompetitorIdentificationService()
    names, warning = svc.identify("EV market", _nav_evidence())
    assert names == ["Tata Motors", "Ola Electric"]
    assert "FakeCorp Inc" not in names
    assert warning is None


def test_identification_accepts_company_key_and_plain_strings(monkeypatch):
    llm = get_llm_service()
    monkeypatch.setattr(llm, "generate_json", lambda prompt, **kw: json.dumps({
        "competitors": [{"company": "Tata Motors"}, "Ola Electric"]
    }))
    svc = CompetitorIdentificationService()
    names, _ = svc.identify("EV market", _nav_evidence())
    assert names == ["Tata Motors", "Ola Electric"]
    assert _parse_names(json.dumps({"competitors": []})) == []
    assert _parse_names("not json") == []


def test_identification_no_competitors_reports_honest_warning(monkeypatch):
    llm = get_llm_service()
    monkeypatch.setattr(llm, "generate_json", lambda prompt, **kw: '{"competitors": []}')
    svc = CompetitorIdentificationService()
    names, warning = svc.identify("EV market", _nav_evidence())
    assert names == []
    assert warning and "No competitors" in warning


def test_identification_llm_failure_fails_soft(monkeypatch):
    llm = get_llm_service()
    monkeypatch.setattr(llm, "generate_json",
                        lambda prompt, **kw: (_ for _ in ()).throw(RuntimeError("boom")))
    svc = CompetitorIdentificationService()
    names, warning = svc.identify("EV market", _nav_evidence())
    assert names == []
    assert warning and "No competitors" in warning


def test_identification_empty_evidence_returns_early(monkeypatch):
    svc = CompetitorIdentificationService()
    names, warning = svc.identify("EV market", [])
    assert names == []
    assert "No evidence" in warning


def test_identification_filters_malformed_names(monkeypatch):
    llm = get_llm_service()
    long_name = "Super" + "X" * 100
    monkeypatch.setattr(llm, "generate_json", lambda prompt, **kw: json.dumps({
        "competitors": [
            {"name": "Tata Motors"},
            {"name": "!!!!Not A Real Company!!!!"},
            {"name": long_name},
            {"name": 123},
        ]
    }))
    svc = CompetitorIdentificationService()
    names, _ = svc.identify("EV market", _nav_evidence())
    assert names == ["Tata Motors"]


# --------------------------------------------------------------------------
# Competitor Research Agent: bounded focused gathering
# --------------------------------------------------------------------------
def test_agent_bounds_competitor_count(monkeypatch):
    monkeypatch.setattr(settings, "MAX_COMPETITORS", 2)
    monkeypatch.setattr(settings, "NEWS_API_KEY", FAKE_NEWS_KEY)
    monkeypatch.setattr(settings, "COMPETITOR_FOCUSED_WEB_SEARCH", False)

    agent = CompetitorResearchAgent()
    monkeypatch.setattr(agent.identifier, "identify", lambda q, ev: (
        ["A Corp", "B Corp", "C Corp", "D Corp", "E Corp"], None))

    seen = []
    agent.news_agent.gather_news_evidence = lambda q: (seen.append(q) or ([], None))

    result = agent.execute_competitor_research("q", _nav_evidence(), document_ids=None)
    assert result.identified == ["A Corp", "B Corp"]
    # Focused gathering runs only for the bounded set.
    assert seen == ["A Corp", "B Corp"]


def test_agent_news_focused_per_competitor(monkeypatch):
    monkeypatch.setattr(settings, "NEWS_API_KEY", FAKE_NEWS_KEY)
    monkeypatch.setattr(settings, "COMPETITOR_FOCUSED_WEB_SEARCH", False)

    agent = CompetitorResearchAgent()
    monkeypatch.setattr(agent.identifier, "identify", lambda q, ev: (
        ["Tata Motors", "Ola Electric"], None))

    seen = []
    agent.news_agent.gather_news_evidence = lambda q: (seen.append(q) or ([
        Evidence(evidence_id="local", source_type="news", title="n",
                 url=f"https://n.example/{len(seen)}", content="c"),
    ], None))

    result = agent.execute_competitor_research(
        "Analyze the Indian EV market", _nav_evidence(), document_ids=None)

    # Focused news queries are the competitor name, never the full question.
    assert seen == ["Tata Motors", "Ola Electric"]
    assert [e.evidence_id for e in result.evidence] == [
        "comp_tata-motors_news_1", "comp_ola-electric_news_1"]


def test_agent_doc_focused_only_when_documents(monkeypatch):
    monkeypatch.setattr(settings, "NEWS_API_KEY", "")
    monkeypatch.setattr(settings, "COMPETITOR_FOCUSED_WEB_SEARCH", False)

    agent = CompetitorResearchAgent()
    monkeypatch.setattr(agent.identifier, "identify", lambda q, ev: (["Tata Motors"], None))

    doc_calls = []
    agent.doc_agent.gather_document_evidence = (
        lambda q, document_ids=None: (doc_calls.append(q) or [
            Evidence(evidence_id="local", source_type="document", title="D",
                     content="Tata Motors details", document_id="d1",
                     filename="r.pdf", chunk_index=0),
        ]))

    # No attached documents -> no RAG calls at all.
    agent.execute_competitor_research("q", _nav_evidence(), document_ids=None)
    assert doc_calls == []

    # With attached documents -> exactly one focused call per competitor.
    agent.execute_competitor_research("q", _nav_evidence(), document_ids=["d1"])
    assert len(doc_calls) == 1
    assert "Tata Motors" in doc_calls[0]


def test_agent_web_zero_by_default(monkeypatch):
    monkeypatch.setattr(settings, "NEWS_API_KEY", "")
    monkeypatch.setattr(settings, "COMPETITOR_FOCUSED_WEB_SEARCH", False)

    agent = CompetitorResearchAgent()
    monkeypatch.setattr(agent.identifier, "identify", lambda q, ev: (["Tata Motors"], None))

    web_calls = []
    agent.web_agent.gather_web_evidence = lambda q: (web_calls.append(q) or ([], None))

    result = agent.execute_competitor_research("q", _nav_evidence(), document_ids=None)
    assert web_calls == []
    assert result.evidence == []


def test_agent_web_focused_only_for_gaps(monkeypatch):
    monkeypatch.setattr(settings, "NEWS_API_KEY", "")
    monkeypatch.setattr(settings, "COMPETITOR_FOCUSED_WEB_SEARCH", True)

    agent = CompetitorResearchAgent()
    monkeypatch.setattr(agent.identifier, "identify", lambda q, ev: (["Tata Motors"], None))

    web_calls = []
    agent.web_agent.gather_web_evidence = lambda q: (web_calls.append(q) or ([], None))

    # Tata Motors already covered by web/news evidence -> no focused web call.
    covered = [Evidence("web_1", "web", "Tata Motors news", "Tata Motors boosted EV output.",
                        url="https://e.com/tata")]
    agent.execute_competitor_research("EV market", covered, document_ids=None)
    assert web_calls == []

    # Only document coverage -> web gap -> exactly one focused web call.
    agent.execute_competitor_research("EV market",
                                      [Evidence("doc_1", "document", "D", "Tata Motors mentioned.",
                                                filename="x.pdf")],
                                      document_ids=None)
    assert len(web_calls) == 1
    assert "Tata Motors" in web_calls[0]


def test_agent_scoped_ids_and_url_dedupe(monkeypatch):
    monkeypatch.setattr(settings, "NEWS_API_KEY", FAKE_NEWS_KEY)
    monkeypatch.setattr(settings, "COMPETITOR_FOCUSED_WEB_SEARCH", False)

    agent = CompetitorResearchAgent()
    monkeypatch.setattr(agent.identifier, "identify", lambda q, ev: (["A Corp", "B Corp"], None))

    shared = Evidence("shared", "news", "Shared article", "c", url="https://share.example/a")
    agent.news_agent.gather_news_evidence = lambda q: ([shared], None)

    result = agent.execute_competitor_research("q", _nav_evidence(), document_ids=None)

    # The shared URL is attached to A Corp only; B Corp deduped by URL.
    assert len(result.evidence) == 1
    assert result.evidence[0].evidence_id == "comp_a-corp_news_1"
    assert len(result.contexts["A Corp"]) == 1
    assert len(result.contexts["B Corp"]) == 0


def test_agent_graceful_when_focused_unavailable(monkeypatch):
    monkeypatch.setattr(settings, "NEWS_API_KEY", "")
    monkeypatch.setattr(settings, "COMPETITOR_FOCUSED_WEB_SEARCH", False)

    agent = CompetitorResearchAgent()
    monkeypatch.setattr(agent.identifier, "identify", lambda q, ev: (["Tata Motors"], None))

    result = agent.execute_competitor_research(
        "q", [Evidence("web_1", "web", "Tata Motors", "Tata Motors competes.",
                       url="https://e.com/tata")],
        document_ids=None)
    assert result.identified == ["Tata Motors"]
    assert result.evidence == []
    assert result.warning and "rely on the original research evidence" in result.warning


def test_agent_no_competitors_honest_degradation(monkeypatch):
    agent = CompetitorResearchAgent()
    monkeypatch.setattr(agent.identifier, "identify", lambda q, ev: (
        [], "No competitors could be identified from available evidence."))
    result = agent.execute_competitor_research(
        "q", [Evidence("doc_1", "document", "D", "No companies mentioned.",
                       filename="x.pdf")])
    assert result.identified == []
    assert result.evidence == []
    assert result.warning and "No competitors" in result.warning


def test_focused_query_bounds_context_length():
    long_question = "Analyze " + "the Indian EV market really thoroughly " * 20
    focused = CompetitorResearchAgent._focused_query(long_question, "Tata Motors")
    assert "Tata Motors" in focused
    assert len(focused) <= 400
    # The unbounded question is truncated before being embedded.
    assert len(focused) < len(long_question)


# --------------------------------------------------------------------------
# Synthesis: competitor-grounded, no fabrication
# --------------------------------------------------------------------------
def test_synthesis_prompt_includes_competitor_blocks(monkeypatch):
    captured = {}
    llm = get_llm_service()
    monkeypatch.setattr(llm, "generate_json", lambda prompt, **kw: (
        captured.update(prompt=prompt) or _valid_synthesis_json()))

    service = get_synthesis_service()
    comp = {
        "Tata Motors": [
            Evidence("comp_tata-motors_news_1", "news", "Tata Motors article",
                     "Tata Motors reported strong EV sales.",
                     url="https://n.example/tata", publisher="Reuters",
                     published_at="2026-09-10T00:00:00Z"),
        ]
    }
    service.synthesize("q", [], [], competitor_contexts=comp)

    prompt = captured["prompt"]
    assert "COMPETITOR EVIDENCE:" in prompt
    assert "--- Competitor: Tata Motors ---" in prompt
    assert "comp_tata-motors_news_1" in prompt
    assert "https://n.example/tata" in prompt


def test_synthesis_instruction_grounds_competitors(monkeypatch):
    captured = {}
    llm = get_llm_service()
    monkeypatch.setattr(llm, "generate_json", lambda prompt, system_instruction=None, **kw: (
        captured.update(si=system_instruction) or _valid_synthesis_json()))

    service = get_synthesis_service()
    service.synthesize("q", [], [], competitor_contexts={
        "A Corp": [Evidence("comp_a-corp_doc_1", "document", "D", "c", filename="x.pdf")],
    })

    si = captured["si"] or ""
    assert "Competitor Integrity" in si
    assert 'set "market_share" to "N/A"' in si
    assert '"evidence" list' in si
    assert "Never invent" in si


def test_synthesis_competitor_evidence_survives_validation(monkeypatch):
    llm = get_llm_service()
    payload = _valid_synthesis_json(competitors=[{
        "company": "Tata Motors", "market_share": "N/A",
        "strengths": ["EV leadership"], "weaknesses": [],
        "evidence": ["comp_tata-motors_news_1"],
    }])
    monkeypatch.setattr(llm, "generate_json", lambda prompt, **kw: payload)

    service = get_synthesis_service()
    comp = {"Tata Motors": [Evidence("comp_tata-motors_news_1", "news", "T", "c",
                                     url="https://n.example/t")]}
    report = service.synthesize("q", [], [], competitor_contexts=comp)
    assert report.competitors[0].company == "Tata Motors"
    assert report.competitors[0].evidence == ["comp_tata-motors_news_1"]


def test_synthesis_fallback_counts_competitor_evidence(monkeypatch):
    llm = get_llm_service()
    monkeypatch.setattr(llm, "generate_json", lambda prompt, **kw: "this is not json")

    service = get_synthesis_service()
    comp = {"A Corp": [Evidence("comp_a-corp_doc_1", "document", "D", "c",
                                filename="r.pdf")]}
    report = service.synthesize("q", [], [], competitor_contexts=comp)
    assert "comp_a-corp_doc_1" in report.source_ids
    assert report.executive_summary


# --------------------------------------------------------------------------
# Source provenance & dedupe
# --------------------------------------------------------------------------
def test_competitor_source_persistence_provenance():
    db = SessionLocal()
    research = Research(user_id=settings.DEFAULT_USER_ID, query="q", status=ResearchStatus.RUNNING)
    db.add(research)
    db.commit()
    db.refresh(research)
    try:
        evidence_list = [
            Evidence("comp_a-corp_web_1", "web", "A Corp reporting", "c",
                     url="https://a.example/r"),
            Evidence("comp_a-corp_web_2", "web", "A Corp summary", "no url"),  # URL-less web skipped
            Evidence("comp_a-corp_news_1", "news", "A Corp news", "c",
                     url="https://n.example/t", publisher="Reuters",
                     published_at="2026-09-10T00:00:00Z"),
            Evidence("comp_a-corp_doc_1", "document", "Uploaded report", "c",
                     document_id="d1", filename="competitors.pdf"),
            Evidence("comp_b-corp_web_1", "web", "A Corp reporting", "c",
                     url="https://a.example/r"),  # URL duplicate of first web item
        ]
        saved = SourceTracker.save_sources(db, research.id, evidence_list)

        assert len(saved) == 3
        urls = {s.url for s in saved if s.url}
        assert urls == {"https://a.example/r", "https://n.example/t"}
        assert {s.source_type for s in saved} == {"web", "news", "document"}
        doc_row = next(s for s in saved if s.source_type == "document")
        assert doc_row.source_name == "competitors.pdf"
        assert all(s.is_mock is False for s in saved)
    finally:
        _cleanup_research(db, research.id)
        db.close()


# --------------------------------------------------------------------------
# Pipeline integration / API
# --------------------------------------------------------------------------
def test_research_agent_initial_passes_run_exactly_once(monkeypatch):
    monkeypatch.setattr(settings, "NEWS_API_KEY", "")
    monkeypatch.setattr(settings, "COMPETITOR_FOCUSED_WEB_SEARCH", False)

    agent = ResearchAgent()
    calls = {"web": 0, "news": 0, "doc": 0, "comp_web": 0, "comp_news": 0, "comp_doc": 0}

    web_evidence = [Evidence("web_1", "web", "Tata Motors", "Tata Motors leads the EV market.",
                             url="https://example.com/tata")]

    agent.web_agent.gather_web_evidence = lambda q: (calls.__setitem__("web", calls["web"] + 1) or (web_evidence, None))
    agent.news_agent.gather_news_evidence = lambda q: (calls.__setitem__("news", calls["news"] + 1) or ([], None))
    agent.doc_agent.gather_document_evidence = lambda q, document_ids=None: (calls.__setitem__("doc", calls["doc"] + 1) or [])

    competitor = agent.competitor_agent
    competitor.web_agent.gather_web_evidence = lambda q: (calls.__setitem__("comp_web", calls["comp_web"] + 1) or ([], None))
    competitor.news_agent.gather_news_evidence = lambda q: (calls.__setitem__("comp_news", calls["comp_news"] + 1) or ([], None))
    competitor.doc_agent.gather_document_evidence = lambda q, document_ids=None: (calls.__setitem__("comp_doc", calls["comp_doc"] + 1) or [])

    # Identification would surface two names; focused gathering is all-disabled.
    competitor.identifier.identify = lambda q, ev: (["Tata Motors", "Ola Electric"], None)

    llm = get_llm_service()
    monkeypatch.setattr(llm, "generate_json", lambda prompt, **kw: _valid_synthesis_json(["web_1"]))

    report, all_evidence = agent.execute_research("Analyze the Indian EV market")

    # Initial query-level passes happen exactly once each.
    assert calls["web"] == 1 and calls["news"] == 1 and calls["doc"] == 1
    # The competitor agent never re-runs the query-level passes (no web toggle,
    # no news key, no attached documents).
    assert calls["comp_web"] == 0 and calls["comp_news"] == 0 and calls["comp_doc"] == 0
    assert all_evidence == web_evidence
    assert report is not None


def test_research_engine_competitor_analysis_e2e(monkeypatch):
    counters = _patch_full_pipeline(monkeypatch)

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
        assert record.research_type.value == "competitor_analysis"

        # Bounded call budget:
        # initial web pass exactly once; focused web skipped (toggle off).
        assert counters["web"] == 1
        # query-level news (1) + focused news for the single competitor (1).
        assert counters["news_get"] == 2
        # query-level RAG (1) + focused RAG for the single competitor (1).
        assert counters["rag"] == 2
        # identification + synthesis + sentiment (Step 7) + trend (Step 8)
        # happen once each.
        assert counters["gen_json"] == 4

        sources = db.query(Source).filter(Source.research_id == record.id).all()
        types = {s.source_type for s in sources}
        assert types == {"web", "document", "news"}
        # web(1) + news(2) + document(1); competitor-scoped items either share
        # URLs/titles with query-level evidence or are URL-less and deduped.
        assert len(sources) == 4

        result = db.get(ResearchResult, record.result.id) if record.result else None
        assert result is not None
        assert result.competitors[0]["company"] == "Tata Motors"
        assert result.competitors[0]["evidence"] == ["comp_tata-motors_news_1"]
    finally:
        _cleanup_research(db, record.id)
        db.close()


def test_research_engine_graceful_when_providers_unavailable(monkeypatch):
    monkeypatch.setattr(settings, "NEWS_API_KEY", "")
    monkeypatch.setattr(settings, "COMPETITOR_FOCUSED_WEB_SEARCH", False)

    ws = get_web_search_service()
    monkeypatch.setattr(ws, "search_web", lambda q: ([], [], "Google Search grounding quota exceeded."))
    rag = get_rag_service()
    monkeypatch.setattr(rag, "retrieve", lambda query, top_k=5, document_ids=None: [])
    llm = get_llm_service()
    monkeypatch.setattr(llm, "generate_text", lambda prompt, **kw: "EV market")
    monkeypatch.setattr(llm, "generate_json", lambda prompt, **kw: _valid_synthesis_json(competitors=[]))

    db = SessionLocal()
    engine = get_research_engine()
    record = engine.run_research(
        db,
        user_id=settings.DEFAULT_USER_ID,
        query="Analyze the Indian EV market",
    )
    try:
        assert record.status == ResearchStatus.COMPLETED
        sources = db.query(Source).filter(Source.research_id == record.id).all()
        assert sources == []
        result = db.get(ResearchResult, record.result.id) if record.result else None
        assert result is not None
        assert result.competitors == []
    finally:
        _cleanup_research(db, record.id)
        db.close()


def test_research_api_competitor_analysis_endpoint(monkeypatch):
    _patch_full_pipeline(monkeypatch)

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
        assert body["research_type"] == "competitor_analysis"
        assert body["result"]["competitors"][0]["company"] == "Tata Motors"
        assert body["result"]["competitors"][0]["evidence"] == ["comp_tata-motors_news_1"]
        types = {s["source_type"] for s in body["sources"]}
        assert types == {"web", "document", "news"}

        get = client.get(f"/api/research/{research_id}")
        assert get.status_code == 200
        assert get.json()["research_id"] == research_id
        assert get.json()["result"]["competitors"][0]["evidence"]
    finally:
        db = SessionLocal()
        try:
            _cleanup_research(db, research_id)
        finally:
            db.close()


def test_secrets_never_exposed_with_competitor_flow(monkeypatch):
    _patch_full_pipeline(monkeypatch)

    for path in ("/api/health", "/api/stats", "/api/research/recent"):
        res = client.get(path)
        assert res.status_code == 200
        assert FAKE_NEWS_KEY not in res.text
        if settings.GEMINI_API_KEY:
            assert settings.GEMINI_API_KEY not in res.text

    post = client.post("/api/research", json={
        "query": "electric vehicle market",
        "research_type": "competitor_analysis",
    })
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


def test_competitor_error_path_redacts_keys(monkeypatch):
    monkeypatch.setattr(settings, "NEWS_API_KEY", FAKE_NEWS_KEY)
    monkeypatch.setattr(settings, "COMPETITOR_FOCUSED_WEB_SEARCH", False)
    gem = settings.GEMINI_API_KEY

    ws = get_web_search_service()
    monkeypatch.setattr(ws, "search_web",
                        lambda q: ([Evidence("web_1", "web", "Tata Motors",
                                             "Tata Motors competes.",
                                             url="https://e.com/tata")], ["q"], ""))
    rag = get_rag_service()
    monkeypatch.setattr(rag, "retrieve", lambda query, top_k=5, document_ids=None: [])
    llm = get_llm_service()
    monkeypatch.setattr(llm, "generate_text", lambda prompt, **kw: "EV market")

    def boom(prompt, **kw):
        raise RuntimeError(f"provider failure key={FAKE_NEWS_KEY} gem={gem}")

    monkeypatch.setattr(llm, "generate_json", boom)

    db = SessionLocal()
    engine = get_research_engine()
    record = engine.run_research(
        db,
        user_id=settings.DEFAULT_USER_ID,
        query="Analyze the Indian EV market",
    )
    try:
        # Identification fails soft and is swallowed; the synthesis failure is
        # recorded with both keys redacted - no secrets reach the database.
        assert record.status == ResearchStatus.FAILED
        error_msg = record.error_message or ""
        assert FAKE_NEWS_KEY not in error_msg
        if gem:
            assert gem not in error_msg
        assert "[REDACTED]" in error_msg
    finally:
        _cleanup_research(db, record.id)
        db.close()