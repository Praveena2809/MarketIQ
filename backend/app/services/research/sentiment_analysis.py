"""
Sentiment Analysis Service.

Consumes ONLY the already-gathered evidence pool (web + news + document +
competitor evidence produced by the ResearchAgent) and produces an
evidence-grounded, categorical sentiment assessment covering:

- the overall research question, and
- each identified competitor (per-company sentiment).

Sentiment is strictly categorical and qualitative - no numeric scores, no
confidence percentages, no invented metrics. Every cited Evidence ID must
exist in the supplied pool; fabricated/unknown IDs are dropped and
source_types are derived server-side from the verified Evidence IDs so the
web / news / document / competitor distinctions are preserved.

This module performs exactly ONE Gemini generate_json call and zero other
external calls. On empty evidence it returns an honest "unavailable" result
without calling Gemini at all.
"""
import json
from typing import Dict, List, Optional, Tuple

from app.schemas.research import EntitySentimentItem, SentimentItem, SentimentSchema
from app.services.llm import get_llm_service
from app.services.research.evidence import Evidence

# Inline JSON Schema (no $ref/$defs) so it is accepted across Gemini versions.
SENTIMENT_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "overall": {
            "type": "object",
            "properties": {
                "label": {"type": "string"},
                "evidence": {"type": "array", "items": {"type": "string"}},
                "summary": {"type": "string"},
            },
            "required": ["label"],
        },
        "entities": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "entity": {"type": "string"},
                    "label": {"type": "string"},
                    "evidence": {"type": "array", "items": {"type": "string"}},
                    "summary": {"type": "string"},
                },
                "required": ["entity", "label"],
            },
        },
    },
    "required": ["overall"],
}

# Bounded prompt budget so the sentiment call stays cheap and deterministic.
MAX_SENTIMENT_EVIDENCE_ITEMS = 40
MAX_SENTIMENT_CHARS = 12000

# The only labels the engine ever emits.
VALID_SENTIMENT_LABELS = frozenset(
    {"positive", "neutral", "negative", "mixed", "unavailable"}
)

COMPETITOR_EVIDENCE_PREFIX = "comp_"

SENTIMENT_SYSTEM_INSTRUCTION = """You are MarketIQ's Sentiment Analysis Engine.
You are given a market-research question, the entities to score, and the
evidence already collected for that question.

CRITICAL CONSTRAINTS:
1. Assess ONLY the sentiment that the evidence supports. Never invent
   sentiment, opinions, facts, dates, statistics, or sources.
2. Use ONLY these exact sentiment labels: positive, neutral, negative,
   mixed, unavailable. If the evidence is insufficient to make a call, use
   "unavailable". Never invent numeric scores, percentages, or confidence
   values.
3. Cite ONLY Evidence IDs that appear in the PROVIDED EVIDENCE. Never cite
   an Evidence ID that is not present. Fabricated or guessed IDs are
   discarded and harm the result.
4. Score sentiment ONLY for the entities listed in "ENTITIES TO SCORE" (a
   competitor may be left out if the evidence does not support it). Never
   invent other companies.
5. Output ONLY valid JSON matching this exact shape:
   {"overall": {"label": "mixed", "evidence": ["web_1", "news_1"], "summary": "..."},
    "entities": [{"entity": "Company X", "label": "positive", "evidence": ["news_2"], "summary": "..."}]}"""


class SentimentAnalysisService:
    """Categorical, evidence-grounded sentiment on the existing evidence pool."""

    def __init__(self):
        self._llm_service = get_llm_service()

    def analyze(
        self,
        query: str,
        evidence: List[Evidence],
        eligible_entities: Optional[List[str]] = None,
    ) -> Tuple[SentimentSchema, Optional[str]]:
        """
        Always returns a usable SentimentSchema. When sentiment cannot be
        assessed (empty evidence, model failure, malformed JSON, quota) an
        honest "unavailable" result is produced and a warning is returned so
        the caller surfaces it without failing the research.
        """
        if not evidence:
            schema = _unavailable_schema(
                "Insufficient evidence was available to assess sentiment."
            )
            return schema, "Sentiment analysis unavailable: insufficient evidence."

        prompt = _build_sentiment_prompt(query, evidence, eligible_entities or [])
        try:
            raw_json = self._llm_service.generate_json(
                prompt=prompt,
                schema=SENTIMENT_JSON_SCHEMA,
                system_instruction=SENTIMENT_SYSTEM_INSTRUCTION,
            )
            schema = _parse_and_verify(raw_json, evidence, eligible_entities or [])
        except Exception as exc:
            err = str(exc)
            if "RESOURCE_EXHAUSTED" in err or "429" in err:
                schema = _unavailable_schema(
                    "Sentiment analysis was not assessed because the Google "
                    "Gemini API quota was exceeded."
                )
                return schema, (
                    "Sentiment analysis unavailable: Google Gemini API quota "
                    "exceeded (RESOURCE_EXHAUSTED); sentiment was not assessed."
                )
            schema = _unavailable_schema(
                "Sentiment analysis was not assessed because the language "
                "model was unavailable."
            )
            return schema, "Sentiment analysis unavailable."

        if schema is None:
            schema = _unavailable_schema(
                "Sentiment analysis produced no parseable result."
            )
            return schema, "Sentiment analysis unavailable: malformed model output."

        return schema, None


def _build_sentiment_prompt(
    query: str, evidence: List[Evidence], eligible_entities: List[str]
) -> str:
    items = evidence[:MAX_SENTIMENT_EVIDENCE_ITEMS]
    text = "\n\n".join(e.to_prompt_text() for e in items)
    if len(text) > MAX_SENTIMENT_CHARS:
        text = text[:MAX_SENTIMENT_CHARS] + "\n...[truncated]"
    entities_note = ", ".join(eligible_entities) if eligible_entities else "None identified."
    return (
        f'RESEARCH QUESTION: "{query}"\n\n'
        f"ENTITIES TO SCORE: {entities_note}\n\n"
        f"PROVIDED EVIDENCE:\n{text}\n\n"
        "Assess the overall sentiment and, where the evidence supports it, "
        "the sentiment for each named entity. Return the JSON now."
    )


def _normalize_label(raw: object) -> Optional[str]:
    if not isinstance(raw, str):
        return None
    label = raw.strip().lower().replace(" ", "")
    if label in VALID_SENTIMENT_LABELS:
        return label
    return None


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


def _resolve_source_type(evidence_id: str, pool: Dict[str, Evidence]) -> Optional[str]:
    item = pool.get(evidence_id)
    if item is None:
        return None
    if evidence_id.startswith(COMPETITOR_EVIDENCE_PREFIX):
        return "competitor"
    return item.source_type


def _build_item(raw: object, pool: Dict[str, Evidence]) -> SentimentItem:
    """
    Builds a verified SentimentItem from an untrusted model-shaped object.
    Evidence is containment-checked and source_types are derived server-side.
    An item with no verifiable backing collapses to "unavailable".
    """
    if not isinstance(raw, dict):
        return _unavailable_item()
    label = _normalize_label(raw.get("label"))
    evidence_ids = _verified_evidence_ids(raw.get("evidence"), pool)
    if not evidence_ids:
        return SentimentItem(
            label="unavailable",
            evidence=[],
            source_types=[],
            summary="No verifiable evidence supported this sentiment assessment.",
        )
    source_types = sorted(
        {
            st
            for rid in evidence_ids
            if (st := _resolve_source_type(rid, pool)) is not None
        }
    )
    summary = " ".join(str(raw.get("summary") or "").split()).strip()
    return SentimentItem(
        label=label if label is not None else "unavailable",
        evidence=evidence_ids,
        source_types=source_types,
        summary=summary if label is not None else (
            "No verifiable categorical label could be derived from the evidence."
        ),
    )


def _unavailable_item(summary: str = "") -> SentimentItem:
    return SentimentItem(
        label="unavailable", evidence=[], source_types=[], summary=summary
    )


def _unavailable_schema(summary: str) -> SentimentSchema:
    return SentimentSchema(
        overall=_unavailable_item(summary or "Sentiment is unavailable."),
        entities=[],
    )


def _parse_and_verify(
    raw_json: str,
    evidence: List[Evidence],
    eligible_entities: List[str],
) -> Optional[SentimentSchema]:
    try:
        data = json.loads(raw_json or "")
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None

    overall_raw = data.get("overall")
    if not isinstance(overall_raw, dict):
        return None

    pool = {e.evidence_id: e for e in evidence}
    overall = _build_item(overall_raw, pool)

    entities: List[EntitySentimentItem] = []
    allowed = {name.strip().lower() for name in eligible_entities if name}
    raw_entities = data.get("entities")
    if isinstance(raw_entities, list) and allowed:
        for raw_entity in raw_entities:
            if not isinstance(raw_entity, dict):
                continue
            name = " ".join(str(raw_entity.get("entity") or "").split()).strip()
            if not name or name.lower() not in allowed:
                continue
            item = _build_item(raw_entity, pool)
            if not item.evidence:
                continue
            entities.append(
                EntitySentimentItem(
                    entity=name,
                    label=item.label,
                    evidence=item.evidence,
                    source_types=item.source_types,
                    summary=item.summary,
                )
            )

    return SentimentSchema(overall=overall, entities=entities)