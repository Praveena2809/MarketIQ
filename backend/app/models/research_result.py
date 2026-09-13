import uuid
from sqlalchemy import String, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class ResearchResult(Base):
    __tablename__ = "research_results"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    research_id: Mapped[str] = mapped_column(
        String, ForeignKey("researches.id"), unique=True, nullable=False
    )
    summary: Mapped[str] = mapped_column(String, default="")
    insights: Mapped[list] = mapped_column(JSON, default=list)
    risks: Mapped[list] = mapped_column(JSON, default=list)
    opportunities: Mapped[list] = mapped_column(JSON, default=list)
    trends: Mapped[list] = mapped_column(JSON, default=list)
    competitors: Mapped[list] = mapped_column(JSON, default=list)
    sentiment: Mapped[dict] = mapped_column(JSON, default=dict)

    research = relationship("Research", back_populates="result")
