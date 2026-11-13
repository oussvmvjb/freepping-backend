import logging
import re
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.deps import check_rate_limit, require_authenticated_user
from app.core.config import settings
from app.db.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter()
token_rate_limit = check_rate_limit("realtime_token", max_requests=10)

DECART_TOKEN_URL = "https://api.decart.ai/v1/client/tokens"
REALTIME_MODEL = "lucy-vton-3.6"
TOKEN_LIFETIME_SECONDS = 300


@router.post(
    "/realtime-token",
    summary="Create a short-lived Decart client token",
    dependencies=[Depends(token_rate_limit)],
)
async def create_realtime_token(
    request: Request,
    _current_user: User = Depends(require_authenticated_user),
) -> dict[str, str]:
    api_key = settings.DECART_API_KEY
    if not api_key or not api_key.strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Realtime virtual try-on is not configured.",
        )

    origin = request.headers.get("origin", "").rstrip("/")
    configured_origins = settings.CORS_ORIGINS
    allowed_origins = (
        configured_origins
        if isinstance(configured_origins, list)
        else [item.strip().rstrip("/") for item in configured_origins.split(",") if item.strip()]
    )
    is_dev = settings.DEBUG or settings.APP_ENV == "development"
    is_lan_or_local = bool(
        re.match(
            r"^https?://(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+)(:\d+)?$",
            origin,
        )
    )
    if not origin or (origin not in allowed_origins and not (is_dev and is_lan_or_local)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This application origin is not allowed to request a realtime token.",
        )

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                DECART_TOKEN_URL,
                headers={"X-API-KEY": api_key},
                json={
                    "expiresIn": TOKEN_LIFETIME_SECONDS,
                    "allowedModels": [REALTIME_MODEL],
                    "allowedOrigins": [origin],
                },
            )
    except httpx.TimeoutException as exc:
        logger.warning("Decart client-token request timed out")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Decart token service timed out. Please try again.",
        ) from exc
    except httpx.RequestError as exc:
        logger.exception("Could not reach Decart client-token service")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not reach the Decart token service. Please try again.",
        ) from exc

    if not response.is_success:
        logger.warning("Decart client-token request failed with status %s", response.status_code)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Decart could not create a realtime client token.",
        )

    try:
        token_data: Any = response.json()
    except ValueError as exc:
        logger.error("Decart client-token response was not valid JSON")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Decart returned an invalid token response.",
        ) from exc

    if not isinstance(token_data, dict) or not isinstance(token_data.get("apiKey"), str) or not token_data["apiKey"]:
        logger.error("Decart client-token response was missing its apiKey")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Decart returned an invalid token response.",
        )

    expires_at = token_data.get("expiresAt")
    if not isinstance(expires_at, str) or not expires_at:
        logger.error("Decart client-token response was missing its expiry")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Decart returned an invalid token response.",
        )

    return {"apiKey": token_data["apiKey"], "expiresAt": expires_at}
