"""
core/encryption.py — Fernet symmetric encryption for sensitive PII fields.

Used to encrypt Aadhaar numbers and guardian phone numbers stored in the database.
The ENCRYPTION_KEY must be a 32-byte URL-safe base64-encoded Fernet key.

Generate a key:
    from cryptography.fernet import Fernet
    print(Fernet.generate_key().decode())

Set in .env:
    ENCRYPTION_KEY=your-fernet-key-here
"""
import base64
from typing import Optional

try:
    from cryptography.fernet import Fernet, InvalidToken
    _CRYPTO_AVAILABLE = True
except ImportError:
    _CRYPTO_AVAILABLE = False

from core.config import settings


def _get_fernet() -> Optional[object]:
    """Return Fernet instance or None if not configured."""
    if not _CRYPTO_AVAILABLE:
        return None
    key = getattr(settings, "ENCRYPTION_KEY", None)
    if not key or key == "generate-with-fernet-generate-key":
        return None
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except Exception:
        return None


def encrypt_field(value: Optional[str]) -> Optional[str]:
    """
    Encrypt a string field value using Fernet symmetric encryption.

    If encryption is not configured, returns the value prefixed with 'plain:'
    to distinguish from encrypted values. In production, always configure ENCRYPTION_KEY.

    Args:
        value: Plaintext string to encrypt (e.g., Aadhaar number).

    Returns:
        Base64-encoded encrypted string, or None if value is None.
    """
    if value is None:
        return None
    fernet = _get_fernet()
    if fernet is None:
        # Fallback: store with prefix for identification — NOT secure, dev only
        return f"plain:{value}"
    encrypted = fernet.encrypt(value.encode())
    return encrypted.decode()


def decrypt_field(encrypted_value: Optional[str]) -> Optional[str]:
    """
    Decrypt a Fernet-encrypted field value.

    Args:
        encrypted_value: The encrypted string from the database.

    Returns:
        Decrypted plaintext string, or None if decryption fails or value is None.
    """
    if encrypted_value is None:
        return None
    # Handle dev-mode plain prefix
    if encrypted_value.startswith("plain:"):
        return encrypted_value[6:]
    fernet = _get_fernet()
    if fernet is None:
        return "[encrypted - key not configured]"
    try:
        return fernet.decrypt(encrypted_value.encode()).decode()
    except InvalidToken:
        return "[decryption failed - invalid key or corrupted data]"
    except Exception:
        return None


def mask_aadhaar(aadhaar: Optional[str]) -> Optional[str]:
    """
    Return a masked Aadhaar for display: XXXX-XXXX-1234.

    Args:
        aadhaar: 12-digit Aadhaar string (plaintext).

    Returns:
        Masked string showing only last 4 digits.
    """
    if not aadhaar or len(aadhaar) < 4:
        return None
    return f"XXXX-XXXX-{aadhaar[-4:]}"
