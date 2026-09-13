from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.research import Research, ResearchStatus
from app.models.source import Source
from app.models.research_result import ResearchResult
from app.schemas.dashboard import QuickStats, ResearchCard

router = APIRouter()


@router.get("/stats", response_model=QuickStats)
def get_quick_stats(db: Session = Depends(get_db)) -> QuickStats:
    researches_completed = db.scalar(
        select(func.count(Research.id)).where(Research.status == ResearchStatus.COMPLETED)
    ) or 0
    sources_analyzed = db.scalar(select(func.count(Source.id))) or 0

    companies = set()
    trends_total = 0
    for result in db.scalars(select(ResearchResult)):
        for c in result.competitors or []:
            name = c.get("company") if isinstance(c, dict) else None
            if name:
                companies.add(name)
        trends_total += len(result.trends or [])

    return QuickStats(
        researches_completed=researches_completed,
        sources_analyzed=sources_analyzed,
        companies_analyzed=len(companies),
        trends_detected=trends_total,
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
