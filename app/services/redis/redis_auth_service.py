import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.core.config import settings
from app.services.redis.redis_client import redis_client

logger = logging.getLogger(__name__)


class RedisAuthService:
    """Provides fast session cache, session revocation, and rate limiting using the existing Redis client."""

    @staticmethod
    def _session_key(session_id: uuid.UUID) -> str:
        return f"auth:refresh:{session_id}"

    @staticmethod
    def _rate_limit_key(identifier: str, action: str) -> str:
        return f"auth:ratelimit:{action}:{identifier}"

    async def cache_refresh_session(
        self,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        token_hash: str,
        expires_at: datetime,
    ) -> bool:
        """
        Caches refresh session metadata in Redis.
        CRITICAL: Never stores the raw refresh token.
        """
        now = datetime.now(timezone.utc)
        ttl = int((expires_at - now).total_seconds())
        if ttl <= 0:
            return False

        data = {
            "session_id": str(session_id),
            "user_id": str(user_id),
            "token_hash": token_hash,
            "expires_at": expires_at.isoformat(),
            "revoked": False,
        }
        return await redis_client.set(self._session_key(session_id), data, ttl=ttl)

    async def get_cached_session(self, session_id: uuid.UUID) -> Optional[Dict[str, Any]]:
        """Retrieves cached session metadata from Redis."""
        return await redis_client.get(self._session_key(session_id))

    async def revoke_cached_session(self, session_id: uuid.UUID, ttl_seconds: int = 86400) -> bool:
        """
        Marks session as revoked in Redis or deletes it to ensure fast refusal.
        """
        key = self._session_key(session_id)
        # Store revoked flag so subsequent attempts immediately trigger revocation/reuse check
        revoked_marker = {"revoked": True, "session_id": str(session_id)}
        await redis_client.set(key, revoked_marker, ttl=ttl_seconds)
        return True

    async def check_rate_limit(self, identifier: str, action: str, max_requests: int, window_seconds: int = 60) -> bool:
        """
        Rate limiter using Redis INCR and EXPIRE.
        Returns True if request is allowed, False if limit exceeded.
        If Redis is down or unavailable, degrades gracefully to True (fail open for rate-limit only).
        """
        key = self._rate_limit_key(identifier, action)
        try:
            client = await redis_client.get_client()
            if not client:
                return True

            current = await client.incr(key)
            if current == 1:
                await client.expire(key, window_seconds)

            return current <= max_requests
        except Exception as e:
            logger.debug(f"Redis rate limit check failed: {e}")
            return True


redis_auth_service = RedisAuthService()
