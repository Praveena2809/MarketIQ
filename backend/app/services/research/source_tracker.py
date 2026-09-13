"""
Source tracker helper for persisting normalized evidence as Source database records.
"""
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy.orm import Session

from app.models.source import Source
from app.services.research.evidence import Evidence


def _to_datetime(value: Optional[str]) -> Optional[datetime]:
    """Best-effort parse of an ISO-8601 string; malformed values become None."""
    if not value:
        return None
    try:
        raw = value
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


class SourceTracker:
    @staticmethod
    def save_sources(db: Session, research_id: str, evidence_list: List[Evidence]) -> List[Source]:
        """
        Deduplicates and saves normalized evidence items into the sources table for a research job.

        Provenance rules:
        - Web evidence is persisted ONLY when it carries a real grounding URL from Gemini
          Google Search grounding metadata. Synthetic items (e.g. a summary blob without a
          URL) are never written as standalone sources.
        - News evidence is persisted ONLY when it carries a real provider URL, using the
          provider's publisher and published_at metadata.
        - Document evidence is persisted using only the actual RAG/database data
          (filename, document_id, relevance).
        """
        seen_urls = set()
        seen_titles = set()
        saved_sources: List[Source] = []

        for item in evidence_list:
            if item.source_type in ("web", "news") and not item.url:
                continue

            # Deduplicate by URL or title
            if item.url and item.url in seen_urls:
                continue
            if not item.url and item.title in seen_titles:
                continue

            if item.url:
                seen_urls.add(item.url)
            seen_titles.add(item.title)

            if item.source_type == "document":
                source_name = item.filename or "Uploaded Document"
                title = item.filename or item.title
            elif item.source_type == "news":
                source_name = item.publisher or item.title or "News Source"
                title = item.title or source_name
            else:
                source_name = item.title or "Web Source"
                title = item.title or "Web Source"

            db_source = Source(
                research_id=research_id,
                title=title,
                url=item.url,
                source_name=source_name,
                source_type=item.source_type,
                relevance=item.relevance_score,
                is_mock=False,
                published_at=_to_datetime(item.published_at),
            )
            db.add(db_source)
            saved_sources.append(db_source)

        db.commit()
        for s in saved_sources:
            db.refresh(s)

        return saved_sources
