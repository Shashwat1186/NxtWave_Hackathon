"""
core/config.py
==============
Central configuration via Pydantic Settings.
All values are loaded from environment variables / .env file.
No secrets are hardcoded here.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
_ENV_PATH = _BACKEND_DIR / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", str(_ENV_PATH)),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── App ─────────────────────────────────────────────────────────────────
    APP_NAME: str = "CivicTriage"
    ENV: Literal["development", "staging", "production"] = "development"
    DEBUG: bool = False

    # ── Demo Mode ────────────────────────────────────────────────────────────
    # When True the pipeline replays cached outputs from ./eval/golden_inputs/
    # instead of calling real LLM / Geo APIs. Set to True during demos.
    DEMO_MODE: bool = False
    DEMO_CACHE_DIR: str = "eval/golden_inputs"

    # ── MongoDB ──────────────────────────────────────────────────────────────
    MONGODB_URI: str = Field(..., description="MongoDB Atlas connection string")
    MONGODB_DB: str = "civictriage"

    # ── LLM ─────────────────────────────────────────────────────────────────
    # Primary model — must support vision + audio (multimodal)
    LLM_PROVIDER: Literal["google", "openai"] = "google"
    LLM_PRIMARY_MODEL: str = "gemini-1.5-flash"
    LLM_FALLBACK_MODEL: str = "gemini-1.5-pro"
    LLM_TIMEOUT_SECONDS: float = 30.0
    LLM_MAX_RETRIES: int = 3

    # Google AI
    GOOGLE_API_KEY: str = Field("", description="Google AI Studio API key")

    # OpenAI (optional fallback provider)
    OPENAI_API_KEY: str = Field("", description="OpenAI API key")

    # ── Embeddings ───────────────────────────────────────────────────────────
    EMBED_MODEL: str = "models/gemini-embedding-001"
    EMBED_DIMENSION: int = 3072

    # ── Geo Services ─────────────────────────────────────────────────────────
    NOMINATIM_URL: str = "https://nominatim.openstreetmap.org"
    NOMINATIM_USER_AGENT: str = "CivicTriage/1.0"
    OVERPASS_URL: str = "https://overpass-api.de/api/interpreter"
    GEO_TIMEOUT_SECONDS: float = 10.0
    GEO_MAX_RETRIES: int = 2
    GEO_CACHE_TTL_HOURS: int = 24 * 7  # 7 days

    # ── Deduplication ────────────────────────────────────────────────────────
    DEDUP_GEO_RADIUS_METERS: float = 500.0
    DEDUP_SIMILARITY_THRESHOLD: float = 0.82

    # ── Severity ─────────────────────────────────────────────────────────────
    PROXIMITY_SCHOOL_BONUS_METERS: float = 200.0
    PROXIMITY_HOSPITAL_BONUS_METERS: float = 300.0

    # ── File Upload ──────────────────────────────────────────────────────────
    UPLOAD_DIR: str = "uploads"
    MAX_UPLOAD_SIZE_MB: int = 25
    ALLOWED_IMAGE_TYPES: list[str] = [
        "image/jpeg",
        "image/jpg",
        "image/pjpeg",
        "image/png",
        "image/webp",
        "image/gif",
        "image/bmp",
        "image/tiff",
        "image/svg+xml",
        "image/heic",
        "image/heif",
    ]
    ALLOWED_AUDIO_TYPES: list[str] = [
        "audio/webm",
        "audio/webm;codecs=opus",
        "video/webm",
        "audio/mpeg",
        "audio/mp3",
        "audio/wav",
        "audio/x-wav",
        "audio/wave",
        "audio/ogg",
        "audio/ogg;codecs=opus",
        "audio/mp4",
        "audio/m4a",
        "audio/x-m4a",
        "audio/aac",
        "audio/flac",
    ]

    # ── SLA ──────────────────────────────────────────────────────────────────
    SLA_CRITICAL_HOURS: int = 4
    SLA_HIGH_HOURS: int = 24
    SLA_MEDIUM_HOURS: int = 72
    SLA_LOW_HOURS: int = 168

    # ── Critic ───────────────────────────────────────────────────────────────
    CRITIC_MAX_RETRIES: int = 2
    CRITIC_MIN_CONFIDENCE: float = 0.65

    # ── Admin ─────────────────────────────────────────────────────────────────
    ADMIN_TOKEN: str = Field(..., description="Bearer token for admin endpoints")

    # ── CORS ─────────────────────────────────────────────────────────────────
    ALLOWED_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ]

    # Production frontend URL (e.g. https://civictriage.vercel.app)
    FRONTEND_URL: str = Field("", description="Production Vercel frontend URL")

    @field_validator("GOOGLE_API_KEY", "OPENAI_API_KEY", mode="before")
    @classmethod
    def _allow_empty(cls, v: str) -> str:
        return v or ""

    @field_validator("UPLOAD_DIR", mode="after")
    @classmethod
    def _resolve_upload_dir(cls, v: str) -> str:
        import os
        # On Vercel serverless / AWS Lambda, the filesystem is read-only except /tmp
        if os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
            return "/tmp/uploads"
        p = Path(v)
        if not p.is_absolute():
            p = _BACKEND_DIR / p
        return str(p)

    @field_validator("DEMO_CACHE_DIR", mode="after")
    @classmethod
    def _resolve_demo_dir(cls, v: str) -> str:
        p = Path(v)
        if not p.is_absolute():
            p = _BACKEND_DIR / p
        return str(p)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached Settings singleton. Import and call this everywhere."""
    return Settings()
