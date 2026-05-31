"""API key usage analytics via Redis counters.

Tracks per-credential daily request counts using Redis INCR for
O(1) per-request overhead.  Data auto-expires after 90 days.

Redis key format::

    api_key_usage:{credential_id}:{YYYY-MM-DD}  →  integer (request count)

The middleware calls ``track_api_key_usage`` on every successful
credential validation.  Admin endpoints use ``get_usage_stats`` and
``get_all_usage_stats`` for analytics dashboards.

All functions are synchronous (Redis operations are fast and the
cache backend handles connection pooling).  For async contexts,
wrap with ``sync_to_async``.
"""

import logging
from datetime import datetime, timedelta

from django.conf import settings

logger = logging.getLogger(__name__)

# Redis key prefix for API key usage counters.
KEY_PREFIX = "api_key_usage"

# Number of days to retain usage data before auto-expiry.
RETENTION_DAYS = 90


def _cache_key(credential_id: int, date_str: str) -> str:
    """Build the Redis key for a credential's daily usage counter."""
    return f"{KEY_PREFIX}:{credential_id}:{date_str}"


def track_api_key_usage(credential_id: int) -> None:
    """Increment the daily request counter for a credential.

    Called from the middleware after successful API key validation.
    Uses Redis INCR which is atomic — safe for concurrent requests.

    The counter auto-expires after ``RETENTION_DAYS`` days.
    """
    from django.core.cache import cache

    today = datetime.utcnow().strftime("%Y-%m-%d")
    key = _cache_key(credential_id, today)

    try:
        # Use raw Redis INCR for atomicity.
        # Django's cache backend wraps Redis but doesn't expose INCR
        # directly, so we use the underlying Redis client.
        redis_client = cache.get_client("default")
        redis_client.incr(key)
        redis_client.expire(key, RETENTION_DAYS * 86400)
    except Exception:
        # Analytics must never break a request.
        logger.debug(
            "ANALYTICS_TRACK_FAILED: credential_id=%s", credential_id
        )


def get_usage_stats(credential_id: int, days: int = 30) -> list[dict]:
    """Get daily usage statistics for a single credential.

    Returns a list of dicts ordered by date descending::

        [
            {"date": "2026-05-06", "requests": 142},
            {"date": "2026-05-05", "requests": 98},
            ...
        ]

    Args:
        credential_id: The ``ServiceCredential.id``.
        days: Number of days to look back (default 30).

    Returns:
        List of daily usage dicts.
    """
    from django.core.cache import cache

    today = datetime.utcnow()
    results = []

    try:
        redis_client = cache.get_client("default")
        pipe = redis_client.pipeline()

        for i in range(days):
            date = today - timedelta(days=i)
            date_str = date.strftime("%Y-%m-%d")
            key = _cache_key(credential_id, date_str)
            pipe.get(key)

        values = pipe.execute()
    except Exception:
        logger.debug(
            "ANALYTICS_QUERY_FAILED: credential_id=%s", credential_id
        )
        return results

    for i in range(days):
        date = today - timedelta(days=i)
        date_str = date.strftime("%Y-%m-%d")
        count = int(values[i]) if values[i] else 0
        if count > 0:
            results.append({"date": date_str, "requests": count})

    return results


def get_all_usage_stats(days: int = 7) -> dict:
    """Get aggregated usage statistics across all credentials.

    Scans the Redis keyspace for ``api_key_usage:*`` keys and returns
    a summary grouped by credential.  For production with many credentials,
    prefer ``get_usage_stats`` with a specific credential ID.

    Args:
        days: Only count keys from the last N days.

    Returns:
        Dict of ``credential_id`` → total requests::

            {"1": 542, "2": 1203, "3": 89}
    """
    from django.core.cache import cache

    today = datetime.utcnow()
    cutoff = (today - timedelta(days=days)).strftime("%Y-%m-%d")
    results: dict[int, int] = {}

    try:
        redis_client = cache.get_client("default")

        # SCAN for api_key_usage:* keys matching the date range.
        pattern = f"{KEY_PREFIX}:*"
        cursor = 0
        while True:
            cursor, keys = redis_client.scan(
                cursor=cursor, match=pattern, count=500
            )
            for key in keys:
                # Parse key: api_key_usage:{credential_id}:{date}
                parts = key.decode("utf-8", errors="ignore").split(":")
                if len(parts) != 3:
                    continue
                _, cred_id_str, date_str = parts
                if date_str < cutoff:
                    continue
                try:
                    count = int(redis_client.get(key) or 0)
                except (ValueError, TypeError):
                    continue
                cred_id = int(cred_id_str)
                results[cred_id] = results.get(cred_id, 0) + count

            if cursor == 0:
                break
    except Exception:
        logger.debug("ANALYTICS_ALL_QUERY_FAILED")

    return {str(k): v for k, v in results.items()}
