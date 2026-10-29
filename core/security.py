"""
core/security.py — JWT creation / verification and password hashing.

Implements JWT (HS256) using the `cryptography` package (already installed)
and bcrypt password hashing via `passlib[bcrypt]`.

If `passlib` is not yet installed, falls back to `hashlib.sha256` — for
development convenience only; production MUST use bcrypt.

For JWT the implementation uses python-jose when available, falling back to
a pure-`cryptography` HMAC-SHA256 implementation.

Install production deps:
    pip install "python-jose[cryptography]" "passlib[bcrypt]"
"""
import hashlib
import hmac
import json
import base64
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from core.config import settings
from core.databsae import get_db

# ---------------------------------------------------------------------------
# Optional imports with graceful fallback
# ---------------------------------------------------------------------------
try:
    from jose import JWTError, jwt as jose_jwt
    _JOSE_AVAILABLE = True
except ImportError:
    _JOSE_AVAILABLE = False

try:
    from passlib.context import CryptContext
    _pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    _PASSLIB_AVAILABLE = True
except ImportError:
    _PASSLIB_AVAILABLE = False

# ---------------------------------------------------------------------------
# OAuth2 token extractor
# ---------------------------------------------------------------------------
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

def hash_password(plain_password: str) -> str:
    """
    Return a secure hash of *plain_password*.

    Uses bcrypt via passlib if available; falls back to PBKDF2-HMAC-SHA256
    for development when passlib is not installed.
    """
    if _PASSLIB_AVAILABLE:
        return _pwd_context.hash(plain_password)
    # Fallback: PBKDF2-HMAC-SHA256 (NOT bcrypt — install passlib for production)
    import os
    salt = os.urandom(16).hex()
    dk = hashlib.pbkdf2_hmac("sha256", plain_password.encode(), salt.encode(), 260_000)
    return f"pbkdf2${salt}${dk.hex()}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify *plain_password* against *hashed_password*.

    Handles both bcrypt (passlib) and PBKDF2 fallback hashes.
    """
    if _PASSLIB_AVAILABLE and not hashed_password.startswith("pbkdf2$"):
        return _pwd_context.verify(plain_password, hashed_password)
    # Fallback PBKDF2 verification
    try:
        _, salt, stored_hex = hashed_password.split("$", 2)
        dk = hashlib.pbkdf2_hmac("sha256", plain_password.encode(), salt.encode(), 260_000)
        return dk.hex() == stored_hex
    except Exception:
        return False


# ---------------------------------------------------------------------------
# JWT — pure-Python HMAC-SHA256 implementation (HS256)
# ---------------------------------------------------------------------------

def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    pad = 4 - len(s) % 4
    if pad != 4:
        s += "=" * pad
    return base64.urlsafe_b64decode(s)


def _jwt_encode_native(payload: dict, secret: str) -> str:
    """Encode a JWT using HMAC-SHA256 (HS256) without python-jose."""
    header = _b64url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    body = _b64url_encode(json.dumps(payload, default=str).encode())
    signing_input = f"{header}.{body}"
    sig = hmac.new(
        secret.encode(), signing_input.encode(), hashlib.sha256
    ).digest()
    return f"{signing_input}.{_b64url_encode(sig)}"


def _jwt_decode_native(token: str, secret: str) -> dict:
    """Decode and verify a JWT. Raises ValueError on any failure."""
    try:
        header_b64, body_b64, sig_b64 = token.split(".")
    except ValueError:
        raise ValueError("Malformed token")
    signing_input = f"{header_b64}.{body_b64}"
    expected_sig = hmac.new(
        secret.encode(), signing_input.encode(), hashlib.sha256
    ).digest()
    if not hmac.compare_digest(expected_sig, _b64url_decode(sig_b64)):
        raise ValueError("Signature verification failed")
    payload = json.loads(_b64url_decode(body_b64))
    exp = payload.get("exp")
    if exp and datetime.utcfromtimestamp(exp) < datetime.utcnow():
        raise ValueError("Token has expired")
    return payload


# ---------------------------------------------------------------------------
# Public JWT API
# ---------------------------------------------------------------------------

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Encode *data* into a signed JWT access token.

    Args:
        data: Payload dict (must include a 'sub' key with teacher ID).
        expires_delta: Optional custom TTL; defaults to settings value.

    Returns:
        Signed JWT string.
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + (
        expires_delta if expires_delta else timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire.timestamp(), "iat": datetime.utcnow().timestamp()})

    if _JOSE_AVAILABLE:
        return jose_jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return _jwt_encode_native(to_encode, settings.SECRET_KEY)


def decode_access_token(token: str) -> dict:
    """
    Decode and verify a JWT token.

    Raises:
        HTTPException 401 if the token is invalid or expired.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        if _JOSE_AVAILABLE:
            return jose_jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return _jwt_decode_native(token, settings.SECRET_KEY)
    except Exception:
        raise credentials_exception


# ---------------------------------------------------------------------------
# FastAPI dependency — authenticated teacher
# ---------------------------------------------------------------------------

def get_current_teacher(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    """
    FastAPI dependency that resolves a Bearer token to a Teacher ORM instance.

    Raises:
        HTTPException 401 if token is invalid or teacher not found.
        HTTPException 403 if teacher account is deactivated.
    """
    from core.models import Teacher  # noqa: PLC0415 — avoid circular import at module level

    payload = decode_access_token(token)
    teacher_id: Optional[str] = payload.get("sub")
    if teacher_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )

    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if teacher is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Teacher not found",
        )
    if not teacher.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Teacher account is deactivated",
        )
    return teacher


def get_admin_teacher(teacher=Depends(get_current_teacher)):
    """
    FastAPI dependency that additionally enforces admin / HM privileges.

    Raises:
        HTTPException 403 if teacher is not an admin.
    """
    if not teacher.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin / Headmaster privileges required for this action",
        )
    return teacher
