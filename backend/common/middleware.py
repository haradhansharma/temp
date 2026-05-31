"""Django middleware for service-to-service API key authentication.

Validates the ``X-API-Key`` header on **every** request that includes it.
When a valid key is found, ``request.service_credential`` and
``request.service_domain_from_key`` are attached for downstream use
(e.g., domain-aware ``auth/me``, per-API-key rate limiting).

Design decisions:

- **Opt-in per request**: the middleware only activates when
  ``X-API-Key`` is present.  Requests without the header pass through
  untouched, preserving regular user JWT authentication.
- **Enforcement mode**: controlled by ``settings.API_KEY_ENFORCED``.
  When ``False`` (default), invalid keys log a warning but the request
  continues — useful for gradual rollout.  When ``True``, invalid keys
  return a 403 JSON response immediately.
- **JSON error responses**: returned directly by the middleware (before
  Django Ninja processes the request) so that SDK consumers receive the
  correct HTTP status code and machine-readable ``code`` field.
- **ASGI-compatible**: uses Django 5.2 ``@sync_and_async_middleware``
  pattern — the async path uses ``aget``/``aupdate`` ORM calls and
  ``await get_response()``, while the sync path uses regular ``get``/
  ``update`` calls.  Under Daphne/uvicorn the async path is taken,
  avoiding thread-pool overhead.
- **Backward compatible**: the existing ``validate_api_key()`` function
  in ``common/api_key_auth.py`` detects when the middleware has already
  validated the key and returns the cached credential, so controllers
  that call it directly continue to work without changes.
"""

import hashlib
import logging

from asgiref.sync import iscoroutinefunction
from django.conf import settings
from django.http import JsonResponse
from django.utils.decorators import sync_and_async_middleware

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared helpers (no DB queries — safe to call from both sync & async paths)
# ---------------------------------------------------------------------------

def _build_reject(status, detail, code):
    """Return a JSON rejection response if ``API_KEY_ENFORCED`` is ``True``.

    When enforcement is off (default), returns ``None`` so the calling
    middleware lets the request pass through with only a log warning.
    """
    enforced = getattr(settings, "API_KEY_ENFORCED", False)
    if not enforced:
        return None
    return JsonResponse({"detail": detail, "code": code}, status=status)


def _client_ip(request):
    """Extract client IP (consistent with ``rate_limit.py``)."""
    return request.META.get("REMOTE_ADDR", "unknown")


def _now():
    """Return timezone-aware now for ``last_used_at`` updates."""
    from django.utils import timezone
    return timezone.now()


# ---------------------------------------------------------------------------
# Sync validation (WSGI path / standard runserver / gunicorn)
# ---------------------------------------------------------------------------

def _validate_and_attach(request, api_key):
    """Validate the API key (sync) and attach credential to *request*.

    Returns a ``JsonResponse`` on hard failure, or ``None`` on success /
    soft-failure (enforcement off).
    """
    # Fast reject: check sb_live_ prefix before DB lookup.
    if not api_key.startswith("sb_live_"):
        logger.warning(
            "API_KEY_AUTH_FAILED: invalid key prefix, path=%s, ip=%s",
            request.path,
            _client_ip(request),
        )
        return _build_reject(
            status=403,
            detail="Invalid API key format. Key must start with 'sb_live_'.",
            code="invalid_api_key_format",
        )

    # Validate X-Service-Domain is also present when API key is sent.
    service_domain_header = request.headers.get("X-Service-Domain", "").strip()
    if not service_domain_header:
        logger.warning(
            "API_KEY_AUTH_FAILED: X-Service-Domain header missing, "
            "path=%s, ip=%s",
            request.path,
            _client_ip(request),
        )
        return _build_reject(
            status=400,
            detail=(
                "X-Service-Domain header is required when "
                "X-API-Key is provided."
            ),
            code="missing_service_domain",
        )

    # Hash the raw key for DB lookup.
    key_hash = hashlib.sha256(api_key.encode("utf-8")).hexdigest()

    from billing.models import ServiceCredential

    try:
        credential = ServiceCredential.objects.select_related(
            "service_domain", "created_by"
        ).get(api_key_hash=key_hash)
    except ServiceCredential.DoesNotExist:
        logger.warning(
            "API_KEY_AUTH_FAILED: no credential found for key with "
            "prefix='%s', path=%s, ip=%s",
            api_key[:12] if len(api_key) >= 12 else api_key,
            request.path,
            _client_ip(request),
        )
        return _build_reject(
            status=403,
            detail=(
                "Invalid API key. No credential found for the "
                "provided key."
            ),
            code="api_key_forbidden",
        )

    # Check credential is active.
    if not credential.is_active:
        logger.warning(
            "API_KEY_AUTH_FAILED: credential '%s' is revoked, "
            "path=%s, ip=%s",
            credential.api_key_prefix,
            request.path,
            _client_ip(request),
        )
        return _build_reject(
            status=403,
            detail="This API key has been revoked.",
            code="api_key_revoked",
        )

    # Check service domain is active.
    if not credential.service_domain.is_active:
        logger.warning(
            "API_KEY_AUTH_FAILED: domain '%s' is inactive, "
            "path=%s, ip=%s",
            credential.service_domain.domain,
            request.path,
            _client_ip(request),
        )
        return _build_reject(
            status=403,
            detail=(
                "The service domain associated with this API key "
                "is inactive."
            ),
            code="service_domain_inactive",
        )

    # Cross-check: X-Service-Domain header must match the credential's
    # bound domain (prevents domain spoofing).
    if credential.service_domain.domain != service_domain_header:
        logger.warning(
            "API_KEY_AUTH_FAILED: domain mismatch — key belongs to "
            "'%s' but header says '%s', path=%s, ip=%s",
            credential.service_domain.domain,
            service_domain_header,
            request.path,
            _client_ip(request),
        )
        return _build_reject(
            status=403,
            detail=(
                "API key domain mismatch. The X-Service-Domain header "
                "does not match the domain bound to this API key."
            ),
            code="domain_mismatch",
        )

    # --- Success: attach to request ---
    request.service_credential = credential
    request.service_domain_from_key = credential.service_domain

    # Update last_used_at atomically (fire-and-forget, avoids race).
    ServiceCredential.objects.filter(pk=credential.pk).update(
        last_used_at=_now()
    )

    # C6: Track usage analytics (Redis INCR — non-blocking).
    try:
        from common.analytics import track_api_key_usage
        track_api_key_usage(credential.pk)
    except Exception:
        pass  # Analytics must never break a request.

    logger.debug(
        "API_KEY_AUTH_OK: credential='%s', domain='%s', path=%s",
        credential.api_key_prefix,
        credential.service_domain.domain,
        request.path,
    )

    return None  # No error — continue processing.


# ---------------------------------------------------------------------------
# Async validation (ASGI path / Daphne / uvicorn)
# ---------------------------------------------------------------------------

async def _avalidate_and_attach(request, api_key):
    """Validate the API key (async) and attach credential to *request*.

    Identical logic to ``_validate_and_attach`` but uses async ORM
    operations (``aget``, ``aupdate``) so the middleware never blocks
    the asyncio event loop.
    """
    # Fast reject: check sb_live_ prefix before DB lookup.
    if not api_key.startswith("sb_live_"):
        logger.warning(
            "API_KEY_AUTH_FAILED: invalid key prefix, path=%s, ip=%s",
            request.path,
            _client_ip(request),
        )
        return _build_reject(
            status=403,
            detail="Invalid API key format. Key must start with 'sb_live_'.",
            code="invalid_api_key_format",
        )

    # Validate X-Service-Domain is also present when API key is sent.
    service_domain_header = request.headers.get("X-Service-Domain", "").strip()
    if not service_domain_header:
        logger.warning(
            "API_KEY_AUTH_FAILED: X-Service-Domain header missing, "
            "path=%s, ip=%s",
            request.path,
            _client_ip(request),
        )
        return _build_reject(
            status=400,
            detail=(
                "X-Service-Domain header is required when "
                "X-API-Key is provided."
            ),
            code="missing_service_domain",
        )

    # Hash the raw key for DB lookup.
    key_hash = hashlib.sha256(api_key.encode("utf-8")).hexdigest()

    from billing.models import ServiceCredential

    try:
        credential = await ServiceCredential.objects.select_related(
            "service_domain", "created_by"
        ).aget(api_key_hash=key_hash)
    except ServiceCredential.DoesNotExist:
        logger.warning(
            "API_KEY_AUTH_FAILED: no credential found for key with "
            "prefix='%s', path=%s, ip=%s",
            api_key[:12] if len(api_key) >= 12 else api_key,
            request.path,
            _client_ip(request),
        )
        return _build_reject(
            status=403,
            detail=(
                "Invalid API key. No credential found for the "
                "provided key."
            ),
            code="api_key_forbidden",
        )

    # Check credential is active.
    if not credential.is_active:
        logger.warning(
            "API_KEY_AUTH_FAILED: credential '%s' is revoked, "
            "path=%s, ip=%s",
            credential.api_key_prefix,
            request.path,
            _client_ip(request),
        )
        return _build_reject(
            status=403,
            detail="This API key has been revoked.",
            code="api_key_revoked",
        )

    # Check service domain is active.
    if not credential.service_domain.is_active:
        logger.warning(
            "API_KEY_AUTH_FAILED: domain '%s' is inactive, "
            "path=%s, ip=%s",
            credential.service_domain.domain,
            request.path,
            _client_ip(request),
        )
        return _build_reject(
            status=403,
            detail=(
                "The service domain associated with this API key "
                "is inactive."
            ),
            code="service_domain_inactive",
        )

    # Cross-check: X-Service-Domain header must match the credential's
    # bound domain (prevents domain spoofing).
    if credential.service_domain.domain != service_domain_header:
        logger.warning(
            "API_KEY_AUTH_FAILED: domain mismatch — key belongs to "
            "'%s' but header says '%s', path=%s, ip=%s",
            credential.service_domain.domain,
            service_domain_header,
            request.path,
            _client_ip(request),
        )
        return _build_reject(
            status=403,
            detail=(
                "API key domain mismatch. The X-Service-Domain header "
                "does not match the domain bound to this API key."
            ),
            code="domain_mismatch",
        )

    # --- Success: attach to request ---
    request.service_credential = credential
    request.service_domain_from_key = credential.service_domain

    # Update last_used_at atomically (async, fire-and-forget).
    await ServiceCredential.objects.filter(pk=credential.pk).aupdate(
        last_used_at=_now()
    )

    # C6: Track usage analytics (Redis INCR — non-blocking).
    try:
        from common.analytics import track_api_key_usage
        track_api_key_usage(credential.pk)
    except Exception:
        pass  # Analytics must never break a request.

    logger.debug(
        "API_KEY_AUTH_OK: credential='%s', domain='%s', path=%s",
        credential.api_key_prefix,
        credential.service_domain.domain,
        request.path,
    )

    return None  # No error — continue processing.


# ---------------------------------------------------------------------------
# Middleware entry point — Django 5.2 @sync_and_async_middleware pattern
# ---------------------------------------------------------------------------

@sync_and_async_middleware
def service_credential_middleware(get_response):
    """Validate ``X-API-Key`` on every request that includes it.

    Django 5.2 ``@sync_and_async_middleware`` pattern:

    - If the next middleware in the chain is async (ASGI/Daphne/uvicorn),
      the **async** inner function is used.  ORM calls go through
      ``aget`` / ``aupdate`` so the event loop is never blocked.
    - If the next middleware is sync (WSGI/runserver/gunicorn), the
      **sync** inner function is used with regular ``get`` / ``update``.

    The middleware is registered in ``settings.MIDDLEWARE`` as::

        "common.middleware.service_credential_middleware"

    It should be placed **after** CORS middleware and **before**
    CSRF / auth middleware so that API key errors are returned before
    Django's auth layer processes the request.
    """

    if iscoroutinefunction(get_response):
        # ---- ASGI path (Daphne / uvicorn) ----
        async def middleware(request):
            api_key = request.headers.get("X-API-Key", "").strip()

            # No API key — regular user auth path, pass through.
            if not api_key:
                return await get_response(request)

            # API key present — validate it.
            error_response = await _avalidate_and_attach(request, api_key)
            if error_response is not None:
                return error_response

            return await get_response(request)

    else:
        # ---- WSGI path (standard runserver / gunicorn) ----
        def middleware(request):
            api_key = request.headers.get("X-API-Key", "").strip()

            # No API key — regular user auth path, pass through.
            if not api_key:
                return get_response(request)

            # API key present — validate it.
            error_response = _validate_and_attach(request, api_key)
            if error_response is not None:
                return error_response

            return get_response(request)

    return middleware
