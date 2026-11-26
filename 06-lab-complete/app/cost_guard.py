"""
Cost guard (tiêu chí 8) — Theo dõi chi phí LLM trong Redis.
"""
import logging
from datetime import datetime, timezone

import redis
from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

logger = logging.getLogger("agent")

# Giá USD / 1K tokens (tham khảo gpt-4o-mini)
PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006


def _daily_key() -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"cost:daily:{today}"


def _monthly_key() -> str:
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    return f"cost:monthly:{month}"


def check_budget() -> None:
    """Gọi TRƯỚC khi gọi LLM. Hết budget → raise HTTPException(status_code=402)."""
    if r is None:
        return

    try:
        daily_spent = float(r.get(_daily_key()) or 0.0)
        monthly_spent = float(r.get(_monthly_key()) or 0.0)
    except redis.RedisError as exc:
        logger.warning("redis_cost_check_error", extra={"error": str(exc)})
        return

    if daily_spent >= settings.daily_budget_usd:
        raise HTTPException(
            status_code=402,
            detail="Daily budget exceeded.",
        )
    if monthly_spent >= settings.monthly_budget_usd:
        raise HTTPException(
            status_code=402,
            detail="Monthly budget exceeded.",
        )


def record_cost(input_tokens: int, output_tokens: int) -> float:
    """Gọi SAU khi gọi LLM. Cộng chi phí của request vào tổng, trả về chi phí request."""
    cost = (
        (input_tokens / 1000.0) * PRICE_INPUT_PER_1K
        + (output_tokens / 1000.0) * PRICE_OUTPUT_PER_1K
    )
    if r is None:
        return cost

    try:
        dkey = _daily_key()
        mkey = _monthly_key()
        pipe = r.pipeline()
        pipe.incrbyfloat(dkey, cost)
        pipe.expire(dkey, 48 * 3600)
        pipe.incrbyfloat(mkey, cost)
        pipe.expire(mkey, 32 * 24 * 3600)
        pipe.execute()
    except redis.RedisError as exc:
        logger.warning("redis_cost_record_error", extra={"error": str(exc)})

    return cost
