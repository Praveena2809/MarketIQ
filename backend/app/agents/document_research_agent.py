"""
Document Research Agent interfacing directly with Phase 2 RAGService.
"""
from typing import List, Optional
from app.core.config import get_settings
from app.services.rag import get_rag_service
from app.services.research.evidence import Evidence


class DocumentResearchAgent:
    def __init__(self):
        self.settings = get_settings()
        self.rag_service = get_rag_service()

    def gather_document_evidence(
        self,
        query: str,
        document_ids: Optional[List[str]] = None,
    ) -> List[Evidence]:
        """
        Retrieves relevant document chunks from ChromaDB using Phase 2 RAGService.
        """
        raw_chunks = self.rag_service.retrieve(
            query=query,
            top_k=self.settings.MAX_RAG_TOP_K,
            document_ids=document_ids,
        )

        doc_evidence: List[Evidence] = []
        for idx, chunk in enumerate(raw_chunks, 1):
            doc_evidence.append(
                Evidence(
                    evidence_id=f"doc_{idx}",
                    source_type="document",
                    title=f"Document Source: {chunk.get('filename', 'Doc')}",
                    content=chunk.get("chunk_text", ""),
                    document_id=chunk.get("document_id"),
                    filename=chunk.get("filename"),
                    chunk_index=chunk.get("chunk_index"),
                    relevance_score=chunk.get("relevance_score", 1.0),
                )
            )

        return doc_evidence
