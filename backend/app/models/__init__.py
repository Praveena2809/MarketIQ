"""
Models package - import all models so SQLAlchemy string-based relationship
references (e.g. "User", "Research") always resolve during mapper configuration.
"""
from app.models.user import User
from app.models.document import Document
from app.models.research import Research, ResearchStatus, ResearchType
from app.models.source import Source
from app.models.research_result import ResearchResult

__all__ = [
    "User",
    "Document",
    "Research",
    "ResearchStatus",
    "ResearchType",
    "Source",
    "ResearchResult",
]