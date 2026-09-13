"""
Insight & Recommendation Analysis Service.

Consumes ONLY the already-gathered evidence pool (web + news + document +
competitor evidence produced by the ResearchAgent) plus the verified outputs
of the competitor, sentiment, and trend passes, and produces evidence-grounded
key insights and actionable recommendations. Recommendations are advice and
are always kept distinct from factual claims.

Every cited Evidence ID must exist in the supplied pool; fabricated/unknown
IDs are dropped. source_types are derived server-side from the verified
Evidence IDs via the shared resolve_evidence_source_type helper. An insight
or recommendation with no surviving evidence IDs is dropped entirely.

This module performs exactly ONE Gemini generate_json call and zero other
external calls. On empty evidence it returns an honest "insufficient evidence"
result without calling Gemini at all.

Success semantics mirror Step 8 / TrendAnalysisService: success=True means a
deterministic run to determination, so the (possibly empty) verified output is
authoritative; success=False (insufficient evidence, quota, exception,
malformed output) tells callers to preserve the synthesis-produced key
findings and leave recommendations empty.
"""
import json
from typing import Dict, List, Optional, Tuple

from app.schemas.research import KeyFindingItem, RecommendationItem, SentimentSchema, TrendItem
from app.services.llm import get_llm_service
from app.services.research.evidence import Evidence, resolve_evidence_source_type

# Inline JSON Schema (no $ref/$defs) so it is accepted across Gemini versions.
INSIGHT_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "insights": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "insight": {"type": "string"},
                    "evidence": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["insight", "evidence"],
            },
        },
        "recommendations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "recommendation": {"type": "string"},
                    "rationale": {"type": "string"},
                    "priority": {"type": "string"},
                    "category": {"type": "string"},
                    "evidence": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["recommendation", "priority", "evidence"],
            },
        },
    },
    "required": ["insights", "recommendations"],
}

# Bounded prompt budget so the insight call stays cheap and deterministic.
MAX_INSIGHT_EVIDENCE_ITEMS = 40
MAX_INSIGHT_CHARS = 12000
# Cap on insights and recommendations requested / retained per job.
MAX_INSIGHTS = 8
MAX_RECOMMENDATIONS = 6

VALID_PRIORITY = frozenset({"high", "medium", "low"})

INSIGHT_SYSTEM_INSTRUCTION = """You are MarketIQ's Insight & Recommendation Engine.
You are given a market-research question, the evidence already collected for it,
and the verified outputs of the dedicated competitor, sentiment, and trend passes.

CRITICAL CONSTRAINTS:
1. Provide at most 8 key insights that the PROVIDED EVIDENCE explicitly supports.
2. Every insight MUST cite at least one Evidence ID that appears in the
   PROVIDED EVIDENCE. Never cite an Evidence ID that is not present.
3. Provide at most 6 actionable recommendations grounded in the evidence.
4. Every recommendation MUST cite at least one Evidence ID from the PROVIDED EVIDENCE.
5. Recommendations are ACTIONABLE ADVICE, not factual claims. They must be
   clearly distinguishable from factual insights and must not exceed what the
   evidence supports.
6. Never invent statistics, growth percentages, confidence scores, probabilities,
   dates, sources, URLs, publishers, companies, or market claims.
7. Weigh the strongest evidence, cross-source corroboration, verified trends,
   competitor context, and sentiment when prioritizing insights and
   recommendations. Do not include generic filler such as
   "Companies should monitor the market."
8. "priority" for recommendations is qualitative ONLY: high, medium, or low.
9. "category" (optional) is a short grouping label such as strategy, product,
   market, risk, or go-to-market.
10. Output ONLY valid JSON in this exact shape:
   {"insights": [{"insight": "...", "evidence": ["web_1"]}],
    "recommendations": [{"recommendation": "...", "rationale": "...",
                         "priority": "high", "category": "strategy",
                         "evidence": ["web_1"]}]}"""


class InsightAnalysisService:
    """Evidence-grounded, qualitative insight and recommendation extraction."""

    def __init__(self):
        self._llm_service = get_llm_service()

    def analyze(
        self,
        query: str,
        evidence: List[Evidence],
        competitors: Optional[List[str]] = None,
        trends: Optional[List[TrendItem]] = None,
        sentiment: Optional[SentimentSchema] = None,
    ) -> Tuple[List[KeyFindingItem], List[RecommendationItem], Optional[str], bool]:
        """
        Returns (verified KeyFindingItems, verified RecommendationItems,
        warning, success).

        success=True means the insight agent completed a deterministic run to
        determination: the verified lists are authoritative and may be empty
        (no evidence-supported insights or recommendations). success=False
        means the result is non-deterministic (insufficient evidence, quota,
        exception, malformed output), so callers fall back to synthesis-produced
        key_findings and leave recommendations empty.
        Empty evidence never triggers a Gemini call.
        """
        if not evidence:
            return (
                [],
                [],
                "Insight & Recommendation analysis unavailable: insufficient evidence.",
                False,
            )

        prompt = _build_insight_prompt(query, evidence, competitors, trends, sentiment)
        try:
            raw_json = self._llm_service.generate_json(
                prompt=prompt,
                schema=INSIGHT_JSON_SCHEMA,
                system_instruction=INSIGHT_SYSTEM_INSTRUCTION,
            )
            result = _parse_and_verify(raw_json, evidence)
        except Exception as exc:
            err = str(exc)
            if "RESOURCE_EXHAUSTED" in err or "429" in err:
                return (
                    [],
                    [],
                    (
                        "Insight & Recommendation analysis unavailable: Google "
                        "Gemini API quota exceeded (RESOURCE_EXHAUSTED); "
                        "synthesis insights were retained."
                    ),
                    False,
                )
            return (
                [],
                [],
                "Insight & Recommendation analysis unavailable; synthesis insights were retained.",
                False,
            )

        if result is None:
            return (
                [],
                [],
                "Insight & Recommendation analysis unavailable: malformed model output.",
                False,
            )

        insights, recommendations = result

        if insights or recommendations:
            return (
                insights[:MAX_INSIGHTS],
                recommendations[:MAX_RECOMMENDATIONS],
                None,
                True,
            )

        # Zero verified insights AND recommendations after a successful,
        # deterministic verification: a legitimate (if empty) evidence-
        # supported result, not a failure.
        return (
            [],
            [],
            (
                "No evidence-supported insights and recommendations could be "
                "verified from the available evidence."
            ),
            True,
        )


def _build_insight_prompt(
    query: str,
    evidence: List[Evidence],
    competitors: Optional[List[str]],
    trends: Optional[List[TrendItem]],
    sentiment: Optional[SentimentSchema],
) -> str:
    items = evidence[:MAX_INSIGHT_EVIDENCE_ITEMS]
    text = "\n\n".join(e.to_prompt_text() for e in items)
    if len(text) > MAX_INSIGHT_CHARS:
        text = text[:MAX_INSIGHT_CHARS] + "\n...[truncated]"

    parts = [
        f'RESEARCH QUESTION: "{query}"',
        f"PROVIDED EVIDENCE:\n{text}",
    ]

    # Verified competitors
    if competitors:
        parts.append(f"VERIFIED COMPETITORS (dedicated pass): {', '.join(competitors)}")
    else:
        parts.append("VERIFIED COMPETITORS: none identified from the evidence")

    # Verified sentiment
    if sentiment is not None:
        parts.append(_format_sentiment(sentiment))
    else:
        parts.append(
            "VERIFIED SENTIMENT: the dedicated sentiment pass was unavailable."
        )

    # Verified trends (only authoritative when trend pass succeeded)
    if trends is not None:
        if trends:
            lines = []
            for t in trends:
                direction = f", direction={t.direction}" if t.direction else ""
                lines.append(
                    f"- {t.trend} (impact: {t.impact}{direction})"
                    f" [evidence: {', '.join(t.evidence)}]"
                )
            parts.append(
                "VERIFIED TRENDS (dedicated pass):\n" + "\n".join(lines)
            )
        else:
            parts.append(
                "VERIFIED TRENDS (dedicated pass): none verified from the evidence"
            )
    else:
        parts.append(
            "VERIFIED TRENDS: the dedicated trend pass was unavailable; no "
            "trends are treated as verified."
        )

    parts.append(
        "Identify the evidence-grounded key insights and actionable "
        "recommendations explicitly supported by the evidence above. Each "
        "item must cite at least one Evidence ID from the provided evidence. "
        "Return the JSON now."
    )
    return "\n\n".join(parts)


def _format_sentiment(sentiment: SentimentSchema) -> str:
    overall = sentiment.overall
    lines = [f"Overall: {overall.label}" + (f" - {overall.summary}" if overall.summary else "")]
    for ent in sentiment.entities or []:
        if ent.label and ent.label not in ("unavailable", ""):
            lines.append(
                f"- {ent.entity}: {ent.label}"
                + (f" - {ent.summary}" if ent.summary else "")
            )
    return "VERIFIED SENTIMENT (dedicated pass):\n" + "\n".join(lines)


def _parse_and_verify(
    raw_json: str, evidence: List[Evidence]
) -> Optional[Tuple[List[KeyFindingItem], List[RecommendationItem]]]:
    try:
        data = json.loads(raw_json or "")
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None

    raw_insights = data.get("insights")
    raw_recs = data.get("recommendations")
    if not isinstance(raw_insights, list) or not isinstance(raw_recs, list):
        return None

    pool: Dict[str, Evidence] = {e.evidence_id: e for e in evidence}
    insights = [
        item
        for item in (_build_insight(i, pool) for i in raw_insights)
        if item is not None
    ]
    recommendations = [
        item
        for item in (_build_recommendation(r, pool) for r in raw_recs)
        if item is not None
    ]
    return insights, recommendations


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


def _sanitize_priority(raw: object) -> str:
    if isinstance(raw, str) and raw.strip().lower() in VALID_PRIORITY:
        return raw.strip().lower()
    return "medium"


def _build_insight(raw: Dict, pool: Dict[str, Evidence]) -> Optional[KeyFindingItem]:
    text = " ".join(str(raw.get("insight") or "").split()).strip()
    if not text:
        return None
    evidence_ids = _verified_evidence_ids(raw.get("evidence"), pool)
    if not evidence_ids:
        return None
    return KeyFindingItem(finding=text, evidence=evidence_ids)


def _build_recommendation(
    raw: Dict, pool: Dict[str, Evidence]
) -> Optional[RecommendationItem]:
    text = " ".join(str(raw.get("recommendation") or "").split()).strip()
    if not text:
        return None
    evidence_ids = _verified_evidence_ids(raw.get("evidence"), pool)
    if not evidence_ids:
        return None
    source_types = sorted(
        {
            st
            for rid in evidence_ids
            if (st := resolve_evidence_source_type(rid, pool)) is not None
        }
    )
    priority = _sanitize_priority(raw.get("priority"))
    rationale = " ".join(str(raw.get("rationale") or "").split()).strip()
    category = " ".join(str(raw.get("category") or "").split()).strip()
    return RecommendationItem(
        recommendation=text,
        rationale=rationale,
        priority=priority,
        category=category,
        evidence=evidence_ids,
        source_types=source_types,
    )
