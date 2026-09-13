"""
Synthesis Service constructing evidence-grounded prompts and enforcing strict JSON output validation.
"""
import json
from typing import Dict, List, Optional
from pydantic import ValidationError

from app.services.llm import get_llm_service
from app.services.research.evidence import Evidence
from app.schemas.research import ResearchSynthesisSchema


SYNTHESIS_SYSTEM_INSTRUCTION = """You are MarketIQ's Executive Market Research Synthesis Engine.
Your task is to analyze the provided evidence and generate a comprehensive, structured market research report in strict JSON format.

CRITICAL CONSTRAINTS:
1. Grounding & Truthfulness: Base your findings strictly on the provided WEB EVIDENCE, NEWS EVIDENCE, and DOCUMENT EVIDENCE. Do NOT invent statistics, market figures, company names, or fake URLs.
2. News Recency Integrity: NEWS EVIDENCE represents RECENT developments. Only attribute a fact to news when a matching news article appears in the NEWS EVIDENCE section, and cite its Evidence ID. If the NEWS EVIDENCE section is empty or marked unavailable, do NOT claim that current news was assessed - instead explicitly note that recent news could not be checked.
3. Citation Integrity: When referencing evidence, include the specific Evidence IDs in key_findings evidence lists.
4. Insufficient Evidence: If web, news, or document evidence is unavailable or insufficient for a section, explicitly state that in the executive_summary or conclusion.
5. Output Format: Output ONLY valid JSON matching the required schema.
6. Competitor Integrity: The COMPETITOR EVIDENCE section is organized as labeled blocks, one per competitor. Produce ONE "competitors" array entry per competitor identified in that section. Ground each competitor's strengths and weaknesses ONLY in that competitor's evidence block and cite its Evidence IDs in the competitor's "evidence" list. If a competitor's evidence block is empty or missing, do NOT invent details - set "market_share" to "N/A" and leave strengths/weaknesses empty. Never invent revenue, market share figures, rankings, prices, dates, URLs, strengths, or weaknesses that are not present in the evidence.

Required JSON Structure:
{
  "executive_summary": "Comprehensive executive summary...",
  "key_findings": [
    {
      "finding": "Specific key finding text...",
      "evidence": ["web_1", "doc_1"]
    }
  ],
  "market_overview": "Detailed market breakdown...",
  "trends": [
    {
      "trend": "Trend title...",
      "impact": "high",
      "description": "Description of trend..."
    }
  ],
  "opportunities": [
    {
      "opportunity": "Opportunity title...",
      "potential_impact": "high"
    }
  ],
  "risks": [
    {
      "risk": "Risk description...",
      "severity": "medium",
      "mitigation": "Possible mitigation..."
    }
  ],
  "competitors": [
    {
      "company": "Company Name",
      "market_share": "N/A",
      "strengths": ["Strength 1"],
      "weaknesses": ["Weakness 1"],
      "evidence": ["comp_company_web_1"]
    }
  ],
  "conclusion": "Final strategic takeaway...",
  "source_ids": ["web_1", "doc_1"]
}"""


def _flatten_competitor_evidence(competitor_contexts: Optional[Dict[str, List[Evidence]]]) -> List[Evidence]:
    """Flatten per-competitor evidence lists into a single list for source_ids."""
    if not competitor_contexts:
        return []
    return [e for items in competitor_contexts.values() for e in items]


def _build_competitor_context(competitor_contexts: Optional[Dict[str, List[Evidence]]]) -> str:
    """Format per-competitor evidence blocks for the synthesis prompt."""
    if not competitor_contexts:
        return "None available."
    sections: List[str] = []
    for name, items in competitor_contexts.items():
        if not items:
            sections.append(f"--- Competitor: {name} ---\nNo additional evidence available for this competitor.")
        else:
            body = "\n\n".join(e.to_prompt_text() for e in items)
            sections.append(f"--- Competitor: {name} ---\n{body}")
    return "\n\n".join(sections)


class SynthesisService:
    def __init__(self):
        self._llm_service = get_llm_service()

    def synthesize(
        self,
        query: str,
        web_evidence: List[Evidence],
        doc_evidence: List[Evidence],
        news_evidence: Optional[List[Evidence]] = None,
        warning_notes: Optional[str] = None,
        competitor_contexts: Optional[Dict[str, List[Evidence]]] = None,
    ) -> ResearchSynthesisSchema:
        """
        Formats evidence into structured prompt context, calls Gemini for synthesis,
        and validates output against Pydantic schema.
        """
        news_evidence = news_evidence or []
        web_context = "\n\n".join([e.to_prompt_text() for e in web_evidence]) if web_evidence else "None available."
        news_context = "\n\n".join([e.to_prompt_text() for e in news_evidence]) if news_evidence else "None available - current news was not checked."
        doc_context = "\n\n".join([e.to_prompt_text() for e in doc_evidence]) if doc_evidence else "None available."
        competitor_context = _build_competitor_context(competitor_contexts)

        warnings_text = f"\nSystem Note: {warning_notes}\n" if warning_notes else ""

        prompt = f"""RESEARCH QUESTION: "{query}"

{warnings_text}
========================================
WEB EVIDENCE:
========================================
{web_context}

========================================
NEWS EVIDENCE:
========================================
{news_context}

========================================
DOCUMENT EVIDENCE:
========================================
{doc_context}

========================================
COMPETITOR EVIDENCE:
========================================
{competitor_context}

Generate the structured JSON market research findings now."""

        try:
            raw_json = self._llm_service.generate_json(
                prompt=prompt,
                system_instruction=SYNTHESIS_SYSTEM_INSTRUCTION,
            )
            return ResearchSynthesisSchema.model_validate_json(raw_json)
        except (ValidationError, json.JSONDecodeError):
            return self._build_fallback_synthesis(
                query, web_evidence, doc_evidence, news_evidence,
                warning_notes, competitor_contexts,
            )

    def _build_fallback_synthesis(
        self,
        query: str,
        web_evidence: List[Evidence],
        doc_evidence: List[Evidence],
        news_evidence: Optional[List[Evidence]] = None,
        warning_notes: Optional[str] = None,
        competitor_contexts: Optional[Dict[str, List[Evidence]]] = None,
    ) -> ResearchSynthesisSchema:
        news_evidence = news_evidence or []
        competitor_evidence = _flatten_competitor_evidence(competitor_contexts)
        evidence_count = len(web_evidence) + len(doc_evidence) + len(news_evidence) + len(competitor_evidence)
        if evidence_count == 0:
            exec_summary = (
                f"Research completed for '{query}', but no evidence was available to support findings. "
                "Insufficient evidence: findings limited to the user query only."
            )
            market_overview = "Insufficient evidence available to provide a market overview."
            conclusion = (
                "Insufficient evidence was available. Add more uploaded documents or retry web research "
                "when Google Search grounding is available."
            )
        else:
            exec_summary = f"Research completed for '{query}'."
            market_overview = (
                "Synthesis produced raw unstructured response. Evidence has been preserved in sources."
            )
            conclusion = "See cited sources for detailed raw evidence."

        if warning_notes:
            exec_summary += f" ({warning_notes})"

        all_sources = [
            e.evidence_id for e in self._flatten_evidence(web_evidence, doc_evidence, news_evidence) + competitor_evidence
        ]

        return ResearchSynthesisSchema(
            executive_summary=exec_summary,
            key_findings=[],
            market_overview=market_overview,
            trends=[],
            opportunities=[],
            risks=[],
            competitors=[],
            conclusion=conclusion,
            source_ids=all_sources,
        )

    @staticmethod
    def _flatten_evidence(web_evidence, doc_evidence, news_evidence):
        return web_evidence + news_evidence + doc_evidence


_synthesis_service_instance = None


def get_synthesis_service() -> SynthesisService:
    global _synthesis_service_instance
    if _synthesis_service_instance is None:
        _synthesis_service_instance = SynthesisService()
    return _synthesis_service_instance
