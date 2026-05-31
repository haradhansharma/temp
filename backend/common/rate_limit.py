"""Rate limiting utilities for the common app."""

import time
import logging
from django.core.cache import cache
from django.conf import settings

logger = logging.getLogger(__name__)


def check_rate_limit(key: str, max_attempts: int, window_seconds: int) -> bool:
    """Check if a request is within the rate limit using a sliding window.

    Stores a list of timestamps in the cache under ``rl:{key}``. Stale
    timestamps outside the window are pruned on each check.

    Args:
        key: Unique identifier for the rate limit bucket
             (e.g. ``"login:192.168.1.1"``).
        max_attempts: Maximum number of requests allowed in the window.
        window_seconds: Length of the sliding window in seconds.

    Returns:
        True if the request is within the limit, False if exceeded.
    """
    now = time.time()
    window_start = now - window_seconds
    cache_key = f"rl:{key}"
    attempts = cache.get(cache_key, [])
    attempts = [ts for ts in attempts if ts > window_start]

    if len(attempts) >= max_attempts:
        logger.warning(f"Rate limit exceeded for key: {key}")
        return False

    attempts.append(now)
    cache.set(cache_key, attempts, timeout=window_seconds)
    return True


def _get_sdk_rate_limit_params(request):
    """Return (bucket_id, max_attempts, window_seconds) for SDK traffic.

    When a valid ``X-API-Key`` is present, the request originates from a
    sister domain backend (server-to-server).  All users proxied through
    the same backend share a single IP, so per-IP rate limiting would
    exhaust the bucket for every user on that domain.  Instead we use
    the API key prefix as the rate limit bucket, with higher limits
    appropriate for trusted server-to-server traffic.

    Returns:
        ``(bucket_id, max_attempts, window_seconds)`` when a valid
        ``service_credential`` is attached to the request, otherwise
        ``None``.
    """
    credential = getattr(request, "service_credential", None)
    if credential is None:
        return None

    prefix = credential.api_key_prefix
    max_attempts = getattr(settings, "RATE_LIMIT_SDK_ATTEMPTS", 1000)
    window_seconds = getattr(settings, "RATE_LIMIT_SDK_WINDOW", 3600)
    return (f"sdk:{prefix}", max_attempts, window_seconds)


def check_rate_limit_or_raise(
    request,
    key_prefix: str,
    max_attempts: int = None,
    window_seconds: int = None,
) -> None:
    """Check rate limit and raise ``TooManyRequestsException`` if exceeded.

    Builds the rate limit key from the request's user ID (if authenticated)
    and either the client IP (direct/browser traffic) or the API key prefix
    (SDK/server-to-server traffic).

    When a valid ``X-API-Key`` is present on the request, the rate limit
    bucket switches from per-IP to per-service-domain (via API key prefix).
    This prevents a sister domain backend that proxies many users through
    a single IP from exhausting the shared bucket.  SDK traffic also uses
    higher default limits (``RATE_LIMIT_SDK_ATTEMPTS`` / ``RATE_LIMIT_SDK_WINDOW``).

    Args:
        request: Django HttpRequest. If ``request.user`` is authenticated,
            the user ID is included in the key for per-user rate limiting.
        key_prefix: Action-specific prefix (e.g. ``"cancel_sub"``,
            ``"checkout"``, ``"change_plan"``).
        max_attempts: Max requests in the window. Falls back to
            ``settings.RATE_LIMIT_SENSITIVE_ATTEMPTS`` (default: 5).
            Ignored for SDK traffic (uses ``RATE_LIMIT_SDK_ATTEMPTS``).
        window_seconds: Window length in seconds. Falls back to
            ``settings.RATE_LIMIT_SENSITIVE_WINDOW`` (default: 3600).
            Ignored for SDK traffic (uses ``RATE_LIMIT_SDK_WINDOW``).

    Raises:
        TooManyRequestsException: If the rate limit is exceeded.

    Example::

        @http_post("/subscriptions/{slug}/cancel")
        async def cancel(self, request, slug):
            check_rate_limit_or_raise(request, "cancel_sub")
            # ... business logic
    """
    from common.exceptions import TooManyRequestsException

    user_id = (
        getattr(request, "user", None)
        and hasattr(request.user, "id")
        and str(request.user.id)
        or "anon"
    )

    # SDK traffic: use API key prefix as bucket with higher limits
    sdk_params = _get_sdk_rate_limit_params(request)
    if sdk_params:
        bucket_id, _max, _window = sdk_params
        rl_key = f"{key_prefix}:{user_id}:{bucket_id}"
    else:
        # Direct/browser traffic: use client IP as bucket
        client_ip = get_client_ip(request)
        rl_key = f"{key_prefix}:{user_id}:{client_ip}"
        _max = max_attempts or getattr(
            settings, "RATE_LIMIT_SENSITIVE_ATTEMPTS", 5
        )
        _window = window_seconds or getattr(
            settings, "RATE_LIMIT_SENSITIVE_WINDOW", 3600
        )

    if not check_rate_limit(rl_key, _max, _window):
        raise TooManyRequestsException()


def get_client_ip(request) -> str:
    """Extract the client's IP address from the request.

    MED-02 Fix: Only trusts ``X-Forwarded-For`` when the immediate
    connecting IP (``REMOTE_ADDR``) is a known trusted proxy.  This
    prevents clients from spoofing the header to bypass rate limiting.

    Configuration:
    Set ``TRUSTED_PROXIES`` in Django settings as a list of IP addresses
    or CIDR ranges (e.g. ``["127.0.0.1", "10.0.0.0/8"]``).  Defaults to
    loopback only for local development safety.

    Falls back to ``REMOTE_ADDR`` when no trusted proxy is configured or
    when the direct connection is not from a trusted proxy.
    """
    from ipaddress import ip_address, ip_network

    remote_addr = request.META.get("REMOTE_ADDR", "0.0.0.0")

    # Load trusted proxies from settings (cached on first call)
    trusted_proxies = getattr(settings, "TRUSTED_PROXIES", None)
    if trusted_proxies is None:
        # Default: trust loopback only
        trusted_proxies = ["127.0.0.1", "::1"]

    # Check if REMOTE_ADDR is a trusted proxy
    is_trusted = False
    try:
        remote_ip = ip_address(remote_addr)
        for proxy in trusted_proxies:
            try:
                if "/" in proxy:
                    if remote_ip in ip_network(proxy, strict=False):
                        is_trusted = True
                        break
                elif remote_ip == ip_address(proxy):
                    is_trusted = True
                    break
            except ValueError:
                continue
    except ValueError:
        pass

    if is_trusted:
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            ip = x_forwarded_for.split(",")[0].strip()
            return ip

    return remote_addr
