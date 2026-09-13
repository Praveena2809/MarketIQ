# MarketIQ — AI Market Research Assistant

An agentic market research platform: enter a research question, and (once the
remaining build steps land) MarketIQ retrieves your uploaded documents via
RAG, pulls recent news, profiles competitors, reads sentiment, spots emerging
trends, and produces a structured, source-backed report.

## Status: Foundation (Build Step 1 of 13)

This milestone stands up the full-stack skeleton and proves it runs
end-to-end, per the project's own build order — agents, RAG, and the rest of
the dashboard come in the steps after this one (see **Roadmap** below).

What exists right now:
- React (Vite) frontend with routing, the left navigation rail, and a real
  **Dashboard** page (welcome search bar, quick stats, recent research list)
  wired to the backend — no hardcoded fake numbers, it shows genuine empty
  states until real research exists.
- FastAPI backend with a real database connection (SQLite locally,
  swappable to PostgreSQL via one env var), `/api/health`, `/api/stats`, and
  `/api/research/recent`.
- Data models for `User`, `Research`, `Document`, `Source`, `ResearchResult`.
- `.env.example` — no secrets committed.

## Run it locally

**Backend** (Python 3.11+):
```bash
cd backend
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # fill in OPENAI_API_KEY when you reach RAG
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
│   │   ├── api/                   # health.py, dashboard.py
│   │   └── agents/                 # (empty — RAG/News/Competitor/etc. land in later steps)
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   └── src/
│       ├── components/            # Sidebar, StatPanel, RecentResearchCard
│       ├── pages/                 # DashboardPage + placeholder pages for other routes
│       └── lib/api.js             # backend API client
└── data/sample/                    # sample documents/news land here in Step 3+
```

## Roadmap (per the project's build order)

| Step | Deliverable |
|---|---|
| 1 | ✅ Project setup, DB connection, health check, dashboard shell |
| 2 | Basic research API (query → LLM → response) |
| 3 | Document ingestion (PDF/TXT/DOCX/CSV → chunks) |
| 4 | RAG pipeline (retrieval → context → answer + sources) |
| 5–9 | News, Competitor, Sentiment, Trend, Insight/Report agents |
| 10–13 | Full dashboard, research history, follow-up Q&A, polish |

Each step will be built, run, and tested before moving to the next — no
half-finished features left in place.
