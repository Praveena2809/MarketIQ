import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import String, DateTime, ForeignKey, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    research_id: Mapped[str] = mapped_column(String, ForeignKey("researches.id"), nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    source_name: Mapped[str] = mapped_column(String, nullable=False)
    source_type: Mapped[str] = mapped_column(String, default="news")  # news | document | review
    relevance: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_mock: Mapped[bool] = mapped_column(default=False)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    research = relationship("Research", back_populates="sources")
