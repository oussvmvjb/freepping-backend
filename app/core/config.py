from typing import List, Optional, Union
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "FREPPING Backend"
    API_V1_STR: str = "/api/v1"
    APP_ENV: str = "development"
    DEBUG: bool = True

    # Database Configuration
    DB_USER: str = "postgres"
    DB_PASSWORD: str = "root"
    DB_HOST: str = "127.0.0.1"
    DB_PORT: int = 5432
    DB_NAME: str = "db_freepping"
    DATABASE_URL: Optional[str] = None

    # Redis Configuration
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: Optional[str] = None
    REDIS_URL: Optional[str] = None

    # CORS
    FRONTEND_URL: str = "http://localhost:4200"
    CORS_ORIGINS: Union[List[str], str] = ["http://localhost:4200"]

    # JWT Authentication Configuration
    JWT_SECRET_KEY: str = "change-this-in-production-super-secret-key-32chars"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Rate Limiting (per minute)
    RATE_LIMIT_LOGIN_PER_MINUTE: int = 10
    RATE_LIMIT_REGISTER_PER_MINUTE: int = 10
    RATE_LIMIT_REFRESH_PER_MINUTE: int = 30

    # Cache TTLs (in seconds)
    CACHE_TTL_PRODUCT_DETAIL: int = 300       # 5 minutes
    CACHE_TTL_PRODUCT_LIST: int = 120         # 2 minutes
    CACHE_TTL_CATEGORIES: int = 600           # 10 minutes

    # Seed admin configuration (development)
    ADMIN_EMAIL: Optional[str] = None
    ADMIN_PASSWORD: Optional[str] = None

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            if v.startswith("[") and v.endswith("]"):
                import json
                try:
                    return json.loads(v)
                except Exception:
                    pass
            return [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, list):
            return v
        return ["http://localhost:4200"]

    @model_validator(mode="after")
    def assemble_db_and_redis_urls(self) -> "Settings":
        if self.DATABASE_URL:
            url = self.DATABASE_URL.strip()
            # Normalize database dialect for asyncpg (compatible with Render & Supabase)
            if url.startswith("postgres://"):
                url = url.replace("postgres://", "postgresql+asyncpg://", 1)
            elif url.startswith("postgresql://"):
                url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
            elif url.startswith("postgresql+psycopg2://"):
                url = url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
            # asyncpg accepts 'ssl=' rather than 'sslmode='
            if "sslmode=" in url:
                url = url.replace("sslmode=", "ssl=")
            self.DATABASE_URL = url
        else:
            pwd = f":{self.DB_PASSWORD}" if self.DB_PASSWORD else ""
            self.DATABASE_URL = f"postgresql+asyncpg://{self.DB_USER}{pwd}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

        if not self.REDIS_URL:
            auth = f":{self.REDIS_PASSWORD}@" if self.REDIS_PASSWORD and self.REDIS_PASSWORD.strip() else ""
            self.REDIS_URL = f"redis://{auth}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

        # Ensure FRONTEND_URL is added to CORS_ORIGINS
        if isinstance(self.CORS_ORIGINS, list):
            if self.FRONTEND_URL and self.FRONTEND_URL not in self.CORS_ORIGINS:
                self.CORS_ORIGINS.append(self.FRONTEND_URL)

        return self

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )


settings = Settings()
