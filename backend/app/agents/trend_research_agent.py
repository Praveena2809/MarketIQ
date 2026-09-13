"""
Trend Research Agent.

Thin orchestrator around the TrendAnalysisService. It is invoked by the
ResearchAgent after web/news/document/competitor/sentiment evidence has been
produced. It performs exactly ONE Gemini generate_json call (via the trend
service) and NO other external calls - it never re-runs web/news/document/
competitor research, RAG, embeddings, Google Search, or any other provider.
"""
from dataclasses import dataclass, field
from typing import List, Optional

from app.schemas.research import TrendItem
from app.services.research.evidence import Evidence
from app.services.research.trend_analysis import TrendAnalysisService


@dataclass
class TrendResearchResult:
    trends: List[TrendItem] = field(default_factory=list)
    warning: Optional[str] = None
    notes: List[str] = field(default_factory=list)
    # True when the trend pass completed a deterministic run to determination
    # (verified list is authoritative, possibly empty). False on insufficient
    # evidence, quota, exception, or malformed output -> callers preserve the
    # synthesis-produced trends as a fail-soft fallback.
    success: bool = False


class TrendResearchAgent:
    """Evidence-grounded, qualitative trend extraction over the existing pool."""

    def __init__(self):
        self._analysis_service = TrendAnalysisService()

    def execute_trend_research(
        self,
        query: str,
        evidence_pool: List[Evidence],
    ) -> TrendResearchResult:
        """
        Returns a TrendResearchResult. `trends` may legitimately be empty when
        the pass succeeded and verified zero evidence-supported trends; the
        caller replaces the synthesis default with that empty result whenever
        `success` is True. On any non-deterministic outcome `success` is False
        and `trends` is empty so the caller preserves the synthesis-default
        trends.
        """
        trends, warning, success = self._analysis_service.analyze(
            query=query,
            evidence=evidence_pool,
        )
        result = TrendResearchResult(
            trends=trends,
            warning=warning,
            success=success,
        )
        if warning:
            result.notes.append(warning)
        return result