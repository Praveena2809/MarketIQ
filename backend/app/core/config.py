"""
Central application settings.

Everything that varies between local dev and production is read from
environment variables (see .env.example). Nothing here is a real secret.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ENVIRONMENT: str = "development"

    # Database: defaults to a local SQLite file so the project runs with
    # zero external setup, but any SQLAlchemy-compatible Postgres URL
    # (postgresql+psycopg2://...) can be dropped in without code changes.
    DATABASE_URL: str = "sqlite:///./marketiq.db"

    # AI - Google Gemini
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.6-flash"
    EMBEDDING_MODEL: str = "gemini-embedding-2"
    EMBEDDING_DIMENSION: int = 768

    # Vector Database & RAG
    VECTOR_DB_DIR: str = "data/chroma"
    CHROMA_COLLECTION_NAME: str = "marketiq_documents"
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 150
    MAX_RAG_TOP_K: int = 5

    # Research Engine Settings
    MAX_RESEARCH_QUERIES: int = 5

    # User Context
    DEFAULT_USER_ID: str = "demo_user"
    DEFAULT_USER_EMAIL: str = "demo@marketiq.ai"

    # News provider (Step 5) - optional. If NEWS_API_KEY is empty or the
    # provider is unreachable/quota-limited, the News Agent fails gracefully
    # and research continues with an explicit "news unchecked" status - it
    # never fabricates articles or URLs.
    NEWS_PROVIDER: str = "newsapi"
    NEWS_BASE_URL: str = "https://newsapi.org/v2/everything"
    NEWS_API_KEY: str = ""
    # Look back window for "recent" news, in days.
    NEWS_RECENCY_DAYS: int = 30
    # Max news articles retained per research job.
    NEWS_RESULTS_PER_QUERY: int = 5
    # Max distinct news searches per research job (bounded, no open loop).
    NEWS_QUERY_LIMIT: int = 1
    NEWS_LANGUAGE: str = "en"
    NEWS_REQUEST_TIMEOUT: int = 10

    CORS_ORIGINS: str = "http://localhost:5173"
    SECRET_KEY: str = "change-me-in-production"

    # Uploads
    UPLOAD_DIR: str = "uploads"
    MAX_UPLOAD_MB: int = 20
    ALLOWED_UPLOAD_EXTENSIONS: tuple = (".pdf", ".txt", ".docx", ".csv")

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def is_postgres(self) -> bool:
        return self.DATABASE_URL.startswith("postgresql")


@lru_cache
def get_settings() -> Settings:
    return Settings()
