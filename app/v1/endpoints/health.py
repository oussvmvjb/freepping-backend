import logging
from typing import Any, Dict
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health", summary="Health Check", description="Returns service and database connectivity health status.")
async def health_check(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    db_status = "ok"
    try:
        await db.execute(text("SELECT 1"))
    except Exception as e:
        logger.error("Database connectivity check failed: %s", type(e).__name__)
        db_status = "unhealthy"

    return {
        "status": "ok",
        "database": db_status
    }
