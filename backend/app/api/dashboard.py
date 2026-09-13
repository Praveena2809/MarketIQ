from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.research import Research, ResearchStatus
from app.models.source import Source
from app.models.research_result import ResearchResult
from app.schemas.dashboard import QuickStats, ResearchCard

router = APIRouter()


def _overall_sentiment_label(sentiment) -> str:
    """Extract the persisted overall sentiment label, falling back to
    'unavailable' when the field is missing or malformed (legacy records)."""
    if not isinstance(sentiment, dict):
        return "unavailable"
    sentiments = sentiment.get("sentiments") or {}
    if not isinstance(sentiments, dict):
        return "unavailable"
    overall = sentiments.get("overall") or {}
    if not isinstance(overall, dict):
        return "unavailable"
    label = overall.get("label")
    return label if isinstance(label, str) and label else "unavailable"


@router.get("/stats", response_model=QuickStats)
def get_quick_stats(db: Session = Depends(get_db)) -> QuickStats:
    researches_completed = db.scalar(
        select(func.count(Research.id)).where(Research.status == ResearchStatus.COMPLETED)
    ) or 0
    sources_analyzed = db.scalar(select(func.count(Source.id))) or 0

    companies = set()
    trends_total = 0
    insights_total = 0
    opportunities_total = 0
    risks_total = 0
    sentiment_counts: dict[str, int] = {}
    for result in db.scalars(select(ResearchResult)):
        for c in result.competitors or []:
            name = c.get("company") if isinstance(c, dict) else None
            if name:
                companies.add(name)
        trends_total += len(result.trends or [])
        insights_total += len(result.insights or [])
        opportunities_total += len(result.opportunities or [])
        risks_total += len(result.risks or [])
        label = _overall_sentiment_label(result.sentiment)
        sentiment_counts[label] = sentiment_counts.get(label, 0) + 1

    research_type_counts: dict[str, int] = {}
    for research in db.scalars(
        select(Research).where(Research.status == ResearchStatus.COMPLETED)
    ):
        key = research.research_type.value
        research_type_counts[key] = research_type_counts.get(key, 0) + 1

    source_type_counts: dict[str, int] = {}
    for source in db.scalars(select(Source)):
        key = source.source_type
        source_type_counts[key] = source_type_counts.get(key, 0) + 1

    return QuickStats(
        researches_completed=researches_completed,
        sources_analyzed=sources_analyzed,
        companies_analyzed=len(companies),
        trends_detected=trends_total,
        insights_synthesized=insights_total,
        opportunities_identified=opportunities_total,
        risks_identified=risks_total,
        sentiment_counts=sentiment_counts,
        research_type_counts=research_type_counts,
        source_type_counts=source_type_counts,
    )


@router.get("/research/recent", response_model=list[ResearchCard])
def get_recent_research(limit: int = 5, db: Session = Depends(get_db)) -> list[ResearchCard]:
    rows = db.scalars(
        select(Research).order_by(Research.updated_at.desc()).limit(limit)
    ).all()
    return [
        ResearchCard(
            id=r.id,
            query=r.query,
            research_type=r.research_type.value,
            status=r.status.value,
            updated_at=r.updated_at,
        )
        for r in rows
    ]
