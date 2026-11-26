"""
Rate limiting (tiêu chí 7) — Sliding window 60s lưu trong Redis.
"""
import logging
import time
import uuid

import redis
from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

logger = logging.getLogger("agent")

WINDOW_SECONDS = 60


def check_rate_limit(key: str) -> None:
    """Kiểm tra sliding window 60s trong Redis; vượt RATE_LIMIT_PER_MINUTE → 429."""
    if r is None:
        return

    now = time.time()
    window_start = now - WINDOW_SECONDS
    redis_key = f"ratelimit:{key}"

    try:
        pipe = r.pipeline()
        pipe.zremrangebyscore(redis_key, 0, window_start)
        pipe.zcard(redis_key)
        _, current_count = pipe.execute()

        if current_count >= settings.rate_limit_per_minute:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Please try again later.",
                headers={"Retry-After": str(WINDOW_SECONDS)},
            )

        member = f"{now}:{uuid.uuid4().hex}"
        pipe = r.pipeline()
        pipe.zadd(redis_key, {member: now})
        pipe.expire(redis_key, WINDOW_SECONDS + 5)
        pipe.execute()
    except HTTPException:
        raise
    except redis.RedisError as exc:
        logger.warning("redis_rate_limit_error", extra={"error": str(exc)})
