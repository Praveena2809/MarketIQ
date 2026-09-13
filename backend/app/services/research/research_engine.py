"""
Main Research Engine managing execution lifecycle, database persistence, and error handling.
"""
from typing import Optional, List
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.research import Research, ResearchStatus, ResearchType
from app.models.research_result import ResearchResult
from app.agents.research_agent import ResearchAgent
from app.services.research.source_tracker import SourceTracker


def _safe_error_string(exc: Exception) -> str:
    """
    Build a useful error message while ensuring no secrets leak into logs or the database.
    """
    raw = str(exc) or exc.__class__.__name__
    settings = get_settings()
    if settings.GEMINI_API_KEY:
        raw = raw.replace(settings.GEMINI_API_KEY, "[REDACTED]")
    return raw[:2000]


class ResearchEngine:
    def __init__(self):
        self.research_agent = ResearchAgent()

    def run_research(
        self,
        db: Session,
        user_id: str,
        query: str,
        research_type_str: str = "market_analysis",
        document_ids: Optional[List[str]] = None,
    ) -> Research:
        """
        Executes a complete research job:
        1. Creates Research record with status='running'.
        2. Gathers web and document evidence and synthesizes report.
        3. Persists ResearchResult and Sources into database.
        4. Updates status to 'completed' or 'failed'.
        """
        try:
            r_type = ResearchType(research_type_str)
        except ValueError:
            r_type = ResearchType.MARKET_ANALYSIS

        # 1. Create Research record
        research_record = Research(
            user_id=user_id,
            query=query,
            research_type=r_type,
            status=ResearchStatus.RUNNING,
        )
        db.add(research_record)
        db.commit()
        db.refresh(research_record)

        try:
            # 2. Execute Research Agent pipeline
            report, all_evidence = self.research_agent.execute_research(
                query=query,
                document_ids=document_ids,
            )

            # 3. Store ResearchResult in DB
            result_record = ResearchResult(
                research_id=research_record.id,
                summary=report.executive_summary or f"Market research analysis for '{query}'.",
                insights=[k.model_dump() for k in report.key_findings],
                risks=[r.model_dump() for r in report.risks],
                opportunities=[o.model_dump() for o in report.opportunities],
                trends=[t.model_dump() for t in report.trends],
                competitors=[c.model_dump() for c in report.competitors],
                sentiment={
                    "market_overview": report.market_overview,
                    "conclusion": report.conclusion,
                },
            )
            db.add(result_record)

            # 4. Save Sources in DB
            SourceTracker.save_sources(db, research_record.id, all_evidence)

            # 5. Mark as completed
            research_record.status = ResearchStatus.COMPLETED
            db.commit()
            db.refresh(research_record)
            return research_record

        except Exception as e:
            db.rollback()
            research_record.status = ResearchStatus.FAILED
            research_record.error_message = _safe_error_string(e)
            db.commit()
            db.refresh(research_record)
            return research_record


_research_engine_instance = None


def get_research_engine() -> ResearchEngine:
    global _research_engine_instance
    if _research_engine_instance is None:
        _research_engine_instance = ResearchEngine()
    return _research_engine_instance
