"""
api/v1/auth.py — Authentication endpoints for SATS Companion.

POST /api/v1/auth/login  — Teacher login with KGID + password (OAuth2 form OR JSON)
POST /api/v1/auth/refresh — Token refresh
GET  /api/v1/auth/me      — Current authenticated teacher profile
"""
from datetime import timedelta

from fastapi import APIRouter, Depends, Form, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from core.config import settings
from core.databsae import get_db
from core.models import Teacher
from core.security import (
    create_access_token,
    decode_access_token,
    verify_password,
    get_current_teacher,
)
from schemas.auth import RefreshRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _success(data: dict, message: str = "OK") -> dict:
    return {"status": "success", "message": message, "data": data}


@router.post(
    "/login",
    response_model=dict,
    summary="Teacher login (KGID + password)",
    description=(
        "Authenticate using KGID (Karnataka Government ID) and password. "
        "Accepts **OAuth2 form** (`username`/`password` fields) as well as **JSON** "
        "(`{\"kgid\": ..., \"password\": ...}`). Returns a JWT bearer token."
    ),
)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """
    Login endpoint that accepts the standard OAuth2 password form.

    The `username` field is used as the KGID.  This makes it compatible with
    both the Swagger UI "Authorize" button and the PWA frontend login form.
    """
    kgid = form_data.username.strip()

    teacher: Teacher = db.query(Teacher).filter(
        Teacher.kgid == kgid,
        Teacher.is_active == True,  # noqa: E712
    ).first()

    if not teacher or not verify_password(form_data.password, teacher.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid KGID or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    expire_minutes = settings.ACCESS_TOKEN_EXPIRE_MINUTES
    token = create_access_token(
        data={"sub": teacher.id, "kgid": teacher.kgid},
        expires_delta=timedelta(minutes=expire_minutes),
    )

    return _success(
        {
            "access_token": token,
            "token_type": "bearer",
            "expires_in": expire_minutes * 60,
            "teacher_id": teacher.id,
            "name": teacher.name,
            "designation": teacher.designation.value if teacher.designation else None,
            "is_admin": teacher.is_admin,
            "kgid": teacher.kgid,
            "school_dise_code": teacher.school_dise_code,
        },
        "Login successful",
    )


@router.post("/refresh", response_model=dict, summary="Refresh JWT token")
def refresh_token(payload: RefreshRequest):
    """Issue a new JWT token given a valid (non-expired) existing token."""
    decoded = decode_access_token(payload.token)
    teacher_id = decoded.get("sub")
    kgid = decoded.get("kgid")

    if not teacher_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    expire_minutes = settings.ACCESS_TOKEN_EXPIRE_MINUTES
    new_token = create_access_token(
        data={"sub": teacher_id, "kgid": kgid},
        expires_delta=timedelta(minutes=expire_minutes),
    )
    return _success(
        {
            "access_token": new_token,
            "token_type": "bearer",
            "expires_in": expire_minutes * 60,
        },
        "Token refreshed",
    )


@router.get("/me", response_model=dict, summary="Current teacher profile")
def me(teacher: Teacher = Depends(get_current_teacher)):
    """Return profile of the currently authenticated teacher."""
    return _success(
        {
            "teacher_id": teacher.id,
            "kgid": teacher.kgid,
            "name": teacher.name,
            "designation": teacher.designation.value if teacher.designation else None,
            "is_admin": teacher.is_admin,
            "school_dise_code": teacher.school_dise_code,
        }
    )
