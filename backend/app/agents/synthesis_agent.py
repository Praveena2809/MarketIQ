"""
Synthesis Agent delegating to SynthesisService for structured Gemini JSON findings.
"""
from typing import List, Optional
from app.services.research.evidence import Evidence
from app.services.research.synthesis import get_synthesis_service
from app.schemas.research import ResearchSynthesisSchema


class SynthesisAgent:
    def __init__(self):
        self.synthesis_service = get_synthesis_service()

    def generate_report(
        self,
        query: str,
        web_evidence: List[Evidence],
        doc_evidence: List[Evidence],
        warning_notes: Optional[str] = None,
        news_evidence: Optional[List[Evidence]] = None,
    ) -> ResearchSynthesisSchema:
        return self.synthesis_service.synthesize(
            query=query,
            web_evidence=web_evidence,
            doc_evidence=doc_evidence,
            news_evidence=news_evidence or [],
            warning_notes=warning_notes,
        )
