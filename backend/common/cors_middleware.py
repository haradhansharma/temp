"""Dynamic CORS middleware for ServiceDomain-based origin validation.

Extends the default ``django-cors-headers`` behavior to dynamically allow
origins from the ``ServiceDomain`` table. This eliminates the need to
manually configure ``CORS_ALLOWED_ORIGINS`` every time a new service
domain is added.

How it works:
    1. Check the ``Origin`` header on every request.
    2. If the origin matches an active ``ServiceDomain.domain`` OR the
       configured ``FRONTEND_URL`` from settings, inject the necessary
       CORS headers directly into the response.
    3. Otherwise, fall through to ``django-cors-headers`` default behavior.

The ServiceDomain origins are cached with a 5-minute TTL to avoid
database lookups on every request.

Security:
    - Only ``is_active=True`` domains are allowed.
    - The origin must match exactly (no wildcards).
    - ``CORS_ALLOW_ALL_ORIGINS`` in DEBUG mode still takes precedence.
    - ``FRONTEND_URL`` is always allowed (read from ``settings.FRONTEND_URL``
      which is set via ``PUBLIC_SITE_URL_SB`` env var).

Note:
    This middleware is fully ASGI-compatible (Django 5.2 ``@sync_and_async_middleware``
    pattern).  It works correctly under both Daphne/uvicorn (ASGI) and the
    standard ``runserver`` (WSGI).
"""

import logging

from asgiref.sync import iscoroutinefunction
from django.conf import settings
from django.utils.decorators import sync_and_async_middleware

logger = logging.getLogger(__name__)

# Cache key for storing allowed origins
CACHE_KEY = "sattabase_allowed_cors_origins"
CACHE_TIMEOUT = 300  # 5 minutes


def _get_allowed_origins() -> set:
    """Get the set of allowed CORS origins from ServiceDomain table.

    Always includes the configured ``FRONTEND_URL`` (``settings.FRONTEND_URL``)
    alongside all active ``ServiceDomain`` entries.  This ensures the main
    frontend is accepted even when it runs on a different domain/port than
    the backend (e.g., Docker deployments).

    Uses Django's cache framework with a 5-minute TTL for the DB portion.
    Falls back to {FRONTEND_URL} only on cache failure.
    """
    from django.conf import settings
    from django.core.cache import cache

    # Frontend URL is always allowed (from PUBLIC_SITE_URL_SB env var)
    frontend_url = getattr(settings, "FRONTEND_URL", "").strip()

    origins = cache.get(CACHE_KEY)
    if origins is not None:
        if frontend_url:
            origins.add(frontend_url)
        return origins

    try:
        from billing.models import ServiceDomain

        origins = set(
            ServiceDomain.objects.filter(
                is_active=True,
            ).values_list("domain", flat=True)
        )
        cache.set(CACHE_KEY, origins, CACHE_TIMEOUT)
        logger.debug(
            "CORS: loaded %d active service domains for CORS whitelist",
            len(origins),
        )
    except Exception as e:
        logger.warning("CORS: failed to load service domains: %s", e)
        origins = set()

    if frontend_url:
        origins.add(frontend_url)

    return origins


def _inject_cors(response, origin: str):
    """Inject CORS headers into *response* for *origin*.

    Always sets headers to ensure proper credential support.
    This overrides any existing `Access-Control-Allow-Origin: *` header
    that may have been set by django-cors-headers with CORS_ALLOW_ALL_ORIGINS=True.
    """
    response["Access-Control-Allow-Origin"] = origin
    response["Access-Control-Allow-Methods"] = (
        "GET, POST, PUT, PATCH, DELETE, OPTIONS, HEAD"
    )
    response["Access-Control-Allow-Headers"] = (
        "Authorization, Content-Type, X-API-Key, X-Service-Domain, "
        "Accept, Origin, X-Requested-With"
    )
    response["Access-Control-Allow-Credentials"] = "true"
    response["Access-Control-Max-Age"] = "86400"  # 24 hours preflight cache
    response["Access-Control-Expose-Headers"] = "X-API-Key, X-Service-Domain"


@sync_and_async_middleware
def service_domain_cors_middleware(get_response):
    """Dynamically allow CORS for registered service domains.

    This middleware should be placed AFTER ``CorsMiddleware`` in
    ``MIDDLEWARE`` so that ``django-cors-headers`` handles the standard
    CORS flow, and this middleware adds dynamic origin support.

    When ``CORS_ALLOW_ALL_ORIGINS`` is True (DEBUG mode), this middleware
    still needs to inject proper CORS headers for credential-based requests
    (cookies), because `Access-Control-Allow-Origin: *` is incompatible with
    `Access-Control-Allow-Credentials: true`.

    Django 5.2 ``@sync_and_async_middleware`` pattern:
        - If the next middleware in the chain is async (ASGI/Daphne),
          the async inner function is used and ``get_response`` is awaited.
        - If the next middleware is sync (WSGI), the sync inner function
          is used instead.
    """

    if iscoroutinefunction(get_response):
        # ASGI path (Daphne / uvicorn)
        async def middleware(request):
            origin = request.META.get("HTTP_ORIGIN", "").strip()
            
            # Always inject specific CORS headers when we have an Origin header
            # This is needed because CORS_ALLOW_ALL_ORIGINS=True sends "*" as origin
            # which is incompatible with credentials (cookies)
            if origin:
                # Check if origin is allowed
                allowed_origins = _get_allowed_origins()
                
                # In DEBUG mode with CORS_ALLOW_ALL_ORIGINS=True, allow any localhost origin
                # This is safe for development and enables cookie-based auth to work
                is_debug_all_origins = (
                    getattr(settings, "CORS_ALLOW_ALL_ORIGINS", False) 
                    and getattr(settings, "DEBUG", False)
                )
                is_localhost = "localhost" in origin or "127.0.0.1" in origin
                
                if origin in allowed_origins or (is_debug_all_origins and is_localhost):
                    response = await get_response(request)
                    _inject_cors(response, origin)
                    return response

            return await get_response(request)

    else:
        # WSGI path (standard runserver / gunicorn)
        def middleware(request):
            origin = request.META.get("HTTP_ORIGIN", "").strip()
            
            # Always inject specific CORS headers when we have an Origin header
            # This is needed because CORS_ALLOW_ALL_ORIGINS=True sends "*" as origin
            # which is incompatible with credentials (cookies)
            if origin:
                # Check if origin is allowed
                allowed_origins = _get_allowed_origins()
                
                # In DEBUG mode with CORS_ALLOW_ALL_ORIGINS=True, allow any localhost origin
                # This is safe for development and enables cookie-based auth to work
                is_debug_all_origins = (
                    getattr(settings, "CORS_ALLOW_ALL_ORIGINS", False) 
                    and getattr(settings, "DEBUG", False)
                )
                is_localhost = "localhost" in origin or "127.0.0.1" in origin
                
                if origin in allowed_origins or (is_debug_all_origins and is_localhost):
                    response = get_response(request)
                    _inject_cors(response, origin)
                    return response

            return get_response(request)

    return middleware
