"""
Coordinator Research Agent orchestrating Web Research, News Research, Document RAG,
Competitor Research, and Synthesis.
"""
from typing import List, Optional, Tuple
from app.agents.web_research_agent import WebResearchAgent
from app.agents.news_research_agent import NewsResearchAgent
from app.agents.document_research_agent import DocumentResearchAgent
from app.agents.competitor_research_agent import CompetitorResearchAgent
from app.agents.sentiment_research_agent import SentimentResearchAgent
from app.agents.trend_research_agent import TrendResearchAgent
from app.agents.synthesis_agent import SynthesisAgent
from app.services.research.evidence import Evidence
from app.schemas.research import ResearchSynthesisSchema


def _combine_warnings(*warnings: Optional[str]) -> Optional[str]:
    """Join non-empty warnings from the evidence gatherers into a single note."""
    merged = " | ".join(w.strip() for w in warnings if w and w.strip())
    return merged if merged else None


class ResearchAgent:
    def __init__(self):
        self.web_agent = WebResearchAgent()
        self.news_agent = NewsResearchAgent()
        self.doc_agent = DocumentResearchAgent()
        self.competitor_agent = CompetitorResearchAgent()
        self.sentiment_agent = SentimentResearchAgent()
        self.trend_agent = TrendResearchAgent()
        self.synthesis_agent = SynthesisAgent()

    def execute_research(
        self,
        query: str,
        document_ids: Optional[List[str]] = None,
    ) -> Tuple[ResearchSynthesisSchema, List[Evidence]]:
        """
        1. Gathers web evidence (Google Search grounding).
        2. Gathers recent news evidence (configured news provider).
        3. Gathers document evidence (Phase 2 RAG).
        4. Runs competitor research over the combined existing evidence pool.
        5. Runs categorical, evidence-grounded sentiment analysis over the
           combined evidence pool (web + news + document + competitor).
        6. Runs evidence-grounded trend analysis over the same combined pool.
        7. Synthesizes findings using Gemini.
        8. Returns structured report and all combined evidence.

        Trend behavior (Step 8): verified trends from step 6 REPLACE the
        synthesis-produced trends whenever the trend pass completes
        successfully, including when it verifiably finds zero evidence-
        supported trends (replaced with an empty list). Only on an
        unsuccessful trend pass (insufficient evidence, quota, exception,
        malformed output) are the synthesis-produced trends preserved as the
        fail-soft fallback, with an honest warning merged into the report's
        warning notes.
        """
        # 1. Gather web evidence
        web_evidence, warning_note = self.web_agent.gather_web_evidence(query)

        # 2. Gather recent news evidence
        news_evidence, news_warning = self.news_agent.gather_news_evidence(query)

        # 3. Gather document evidence
        doc_evidence = self.doc_agent.gather_document_evidence(query, document_ids=document_ids)

        # 4. Identify competitors from the gathered evidence and, only where
        #    necessary and bounded, collect focused per-competitor evidence.
        #    The initial web/news/document passes are NOT repeated here.
        existing_evidence = web_evidence + news_evidence + doc_evidence
        competitor_research = self.competitor_agent.execute_competitor_research(
            query=query,
            existing_evidence=existing_evidence,
            document_ids=document_ids,
        )

        all_evidence = existing_evidence + competitor_research.evidence

        # 5. Categorical, evidence-grounded sentiment over the combined pool.
        #    Exactly one Gemini call; no new evidence is gathered.
        sentiment_research = self.sentiment_agent.execute_sentiment_analysis(
            query=query,
            evidence_pool=all_evidence,
            competitors=competitor_research.identified,
        )

        # 6. Evidence-grounded trend analysis over the same combined pool.
        #    Exactly one Gemini call; no new evidence is gathered.
        trend_research = self.trend_agent.execute_trend_research(
            query=query,
            evidence_pool=all_evidence,
        )

        # 7. Synthesize report grounded in web + news + document + competitor evidence
        report = self.synthesis_agent.generate_report(
            query=query,
            web_evidence=web_evidence,
            news_evidence=news_evidence,
            doc_evidence=doc_evidence,
            competitor_contexts=competitor_research.contexts,
            warning_notes=_combine_warnings(
                warning_note, news_warning, competitor_research.warning,
                sentiment_research.warning, trend_research.warning,
            ),
        )

        # 7b. Attach sentiment (additive optional field; None stays a no-op).
        report.sentiment = sentiment_research.sentiment

        # 8. Successful trend pass wins, including an empty verified result
        #    (no evidence-supported trends). Unsuccessful passes leave the
        #    synthesis-produced trends as the fail-soft fallback.
        if trend_research.success:
            report.trends = trend_research.trends

        return report, all_evidence