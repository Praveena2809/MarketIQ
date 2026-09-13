from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class QuickStats(BaseModel):
    researches_completed: int
    sources_analyzed: int
    companies_analyzed: int
    trends_detected: int


class ResearchCard(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    query: str
    research_type: str
    status: str
    updated_at: datetime


class HealthResponse(BaseModel):
    status: str
    environment: str
    database: str
    gemini_configured: bool
