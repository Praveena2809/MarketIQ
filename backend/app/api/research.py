from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.models.research import Research
from app.models.source import Source
from app.schemas.dashboard import ResearchCard
from app.schemas.research import (
    ResearchRequest,
    ResearchResponse,
    ResearchSynthesisSchema,
    SourceSchema,
    KeyFindingItem,
    TrendItem,
    RiskItem,
    OpportunityItem,
    CompetitorItem,
    SentimentSchema,
)
from app.services.research.research_engine import get_research_engine

router = APIRouter()
settings = get_settings()


def _format_research_response(r: Research) -> ResearchResponse:
    sources_data = [SourceSchema.model_validate(s) for s in (r.sources or [])]

    result_data = None
    if r.result:
        res = r.result
        sentiment_dict = res.sentiment or {}
        sentiments = sentiment_dict.get("sentiments") or None
        result_data = ResearchSynthesisSchema(
            executive_summary=res.summary or "",
            key_findings=[KeyFindingItem(**k) for k in (res.insights or [])],
            market_overview=sentiment_dict.get("market_overview", ""),
            trends=[TrendItem(**t) for t in (res.trends or [])],
            opportunities=[OpportunityItem(**o) for o in (res.opportunities or [])],
            risks=[RiskItem(**rk) for rk in (res.risks or [])],
            competitors=[CompetitorItem(**c) for c in (res.competitors or [])],
            conclusion=sentiment_dict.get("conclusion", ""),
            # Step 7 (additive): rebuilt only when a stored sentiments payload exists.
            sentiment=SentimentSchema(**sentiments) if sentiments else None,
            source_ids=[s.id for s in (r.sources or [])],
        )

    return ResearchResponse(
        research_id=r.id,
        query=r.query,
        research_type=r.research_type.value,
        status=r.status.value,
        created_at=r.created_at,
        updated_at=r.updated_at,
        error_message=r.error_message,
        result=result_data,
        sources=sources_data,
    )


@router.post("", response_model=ResearchResponse, status_code=status.HTTP_201_CREATED)
def create_research(
    req: ResearchRequest,
    db: Session = Depends(get_db),
) -> ResearchResponse:
    if not req.query or not req.query.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Research query cannot be empty.",
        )

    engine = get_research_engine()
    research_record = engine.run_research(
        db=db,
        user_id=settings.DEFAULT_USER_ID,
        query=req.query.strip(),
        research_type_str=req.research_type or "market_analysis",
        document_ids=req.document_ids,
    )

    return _format_research_response(research_record)


@router.get("/history", response_model=list[ResearchCard])
def get_research_history(
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> list[ResearchCard]:
    rows = db.scalars(
        select(Research).order_by(Research.updated_at.desc()).offset(offset).limit(limit)
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


@router.get("/{research_id}", response_model=ResearchResponse)
def get_research(
    research_id: str,
    db: Session = Depends(get_db),
) -> ResearchResponse:
    r = db.scalar(select(Research).where(Research.id == research_id))
    if not r:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Research job '{research_id}' not found.",
        )
    return _format_research_response(r)
