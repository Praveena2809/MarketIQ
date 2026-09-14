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
- **Step 5 / News Research — COMPLETE**: recent-news retrieval via NewsAPI,
  normalized into the existing evidence/synthesis architecture with full
  provenance (title, URL, publisher, publication date). Integrates with the
  research pipeline; gracefully falls back when the provider is unconfigured
  or unreachable. No new Python dependencies added.
- **Step 6 / Competitor research — COMPLETE**: per-competitor spotlight
  profiles (name, overview, product, pricing, funding, positioning) with
  honest "not enough evidence" states.
- **Step 7 / Sentiment research — COMPLETE**: per-report sentiment scores with
  dedicated, clearly-labeled uncertain/neutral states and explicit
  confidence caveats.
- **Step 8 / Trend research — COMPLETE**: API-available emerging-trend
  articles and API `trends` data behind the pipeline-failure gate.
- **Steps 9–10 / Insight/Report synthesis + full dashboard — COMPLETE**: the
  final structured report object (opportunities, risks, conclusion, etc.)
  persisted per run, with a real dashboard over the data.
- **Step 11 / Research history — COMPLETE**: full history view with search,
  status and research-type filters, paginated load-more, and deep-linkable
  report pages.
- **Step 12 / Follow-up Q&A — COMPLETE**: per-report in-context Q&A box that
  answers follow-up questions using the stored research context via a single
  LLM call.

Next development milestone: **Step 13 — Polish** — a final pass to tighten
consistency (shared error banner, one `<h1>` per page, consistent loading /
toggle semantics), accessibility (focus-visible outlines, `aria-pressed`
toggles, live-region announcement for follow-up answers), documentation and
cleanup of unused/dependencies.

What exists right now:
- React (Vite) frontend with routing, the left navigation rail, and a real
  **Dashboard** page (welcome search bar, quick stats across all engine
  outputs, sentiment / research / source mix chips, recent research list)
  wired to the backend — no hardcoded fake numbers, it shows genuine empty
  states until real research exists.
- A full **Research History** view: search, status and research-type filters,
  load-more pagination, and deep-linkable report pages.
- A **Follow-up Q&A** box on every report: ask a follow-up question and the
  backend answers from the stored research context (with the research sources
  shown below the answer).
- Competitor, Sentiment and Trend analysis pages with honest empty/uncertain
  states, plus a Sources tab that lists every recorded research source.
- FastAPI backend with a real database connection (SQLite locally,
  swappable to PostgreSQL via one env var): `/api/health`, `/api/stats`,
  `/api/research/recent`, `/api/research/history`, `/api/research/*` (incl.
  `/follow-up`), `/api/documents/*`, plus `/api/competitors`,
  `/api/sentiment`, `/api/trends` routes.
- Document ingestion for PDF/TXT/DOCX/CSV with chunking, Gemini embeddings
  (768-dim), and a ChromaDB vector store.
- An AI research engine that gathers web, news, and document evidence and
  synthesizes a structured, source-backed report (Gemini + Google Search
  grounding + NewsAPI for recent news).
- News research via `NewsResearchAgent`: derives focused search queries,
  retrieves recent articles from NewsAPI, normalizes them into
  evidence with real provenance, and feeds them into synthesis. Falls back
  honestly (no fabricated articles) when `NEWS_API_KEY` is missing or the
  provider is unavailable.
- Data models for `User`, `Research`, `Document`, `Source`, `ResearchResult`,
  plus a persisted `ResearchResult` per run.
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
│   │   ├── agents/               # research, web-research, news-research, document-research, synthesis agents
│   │   └── services/             # llm, embeddings, vector_store, chunking, rag, parsers/, news/, research/
│   │       └── research/         # follow_up.py (+ helpers)
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   └── src/
│       ├── components/            # Sidebar, Header, StatPanel, EmptyState, StatusBadge, cards, FollowUpBox
│       ├── hooks/                 # useRecentReports, useResearchHistory
│       ├── lib/                   # format.js (date/type formatting)
│       ├── pages/                 # DashboardPage, NewResearchPage, ResearchReportPage, ReportsPage, …
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
| 5 | News research (NewsAPI, recent-news evidence, provenance) | Complete |
| 6 | Competitor research | Complete |
| 7–9 | Sentiment, Trend, Insight/Report agents | Complete |
| 10 | Full dashboard | Complete |
| 11 | Research history | Complete |
| 12 | Follow-up Q&A | Complete |
| 13 | Polish | Next |

Each step will be built, run, and tested before moving to the next — no
half-finished features left in place.
