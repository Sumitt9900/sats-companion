"""
core/databsae.py — Database engine and session factory for SATS Companion.

Note: The filename intentionally keeps the original typo ("databsae") so
imports from existing skeleton code remain unbroken.

Uses synchronous SQLAlchemy 2.0 sessions with psycopg2 for PostgreSQL.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from core.config import settings


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,          # Detect stale connections before use
    pool_size=10,                # Default connection pool size
    max_overflow=20,             # Extra connections allowed under load
    echo=(settings.ENVIRONMENT == "development"),  # SQL logging in dev
)


# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)


# ---------------------------------------------------------------------------
# Declarative base — all ORM models inherit from this
# ---------------------------------------------------------------------------
class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""
    pass


# ---------------------------------------------------------------------------
# FastAPI dependency — yields a DB session per request
# ---------------------------------------------------------------------------
def get_db():
    """
    Dependency that provides a SQLAlchemy session.

    Usage in route::

        @router.get("/endpoint")
        def my_endpoint(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
