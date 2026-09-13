from dataclasses import dataclass
from typing import Optional


def resolve_evidence_source_type(
    evidence_id: str, pool: "dict[str, Evidence]"
) -> Optional[str]:
    """
    Shared provenance helper (Step 8). Resolves the source-type tag for a
    verified evidence ID:
    - competitor-scoped evidence IDs (comp_*) always map to "competitor",
    - everything else uses the item's own source_type (web/news/document),
    - unknown/fabricated IDs resolve to None (callers drop them).
    """
    item = pool.get(evidence_id)
    if item is None:
        return None
    if evidence_id.startswith("comp_"):
        return "competitor"
    return item.source_type


@dataclass
class Evidence:
    evidence_id: str
    source_type: str  # "web" | "document" | "news"
    title: str
    content: str
    url: Optional[str] = None
    document_id: Optional[str] = None
    filename: Optional[str] = None
    chunk_index: Optional[int] = None
    relevance_score: float = 1.0
    publisher: Optional[str] = None
    published_at: Optional[str] = None

    def to_prompt_text(self) -> str:
        if self.source_type == "news":
            loc = f"URL: {self.url}" if self.url else "News Source"
            details = []
            if self.publisher:
                details.append(f"Publisher: {self.publisher}")
            if self.published_at:
                details.append(f"Published: {self.published_at}")
            meta = f"\n{' | '.join(details)}" if details else ""
            return f"[Evidence ID: {self.evidence_id}] {self.title}\n{loc}{meta}\n{self.content}"
        if self.source_type == "web":
            loc = f"URL: {self.url}" if self.url else "Web Grounding Source"
            return f"[Evidence ID: {self.evidence_id}] {self.title}\n{loc}\n{self.content}"
        else:
            doc_info = f"File: {self.filename or 'Document'}"
            if self.chunk_index is not None:
                doc_info += f" (Chunk {self.chunk_index})"
            return f"[Evidence ID: {self.evidence_id}] {doc_info}\n{self.content}"
