"""
Embedding service utilizing Google's official GenAI SDK (google-genai) and gemini-embedding-2.
Provides 768-dimensional embeddings for document chunks and search queries using asymmetric task prefixes.
"""
from typing import List, Optional
from google.genai import types

from app.core.config import get_settings
from app.services.llm import get_llm_service


class EmbeddingService:
    def __init__(self, model: Optional[str] = None, dimension: Optional[int] = None):
        settings = get_settings()
        self.model = model or settings.EMBEDDING_MODEL
        self.dimension = dimension or settings.EMBEDDING_DIMENSION
        self._llm_service = get_llm_service()

    def embed_chunk(self, chunk_text: str) -> List[float]:
        """
        Embed an individual document chunk using asymmetric document prefix.
        Returns a single 768-dimensional embedding vector.
        """
        if not chunk_text or not chunk_text.strip():
            raise ValueError("Cannot generate embedding for empty chunk text.")

        # Asymmetric document prefix for retrieval
        formatted_text = f"search document: {chunk_text.strip()}"

        client = self._llm_service.client
        config = types.EmbedContentConfig(output_dimensionality=self.dimension)
        response = client.models.embed_content(
            model=self.model,
            contents=formatted_text,
            config=config,
        )

        embedding = self._extract_vector(response)
        if len(embedding) != self.dimension:
            raise ValueError(f"Expected embedding dimension {self.dimension}, got {len(embedding)}")
        return embedding

    def embed_chunks(self, chunks: List[str]) -> List[List[float]]:
        """
        Embed a list of document chunks individually, returning a list of 768-dimensional vectors.
        Each chunk receives its own unique embedding.
        """
        embeddings: List[List[float]] = []
        for chunk in chunks:
            vector = self.embed_chunk(chunk)
            embeddings.append(vector)
        return embeddings

    def embed_query(self, query_text: str) -> List[float]:
        """
        Embed a user search query using asymmetric query prefix.
        Returns a single 768-dimensional query embedding vector.
        """
        if not query_text or not query_text.strip():
            raise ValueError("Cannot generate embedding for empty query text.")

        # Asymmetric query prefix for retrieval
        formatted_query = f"search query: {query_text.strip()}"

        client = self._llm_service.client
        config = types.EmbedContentConfig(output_dimensionality=self.dimension)
        response = client.models.embed_content(
            model=self.model,
            contents=formatted_query,
            config=config,
        )

        embedding = self._extract_vector(response)
        if len(embedding) != self.dimension:
            raise ValueError(f"Expected query embedding dimension {self.dimension}, got {len(embedding)}")
        return embedding

    def _extract_vector(self, response: getattr(types, "EmbedContentResponse", object)) -> List[float]:
        """Helper to extract float values from SDK response."""
        if hasattr(response, "embedding") and response.embedding and hasattr(response.embedding, "values"):
            return list(response.embedding.values)
        if hasattr(response, "embeddings") and response.embeddings and len(response.embeddings) > 0:
            return list(response.embeddings[0].values)
        raise ValueError("Failed to extract embedding values from Gemini response.")


_embedding_service_instance: Optional[EmbeddingService] = None


def get_embedding_service() -> EmbeddingService:
    """Singleton getter for EmbeddingService."""
    global _embedding_service_instance
    if _embedding_service_instance is None:
        _embedding_service_instance = EmbeddingService()
    return _embedding_service_instance
