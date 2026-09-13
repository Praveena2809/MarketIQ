"""
Coordinator Research Agent orchestrating Web Research, News Research, Document RAG,
Evidence Normalization, and Synthesis.
"""
from typing import List, Optional, Tuple
from app.agents.web_research_agent import WebResearchAgent
from app.agents.news_research_agent import NewsResearchAgent
from app.agents.document_research_agent import DocumentResearchAgent
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
        4. Combines evidence into a normalized list.
        5. Synthesizes findings using Gemini.
        6. Returns structured report and all combined evidence.
        """
        # 1. Gather web evidence
        web_evidence, warning_note = self.web_agent.gather_web_evidence(query)

        # 2. Gather recent news evidence
        news_evidence, news_warning = self.news_agent.gather_news_evidence(query)

        # 3. Gather document evidence
        doc_evidence = self.doc_agent.gather_document_evidence(query, document_ids=document_ids)

        # 4. Synthesize report grounded in web + news + document evidence
        report = self.synthesis_agent.generate_report(
            query=query,
            web_evidence=web_evidence,
            news_evidence=news_evidence,
            doc_evidence=doc_evidence,
            warning_notes=_combine_warnings(warning_note, news_warning),
        )

        all_evidence = web_evidence + news_evidence + doc_evidence
        return report, all_evidence