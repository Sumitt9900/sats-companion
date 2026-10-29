"""
api/v1/auth.py — Authentication endpoints for SATS Companion.

POST /api/v1/auth/login  — Teacher login with KGID + password
POST /api/v1/auth/refresh — Token refresh
"""
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
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
from schemas.auth import LoginRequest, RefreshRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _success(data: dict, message: str = "OK") -> dict:
    return {"status": "success", "message": message, "data": data}


@router.post("/login", response_model=dict, summary="Teacher login")
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    """
    Authenticate a teacher using KGID and password.

    Returns a JWT access token on success.

    - **kgid**: Karnataka Government ID / Employee ID
    - **password**: Account password
    """
    teacher: Teacher = db.query(Teacher).filter(
        Teacher.kgid == payload.kgid,
        Teacher.is_active == True,
    ).first()

    if not teacher or not verify_password(payload.password, teacher.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid KGID or password",
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
            "is_admin": teacher.is_admin,
        },
        "Login successful",
    )


@router.post("/refresh", response_model=dict, summary="Refresh JWT token")
def refresh_token(payload: RefreshRequest):
    """
    Issue a new JWT token given a valid (non-expired) existing token.

    Useful for extending sessions without re-authenticating.
    """
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


@router.get("/me", response_model=dict, summary="Current teacher profile (quick check)")
def me(teacher: Teacher = Depends(get_current_teacher)):
    """Return basic profile of the currently authenticated teacher."""
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
