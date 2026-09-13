from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    file_type: str
    file_size: int
    status: str
    chunk_count: int
    error_message: Optional[str] = None
    uploaded_at: datetime


class DocumentSearchRequest(BaseModel):
    query: str
    top_k: int = 5
    document_ids: Optional[List[str]] = None


class DocumentSearchResultItem(BaseModel):
    chunk_id: str
    chunk_text: str
    document_id: str
    chunk_index: int
    filename: str
    file_type: str
    relevance_score: Optional[float] = None


class DocumentSearchResponse(BaseModel):
    query: str
    results: List[DocumentSearchResultItem]
    total_results: int
