"""
Shared Redis connection.
Used by: presence tracking (Module: Conversations), rate limiting middleware,
Celery broker, and WebSocket Pub/Sub fan-out across backend instances.
"""
from redis.asyncio import Redis, from_url

from app.core.config import settings

redis_client: Redis = from_url(settings.REDIS_URL, decode_responses=True)


async def get_redis() -> Redis:
    """FastAPI dependency — returns the shared Redis client."""
    return redis_client
