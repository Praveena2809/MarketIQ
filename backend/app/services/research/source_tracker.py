"""
Source tracker helper for persisting normalized evidence as Source database records.
"""
from typing import List
from sqlalchemy.orm import Session

from app.models.source import Source
from app.services.research.evidence import Evidence


class SourceTracker:
    @staticmethod
    def save_sources(db: Session, research_id: str, evidence_list: List[Evidence]) -> List[Source]:
        """
        Deduplicates and saves normalized evidence items into the sources table for a research job.

        Provenance rules:
        - Web evidence is persisted ONLY when it carries a real grounding URL from Gemini
          Google Search grounding metadata. Synthetic items (e.g. a summary blob without a
          URL) are never written as standalone sources.
        - Document evidence is persisted using only the actual RAG/database data
          (filename, document_id, relevance).
        """
        seen_urls = set()
        seen_titles = set()
        saved_sources: List[Source] = []

        for item in evidence_list:
            if item.source_type == "web" and not item.url:
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
            )
            db.add(db_source)
            saved_sources.append(db_source)

        db.commit()
        for s in saved_sources:
            db.refresh(s)

        return saved_sources
