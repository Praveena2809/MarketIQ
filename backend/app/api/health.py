from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.schemas.dashboard import HealthResponse

router = APIRouter()
settings = get_settings()


@router.get("/health", response_model=HealthResponse)
def health_check(db: Session = Depends(get_db)) -> HealthResponse:
    try:
        db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception:
        db_status = "unreachable"

    return HealthResponse(
        status="ok" if db_status == "connected" else "degraded",
        environment=settings.ENVIRONMENT,
        database=db_status,
        gemini_configured=bool(settings.GEMINI_API_KEY),
    )
