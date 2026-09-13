"""
Phase 3 research-engine tests: evidence normalization, web grounding
provenance, document RAG evidence, synthesis schema validation, malformed
output handling, insufficient-evidence fallback, database lifecycle, API
endpoints, and secret non-exposure.

Deterministic unit/component tests mock only the external AI/vector calls.
One live end-to-end test exercises the real API (graceful degradation).
"""
import json
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import get_settings
from app.core.database import init_db, SessionLocal
from app.models.research import Research, ResearchStatus
from app.models.research_result import ResearchResult
from app.models.source import Source
from app.agents.document_research_agent import DocumentResearchAgent
from app.agents.research_agent import ResearchAgent
from app.services.llm import get_llm_service
from app.services.rag import get_rag_service
from app.services.research.web_search import get_web_search_service
from app.services.research.synthesis import get_synthesis_service
from app.services.research.evidence import Evidence
from app.services.research.source_tracker import SourceTracker
from app.services.research.research_engine import get_research_engine

client = TestClient(app)
settings = get_settings()


def setup_module(module):
    init_db()


# --------------------------------------------------------------------------
# Fake google-genai response objects for deterministic grounding tests
# --------------------------------------------------------------------------
class FakeWeb:
    def __init__(self, uri, title):
        self.uri = uri
        self.title = title


class FakeGroundingChunk:
    def __init__(self, web):
        self.web = web


class FakeGroundingMetadata:
    def __init__(self, queries, chunks):
        self.web_search_queries = queries
        self.grounding_chunks = chunks


class FakeCandidate:
    def __init__(self, grounding_metadata=None):
        self.grounding_metadata = grounding_metadata


class FakeGenerateResponse:
    def __init__(self, text, candidates):
        self.text = text
        self.candidates = candidates


class FakeModels:
    def __init__(self, result=None, error=None):
        self._result = result
        self._error = error

    def generate_content(self, **kwargs):
        if self._error is not None:
            raise self._error
        return self._result


class FakeClient:
    def __init__(self, result=None, error=None):
        self.models = FakeModels(result=result, error=error)


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


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------
def test_gemini_configuration():
    assert settings.GEMINI_MODEL, "GEMINI_MODEL must be configured"
    assert settings.GEMINI_API_KEY, "GEMINI_API_KEY must be configured"
    assert settings.EMBEDDING_MODEL == "gemini-embedding-2"
    assert settings.EMBEDDING_DIMENSION == 768
    assert settings.MAX_RESEARCH_QUERIES == 5
    assert settings.MAX_RAG_TOP_K == 5


def test_gemini_research_generation_live():
    """Live: Gemini can produce a JSON payload for a research-style prompt."""
    llm = get_llm_service()
    raw = llm.generate_json('Given the research question "EV market", return JSON: {"ok": true}')
    assert raw.strip()
    data = json.loads(raw)
    assert data.get("ok") is True


# --------------------------------------------------------------------------
# Web search grounding & provenance (deterministic mocks)
# --------------------------------------------------------------------------
def test_web_search_grounding_extracts_real_citations(monkeypatch):
    chunks = [
        FakeGroundingChunk(FakeWeb(uri="https://example.com/ev-report", title="EV Global Report 2026")),
        FakeGroundingChunk(FakeWeb(uri="https://stats.example.org/market", title="Market Statistics")),
    ]
    gm = FakeGroundingMetadata(queries=["EV market size 2026 is what?"], chunks=chunks)
    fake_resp = FakeGenerateResponse(text="EV market is growing.", candidates=[FakeCandidate(gm)])
    llm = get_llm_service()
    monkeypatch.setattr(llm, "_client", FakeClient(result=fake_resp))

    service = get_web_search_service()
    evidence, queries, warning = service.search_web("EV market size")

    assert warning == ""
    assert queries == ["EV market size 2026 is what?"]
    urls = [e.url for e in evidence]
    assert "https://example.com/ev-report" in urls
    assert "https://stats.example.org/market" in urls
    titles = {e.title for e in evidence}
    assert "EV Global Report 2026" in titles
    assert "Market Statistics" in titles
    # Every web item must carry a real grounding URL.
    for e in evidence:
        if e.source_type == "web":
            assert e.url is None or e.url in urls


def test_web_search_summary_preserves_grounded_text(monkeypatch):
    chunks = [FakeGroundingChunk(FakeWeb(uri="https://example.com/a", title="Source A"))]
    gm = FakeGroundingMetadata(queries=["q"], chunks=chunks)
    fake_resp = FakeGenerateResponse(text="Grounded market summary text.", candidates=[FakeCandidate(gm)])
    llm = get_llm_service()
    monkeypatch.setattr(llm, "_client", FakeClient(result=fake_resp))

    evidence, _, warning = get_web_search_service().search_web("q")
    assert warning == ""
    assert evidence[0].content == "Grounded market summary text."
    assert evidence[0].source_type == "web"


def test_web_search_quota_exhaustion_graceful(monkeypatch):
    llm = get_llm_service()
    err = RuntimeError("429 RESOURCE_EXHAUSTED. quota exceeded")
    monkeypatch.setattr(llm, "_client", FakeClient(error=err))

    evidence, queries, warning = get_web_search_service().search_web("EV market")
    assert evidence == []
    assert queries == []
    assert "quota" in warning.lower()


def test_web_search_generic_error_graceful(monkeypatch):
    llm = get_llm_service()
    monkeypatch.setattr(llm, "_client", FakeClient(error=RuntimeError("service unavailable")))

    evidence, queries, warning = get_web_search_service().search_web("EV market")
    assert evidence == []
    assert queries == []
    assert "unavailable" in warning.lower()


# --------------------------------------------------------------------------
# Document RAG evidence
# --------------------------------------------------------------------------
def test_document_rag_evidence_normalization(monkeypatch):
    fake_chunks = [
        {
            "chunk_id": "doc_x_0",
            "chunk_text": "Enterprise AI market reached 50B USD.",
            "document_id": "doc_x",
            "chunk_index": 0,
            "filename": "ai_report.txt",
            "file_type": "txt",
            "relevance_score": 0.91,
        }
    ]
    rag = get_rag_service()
    monkeypatch.setattr(rag, "retrieve", lambda query, top_k=5, document_ids=None: fake_chunks)

    agent = DocumentResearchAgent()
    evidence = agent.gather_document_evidence("enterprise AI market", document_ids=["doc_x"])

    assert len(evidence) == 1
    item = evidence[0]
    assert item.source_type == "document"
    assert item.document_id == "doc_x"
    assert item.filename == "ai_report.txt"
    assert item.chunk_index == 0
    assert item.relevance_score == 0.91
    assert item.content == "Enterprise AI market reached 50B USD."
    assert "ai_report.txt" in item.to_prompt_text()


def test_evidence_normalization_helpers():
    web = Evidence(
        evidence_id="web_1",
        source_type="web",
        title="Web Source",
        url="https://example.com",
        content="content",
    )
    txt = web.to_prompt_text()
    assert "[Evidence ID: web_1]" in txt
    assert "https://example.com" in txt

    doc = Evidence(
        evidence_id="doc_1",
        source_type="document",
        title="Doc",
        document_id="doc_x",
        filename="report.pdf",
        chunk_index=3,
        content="chunk",
    )
    assert "File: report.pdf" in doc.to_prompt_text()
    assert "(Chunk 3)" in doc.to_prompt_text()


# --------------------------------------------------------------------------
# Synthesis schema validation
# --------------------------------------------------------------------------
def test_synthesis_valid_schema_and_evidence_fidelity(monkeypatch):
    captured = {}

    def fake_generate_json(prompt, **kwargs):
        captured["prompt"] = prompt
        return _valid_synthesis_json()

    llm = get_llm_service()
    monkeypatch.setattr(llm, "generate_json", fake_generate_json)

    service = get_synthesis_service()
    web = [Evidence(evidence_id="web_1", source_type="web", title="W", url="https://e.com", content="web ctx")]
    doc = [Evidence(evidence_id="doc_1", source_type="document", title="D", filename="a.pdf", content="doc ctx")]

    report = service.synthesize("question", web, doc)

    assert report.executive_summary == "The enterprise AI market is expanding quickly."
    assert len(report.key_findings) == 1
    assert report.key_findings[0].evidence == ["web_1", "doc_1"]
    assert report.trends[0].impact == "high"
    assert report.competitors[0].company == "Acme Corp"
    assert report.source_ids == ["web_1", "doc_1"]

    # The prompt must carry the normalized evidence, so the LLM is grounded.
    assert "web_1" in captured["prompt"]
    assert "doc_1" in captured["prompt"]
    assert "https://e.com" in captured["prompt"]


def test_synthesis_malformed_gemini_output(monkeypatch):
    llm = get_llm_service()
    monkeypatch.setattr(llm, "generate_json", lambda prompt, **kwargs: "this is not json at all")

    service = get_synthesis_service()
    web = [Evidence(evidence_id="web_1", source_type="web", title="W", url="https://e.com", content="c")]
    report = service.synthesize("q", web, [], warning_notes="web warning")

    # Must fall back gracefully to a valid schema, never raise.
    from app.schemas.research import ResearchSynthesisSchema
    assert isinstance(report, ResearchSynthesisSchema)
    assert "web_1" in report.source_ids


def test_synthesis_insufficient_evidence(monkeypatch):
    llm = get_llm_service()
    # Gemini returns garbage AND no evidence exists -> fallback must flag insufficiency.
    monkeypatch.setattr(llm, "generate_json", lambda prompt, **kwargs: "not json")

    service = get_synthesis_service()
    report = service.synthesize("EV market", [], [], warning_notes="Google Search grounding unavailable.")

    combined = f"{report.executive_summary} {report.market_overview} {report.conclusion}"
    assert "Insufficient evidence" in combined


# --------------------------------------------------------------------------
# Source persistence provenance
# --------------------------------------------------------------------------
def test_source_persistence_only_real_sources():
    db = SessionLocal()
    research = Research(user_id=settings.DEFAULT_USER_ID, query="q", status=ResearchStatus.RUNNING)
    db.add(research)
    db.commit()
    db.refresh(research)
    try:
        evidence_list = [
            Evidence(
                evidence_id="web_1",
                source_type="web",
                title="Real Grounding Source",
                url="https://real.example.com/report",
                content="x",
            ),
            # Synthetic web summary without a URL must NOT become a source.
            Evidence(
                evidence_id="web_summary",
                source_type="web",
                title="Market Overview (synthesized)",
                content="summary",
            ),
            Evidence(
                evidence_id="doc_1",
                source_type="document",
                title="Doc",
                document_id="doc_x",
                filename="uploaded_report.pdf",
                content="c",
                relevance_score=0.8,
            ),
        ]
        saved = SourceTracker.save_sources(db, research.id, evidence_list)
        assert len(saved) == 2

        urls = {s.url for s in saved}
        assert "https://real.example.com/report" in urls
        titles = {s.title for s in saved}
        assert "Market Overview (synthesized)" not in titles

        doc_source = next(s for s in saved if s.source_type == "document")
        assert doc_source.source_name == "uploaded_report.pdf"
        assert doc_source.relevance == 0.8
    finally:
        _cleanup_research(db, research.id)
        db.close()


# --------------------------------------------------------------------------
# Research engine lifecycle
# --------------------------------------------------------------------------
def test_research_engine_completed_lifecycle(monkeypatch):
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
    monkeypatch.setattr(llm, "generate_json", lambda prompt, **kwargs: _valid_synthesis_json())

    db = SessionLocal()
    engine = get_research_engine()
    record = engine.run_research(
        db,
        user_id=settings.DEFAULT_USER_ID,
        query="Test lifecycle query",
        research_type_str="market_analysis",
    )
    try:
        assert record.status == ResearchStatus.COMPLETED
        assert record.error_message is None

        result = db.get(ResearchResult, record.result.id) if record.result else None
        assert result is not None
        assert result.summary == "The enterprise AI market is expanding quickly."
        assert len(result.insights) == 1
        assert len(result.trends) == 1
        assert len(result.competitors) == 1

        sources = db.query(Source).filter(Source.research_id == record.id).all()
        assert len(sources) == 2
        assert {s.source_type for s in sources} == {"web", "document"}
    finally:
        _cleanup_research(db, record.id)
        db.close()


def test_research_engine_failed_lifecycle_no_secret(monkeypatch):
    secret = settings.GEMINI_API_KEY

    def boom(self, query=None, document_ids=None):
        raise RuntimeError(f"internal failure key={secret}")

    monkeypatch.setattr(ResearchAgent, "execute_research", boom)

    db = SessionLocal()
    engine = get_research_engine()
    record = engine.run_research(
        db,
        user_id=settings.DEFAULT_USER_ID,
        query="Query that fails",
    )
    try:
        assert record.status == ResearchStatus.FAILED, "Failed research must not stay running"
        assert record.error_message is not None
        # Crucial: the sanitized error must never leak the API key.
        assert secret not in record.error_message
        assert "[REDACTED]" in record.error_message
    finally:
        _cleanup_research(db, record.id)
        db.close()


def test_failed_research_not_stuck_running_in_db():
    db = SessionLocal()
    try:
        stuck = db.query(Research).filter(Research.status == ResearchStatus.RUNNING).count()
        # No research is ever left in 'running' after engine completion/failure.
        assert stuck == 0
    finally:
        db.close()


# --------------------------------------------------------------------------
# API endpoints (deterministic via mocks)
# --------------------------------------------------------------------------
def test_post_and_get_research_endpoints(monkeypatch):
    ws = get_web_search_service()
    monkeypatch.setattr(
        ws,
        "search_web",
        lambda query: (
            [Evidence(evidence_id="web_1", source_type="web", title="A Web Source",
                      url="https://news.example.com/story", content="web text")],
            ["q"],
            "",
        ),
    )
    rag = get_rag_service()
    monkeypatch.setattr(
        rag,
        "retrieve",
        lambda query, top_k=5, document_ids=None: [
            {"chunk_id": "c1", "chunk_text": "Doc text.", "document_id": "dx",
             "chunk_index": 0, "filename": "f.txt", "file_type": "txt", "relevance_score": 0.9}
        ],
    )
    llm = get_llm_service()
    monkeypatch.setattr(llm, "generate_json", lambda prompt, **kwargs: _valid_synthesis_json())

    post = client.post("/api/research", json={"query": "post endpoint test"})
    assert post.status_code == 201, post.text
    body = post.json()
    assert body["status"] == "completed"
    assert body["research_id"]
    assert body["result"]["executive_summary"]
    assert len(body["result"]["key_findings"]) == 1
    assert len(body["sources"]) == 2

    get = client.get(f"/api/research/{body['research_id']}")
    assert get.status_code == 200
    assert get.json()["research_id"] == body["research_id"]
    assert get.json()["status"] == "completed"

    db = SessionLocal()
    try:
        _cleanup_research(db, body["research_id"])
    finally:
        db.close()


def test_get_research_404():
    res = client.get("/api/research/does-not-exist")
    assert res.status_code == 404


def test_post_research_empty_query():
    res = client.post("/api/research", json={"query": "   "})
    assert res.status_code == 400


def test_recent_research_endpoint_shape():
    res = client.get("/api/research/recent")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    if data:
        assert "id" in data[0]
        assert "query" in data[0]
        assert "status" in data[0]
        assert "updated_at" in data[0]


def test_secrets_never_exposed_in_responses():
    key = settings.GEMINI_API_KEY
    for path in ("/api/health", "/api/stats", "/api/research/recent"):
        r = client.get(path)
        assert key not in r.text

    invalid = "/" + str(uuid.uuid4())
    r = client.get(f"/api/research/{invalid}")
    assert r.status_code == 404
    assert key not in r.text


# --------------------------------------------------------------------------
# Live end-to-end (uses real API, graceful degradation expected)
# --------------------------------------------------------------------------
def test_live_end_to_end_research():
    """Real POST /api/research must persist and never hang in 'running'."""
    post = client.post(
        "/api/research",
        json={"query": "What is the outlook for generative AI in healthcare for the next year?"},
    )
    assert post.status_code == 201, post.text
    body = post.json()
    research_id = body["research_id"]
    assert research_id

    get = client.get(f"/api/research/{research_id}")
    assert get.status_code == 200
    data = get.json()

    # The lifecycle must always settle — never stuck mid-flight.
    assert data["status"] in ("completed", "failed")
    assert data["status"] != "running"

    if data["status"] == "completed":
        assert data["result"] is not None
        assert data["result"]["executive_summary"]
        # Result must be persisted (fetchable again).
        again = client.get(f"/api/research/{research_id}")
        assert again.status_code == 200
        assert again.json()["status"] == "completed"
    else:
        assert data["error_message"]

    # Never expose the API key anywhere in the response.
    assert settings.GEMINI_API_KEY not in get.text