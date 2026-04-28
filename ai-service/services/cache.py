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
from typing import Optional
from urllib.parse import urlparse

import redis as redis_lib

logger = logging.getLogger(__name__)

# ME-5 FIX: Named constant for cache TTL — easy to find and change globally.
CACHE_TTL_SECONDS = 900

_redis_client = None
_redis_warned = False
# LO-2 FIX: Use monotonic() which is immune to system clock changes.
_next_retry_time: float = 0.0


def _mask_redis_url(url: str) -> str:
    """Return the Redis URL with the password masked for safe logging."""
    try:
        parsed = urlparse(url)
        if parsed.password:
            masked = parsed._replace(
                netloc=f"{parsed.username or ''}:***@{parsed.hostname}:{parsed.port or 6379}"
            )
            return masked.geturl()
        return url
    except Exception:
        return "<unparseable-url>"


def _get_redis():
    global _redis_client, _redis_warned, _next_retry_time

    if _redis_client is not None:
        return _redis_client

    # Cooldown: do not retry for 30s after a failed attempt
    if time.monotonic() < _next_retry_time:
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
        # HI-5 FIX: Mask password before logging the Redis URL.
        logger.info("AI cache: Redis connected at %s", _mask_redis_url(redis_url))
        return _redis_client
    except Exception as exc:
        _next_retry_time = time.monotonic() + 30
        if not _redis_warned:
            logger.warning(
                "AI cache: Redis unavailable (%s) — caching disabled. "
                "Will retry in 30s.", exc,
            )
            _redis_warned = True
        return None


def make_cache_key(endpoint: str, text: str) -> str:
    """Generate a deterministic cache key from the endpoint name and input text."""
    raw = f"{endpoint}:{text}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def cache_get(key: str) -> Optional[dict]:
    """Retrieve a cached response by key.  Returns None on cache miss or error."""
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


def cache_set(key: str, value: dict, ttl_seconds: int = CACHE_TTL_SECONDS) -> None:
    """Store a response in the cache with the given TTL."""
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
