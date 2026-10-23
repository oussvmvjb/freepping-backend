from typing import List, Optional, Union
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "FREPPING Backend"
    API_V1_STR: str = "/api/v1"
    APP_ENV: str = "development"
    DEBUG: bool = True

    # ── Database ──────────────────────────────────────────────────────────────
    # If DATABASE_URL is set (e.g. from Render env vars), it takes full priority.
    # Otherwise the discrete DB_* fields are used to build a local connection URL.
    DB_USER: str = "postgres"
    DB_PASSWORD: str = "root"
    DB_HOST: str = "127.0.0.1"
    DB_PORT: int = 5432
    DB_NAME: str = "db_freepping"
    DATABASE_URL: Optional[str] = None

    # ── Redis ─────────────────────────────────────────────────────────────────
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: Optional[str] = None
    REDIS_URL: Optional[str] = None

    # ── CORS ──────────────────────────────────────────────────────────────────
    # In production, set FRONTEND_URL and CORS_ORIGINS via Render environment vars.
    # Local defaults only allow localhost — production URL is never baked in.
    FRONTEND_URL: str = "http://localhost:4200"
    CORS_ORIGINS: Union[List[str], str] = ["http://localhost:4200"]

    # ── JWT ───────────────────────────────────────────────────────────────────
    JWT_SECRET_KEY: str = "change-this-in-production-super-secret-key-32chars"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── Rate Limiting (per minute) ────────────────────────────────────────────
    RATE_LIMIT_LOGIN_PER_MINUTE: int = 10
    RATE_LIMIT_REGISTER_PER_MINUTE: int = 10
    RATE_LIMIT_REFRESH_PER_MINUTE: int = 30
    RATE_LIMIT_LIKE_PER_MINUTE: int = 30
    RATE_LIMIT_PROMO_VALIDATE_PER_MINUTE: int = 10
    RATE_LIMIT_GIFT_CARD_CHECK_PER_MINUTE: int = 5

    # ── Cache TTLs (seconds) ──────────────────────────────────────────────────
    CACHE_TTL_PRODUCT_DETAIL: int = 300       # 5 minutes
    CACHE_TTL_PRODUCT_LIST: int = 120         # 2 minutes
    CACHE_TTL_CATEGORIES: int = 600           # 10 minutes
    CACHE_TTL_DELIVERY_OPTIONS: int = 300     # 5 minutes
    CACHE_TTL_DASHBOARD: int = 60             # 1 minute

    # ── Cart / Order Settings ─────────────────────────────────────────────────
    GIFT_WRAP_COST: float = 2.00              # configurable gift wrap fee

    # ── Seed admin (development only) ─────────────────────────────────────────
    ADMIN_EMAIL: Optional[str] = None
    ADMIN_PASSWORD: Optional[str] = None

    # ── Trellis 3D Model Generation ───────────────────────────────────────────
    HF_TOKEN: Optional[str] = None
    TRELLIS_SPACE: str = "microsoft/TRELLIS.2"
    TRELLIS_TIMEOUT_SECONDS: int = 300
    TRELLIS_MAX_FILE_SIZE_MB: int = 15
    TRELLIS_MAX_CONCURRENT_JOBS: int = 2
    STORAGE_DIR: str = "storage"

    # ── Validators ────────────────────────────────────────────────────────────

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        """Parse CORS_ORIGINS from env string or list and normalise trailing slashes."""
        if isinstance(v, str):
            if v.startswith("[") and v.endswith("]"):
                import json
                try:
                    origins = json.loads(v)
                    return [str(i).strip().rstrip("/") for i in origins if i]
                except Exception:
                    pass
            return [i.strip().rstrip("/") for i in v.split(",") if i.strip()]
        elif isinstance(v, list):
            return [str(i).strip().rstrip("/") for i in v if i]
        return ["http://localhost:4200"]

    @model_validator(mode="after")
    def assemble_db_and_redis_urls(self) -> "Settings":
        # ── DATABASE_URL ─────────────────────────────────────────────────────
        if self.DATABASE_URL:
            url = self.DATABASE_URL.strip()
            # Normalise scheme so asyncpg is always used regardless of source URL format
            if url.startswith("postgres://"):
                url = url.replace("postgres://", "postgresql+asyncpg://", 1)
            elif url.startswith("postgresql://"):
                url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
            elif url.startswith("postgresql+psycopg2://"):
                url = url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
            # asyncpg uses ssl= not sslmode=
            if "sslmode=" in url:
                url = url.replace("sslmode=", "ssl=")
            self.DATABASE_URL = url
        else:
            # Fallback: build from discrete DB_* variables (local dev)
            pwd = f":{self.DB_PASSWORD}" if self.DB_PASSWORD else ""
            self.DATABASE_URL = (
                f"postgresql+asyncpg://{self.DB_USER}{pwd}"
                f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
            )

        # ── REDIS_URL ────────────────────────────────────────────────────────
        if not self.REDIS_URL:
            auth = f":{self.REDIS_PASSWORD}@" if self.REDIS_PASSWORD and self.REDIS_PASSWORD.strip() else ""
            self.REDIS_URL = f"redis://{auth}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

        # ── CORS: ensure FRONTEND_URL is allowed ─────────────────────────────
        # NEVER add hard-coded production URLs here. All origins come from env vars.
        if isinstance(self.CORS_ORIGINS, list) and self.FRONTEND_URL:
            cleaned = self.FRONTEND_URL.strip().rstrip("/")
            if cleaned and cleaned not in self.CORS_ORIGINS:
                self.CORS_ORIGINS.append(cleaned)

        return self

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )


settings = Settings()
