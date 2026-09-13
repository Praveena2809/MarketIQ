"""
Insight & Recommendation Research Agent.

Thin orchestrator around the InsightAnalysisService. It is invoked by the
ResearchAgent after web/news/document/competitor/sentiment/trend evidence and
the verified analytical outputs have been produced. It performs exactly ONE
Gemini generate_json call (via the insight service) and NO other external
calls - it never re-runs web/news/document/competitor research, RAG,
embeddings, or search.
"""
from dataclasses import dataclass, field
from typing import List, Optional

from app.schemas.research import KeyFindingItem, RecommendationItem, SentimentSchema, TrendItem
from app.services.research.evidence import Evidence
from app.services.research.insight_analysis import InsightAnalysisService


@dataclass
class InsightResearchResult:
    insights: List[KeyFindingItem] = field(default_factory=list)
    recommendations: List[RecommendationItem] = field(default_factory=list)
    warning: Optional[str] = None
    notes: List[str] = field(default_factory=list)
    # True when the insight pass completed a deterministic run to determination
    # (the verified lists are authoritative, possibly empty). False on
    # insufficient evidence, quota, exception, or malformed output -> callers
    # preserve the synthesis-produced key_findings and leave recommendations
    # empty as a fail-soft fallback.
    success: bool = False


class InsightResearchAgent:
    """Evidence-grounded insight and recommendation extraction over the pool."""

    def __init__(self):
        self._analysis_service = InsightAnalysisService()

    def execute_insight_research(
        self,
        query: str,
        evidence_pool: List[Evidence],
        competitors: Optional[List[str]] = None,
        trends: Optional[List[TrendItem]] = None,
        sentiment: Optional[SentimentSchema] = None,
    ) -> InsightResearchResult:
        """
        Returns an InsightResearchResult. `insights`/`recommendations` may
        legitimately be empty when the pass succeeded and verified zero
        evidence-supported items; the caller replaces the synthesis default
        key_findings and fills recommendations whenever `success` is True. On
        any non-deterministic outcome `success` is False and both lists are
        empty so the caller preserves the synthesis-produced key_findings and
        leaves recommendations empty.

        `trends` must only contain verified trends from a successful trend
        pass; pass None when the dedicated trend pass was unavailable.
        """
        insights, recommendations, warning, success = self._analysis_service.analyze(
            query=query,
            evidence=evidence_pool,
            competitors=competitors,
            trends=trends,
            sentiment=sentiment,
        )
        result = InsightResearchResult(
            insights=insights,
            recommendations=recommendations,
            warning=warning,
            success=success,
        )
        if warning:
            result.notes.append(warning)
        return result