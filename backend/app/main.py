from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.database import init_db
from app.api import health, dashboard, documents, research

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="MarketIQ API",
    description="AI Market Research Assistant - agentic backend",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(dashboard.router, prefix="/api", tags=["dashboard"])
app.include_router(documents.router, prefix="/api/documents", tags=["documents"])
app.include_router(research.router, prefix="/api/research", tags=["research"])


@app.get("/")
def root():
    return {"service": "MarketIQ API", "docs": "/docs"}
