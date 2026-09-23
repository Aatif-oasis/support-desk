"""
Fixed-window rate limiting via Redis INCR + EXPIRE — closes the gap
flagged repeatedly since Module 3: every public, unauthenticated endpoint
(identify, start conversation, send message, KB public routes) had no
limit on how often a single visitor could call it.

Deliberately NOT applied to authenticated agent/admin endpoints — those
are protected by requiring a valid JWT in the first place, and rate
limiting an org_admin's own dashboard would just create false positives
for legitimate heavy usage. The threat model here is specifically abuse
of endpoints anyone on the internet can hit with zero credentials.
"""
import time

from fastapi import Depends, HTTPException, Request, status
from redis.asyncio import Redis

from app.core.redis import get_redis


class RateLimiter:
    def __init__(self, max_requests: int, window_seconds: int, bucket: str):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.bucket = bucket

    async def __call__(self, request: Request, redis: Redis = Depends(get_redis)) -> None:
        client_ip = request.client.host if request.client else "unknown"
        window = int(time.time() // self.window_seconds)
        key = f"ratelimit:{self.bucket}:{client_ip}:{window}"

        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, self.window_seconds)

        if count > self.max_requests:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded: max {self.max_requests} requests "
                f"per {self.window_seconds}s for this endpoint.",
            )


# Pre-configured instances for the public endpoint families that needed this.
# Numbers are deliberately generous for legitimate widget use (a real
# customer might send several messages a minute) while still bounding
# abuse — tune per deployment via env vars in a later pass if needed.
identify_rate_limit = RateLimiter(max_requests=30, window_seconds=60, bucket="identify")
conversation_start_rate_limit = RateLimiter(max_requests=10, window_seconds=60, bucket="conv_start")
message_send_rate_limit = RateLimiter(max_requests=60, window_seconds=60, bucket="msg_send")
kb_public_rate_limit = RateLimiter(max_requests=60, window_seconds=60, bucket="kb_public")
attachment_upload_rate_limit = RateLimiter(max_requests=20, window_seconds=60, bucket="attach_upload")
