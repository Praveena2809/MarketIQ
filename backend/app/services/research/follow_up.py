"""
Follow-up Q&A Service (Step 12).

Answers a user's follow-up question about an existing completed research record
using ONLY the stored research context:
- the ResearchResult structured findings (summary, insights, trends,
  competitors, risks, opportunities, sentiment)
- the Source records (title, url, source_name, source_type)

This service performs exactly ONE Gemini LLMService.generate_text() call and
zero other external calls. It never re-runs web/news/document research, RAG,
embeddings, Chroma queries, or search. The original research record is never
modified.

The prompt explicitly requires the model to:
- answer only from the supplied stored research context,
- never invent facts, statistics, dates, URLs, or sources,
- clearly state when the context is insufficient,
- not perform or imply additional research,
- distinguish uncertainty from established findings.

Context is bounded to approximately MAX_CONTEXT_CHARS characters, prioritizing
executive summary, key findings, trends, competitors, risks, opportunities,
sentiment, and source metadata.

Follow-ups are stateless: there is no conversation-history database, and each
call answers from the same stored research context.
"""
from dataclasses import dataclass, field
from typing import List, Optional

from app.models.research import Research
from app.models.research_result import ResearchResult
from app.models.source import Source
from app.schemas.research import FollowUpResponse, SourceSchema
from app.services.llm import get_llm_service

# Bounded prompt budget so the follow-up call stays cheap and deterministic.
MAX_CONTEXT_CHARS = 12000

# Marker phrases the model is instructed to use when the stored context cannot
# support an answer. Detection is case-insensitive substring matching.
INSUFFICIENT_MARKERS = (
    "insufficient evidence",
    "insufficient information",
    "not enough evidence",
    "not enough information",
    "cannot be answered",
    "no evidence in the",
    "context does not contain",
)

FOLLOW_UP_SYSTEM_INSTRUCTION = """You are MarketIQ's Follow-up Research Answer Engine.
You are given a stored market-research report for a previously completed
research job and a follow-up question from the user.

CRITICAL CONSTRAINTS:
1. Answer ONLY from the supplied STORED RESEARCH CONTEXT (the report findings
   and its recorded sources). Treat that context as the complete and only
   source of information for this answer.
2. Never invent facts, statistics, growth figures, percentages, dates, URLs,
   publishers, company names, market claims, or sources that are not present
   in the stored research context.
3. If the stored research context does not contain enough information to
   answer the question, say so explicitly using the phrase
   "insufficient evidence" and explain briefly what evidence would be needed.
4. Do not perform or imply additional research. You have no ability to search
   the web, news, documents, or any other source.
5. Distinguish uncertainty from established findings: clearly mark statements
   you are confident are grounded in the stored context as findings, and label
   anything speculative or uncertain as such (e.g. "the report does not state
   ...").
6. Where the context references a company name, trend, risk, or opportunity,
   you may reference it directly. You may mention which recorded source a
   claim relates to when the context makes that explicit, but never invent a
   URL or a source that is not listed.
7. Answer in clear, direct prose. Do not output JSON."""


@dataclass
class FollowUpResult:
    answer: str = ""
    insufficient_evidence: bool = False
    sources: List[SourceSchema] = field(default_factory=list)


class FollowUpService:
    """Stateless evidence-grounded follow-up answering over a stored research record."""

    def __init__(self):
        self._llm_service = get_llm_service()

    def answer(self, question: str, research: Research) -> FollowUpResult:
        """
        Answer a follow-up question using only the stored research context.
        Raises ValueError on missing result (callers map it to HTTP 400).
        Exactly one generate_text() call when execution reaches the LLM.
        """
        result = research.result
        if result is None:
            raise ValueError("Research has no stored result to answer from.")

        context = _build_context(question, research, result)
        prompt = _build_follow_up_prompt(question, context)
        answer = self._llm_service.generate_text(
            prompt=prompt,
            system_instruction=FOLLOW_UP_SYSTEM_INSTRUCTION,
            temperature=0.3,
        ).strip()

        sources = [SourceSchema.model_validate(s) for s in (research.sources or [])]
        return FollowUpResult(
            answer=answer,
            insufficient_evidence=_flags_insufficient(answer),
            sources=sources,
        )


def _flags_insufficient(answer: str) -> bool:
    """Detect whether the model marked the stored context as insufficient."""
    if not answer:
        return True
    lowered = answer.lower()
    return any(marker in lowered for marker in INSUFFICIENT_MARKERS)


def _build_context(
    question: str,
    research: Research,
    result: ResearchResult,
) -> str:
    """Serialize the stored research context into a single bounded text block."""
    parts: List[str] = []

    def add(label: str, body: str) -> None:
        if body and body.strip():
            parts.append(f"{label}:\n{body.strip()}")

    add("RESEARCH QUESTION", research.query)

    if result.summary:
        add("EXECUTIVE SUMMARY", result.summary)

    if result.insights:
        lines = []
        for item in result.insights:
            finding = item.get("finding") if isinstance(item, dict) else ""
            evidence = item.get("evidence") if isinstance(item, dict) else []
            if finding:
                suffix = f" [evidence: {', '.join(evidence)}]" if evidence else ""
                lines.append(f"- {finding}{suffix}")
        if lines:
            add("KEY FINDINGS", "\n".join(lines))

    if result.trends:
        lines = []
        for t in result.trends:
            if not isinstance(t, dict):
                continue
            name = t.get("trend") or ""
            impact = t.get("impact") or ""
            desc = t.get("description") or ""
            evidence = t.get("evidence") or []
            if name:
                line = f"- {name}"
                if impact:
                    line += f" (impact: {impact})"
                if desc:
                    line += f" - {desc}"
                if evidence:
                    line += f" [evidence: {', '.join(evidence)}]"
                lines.append(line)
        if lines:
            add("TRENDS", "\n".join(lines))

    if result.competitors:
        lines = []
        for c in result.competitors:
            if not isinstance(c, dict):
                continue
            name = c.get("company") or ""
            share = c.get("market_share") or ""
            strengths = c.get("strengths") or []
            weaknesses = c.get("weaknesses") or []
            evidence = c.get("evidence") or []
            if name:
                line = f"- {name}"
                if share:
                    line += f" (market share: {share})"
                if strengths:
                    line += f" | strengths: {'; '.join(strengths)}"
                if weaknesses:
                    line += f" | weaknesses: {'; '.join(weaknesses)}"
                if evidence:
                    line += f" [evidence: {', '.join(evidence)}]"
                lines.append(line)
        if lines:
            add("COMPETITORS", "\n".join(lines))

    if result.risks:
        lines = []
        for rk in result.risks:
            if not isinstance(rk, dict):
                continue
            risk = rk.get("risk") or ""
            severity = rk.get("severity") or ""
            mitigation = rk.get("mitigation") or ""
            if risk:
                line = f"- {risk}"
                if severity:
                    line += f" (severity: {severity})"
                if mitigation:
                    line += f" | mitigation: {mitigation}"
                lines.append(line)
        if lines:
            add("RISKS", "\n".join(lines))

    if result.opportunities:
        lines = []
        for o in result.opportunities:
            if not isinstance(o, dict):
                continue
            opp = o.get("opportunity") or ""
            impact = o.get("potential_impact") or ""
            if opp:
                line = f"- {opp}"
                if impact:
                    line += f" (potential impact: {impact})"
                lines.append(line)
        if lines:
            add("OPPORTUNITIES", "\n".join(lines))

    sentiment = result.sentiment if isinstance(result.sentiment, dict) else {}
    sent_parts: List[str] = []
    if sentiment.get("market_overview"):
        sent_parts.append(f"Market overview: {sentiment['market_overview']}")
    if sentiment.get("conclusion"):
        sent_parts.append(f"Conclusion: {sentiment['conclusion']}")
    sentiments = sentiment.get("sentiments")
    if isinstance(sentiments, dict):
        overall = sentiments.get("overall")
        if isinstance(overall, dict) and overall.get("label"):
            line = f"Overall sentiment: {overall.get('label')}"
            if overall.get("summary"):
                line += f" - {overall['summary']}"
            sent_parts.append(line)
        entities = sentiments.get("entities")
        if isinstance(entities, list):
            for ent in entities:
                if not isinstance(ent, dict):
                    continue
                name = ent.get("entity") or ""
                label = ent.get("label") or ""
                if name and label and label not in ("unavailable", ""):
                    line = f"Entity sentiment for {name}: {label}"
                    if ent.get("summary"):
                        line += f" - {ent['summary']}"
                    sent_parts.append(line)
    if sent_parts:
        add("SENTIMENT", "\n".join(sent_parts))

    sources = research.sources or []
    if sources:
        lines = []
        for i, s in enumerate(sources, start=1):
            url_suffix = f" ({s.url})" if s.url else ""
            lines.append(f"{i}. {s.title} - {s.source_name} [{s.source_type}]{url_suffix}")
        add("RECORDED SOURCES", "\n".join(lines))

    return _bounded_text("\n\n".join(parts))


def _bounded_text(text: str) -> str:
    if len(text) <= MAX_CONTEXT_CHARS:
        return text
    return text[:MAX_CONTEXT_CHARS] + "\n...[stored context truncated]"


def _build_follow_up_prompt(question: str, context: str) -> str:
    return (
        f'USER FOLLOW-UP QUESTION: "{question}"\n\n'
        f"STORED RESEARCH CONTEXT:\n{context}\n\n"
        "Answer the user's follow-up question using ONLY the stored research "
        "context above. Cite which recorded source a claim relates to only when "
        "the context makes that explicit. If the context is insufficient, state "
        '"insufficient evidence" and explain what is missing. Do not perform or '
        "imply additional research. Do not invent facts, statistics, dates, URLs, "
        "or sources. Answer now in clear prose."
    )


_follow_up_service_instance: Optional[FollowUpService] = None


def get_follow_up_service() -> FollowUpService:
    """Singleton getter for FollowUpService."""
    global _follow_up_service_instance
    if _follow_up_service_instance is None:
        _follow_up_service_instance = FollowUpService()
    return _follow_up_service_instance