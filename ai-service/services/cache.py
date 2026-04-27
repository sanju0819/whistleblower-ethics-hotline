"""
services/cache.py
Redis AI response cache.
Key format: SHA256(endpoint + ":" + input_text)
TTL: 15 minutes (900 seconds)
Falls back to no-op if Redis is unavailable.
"""
import os
import json
import time
import hashlib
import logging
import redis as redis_lib

logger = logging.getLogger(__name__)

_redis_client = None
_redis_warned = False
_next_retry_time: float = 0.0


def _get_redis():
    global _redis_client, _redis_warned, _next_retry_time

    if _redis_client is not None:
        return _redis_client

    # Cooldown: do not retry for 30s after a failed attempt
    if time.time() < _next_retry_time:
        return None

    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        return None

    try:
        client = redis_lib.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
        )
        client.ping()
        _redis_client = client
        logger.info("AI cache: Redis connected at %s", redis_url)
        return _redis_client
    except Exception as exc:
        _next_retry_time = time.time() + 30
        if not _redis_warned:
            logger.warning(
                "AI cache: Redis unavailable (%s) — caching disabled. "
                "Will retry in 30s.", exc,
            )
            _redis_warned = True
        return None


def make_cache_key(endpoint: str, text: str) -> str:
    raw = f"{endpoint}:{text}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def cache_get(key: str) -> dict | None:
    global _redis_client, _redis_warned
    r = _get_redis()
    if r is None:
        return None
    try:
        value = r.get(key)
        if value:
            logger.debug("Cache HIT: %s", key[:16])
            return json.loads(value)
        logger.debug("Cache MISS: %s", key[:16])
        return None
    except Exception as exc:
        logger.warning("cache_get error — resetting client: %s", exc)
        _redis_client = None
        _redis_warned = False
        return None


def cache_set(key: str, value: dict, ttl_seconds: int = 900) -> None:
    global _redis_client, _redis_warned
    r = _get_redis()
    if r is None:
        return
    try:
        r.setex(key, ttl_seconds, json.dumps(value))
    except Exception as exc:
        logger.warning("cache_set error — resetting client: %s", exc)
        _redis_client = None
        _redis_warned = False
