"""
Coordinator Research Agent orchestrating Web Research, News Research, Document RAG,
Competitor Research, and Synthesis.
"""
from typing import List, Optional, Tuple
from app.agents.web_research_agent import WebResearchAgent
from app.agents.news_research_agent import NewsResearchAgent
from app.agents.document_research_agent import DocumentResearchAgent
from app.agents.competitor_research_agent import CompetitorResearchAgent
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
        5. Synthesizes findings using Gemini.
        6. Returns structured report and all combined evidence.
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

        # 5. Synthesize report grounded in web + news + document + competitor evidence
        report = self.synthesis_agent.generate_report(
            query=query,
            web_evidence=web_evidence,
            news_evidence=news_evidence,
            doc_evidence=doc_evidence,
            competitor_contexts=competitor_research.contexts,
            warning_notes=_combine_warnings(
                warning_note, news_warning, competitor_research.warning,
            ),
        )

        all_evidence = existing_evidence + competitor_research.evidence
        return report, all_evidence