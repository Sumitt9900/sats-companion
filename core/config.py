"""
core/config.py — Pydantic Settings configuration for SATS Companion.

Loads environment variables from .env and exposes them as typed settings
throughout the application.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables / .env file.

    Attributes:
        DATABASE_URL: PostgreSQL connection string.
        SECRET_KEY: HMAC secret used to sign JWT tokens.
        ALGORITHM: JWT signing algorithm (default HS256).
        ACCESS_TOKEN_EXPIRE_MINUTES: Token lifetime in minutes.
        GOOGLE_API_KEY: Google Gemini API key for AI endpoints.
        ENVIRONMENT: Runtime environment label (development / production).
    """

    DATABASE_URL: str = "postgresql://postgres:password@localhost:5432/sats_companion"
    SECRET_KEY: str = "changeme-use-openssl-rand-hex-32"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    GOOGLE_API_KEY: str = ""
    ENVIRONMENT: str = "development"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


# Singleton instance used across the application
settings = Settings()
