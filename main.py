"""
main.py — FastAPI application entry point for SATS Companion.

Karnataka SATS (Student Achievement Tracking System) Companion API
A middleware/companion service that provides REST endpoints for:
  - Teacher authentication (KGID-based JWT)
  - School and teacher management
  - Student enrollment and tracking
  - Attendance marking (bulk)
  - Assessment recording and reporting
  - Transfer Certificate lifecycle
  - AI-powered insights via Google Gemini

Usage:
    uvicorn main:app --reload --port 8000

Swagger UI: http://localhost:8000/docs
ReDoc:       http://localhost:8000/redoc
"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
import os

from core.config import settings
from core.databsae import engine, Base
from core import models  # noqa: F401 — registers all ORM models with Base metadata
from api.v1.router import v1_router

# ---------------------------------------------------------------------------
# Create all database tables on startup (idempotent — safe to re-run)
# ---------------------------------------------------------------------------
Base.metadata.create_all(bind=engine)

# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------
app = FastAPI(
    title="SATS Companion API",
    description=(
        "Companion middleware for the Karnataka Student Achievement Tracking System (SATS). "
        "Provides teacher authentication, student management, attendance tracking, "
        "assessment recording, Transfer Certificate workflows, and AI-powered insights "
        "via Google Gemini — all designed for Karnataka government and aided school teachers."
    ),
    version="1.0.0",
    contact={
        "name": "Karnataka SATS Companion",
        "url": "https://sats.karnataka.gov.in",
    },
    license_info={
        "name": "Government of Karnataka",
    },
    openapi_tags=[
        {"name": "Authentication", "description": "Teacher login (KGID + password) and JWT management"},
        {"name": "Schools", "description": "Karnataka school (DISE) management"},
        {"name": "Teachers", "description": "Teacher registration and profile management"},
        {"name": "Students", "description": "Student enrollment, update, and withdrawal"},
        {"name": "Attendance", "description": "Bulk attendance marking and reports"},
        {"name": "Assessments", "description": "FA/SA assessment recording and analysis"},
        {"name": "Transfer Certificates", "description": "TC request and approval workflow"},
        {"name": "AI Insights (Gemini)", "description": "Google Gemini-powered educational insights"},
    ],
)

# ---------------------------------------------------------------------------
# CORS middleware — allow frontend (React/Vue/etc.) to call the API
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.ENVIRONMENT == "development" else [
        "https://sats.karnataka.gov.in",
        "https://companion.sats.karnataka.gov.in",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Global exception handler — ensures consistent error response envelope
# ---------------------------------------------------------------------------
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch-all handler that wraps unhandled exceptions in the standard envelope."""
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "message": "An unexpected internal error occurred. Please try again later.",
            "data": None,
        },
    )


# ---------------------------------------------------------------------------
# API versioned router
# ---------------------------------------------------------------------------
app.include_router(v1_router, prefix="/api/v1")

# ---------------------------------------------------------------------------
# Static files for Offline-First PWA Client
# ---------------------------------------------------------------------------
_static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(_static_dir):
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")

# ---------------------------------------------------------------------------
# Health / root endpoints
# ---------------------------------------------------------------------------

@app.get("/", tags=["Health"], summary="Root web entry")
def root():
    """
    Root endpoint: redirects browser to the offline-capable PWA client,
    or returns service status if static assets are not mounted.
    """
    if os.path.isdir(_static_dir):
        return RedirectResponse(url="/static/index.html")
    return {
        "status": "success",
        "message": "SATS Companion Middleware is online",
        "data": {
            "service": "SATS Companion API",
            "version": "1.0.0",
            "environment": settings.ENVIRONMENT,
            "description": "Karnataka Student Achievement Tracking System — Companion Middleware",
        },
    }


@app.get("/health", tags=["Health"], summary="Detailed health check")
def health_check():
    """
    Detailed health check. Verifies database connectivity.
    """
    from sqlalchemy import text  # noqa: PLC0415
    from core.databsae import SessionLocal  # noqa: PLC0415

    db_ok = False
    db_error = None
    try:
        with SessionLocal() as session:
            session.execute(text("SELECT 1"))
            db_ok = True
    except Exception as exc:
        db_error = str(exc)

    return {
        "status": "success" if db_ok else "degraded",
        "message": "All systems operational" if db_ok else "Database unavailable",
        "data": {
            "database": "connected" if db_ok else f"error: {db_error}",
            "gemini_configured": bool(
                settings.GOOGLE_API_KEY and settings.GOOGLE_API_KEY != "your-gemini-api-key-here"
            ),
            "environment": settings.ENVIRONMENT,
        },
    }
