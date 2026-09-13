"""
Trend Analysis Service.

Consumes ONLY the already-gathered evidence pool (web + news + document +
competitor evidence produced by the ResearchAgent) and extracts the
evidence-grounded trends explicitly supported by it. Trends are strictly
qualitative - impact (high/medium/low) and an optional direction
(rising/stable/declining/mixed) are labels, never numeric scores, growth
percentages, or confidence values.

Every cited Evidence ID must exist in the supplied pool; fabricated/unknown
IDs are dropped. source_types are derived server-side from the verified
Evidence IDs via the shared resolve_evidence_source_type helper so the
web / news / document / competitor distinctions are preserved. A trend with
no surviving evidence IDs is dropped entirely. as_of is kept ONLY when it
exactly matches the published_at of a cited news evidence item.

This module performs exactly ONE Gemini generate_json call and zero other
external calls. On empty evidence it returns an honest "insufficient
evidence" result without calling Gemini at all.
"""
import json
from typing import Dict, List, Optional, Tuple

from app.schemas.research import TrendItem
from app.services.llm import get_llm_service
from app.services.research.evidence import Evidence, resolve_evidence_source_type

# Inline JSON Schema (no $ref/$defs) so it is accepted across Gemini versions.
TREND_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "trends": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "trend": {"type": "string"},
                    "impact": {"type": "string"},
                    "description": {"type": "string"},
                    "direction": {"type": "string"},
                    "evidence": {"type": "array", "items": {"type": "string"}},
                    "as_of": {"type": "string"},
                },
                "required": ["trend", "impact", "evidence"],
            },
        }
    },
    "required": ["trends"],
}

# Bounded prompt budget so the trend call stays cheap and deterministic.
MAX_TREND_EVIDENCE_ITEMS = 40
MAX_TREND_CHARS = 12000
# Cap on trends requested / retained per job (bounded output, no open loop).
MAX_TRENDS = 8

# The only labels the engine ever emits.
VALID_TREND_IMPACT = frozenset({"high", "medium", "low"})
VALID_TREND_DIRECTIONS = frozenset({"rising", "stable", "declining", "mixed"})

TREND_SYSTEM_INSTRUCTION = """You are MarketIQ's Trend Analysis Engine.
You are given a market-research question and the evidence already collected
for it.

CRITICAL CONSTRAINTS:
1. Identify at most 8 emerging trends that the PROVIDED EVIDENCE explicitly
   supports. Never invent trends.
2. Every trend MUST cite at least one Evidence ID that appears in the
   PROVIDED EVIDENCE. Never cite an Evidence ID that is not present.
3. Never invent statistics, growth percentages, confidence scores,
   probabilities, dates, sources, URLs, publishers, or market claims.
4. "impact" is qualitative ONLY: high, medium, or low.
5. "direction" (optional) is ONLY: rising, stable, declining, or mixed, and
   ONLY when the evidence actually supports a direction; otherwise omit it.
6. "as_of" (optional) ONLY when the exact published date of a cited news
   item supports it; never invent or guess a date.
7. Output ONLY valid JSON in this exact shape:
   {"trends": [{"trend": "...", "impact": "high", "description": "...",
                "direction": "rising", "evidence": ["news_1"],
                "as_of": "2026-09-10T08:30:00Z"}]}"""


class TrendAnalysisService:
    """Evidence-grounded, qualitative trend extraction over the existing pool."""

    def __init__(self):
        self._llm_service = get_llm_service()

    def analyze(
        self,
        query: str,
        evidence: List[Evidence],
    ) -> Tuple[List[TrendItem], Optional[str], bool]:
        """
        Returns (verified TrendItems, warning, success).

        success=True means the trend agent completed a deterministic run to
        determination: the verified list is authoritative and may be empty
        (no evidence-supported trends). success=False means the result is
        non-deterministic (insufficient evidence, quota, exception, malformed
        output), so callers fall back to synthesis-produced trends.
        Empty evidence never triggers a Gemini call.
        """
        if not evidence:
            return [], "Trend analysis unavailable: insufficient evidence.", False

        prompt = _build_trend_prompt(query, evidence)
        try:
            raw_json = self._llm_service.generate_json(
                prompt=prompt,
                schema=TREND_JSON_SCHEMA,
                system_instruction=TREND_SYSTEM_INSTRUCTION,
            )
            trends = _parse_and_verify(raw_json, evidence)
        except Exception as exc:
            err = str(exc)
            if "RESOURCE_EXHAUSTED" in err or "429" in err:
                return [], (
                    "Trend analysis unavailable: Google Gemini API quota "
                    "exceeded (RESOURCE_EXHAUSTED); default trends were retained."
                ), False
            return [], "Trend analysis unavailable; default trends were retained.", False

        if trends is None:
            return [], "Trend analysis unavailable: malformed model output.", False

        if trends:
            return trends[:MAX_TRENDS], None, True

        # Zero verified trends after a successful, deterministic verification:
        # a legitimate (if empty) evidence-supported result, not a failure.
        return [], (
            "No evidence-supported trends could be verified from the available "
            "evidence."
        ), True


def _build_trend_prompt(query: str, evidence: List[Evidence]) -> str:
    items = evidence[:MAX_TREND_EVIDENCE_ITEMS]
    text = "\n\n".join(e.to_prompt_text() for e in items)
    if len(text) > MAX_TREND_CHARS:
        text = text[:MAX_TREND_CHARS] + "\n...[truncated]"
    return (
        f'RESEARCH QUESTION: "{query}"\n\n'
        f"PROVIDED EVIDENCE:\n{text}\n\n"
        "Identify the emerging trends explicitly supported by the evidence "
        "above. Each trend must cite at least one Evidence ID from the "
        "evidence. Return the JSON now."
    )


def _parse_and_verify(
    raw_json: str, evidence: List[Evidence]
) -> Optional[List[TrendItem]]:
    try:
        data = json.loads(raw_json or "")
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None

    raw_trends = data.get("trends")
    if not isinstance(raw_trends, list):
        return None

    pool: Dict[str, Evidence] = {e.evidence_id: e for e in evidence}
    trends: List[TrendItem] = []
    for raw_trend in raw_trends:
        if not isinstance(raw_trend, dict):
            continue
        item = _build_item(raw_trend, pool)
        if item is not None:
            trends.append(item)
    return trends


def _sanitize_impact(raw: object) -> str:
    if isinstance(raw, str) and raw.strip().lower() in VALID_TREND_IMPACT:
        return raw.strip().lower()
    return "medium"


def _sanitize_direction(raw: object) -> str:
    if isinstance(raw, str) and raw.strip().lower() in VALID_TREND_DIRECTIONS:
        return raw.strip().lower()
    return ""


def _verified_evidence_ids(raw: object, pool: Dict[str, Evidence]) -> List[str]:
    """Keep only Evidence IDs that actually exist in the supplied pool."""
    if not isinstance(raw, list):
        return []
    out: List[str] = []
    seen = set()
    for rid in raw:
        if isinstance(rid, str) and rid in pool and rid not in seen:
            seen.add(rid)
            out.append(rid)
    return out


def _validated_as_of(
    raw: object, evidence_ids: List[str], pool: Dict[str, Evidence]
) -> Optional[str]:
    """
    as_of survives ONLY when it exactly matches the published_at of a cited
    news evidence item. Never infer or invent dates.
    """
    if not isinstance(raw, str) or not raw.strip():
        return None
    candidate = raw.strip()
    for rid in evidence_ids:
        item = pool[rid]
        if item.source_type == "news" and item.published_at == candidate:
            return candidate
    return None


def _build_item(raw: Dict, pool: Dict[str, Evidence]) -> Optional[TrendItem]:
    name = " ".join(str(raw.get("trend") or "").split()).strip()
    if not name:
        return None

    evidence_ids = _verified_evidence_ids(raw.get("evidence"), pool)
    # A trend must be anchored to at least one verifiable evidence ID.
    if not evidence_ids:
        return None

    source_types = sorted(
        {
            st
            for rid in evidence_ids
            if (st := resolve_evidence_source_type(rid, pool)) is not None
        }
    )
    impact = _sanitize_impact(raw.get("impact"))
    direction = _sanitize_direction(raw.get("direction"))
    as_of = _validated_as_of(raw.get("as_of"), evidence_ids, pool)
    description = " ".join(str(raw.get("description") or "").split()).strip()

    return TrendItem(
        trend=name,
        impact=impact,
        description=description,
        evidence=evidence_ids,
        source_types=source_types,
        direction=direction,
        as_of=as_of,
    )