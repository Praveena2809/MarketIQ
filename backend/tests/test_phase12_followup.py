"""
Phase 12 regression tests: the follow-up Q&A endpoint
(POST /api/research/{research_id}/follow-up).

Deterministic: truncates the research tables at module start, seeds Research /
ResearchResult / Source rows directly (no external/AI calls), and mocks the
LLM service so no live Gemini call is made. Verifies the 404/400 validation
behavior, route ordering, response shape, secret non-exposure, successful and
insufficient-evidence answers with a mocked LLM, that the LLM is called exactly
once per valid follow-up, and that no web/news/RAG/embedding/Chroma retrieval
path is exercised.

Run with: venv/bin/python -m pytest tests/test_phase12_followup.py
"""
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.core.config import get_settings
from app.core.database import init_db, SessionLocal
from app.models.research import Research, ResearchStatus, ResearchType
from app.models.research_result import ResearchResult
from app.models.source import Source
from app.services.research import follow_up as follow_up_module
from app.services.research.follow_up import get_follow_up_service

client = TestClient(app)
settings = get_settings()

FOLLOW_UP_PATH = "/api/research/research-followup-1/follow-up"


class FakeLLM:
    """Recorded fake standing in for LLMService.generate_text."""

    def __init__(self, text=""):
        self.text = text
        self.calls = []

    def generate_text(self, *, prompt, system_instruction=None, temperature=None):
        self.calls.append(
            {
                "prompt": prompt,
                "system_instruction": system_instruction,
                "temperature": temperature,
            }
        )
        return self.text


def setup_module(module):
    init_db()
    _clear_tables()


def teardown_module(module):
    _clear_tables()


def _clear_tables():
    db = SessionLocal()
    try:
        db.query(Source).delete()
        db.query(ResearchResult).delete()
        db.query(Research).delete()
        db.commit()
    finally:
        db.close()


def _seed_research(
    status=ResearchStatus.COMPLETED,
    with_result=True,
    with_sources=True,
):
    db = SessionLocal()
    try:
        r = Research(
            id="research-followup-1",
            user_id=settings.DEFAULT_USER_ID,
            query="Acme widget market analysis",
            research_type=ResearchType.MARKET_ANALYSIS,
            status=status,
        )
        db.add(r)
        db.flush()
        if with_result:
            db.add(
                ResearchResult(
                    research_id=r.id,
                    summary="Acme operates in a growing widget market.",
                    insights=[
                        {"finding": "Widget demand is rising.", "evidence": ["web_1"]},
                        {"finding": "Raw material costs are rising.", "evidence": ["news_2"]},
                    ],
                    risks=[
                        {"risk": "Raw material costs are volatile.", "severity": "medium"},
                    ],
                    opportunities=[
                        {"opportunity": "Expand into adjacent region.", "potential_impact": "high"},
                    ],
                    trends=[
                        {
                            "trend": "Factory automation adoption rising.",
                            "impact": "high",
                            "description": "Manufacturers are automating.",
                            "evidence": ["web_1"],
                        },
                    ],
                    competitors=[
                        {
                            "company": "Globex",
                            "market_share": "N/A",
                            "strengths": ["Distribution scale"],
                            "weaknesses": ["Limited product range"],
                            "evidence": ["comp_globex_web_1"],
                        },
                    ],
                    sentiment={
                        "market_overview": "Positive overall growth outlook.",
                        "conclusion": "Optimistic near term.",
                        "sentiments": None,
                    },
                )
            )
        if with_sources:
            db.add(
                Source(
                    id="source-followup-1",
                    research_id=r.id,
                    title="Widget Market Report 2026",
                    url="https://example.com/widgets",
                    source_name="Example Analytics",
                    source_type="web",
                )
            )
            db.add(
                Source(
                    id="source-followup-2",
                    research_id=r.id,
                    title="Quarterly News Briefing",
                    url="https://example.com/news/quarterly",
                    source_name="Example Wire",
                    source_type="news",
                )
            )
        db.commit()
        return r.id
    finally:
        db.close()


def _patch_llm(fake):
    svc = get_follow_up_service()
    patcher = patch.object(svc, "_llm_service", fake)
    patcher.start()
    return patcher


def test_follow_up_nonexistent_research_404():
    res = client.post(
        "/api/research/does-not-exist/follow-up",
        json={"question": "What risks exist?"},
    )
    assert res.status_code == 404


def test_follow_up_failed_research_400():
    _seed_research(status=ResearchStatus.FAILED)
    try:
        res = client.post(FOLLOW_UP_PATH, json={"question": "What risks exist?"})
        assert res.status_code == 400
        assert "completed" in res.json()["detail"]
    finally:
        _clear_tables()


def test_follow_up_running_research_400():
    _seed_research(status=ResearchStatus.RUNNING)
    try:
        res = client.post(FOLLOW_UP_PATH, json={"question": "What risks exist?"})
        assert res.status_code == 400
        assert "completed" in res.json()["detail"]
    finally:
        _clear_tables()


def test_follow_up_completed_without_result_400():
    _seed_research(status=ResearchStatus.COMPLETED, with_result=False)
    try:
        res = client.post(FOLLOW_UP_PATH, json={"question": "What risks exist?"})
        assert res.status_code == 400
        assert "result" in res.json()["detail"]
    finally:
        _clear_tables()


def test_follow_up_empty_question_400():
    _seed_research(status=ResearchStatus.COMPLETED)
    try:
        for question in ("", "   "):
            res = client.post(FOLLOW_UP_PATH, json={"question": question})
            assert res.status_code == 400
            assert "cannot be empty" in res.json()["detail"]
    finally:
        _clear_tables()


def test_follow_up_route_ordering_guard():
    """GET /api/research/history must still be the list route, and the
    POST follow-up route must not be shadowed by the dynamic {research_id}."""
    res = client.get("/api/research/history")
    assert res.status_code == 200
    assert isinstance(res.json(), list)

    res = client.post(
        "/api/research/history/follow-up",
        json={"question": "Any question"},
    )
    assert res.status_code == 404


def test_follow_up_response_shape_with_mocked_llm():
    _seed_research(status=ResearchStatus.COMPLETED)
    fake = FakeLLM("The main risks are rising input costs.")
    patcher = _patch_llm(fake)
    try:
        res = client.post(FOLLOW_UP_PATH, json={"question": "What risks exist?"})
        assert res.status_code == 200
        body = res.json()
        assert set(body) == {"answer", "insufficient_evidence", "sources"}
        assert body["answer"] == "The main risks are rising input costs."
        assert body["insufficient_evidence"] is False
        assert len(body["sources"]) == 2
        src = body["sources"][0]
        assert set(src) >= {
            "id",
            "research_id",
            "title",
            "url",
            "source_name",
            "source_type",
            "relevance",
            "is_mock",
            "published_at",
        }
    finally:
        patcher.stop()
        _clear_tables()


def test_follow_up_success_uses_stored_context_only():
    _seed_research(status=ResearchStatus.COMPLETED)
    fake = FakeLLM("Acme competes with Globex, which has distribution scale.")
    patcher = _patch_llm(fake)
    try:
        res = client.post(FOLLOW_UP_PATH, json={"question": "Who are the competitors?"})
        assert res.status_code == 200
        prompt = fake.calls[0]["prompt"]
        assert "STORED RESEARCH CONTEXT" in prompt
        assert "Globex" in prompt
        assert "Widget Market Report 2026" in prompt
        assert "https://example.com/widgets" in prompt
    finally:
        patcher.stop()
        _clear_tables()


def test_follow_up_insufficient_evidence_with_mocked_llm():
    _seed_research(status=ResearchStatus.COMPLETED)
    fake = FakeLLM(
        "The stored context provides insufficient evidence to answer the "
        "question about historical pricing trends."
    )
    patcher = _patch_llm(fake)
    try:
        res = client.post(FOLLOW_UP_PATH, json={"question": "Historical pricing?"})
        assert res.status_code == 200
        body = res.json()
        assert body["insufficient_evidence"] is True
        assert "insufficient evidence" in body["answer"]
    finally:
        patcher.stop()
        _clear_tables()


def test_follow_up_llm_called_exactly_once():
    _seed_research(status=ResearchStatus.COMPLETED)
    fake = FakeLLM("A grounded answer.")
    patcher = _patch_llm(fake)
    try:
        res = client.post(FOLLOW_UP_PATH, json={"question": "Summary?"})
        assert res.status_code == 200
        assert res.json()["answer"] == "A grounded answer."
        assert len(fake.calls) == 1
        assert fake.calls[0]["temperature"] == 0.3
        assert fake.calls[0]["system_instruction"] is not None
    finally:
        patcher.stop()
        _clear_tables()


def test_follow_up_no_web_news_rag_embedding_calls():
    _seed_research(status=ResearchStatus.COMPLETED)
    fake = FakeLLM("Answer derived purely from stored context.")
    patcher = _patch_llm(fake)

    def _raise_if_used(*args, **kwargs):
        raise AssertionError("An external research/retrieval path was exercised")

    import app.services.rag as rag_mod
    import app.services.embeddings as emb_mod
    import app.services.vector_store as vs_mod

    rag_patch = patch.object(rag_mod, "get_rag_service", side_effect=_raise_if_used)
    emb_patch = patch.object(emb_mod, "get_embedding_service", side_effect=_raise_if_used)
    vs_patch = patch.object(vs_mod, "get_vector_store_service", side_effect=_raise_if_used)
    rag_patch.start()
    emb_patch.start()
    vs_patch.start()
    try:
        res = client.post(FOLLOW_UP_PATH, json={"question": "Any question?"})
        assert res.status_code == 200
        assert res.json()["answer"] == "Answer derived purely from stored context."
        assert len(fake.calls) == 1
    finally:
        vs_patch.stop()
        emb_patch.stop()
        rag_patch.stop()
        patcher.stop()
        _clear_tables()


def test_follow_up_secret_non_exposure():
    """The Gemini and News API keys must never appear in the follow-up response."""
    _seed_research(status=ResearchStatus.COMPLETED)
    fake = FakeLLM("Secret-safe answer.")
    patcher = _patch_llm(fake)
    try:
        res = client.post(FOLLOW_UP_PATH, json={"question": "My question?"})
        assert res.status_code == 200
        assert settings.GEMINI_API_KEY not in res.text
        if settings.NEWS_API_KEY:
            assert settings.NEWS_API_KEY not in res.text
    finally:
        patcher.stop()
        _clear_tables()


def test_follow_up_system_instruction_requires_grounding():
    """The system instruction must forbid fabrication, require an explicit
    insufficient-evidence statement, and force answers from stored context only."""
    instruction = follow_up_module.FOLLOW_UP_SYSTEM_INSTRUCTION
    assert "invent" in instruction
    assert "STORED RESEARCH CONTEXT" in instruction
    assert "ONLY from" in instruction
    assert "insufficient evidence" in instruction
    assert "no ability to search" in instruction