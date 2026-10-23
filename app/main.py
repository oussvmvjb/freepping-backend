from contextlib import asynccontextmanager
from urllib.parse import urlparse, urlunparse

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

import app.db.models  # noqa: F401  # Ensure all models are registered before create_all.
from app.api.router import api_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.db.base import Base
from app.db.session import engine
from app.services.redis.redis_client import redis_client


async def ensure_database_exists() -> None:
    """Create the local PostgreSQL database if it does not already exist."""
    parsed = urlparse(settings.DATABASE_URL)
    database_name = parsed.path.lstrip("/")

    if not database_name or database_name == "postgres":
        return

    admin_url = urlunparse(parsed._replace(path="/postgres", scheme="postgresql+asyncpg"))

    database_engine = create_async_engine(admin_url, future=True)
    try:
        async with database_engine.connect() as connection:
            exists = await connection.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :dbname"),
                {"dbname": database_name},
            )
            if exists.scalar() is None:
                quoted_name = '"' + database_name.replace('"', '""') + '"'
                await connection.execution_options(isolation_level="AUTOCOMMIT").execute(
                    text(f"CREATE DATABASE {quoted_name}")
                )
                print(f"[OK] PostgreSQL database '{database_name}' created")
            else:
                print(f"[OK] PostgreSQL database '{database_name}' already exists")
    finally:
        await database_engine.dispose()


async def create_database_schema() -> None:
    """Create or verify all tables in the local PostgreSQL database."""
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    print("[OK] Database tables created/verified")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await ensure_database_exists()
    await create_database_schema()
    yield
    await redis_client.close()
    await engine.dispose()


app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    description="FREPPING E-Commerce Backend Service - Products, Categories, Images & Variants API.",
    version="1.0.0",
    lifespan=lifespan,
)

# Exception handlers
register_exception_handlers(app)

# CORS Configuration
if settings.CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Include API Router
app.include_router(api_router, prefix=settings.API_V1_STR)

# Also mount Trellis 3D endpoints directly under /api for specification parity (/api/generate-3d, /api/health)
from app.v1.endpoints.trellis import router as trellis_api_router
app.include_router(trellis_api_router, prefix="/api", tags=["TRELLIS 3D Generation (/api)"])


@app.get("/", tags=["Root"], summary="API Root")
async def root():
    return {
        "service": settings.PROJECT_NAME,
        "status": "online",
        "docs_url": "/docs",
        "api_v1": f"{settings.API_V1_STR}/health",
    }