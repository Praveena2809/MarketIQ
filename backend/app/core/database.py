from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.core.config import get_settings

settings = get_settings()

connect_args = {"check_same_thread": False} if not settings.is_postgres else {}

engine = create_engine(settings.DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency: yields a DB session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create tables if they don't exist and seed default demo user. Called once at startup."""
    # Import models here so they register on Base.metadata before create_all.
    from app.models import user, research, document, source, research_result  # noqa: F401
    from app.models.user import User

    Base.metadata.create_all(bind=engine)

    # Safe migration helper for added columns in SQLite
    from sqlalchemy import inspect, text
    inspector = inspect(engine)
    if "documents" in inspector.get_table_names():
        columns = [c["name"] for c in inspector.get_columns("documents")]
        with engine.connect() as conn:
            if "file_size" not in columns:
                conn.execute(text("ALTER TABLE documents ADD COLUMN file_size INTEGER DEFAULT 0"))
            if "status" not in columns:
                conn.execute(text("ALTER TABLE documents ADD COLUMN status VARCHAR DEFAULT 'uploaded'"))
            if "error_message" not in columns:
                conn.execute(text("ALTER TABLE documents ADD COLUMN error_message VARCHAR"))
            conn.commit()

    if "researches" in inspector.get_table_names():
        columns = [c["name"] for c in inspector.get_columns("researches")]
        with engine.connect() as conn:
            if "error_message" not in columns:
                conn.execute(text("ALTER TABLE researches ADD COLUMN error_message VARCHAR"))
            conn.commit()

    # Seed default demo user if missing
    db = SessionLocal()
    try:
        demo_user = db.query(User).filter(User.id == settings.DEFAULT_USER_ID).first()
        if not demo_user:
            demo_user = User(
                id=settings.DEFAULT_USER_ID,
                email=settings.DEFAULT_USER_EMAIL,
                hashed_password="demo_password_hash",
            )
            db.add(demo_user)
            db.commit()
    except Exception as e:
        db.rollback()
        print(f"Warning: Failed to seed default user: {e}")
    finally:
        db.close()

