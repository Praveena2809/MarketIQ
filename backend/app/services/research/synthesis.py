"""
Synthesis Service constructing evidence-grounded prompts and enforcing strict JSON output validation.
"""
import json
from typing import List, Optional
from pydantic import ValidationError

from app.services.llm import get_llm_service
from app.services.research.evidence import Evidence
from app.schemas.research import ResearchSynthesisSchema


SYNTHESIS_SYSTEM_INSTRUCTION = """You are MarketIQ's Executive Market Research Synthesis Engine.
Your task is to analyze the provided evidence and generate a comprehensive, structured market research report in strict JSON format.

CRITICAL CONSTRAINTS:
1. Grounding & Truthfulness: Base your findings strictly on the provided WEB EVIDENCE and DOCUMENT EVIDENCE. Do NOT invent statistics, market figures, company names, or fake URLs.
2. Citation Integrity: When referencing evidence, include the specific Evidence IDs in key_findings evidence lists.
3. Insufficient Evidence: If web or document evidence is unavailable or insufficient for a section, explicitly state that in the executive_summary or conclusion.
4. Output Format: Output ONLY valid JSON matching the required schema.

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
      "market_share": "Estimated share or N/A",
      "strengths": ["Strength 1"],
      "weaknesses": ["Weakness 1"]
    }
  ],
  "conclusion": "Final strategic takeaway...",
  "source_ids": ["web_1", "doc_1"]
}"""


class SynthesisService:
    def __init__(self):
        self._llm_service = get_llm_service()

    def synthesize(
        self,
        query: str,
        web_evidence: List[Evidence],
        doc_evidence: List[Evidence],
        warning_notes: Optional[str] = None,
    ) -> ResearchSynthesisSchema:
        """
        Formats evidence into structured prompt context, calls Gemini for synthesis, and validates output against Pydantic schema.
        """
        web_context = "\n\n".join([e.to_prompt_text() for e in web_evidence]) if web_evidence else "None available."
        doc_context = "\n\n".join([e.to_prompt_text() for e in doc_evidence]) if doc_evidence else "None available."

        warnings_text = f"\nSystem Note: {warning_notes}\n" if warning_notes else ""

        prompt = f"""RESEARCH QUESTION: "{query}"

{warnings_text}
========================================
WEB EVIDENCE:
========================================
{web_context}

========================================
DOCUMENT EVIDENCE:
========================================
{doc_context}

Generate the structured JSON market research findings now."""

        try:
            raw_json = self._llm_service.generate_json(
                prompt=prompt,
                system_instruction=SYNTHESIS_SYSTEM_INSTRUCTION,
            )
            return ResearchSynthesisSchema.model_validate_json(raw_json)
        except (ValidationError, json.JSONDecodeError) as e:
            # Safe recovery fallback
            return self._build_fallback_synthesis(query, web_evidence, doc_evidence, warning_notes)

    def _build_fallback_synthesis(
        self,
        query: str,
        web_evidence: List[Evidence],
        doc_evidence: List[Evidence],
        warning_notes: Optional[str],
    ) -> ResearchSynthesisSchema:
        evidence_count = len(web_evidence) + len(doc_evidence)
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

        all_sources = [e.evidence_id for e in web_evidence + doc_evidence]

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


_synthesis_service_instance = None


def get_synthesis_service() -> SynthesisService:
    global _synthesis_service_instance
    if _synthesis_service_instance is None:
        _synthesis_service_instance = SynthesisService()
    return _synthesis_service_instance
