import os
import shutil
import uuid
from typing import List

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.models.document import Document
from app.schemas.document import (
    DocumentResponse,
    DocumentSearchRequest,
    DocumentSearchResponse,
    DocumentSearchResultItem,
)
from app.services.parsers.base import DocumentParser
from app.services.chunking import ChunkingService
from app.services.embeddings import get_embedding_service
from app.services.vector_store import get_vector_store_service
from app.services.rag import get_rag_service

router = APIRouter()
settings = get_settings()


@router.post("/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> DocumentResponse:
    if not file or not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No file provided.",
        )

    filename = file.filename
    ext = os.path.splitext(filename)[1].lower()

    if ext not in settings.ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file format '{ext}'. Allowed extensions: {', '.join(settings.ALLOWED_UPLOAD_EXTENSIONS)}",
        )

    # Ensure uploads directory exists
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    document_id = str(uuid.uuid4())
    stored_filename = f"{document_id}_{filename}"
    file_path = os.path.join(settings.UPLOAD_DIR, stored_filename)

    # Save uploaded file
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save uploaded file: {str(e)}",
        )

    file_size = os.path.getsize(file_path)
    if file_size == 0:
        os.remove(file_path)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    if file_size > settings.MAX_UPLOAD_MB * 1024 * 1024:
        os.remove(file_path)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File exceeds maximum allowed size of {settings.MAX_UPLOAD_MB}MB.",
        )

    # Create initial DB record
    doc_record = Document(
        id=document_id,
        user_id=settings.DEFAULT_USER_ID,
        filename=filename,
        file_type=ext.lstrip("."),
        storage_path=file_path,
        file_size=file_size,
        status="processing",
        chunk_count=0,
    )
    db.add(doc_record)
    db.commit()
    db.refresh(doc_record)

    vector_store = get_vector_store_service()
    embedding_service = get_embedding_service()
    chunking_service = ChunkingService()

    try:
        # 1. Parse text
        raw_text = DocumentParser.parse_document(file_path, ext.lstrip("."))

        # 2. Chunk text
        chunks = chunking_service.chunk_text(raw_text)
        if not chunks:
            raise ValueError("No valid text chunks could be extracted from the document.")

        # 3. Generate embeddings using gemini-embedding-2 (768-dim)
        embeddings = embedding_service.embed_chunks(chunks)

        # 4. Store in ChromaDB
        metadatas = [
            {
                "filename": filename,
                "file_type": ext.lstrip("."),
            }
            for _ in chunks
        ]
        vector_store.add_chunks(
            document_id=document_id,
            chunks=chunks,
            embeddings=embeddings,
            metadatas=metadatas,
        )

        # 5. Update DB status to completed
        doc_record.status = "completed"
        doc_record.chunk_count = len(chunks)
        db.commit()
        db.refresh(doc_record)
        return doc_record

    except Exception as e:
        # Mark as failed in DB
        doc_record.status = "failed"
        doc_record.error_message = str(e)
        db.commit()

        # Cleanup vector store data if any
        vector_store.delete_document_chunks(document_id)

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Document processing failed: {str(e)}",
        )


@router.get("", response_model=List[DocumentResponse])
def list_documents(db: Session = Depends(get_db)) -> List[DocumentResponse]:
    docs = db.scalars(
        select(Document).order_by(Document.uploaded_at.desc())
    ).all()
    return list(docs)


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(document_id: str, db: Session = Depends(get_db)) -> DocumentResponse:
    doc = db.scalar(select(Document).where(Document.id == document_id))
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found.",
        )
    return doc


@router.delete("/{document_id}", status_code=status.HTTP_200_OK)
def delete_document(document_id: str, db: Session = Depends(get_db)) -> dict:
    doc = db.scalar(select(Document).where(Document.id == document_id))
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found.",
        )

    # 1. Delete ChromaDB vectors
    vector_store = get_vector_store_service()
    vector_store.delete_document_chunks(document_id)

    # 2. Delete local physical file
    if doc.storage_path and os.path.exists(doc.storage_path):
        try:
            os.remove(doc.storage_path)
        except Exception:
            pass

    # 3. Delete DB record
    db.delete(doc)
    db.commit()

    return {"message": f"Document '{document_id}' deleted successfully."}


@router.post("/search", response_model=DocumentSearchResponse)
def search_documents(
    req: DocumentSearchRequest,
) -> DocumentSearchResponse:
    if not req.query or not req.query.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query string cannot be empty.",
        )

    rag_service = get_rag_service()
    try:
        raw_results = rag_service.retrieve(
            query=req.query,
            top_k=req.top_k,
            document_ids=req.document_ids,
        )
        items = [DocumentSearchResultItem(**r) for r in raw_results]
        return DocumentSearchResponse(
            query=req.query,
            results=items,
            total_results=len(items),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {str(e)}",
        )
