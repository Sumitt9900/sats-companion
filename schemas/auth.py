"""
schemas/auth.py — Pydantic schemas for authentication endpoints.
"""
from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """Request body for POST /auth/login."""

    kgid: str = Field(..., description="Teacher's KGID / Employee ID", examples=["KGD123456"])
    password: str = Field(..., min_length=6, description="Teacher's account password")


class TokenResponse(BaseModel):
    """Successful login / refresh response."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Token lifetime in seconds")
    teacher_id: str
    name: str
    is_admin: bool


class RefreshRequest(BaseModel):
    """Request body for POST /auth/refresh."""

    token: str = Field(..., description="Existing (non-expired) JWT access token")
