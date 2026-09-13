"""
RAG Retrieval Service coordinating query embedding and ChromaDB vector search.
"""
from typing import List, Dict, Any, Optional

from app.services.embeddings import get_embedding_service
from app.services.vector_store import get_vector_store_service


class RAGService:
    def __init__(self):
        self.embedding_service = get_embedding_service()
        self.vector_store_service = get_vector_store_service()

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        document_ids: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        1. Generates query embedding using gemini-embedding-2.
        2. Searches ChromaDB vector store for top_k relevant chunks.
        3. Returns ranked chunk list with relevance scores.
        """
        if not query or not query.strip():
            return []

        # Generate query embedding vector
        query_embedding = self.embedding_service.embed_query(query)

        # Retrieve matching chunks from vector database
        results = self.vector_store_service.search(
            query_embedding=query_embedding,
            top_k=top_k,
            document_ids=document_ids,
        )
        return results


_rag_service_instance: Optional[RAGService] = None


def get_rag_service() -> RAGService:
    """Singleton getter for RAGService."""
    global _rag_service_instance
    if _rag_service_instance is None:
        _rag_service_instance = RAGService()
    return _rag_service_instance
