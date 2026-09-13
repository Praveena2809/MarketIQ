import uuid
import enum
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, DateTime, ForeignKey, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class ResearchType(str, enum.Enum):
    MARKET_ANALYSIS = "market_analysis"
    COMPETITOR_ANALYSIS = "competitor_analysis"
    PRODUCT_ANALYSIS = "product_analysis"
    INDUSTRY_TRENDS = "industry_trends"


class ResearchStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Research(Base):
    __tablename__ = "researches"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)
    query: Mapped[str] = mapped_column(String, nullable=False)
    research_type: Mapped[ResearchType] = mapped_column(
        Enum(ResearchType), default=ResearchType.MARKET_ANALYSIS
    )
    status: Mapped[ResearchStatus] = mapped_column(
        Enum(ResearchStatus), default=ResearchStatus.PENDING
    )
    error_message: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    user = relationship("User", back_populates="researches")
    documents = relationship("Document", back_populates="research")
    sources = relationship("Source", back_populates="research", cascade="all, delete-orphan")
    result = relationship(
        "ResearchResult", back_populates="research", uselist=False, cascade="all, delete-orphan"
    )
