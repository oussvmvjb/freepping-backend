import json
import logging
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID
import redis.asyncio as aioredis
from app.core.config import settings

logger = logging.getLogger(__name__)


class CustomJSONEncoder(json.JSONEncoder):
    """Encodes UUID, Decimal, and datetime objects into JSON-compatible values."""
    def default(self, obj: Any) -> Any:
        if isinstance(obj, UUID):
            return str(obj)
        if isinstance(obj, Decimal):
            return float(obj)
        if hasattr(obj, "isoformat"):
            return obj.isoformat()
        return super().default(obj)


class AsyncRedisClient:
    """Reusable asynchronous Redis cache client with graceful degradation."""

    def __init__(self, redis_url: str):
        self.redis_url = redis_url
        self._client: Optional[aioredis.Redis] = None

    async def get_client(self) -> Optional[aioredis.Redis]:
        """Lazy-initializes and returns the async Redis connection pool."""
        if self._client is None:
            try:
                self._client = aioredis.from_url(
                    self.redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                    socket_connect_timeout=2.0,
                    socket_timeout=2.0
                )
            except Exception as e:
                logger.warning(f"Failed to connect to Redis at {self.redis_url}: {e}. Running without cache.")
                self._client = None
        return self._client

    async def get(self, key: str) -> Optional[Any]:
        """Retrieves and deserializes JSON value from cache."""
        try:
            client = await self.get_client()
            if not client:
                return None
            cached_value = await client.get(key)
            if cached_value:
                return json.loads(cached_value)
        except Exception as e:
            logger.debug(f"Redis GET failed for key '{key}': {e}")
        return None

    async def set(self, key: str, value: Any, ttl: int) -> bool:
        """Serializes and sets a value in cache with a TTL (seconds)."""
        try:
            client = await self.get_client()
            if not client:
                return False
            payload = json.dumps(value, cls=CustomJSONEncoder)
            await client.set(key, payload, ex=ttl)
            return True
        except Exception as e:
            logger.debug(f"Redis SET failed for key '{key}': {e}")
            return False

    async def delete(self, key: str) -> bool:
        """Deletes a key from cache."""
        try:
            client = await self.get_client()
            if not client:
                return False
            await client.delete(key)
            return True
        except Exception as e:
            logger.debug(f"Redis DELETE failed for key '{key}': {e}")
            return False

    async def delete_by_pattern(self, pattern: str) -> bool:
        """Deletes all keys matching a wildcard pattern (e.g. 'products:list:*')."""
        try:
            client = await self.get_client()
            if not client:
                return False
            keys = []
            async for key in client.scan_iter(match=pattern):
                keys.append(key)
            if keys:
                await client.delete(*keys)
            return True
        except Exception as e:
            logger.debug(f"Redis DELETE pattern '{pattern}' failed: {e}")
            return False

    async def invalidate_product_caches(self, product_id: Optional[str] = None) -> None:
        """Convenience method to invalidate product listings and optional specific product detail."""
        if product_id:
            await self.delete(f"products:{product_id}")
        await self.delete_by_pattern("products:list:*")

    async def invalidate_category_caches(self, category_id: Optional[str] = None) -> None:
        """Convenience method to invalidate category caches and product listings."""
        if category_id:
            await self.delete(f"categories:{category_id}")
        await self.delete("categories:list")
        await self.delete_by_pattern("products:list:*")

    async def close(self) -> None:
        """Gracefully closes Redis connection."""
        if self._client:
            try:
                await self._client.close()
            except Exception:
                pass
            self._client = None


redis_client = AsyncRedisClient(settings.REDIS_URL)
