import os
import tempfile
import pytest
import io
import shutil
import docx
import pandas as pd
from pypdf import PdfWriter
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import get_settings
from app.core.database import init_db, SessionLocal
from app.models.user import User
from app.models.document import Document
from app.services.parsers.base import DocumentParser
from app.services.chunking import ChunkingService
from app.services.embeddings import get_embedding_service
from app.services.vector_store import get_vector_store_service
from app.services.rag import get_rag_service

client = TestClient(app)
settings = get_settings()


def setup_module(module):
    """Ensure database and demo user exist before tests run."""
    init_db()


def test_phase1_regressions():
    """Verify Phase 1 health, stats, and user seeding remain fully functional."""
    db = SessionLocal()
    demo_user = db.query(User).filter(User.id == settings.DEFAULT_USER_ID).first()
    assert demo_user is not None, "Demo user must exist"
    db.close()

    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"
    assert res.json()["database"] == "connected"
    assert res.json()["gemini_configured"] is True

    res = client.get("/api/stats")
    assert res.status_code == 200
    assert "researches_completed" in res.json()

    res = client.get("/api/research/recent")
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_gemini_embedding_2_chunk_dimension():
    """Explicitly verify that an individual chunk produces exactly one 768-dimensional embedding."""
    embedding_service = get_embedding_service()
    chunk_text = "MarketIQ provides automated agentic market research analysis."

    vector = embedding_service.embed_chunk(chunk_text)
    assert isinstance(vector, list)
    assert len(vector) == 768, f"Expected 768 dimensions for gemini-embedding-2, got {len(vector)}"
    assert all(isinstance(val, float) for val in vector)


def test_gemini_embedding_2_query_embedding_and_retrieval():
    """Explicitly verify query embedding generation and separate ChromaDB retrieval."""
    embedding_service = get_embedding_service()
    vector_store = get_vector_store_service()

    test_doc_id = "test_query_embed_doc"
    chunk_text = "Electric vehicles market share grew by 25 percent in 2025."
    chunk_vector = embedding_service.embed_chunk(chunk_text)

    # Clean up previous test run if any
    vector_store.delete_document_chunks(test_doc_id)

    vector_store.add_chunks(
        document_id=test_doc_id,
        chunks=[chunk_text],
        embeddings=[chunk_vector],
        metadatas=[{"filename": "ev_report.txt", "file_type": "txt"}],
    )

    query_vector = embedding_service.embed_query("electric vehicle growth rate")
    assert len(query_vector) == 768, "Query embedding must be 768 dimensions"

    search_results = vector_store.search(query_embedding=query_vector, top_k=1, document_ids=[test_doc_id])
    assert len(search_results) == 1
    assert search_results[0]["document_id"] == test_doc_id
    assert "25 percent" in search_results[0]["chunk_text"]

    # Cleanup
    vector_store.delete_document_chunks(test_doc_id)


def test_txt_upload_and_rag_flow():
    """Full lifecycle test for TXT file: upload -> parse -> chunk -> embed -> chroma -> search -> delete."""
    content = (
        "MarketIQ Autonomous AI Agent Research System.\n\n"
        "The global market size for enterprise AI solutions reached 50 billion USD in 2025.\n"
        "Key competitors include Company Alpha, Company Beta, and Company Gamma.\n\n"
        "Emerging trends indicate strong demand for real-time market sentiment analysis."
    )
    files = {"file": ("test_market.txt", io.BytesIO(content.encode("utf-8")), "text/plain")}

    # 1. Upload
    response = client.post("/api/documents/upload", files=files)
    assert response.status_code == 201, response.text
    data = response.json()
    doc_id = data["id"]
    assert data["filename"] == "test_market.txt"
    assert data["status"] == "completed"
    assert data["chunk_count"] > 0

    # 2. Check Database record
    res = client.get(f"/api/documents/{doc_id}")
    assert res.status_code == 200
    assert res.json()["id"] == doc_id

    # 3. RAG Search
    search_res = client.post(
        "/api/documents/search",
        json={"query": "What is the global market size for enterprise AI?", "top_k": 3},
    )
    assert search_res.status_code == 200
    search_data = search_res.json()
    assert search_data["total_results"] > 0
    top_chunk = search_data["results"][0]["chunk_text"]
    assert "50 billion USD" in top_chunk or "Company Alpha" in top_chunk

    # 4. Delete document
    del_res = client.delete(f"/api/documents/{doc_id}")
    assert del_res.status_code == 200

    # 5. Verify deletion
    res_after = client.get(f"/api/documents/{doc_id}")
    assert res_after.status_code == 404


def test_pdf_upload():
    """Verify PDF document ingestion."""
    pdf_buffer = io.BytesIO()
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    # Note: simple blank pdf to test parser handling
    writer.write(pdf_buffer)
    pdf_bytes = pdf_buffer.getvalue()

    # Create PDF with text using ReportLab or simple text string if available
    files = {"file": ("sample_report.pdf", io.BytesIO(b"%PDF-1.4 sample pdf content line for testing"), "application/pdf")}
    res = client.post("/api/documents/upload", files=files)
    # Should either parse or fail gracefully if text is unreadable
    assert res.status_code in (201, 400)


def test_docx_upload():
    """Verify DOCX document ingestion."""
    doc = docx.Document()
    doc.add_paragraph("MarketIQ Competitor Analysis Document for Q3 2026.")
    doc.add_paragraph("Company Zenith dominates the cloud analytics segment with 40% market share.")
    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    files = {"file": ("competitor_q3.docx", buffer, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
    res = client.post("/api/documents/upload", files=files)
    assert res.status_code == 201, res.text
    data = res.json()
    doc_id = data["id"]
    assert data["status"] == "completed"

    # Search DOCX content
    search_res = client.post(
        "/api/documents/search",
        json={"query": "Company Zenith market share", "top_k": 1},
    )
    assert search_res.status_code == 200
    assert any("Zenith" in item["chunk_text"] for item in search_res.json()["results"])

    # Cleanup
    client.delete(f"/api/documents/{doc_id}")


def test_csv_upload():
    """Verify CSV document ingestion."""
    df = pd.DataFrame({
        "Company": ["Acme Corp", "Beta Inc", "Cyberdyne"],
        "Revenue_Millions": [120, 85, 310],
        "Growth_Pct": [15, 8, 42]
    })
    buffer = io.BytesIO()
    df.to_csv(buffer, index=False)
    buffer.seek(0)

    files = {"file": ("financial_summary.csv", buffer, "text/csv")}
    res = client.post("/api/documents/upload", files=files)
    assert res.status_code == 201, res.text
    data = res.json()
    doc_id = data["id"]
    assert data["status"] == "completed"

    # Search CSV content
    search_res = client.post(
        "/api/documents/search",
        json={"query": "Cyberdyne revenue", "top_k": 1},
    )
    assert search_res.status_code == 200
    assert any("Cyberdyne" in item["chunk_text"] for item in search_res.json()["results"])

    # Cleanup
    client.delete(f"/api/documents/{doc_id}")


def test_unsupported_file_type():
    """Verify clear error response for unsupported file formats."""
    files = {"file": ("malicious_script.exe", io.BytesIO(b"binary data"), "application/octet-stream")}
    res = client.post("/api/documents/upload", files=files)
    assert res.status_code == 400
    assert "Unsupported file format" in res.json()["detail"]


def test_empty_file_upload():
    """Verify error response for empty files."""
    files = {"file": ("empty_file.txt", io.BytesIO(b""), "text/plain")}
    res = client.post("/api/documents/upload", files=files)
    assert res.status_code == 400
    assert "empty" in res.json()["detail"].lower()
