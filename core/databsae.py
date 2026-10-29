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
# Engine (Supports both PostgreSQL and SQLite for offline / standalone use)
# ---------------------------------------------------------------------------
connect_args = {}
engine_kwargs = {"echo": (settings.ENVIRONMENT == "development")}

if settings.DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False
else:
    engine_kwargs["pool_pre_ping"] = True
    engine_kwargs["pool_size"] = 10
    engine_kwargs["max_overflow"] = 20

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    **engine_kwargs,
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
