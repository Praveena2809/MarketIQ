"""
Competitor Identification Service.

Consumes ONLY the already-gathered research evidence pool (web + news + document
evidence produced by the ResearchAgent) and extracts the company names that are
explicitly mentioned in it. Strict evidence-containment is enforced: no
candidate name survives unless it appears verbatim in the provided evidence
text, so competitor names are never fabricated or pulled from hardcoded lists.

This module never performs any external search/provider calls - it works purely
from the evidence it is handed.
"""
import json
import re
from typing import List, Optional, Tuple

from app.services.llm import get_llm_service
from app.services.research.evidence import Evidence

# Structured-output schema for the identification call. Kept as an inline JSON
# Schema so it is accepted across Gemini versions (no $ref/$defs).
IDENTIFICATION_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "competitors": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
        }
    },
    "required": ["competitors"],
}

# Bounded prompt budget so identification stays cheap and deterministic.
MAX_IDENTIFICATION_EVIDENCE_ITEMS = 40
MAX_IDENTIFICATION_CHARS = 12000

VALID_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 &.,'\-()/]{1,79}$")

IDENTIFICATION_SYSTEM_INSTRUCTION = """You are MarketIQ's Competitor Identification Engine.
You are given a market-research question and the evidence already collected for it.

CRITICAL CONSTRAINTS:
1. Identify only the companies that are EXPLICITLY mentioned in the provided EVIDENCE as competitors or market participants.
2. Never invent a company, brand, or trading name that is not present in the evidence.
3. Use the exact company name as it appears in the evidence.
4. A company mentioned only in passing as a historical/factual reference is still acceptable; the rule is that the name must be present in the evidence.
5. If no companies are identifiable from the evidence, return an empty competitors list.
6. Output ONLY valid JSON in this exact shape:
   {"competitors": [{"name": "Company Name"}, {"name": "Another Company"}]}"""


class CompetitorIdentificationService:
    """Extracts and verifies competitor names from the existing evidence pool."""

    def __init__(self):
        self._llm_service = get_llm_service()

    def identify(
        self,
        query: str,
        evidence: List[Evidence],
    ) -> Tuple[List[str], Optional[str]]:
        """
        Returns:
            - Verified competitor names (each appears verbatim in `evidence`),
              bounded only by length; the caller applies MAX_COMPETITORS.
            - Warning string (None if competitors were identified).
        """
        if not evidence:
            return [], "No evidence was available to identify competitors."

        prompt = _build_identification_prompt(query, evidence)
        candidates: List[str] = []
        try:
            raw_json = self._llm_service.generate_json(
                prompt=prompt,
                schema=IDENTIFICATION_JSON_SCHEMA,
                system_instruction=IDENTIFICATION_SYSTEM_INSTRUCTION,
            )
            candidates = _parse_names(raw_json)
        except Exception:
            candidates = []

        if not candidates:
            return [], "No competitors could be identified from available evidence."

        verified = _verify_names_against_evidence(candidates, evidence)
        if not verified:
            return [], (
                "Competitor names suggested by the model could not be verified "
                "against the available evidence; no competitors were retained."
            )

        return verified, None


def _build_identification_prompt(query: str, evidence: List[Evidence]) -> str:
    items = evidence[:MAX_IDENTIFICATION_EVIDENCE_ITEMS]
    text = "\n\n".join(e.to_prompt_text() for e in items)
    if len(text) > MAX_IDENTIFICATION_CHARS:
        text = text[:MAX_IDENTIFICATION_CHARS] + "\n...[truncated]"
    return (
        f'RESEARCH QUESTION: "{query}"\n\n'
        f"PROVIDED EVIDENCE:\n{text}\n\n"
        "Identify the competitors explicitly mentioned in the evidence above. "
        "Return the JSON now."
    )


def _parse_names(raw_json: str) -> List[str]:
    """Parse the identification JSON. Accepts {"competitors": [{"name": ...}]}
    or a flexibly-shaped competitors array (name/company keys, or plain strings)."""
    try:
        data = json.loads(raw_json or "")
    except (json.JSONDecodeError, TypeError):
        return []

    raw = data.get("competitors") if isinstance(data, dict) else None
    if not isinstance(raw, list):
        return []

    names: List[str] = []
    for item in raw:
        if isinstance(item, dict):
            name = item.get("name") or item.get("company")
        elif isinstance(item, str):
            name = item
        else:
            name = None
        if not name or not isinstance(name, str):
            continue
        name = " ".join(name.split()).strip()
        if not VALID_NAME_RE.match(name) or len(name) > 80:
            continue
        names.append(name)
    return names


def _verify_names_against_evidence(candidates: List[str], evidence: List[Evidence]) -> List[str]:
    """
    Strict evidence-containment: a competitor name must appear verbatim in the
    title or content of at least one evidence item. Case-insensitive substring
    match on the concatenated evidence pool.
    """
    corpus = " ".join(f"{e.title} {e.content}" for e in evidence).lower()
    seen = set()
    verified: List[str] = []
    for name in candidates:
        key = name.lower()
        if key in seen or key not in corpus:
            continue
        seen.add(key)
        verified.append(name)
    return verified