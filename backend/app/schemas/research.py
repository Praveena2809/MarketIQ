from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field


class ResearchRequest(BaseModel):
    query: str
    research_type: Optional[str] = "market_analysis"
    document_ids: Optional[List[str]] = None


class KeyFindingItem(BaseModel):
    finding: str
    evidence: List[str] = Field(default_factory=list)


class CompetitorItem(BaseModel):
    company: str
    market_share: Optional[str] = None
    strengths: List[str] = Field(default_factory=list)
    weaknesses: List[str] = Field(default_factory=list)
    # Evidence IDs backing this competitor profile (Step 6, additive optional).
    evidence: List[str] = Field(default_factory=list)


class CompetitorIdentificationItem(BaseModel):
    name: str


class CompetitorIdentificationSchema(BaseModel):
    competitors: List[CompetitorIdentificationItem] = Field(default_factory=list)


class TrendItem(BaseModel):
    trend: str
    impact: str = "medium"  # high | medium | low
    description: str = ""


class RiskItem(BaseModel):
    risk: str
    severity: str = "medium"  # high | medium | low
    mitigation: Optional[str] = None


class OpportunityItem(BaseModel):
    opportunity: str
    potential_impact: str = "medium"


class ResearchSynthesisSchema(BaseModel):
    executive_summary: str = ""
    key_findings: List[KeyFindingItem] = Field(default_factory=list)
    market_overview: str = ""
    trends: List[TrendItem] = Field(default_factory=list)
    opportunities: List[OpportunityItem] = Field(default_factory=list)
    risks: List[RiskItem] = Field(default_factory=list)
    competitors: List[CompetitorItem] = Field(default_factory=list)
    conclusion: str = ""
    source_ids: List[str] = Field(default_factory=list)


class SourceSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    research_id: str
    title: str
    url: Optional[str] = None
    source_name: str
    source_type: str  # web | document | news
    relevance: Optional[float] = None
    is_mock: bool = False
    published_at: Optional[datetime] = None


class ResearchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    research_id: str
    query: str
    research_type: str
    status: str
    created_at: datetime
    updated_at: datetime
    error_message: Optional[str] = None
    result: Optional[ResearchSynthesisSchema] = None
    sources: List[SourceSchema] = Field(default_factory=list)
