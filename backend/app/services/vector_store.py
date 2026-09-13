"""
ChromaDB Vector Store wrapper providing persistent vector storage, retrieval, and deletion for document chunks.
"""
import os
from typing import List, Dict, Any, Optional
import chromadb

from app.core.config import get_settings


class VectorStoreService:
    def __init__(self, db_dir: Optional[str] = None, collection_name: Optional[str] = None):
        settings = get_settings()
        self.db_dir = db_dir or settings.VECTOR_DB_DIR
        self.collection_name = collection_name or settings.CHROMA_COLLECTION_NAME

        os.makedirs(self.db_dir, exist_ok=True)
        self._client = chromadb.PersistentClient(path=self.db_dir)
        self._collection = self._client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"}
        )

    def add_chunks(
        self,
        document_id: str,
        chunks: List[str],
        embeddings: List[List[float]],
        metadatas: List[Dict[str, Any]],
    ) -> List[str]:
        """
        Store document chunks and their embeddings into ChromaDB collection.
        Returns the generated chunk IDs.
        """
        if not chunks or not embeddings or len(chunks) != len(embeddings):
            raise ValueError("Chunks and embeddings lists must be non-empty and of equal length.")

        chunk_ids = [f"{document_id}_{i}" for i in range(len(chunks))]

        # Ensure document_id is attached to metadata
        for i, meta in enumerate(metadatas):
            meta["document_id"] = document_id
            meta["chunk_index"] = i

        self._collection.add(
            ids=chunk_ids,
            embeddings=embeddings,
            documents=chunks,
            metadatas=metadatas,
        )
        return chunk_ids

    def search(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        document_ids: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search for top_k most relevant chunks matching the query embedding.
        Optionally filter by a list of document IDs.
        """
        where_filter = None
        if document_ids:
            if len(document_ids) == 1:
                where_filter = {"document_id": document_ids[0]}
            elif len(document_ids) > 1:
                where_filter = {"document_id": {"$in": document_ids}}

        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, max(1, self._collection.count())),
            where=where_filter,
            include=["documents", "metadatas", "distances"],
        )

        formatted_results: List[Dict[str, Any]] = []
        if results and results.get("ids") and len(results["ids"]) > 0:
            ids = results["ids"][0]
            docs = results["documents"][0] if results.get("documents") else []
            metas = results["metadatas"][0] if results.get("metadatas") else []
            dists = results["distances"][0] if results.get("distances") else []

            for i in range(len(ids)):
                # Convert distance (cosine distance) to relevance score (1 - distance)
                distance = dists[i] if i < len(dists) else 0.0
                relevance_score = max(0.0, 1.0 - distance) if distance is not None else 1.0

                meta = metas[i] if i < len(metas) else {}
                formatted_results.append({
                    "chunk_id": ids[i],
                    "chunk_text": docs[i] if i < len(docs) else "",
                    "document_id": meta.get("document_id", ""),
                    "chunk_index": meta.get("chunk_index", 0),
                    "filename": meta.get("filename", ""),
                    "file_type": meta.get("file_type", ""),
                    "relevance_score": round(relevance_score, 4),
                })

        return formatted_results

    def delete_document_chunks(self, document_id: str) -> None:
        """Delete all vector records associated with a document_id."""
        try:
            self._collection.delete(where={"document_id": document_id})
        except Exception as e:
            # Silence deletion errors if document was not indexed
            pass

    def get_document_chunks(self, document_id: str) -> List[Dict[str, Any]]:
        """Retrieve all chunk records for a given document_id."""
        results = self._collection.get(
            where={"document_id": document_id},
            include=["documents", "metadatas"],
        )
        chunks: List[Dict[str, Any]] = []
        if results and results.get("ids"):
            ids = results["ids"]
            docs = results.get("documents", [])
            metas = results.get("metadatas", [])
            for i in range(len(ids)):
                meta = metas[i] if i < len(metas) else {}
                chunks.append({
                    "chunk_id": ids[i],
                    "chunk_text": docs[i] if i < len(docs) else "",
                    "document_id": meta.get("document_id", document_id),
                    "chunk_index": meta.get("chunk_index", i),
                    "filename": meta.get("filename", ""),
                    "file_type": meta.get("file_type", ""),
                })
        return sorted(chunks, key=lambda c: c["chunk_index"])

    def count(self) -> int:
        """Get total number of chunks stored in vector database."""
        return self._collection.count()


_vector_store_service_instance: Optional[VectorStoreService] = None


def get_vector_store_service() -> VectorStoreService:
    """Singleton getter for VectorStoreService."""
    global _vector_store_service_instance
    if _vector_store_service_instance is None:
        _vector_store_service_instance = VectorStoreService()
    return _vector_store_service_instance
