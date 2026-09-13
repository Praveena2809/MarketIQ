# MarketIQ — AI Market Research Assistant

An agentic market research platform: enter a research question, and MarketIQ
retrieves your uploaded documents via RAG, pulls recent news, profiles
competitors, reads sentiment, spots emerging trends, and produces a
structured, source-backed report.

## Status

The core platform is built, run, and tested end-to-end. Current completion:

- **Phase 1 / Foundation — COMPLETE**: project setup, DB connection, health
  checks, dashboard shell.
- **Phase 2 / AI Research Engine — COMPLETE**: query → evidence gathering
  (web grounding + document RAG) → LLM synthesis → structured, source-backed
  report.
- **Phase 3 / Document Ingestion + RAG — COMPLETE**: PDF/TXT/DOCX/CSV
  ingestion (parse → chunk → embed → vector store) and retrieval.
- **RAG pipeline (retrieval → context → answer + sources) — COMPLETE**.

Next development milestone: **News Research**.

What exists right now:
- React (Vite) frontend with routing, the left navigation rail, and a real
  **Dashboard** page (welcome search bar, quick stats, recent research list)
  wired to the backend — no hardcoded fake numbers, it shows genuine empty
  states until real research exists.
- FastAPI backend with a real database connection (SQLite locally,
  swappable to PostgreSQL via one env var): `/api/health`, `/api/stats`,
  `/api/research/recent`, `/api/documents/*`, and `/api/research/*`.
- Document ingestion for PDF/TXT/DOCX/CSV with chunking, Gemini embeddings
  (768-dim), and a ChromaDB vector store.
- An AI research engine that gathers web and document evidence and
  synthesizes a structured, source-backed report (Gemini + Google Search
  grounding).
- Data models for `User`, `Research`, `Document`, `Source`, `ResearchResult`.
- `.env.example` — no secrets committed.

## Run it locally

**Backend** (Python 3.11+):
```bash
cd backend
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # fill in GEMINI_API_KEY
uvicorn app.main:app --reload --port 8000
```
Visit `http://localhost:8000/docs` for interactive API docs.

**Frontend** (Node 18+), in a second terminal:
```bash
cd frontend
npm install
npm run dev
```
Visit `http://localhost:5173`. The dev server proxies `/api/*` to the
backend on port 8000, so both must be running.

## Project structure

```text
MarketIQ/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app + router registration
│   │   ├── core/
│   │   │   ├── config.py        # env-driven settings
│   │   │   └── database.py      # SQLAlchemy engine/session (SQLite/Postgres)
│   │   ├── models/               # User, Research, Document, Source, ResearchResult
│   │   ├── schemas/               # Pydantic request/response models
│   │   ├── api/                   # health.py, dashboard.py, documents.py, research.py
│   │   ├── agents/               # research, web-research, document-research, synthesis agents
│   │   └── services/             # llm, embeddings, vector_store, chunking, rag, parsers/, research/
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   └── src/
│       ├── components/            # Sidebar, StatPanel, RecentResearchCard, report cards
│       ├── pages/                 # DashboardPage, NewResearchPage, ResearchReportPage, ...
│       └── services/api.js        # backend API client
└── data/sample/                   # sample documents/news land here in later steps
```

## Roadmap (per the project's build order)

| Step | Deliverable | Status |
|---|---|---|
| 1 | Project setup, DB connection, health check, dashboard shell | Complete |
| 2 | Basic research API (query → LLM → response) | Complete |
| 3 | Document ingestion (PDF/TXT/DOCX/CSV → chunks) | Complete |
| 4 | RAG pipeline (retrieval → context → answer + sources) | Complete |
| 5 | News research | Next |
| 6–9 | Competitor, Sentiment, Trend, Insight/Report agents | Planned |
| 10–13 | Full dashboard, research history, follow-up Q&A, polish | Planned |

Each step will be built, run, and tested before moving to the next — no
half-finished features left in place.
