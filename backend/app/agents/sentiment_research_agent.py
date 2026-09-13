"""
Sentiment Research Agent.

Thin orchestrator around the SentimentAnalysisService. It is invoked by the
ResearchAgent after web/news/document/competitor evidence has been gathered.
It performs exactly ONE Gemini generate_json call (via the sentiment service)
and NO other external calls - it never re-runs web/news/document/competitor
research, RAG, embeddings, or search.
"""
from dataclasses import dataclass, field
from typing import List, Optional

from app.schemas.research import SentimentSchema
from app.services.research.evidence import Evidence
from app.services.research.sentiment_analysis import SentimentAnalysisService


@dataclass
class SentimentResearchResult:
    sentiment: Optional[SentimentSchema] = None
    warning: Optional[str] = None
    notes: List[str] = field(default_factory=list)


class SentimentResearchAgent:
    """Categorical, evidence-grounded sentiment over the existing evidence pool."""

    def __init__(self):
        self._analysis_service = SentimentAnalysisService()

    def execute_sentiment_analysis(
        self,
        query: str,
        evidence_pool: List[Evidence],
        competitors: Optional[List[str]] = None,
    ) -> SentimentResearchResult:
        """
        Returns a SentimentResearchResult. The sentiment schema is always
        populated (possibly an honest "unavailable" result), and a warning is
        returned when sentiment could not be fully assessed.
        """
        eligible_entities = list(competitors or [])
        sentiment, warning = self._analysis_service.analyze(
            query=query,
            evidence=evidence_pool,
            eligible_entities=eligible_entities,
        )
        result = SentimentResearchResult(sentiment=sentiment, warning=warning)
        if warning:
            result.notes.append(warning)
        return result