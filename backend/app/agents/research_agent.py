"""
Coordinator Research Agent orchestrating Web Research, Document RAG, Evidence Normalization, and Synthesis.
"""
from typing import List, Optional, Tuple
from app.agents.web_research_agent import WebResearchAgent
from app.agents.document_research_agent import DocumentResearchAgent
from app.agents.synthesis_agent import SynthesisAgent
from app.services.research.evidence import Evidence
from app.schemas.research import ResearchSynthesisSchema


class ResearchAgent:
    def __init__(self):
        self.web_agent = WebResearchAgent()
        self.doc_agent = DocumentResearchAgent()
        self.synthesis_agent = SynthesisAgent()

    def execute_research(
        self,
        query: str,
        document_ids: Optional[List[str]] = None,
    ) -> Tuple[ResearchSynthesisSchema, List[Evidence]]:
        """
        1. Gathers web evidence (Google Search grounding).
        2. Gathers document evidence (Phase 2 RAG).
        3. Combines evidence into a normalized list.
        4. Synthesizes findings using Gemini.
        5. Returns structured report and all combined evidence.
        """
        # 1. Gather web evidence
        web_evidence, warning_note = self.web_agent.gather_web_evidence(query)

        # 2. Gather document evidence
        doc_evidence = self.doc_agent.gather_document_evidence(query, document_ids=document_ids)

        # 3. Synthesize report
        report = self.synthesis_agent.generate_report(
            query=query,
            web_evidence=web_evidence,
            doc_evidence=doc_evidence,
            warning_notes=warning_note,
        )

        all_evidence = web_evidence + doc_evidence
        return report, all_evidence
