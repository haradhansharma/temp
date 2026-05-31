"""API key authentication for service-to-service requests.

Validates the ``X-API-Key`` header against ``ServiceCredential`` records.
On success, attaches ``service_credential`` and ``service_domain`` to the
request object for downstream use (e.g., domain-aware ``auth/me``).

Usage in controllers::

    from common.api_key_auth import validate_api_key

    @http_get("/auth/me")
    async def auth_me(self, request):
        validate_api_key(request)
        # request.service_credential is now available
        # request.service_domain is now available

Security audit (E3 — 2026-05-07):
    Verified that **no raw API key material** is ever written to logs,
    error responses, or exception messages.  All log statements use the
    12-character ``api_key_prefix`` (stored in DB) or a truncated
    ``api_key[:12]`` slice.  The raw key exists only in (a) the HTTP
    request header (in transit) and (b) the creation/rotation HTTP
    response body (shown exactly once, never persisted).
"""

import hashlib
import logging
from typing import Optional

from django.conf import settings
from django.http import HttpRequest

from common.exceptions import UnauthorizedException

logger = logging.getLogger(__name__)


def validate_api_key(request: HttpRequest) -> Optional["ServiceCredential"]:
    """Validate the X-API-Key header and attach credential to request.

    This function is middleware-aware: if the
    ``service_credential_middleware`` (``common/middleware.py``) has already
    validated the key and attached ``request.service_credential``, this
    function returns the cached credential immediately without re-querying
    the database.  This makes controllers that call ``validate_api_key()``
    directly (e.g., ``auth/me``) work seamlessly with or without the
    middleware enabled.

    Flow:
    1. Check if ``request.service_credential`` is already set (by
       middleware).  If so, return it.
    2. Extract ``X-API-Key`` from the request header.
    3. SHA-256 hash the raw key.
    4. Look up ``ServiceCredential`` by hash.
    5. Check ``is_active`` and ``service_domain.is_active``.
    6. Update ``last_used_at`` (atomic update to avoid race conditions).
    7. Attach ``request.service_credential`` and ``request.service_domain``.
    8. When ``API_KEY_ENFORCED`` is ``False`` (default), missing keys
       log a warning but allow the request through for backward compatibility.
       When ``True``, missing/invalid keys raise ``UnauthorizedException``.

    Returns:
        The ``ServiceCredential`` instance if a valid key was provided.

    Raises:
        ``UnauthorizedException`` if key is invalid and enforcement is on.
    """
    # Middleware-aware: return cached credential if already validated.
    credential = getattr(request, "service_credential", None)
    if credential is not None:
        return credential

    from billing.models import ServiceCredential

    api_key = request.headers.get("X-API-Key", "").strip()

    if not api_key:
        _handle_missing_key(request)
        return None

    # Hash the raw key for lookup
    key_hash = hashlib.sha256(api_key.encode("utf-8")).hexdigest()

    try:
        credential = ServiceCredential.objects.select_related(
            "service_domain", "created_by"
        ).get(api_key_hash=key_hash)
    except ServiceCredential.DoesNotExist:
        logger.warning(
            "API_KEY_AUTH_FAILED: no credential found for key with prefix='%s', "
            "path=%s, ip=%s",
            api_key[:12] if len(api_key) >= 12 else api_key,
            request.path,
            request.META.get("REMOTE_ADDR"),
        )
        enforced = getattr(settings, "API_KEY_ENFORCED", False)
        if enforced:
            raise UnauthorizedException(
                "Invalid API key. Provide a valid X-API-Key header."
            )
        return None

    # Check credential and domain active status
    if not credential.is_active:
        logger.warning(
            "API_KEY_AUTH_FAILED: credential '%s' is revoked, path=%s, ip=%s",
            credential.api_key_prefix,
            request.path,
            request.META.get("REMOTE_ADDR"),
        )
        enforced = getattr(settings, "API_KEY_ENFORCED", False)
        if enforced:
            raise UnauthorizedException("This API key has been revoked.")
        return None

    if not credential.service_domain.is_active:
        logger.warning(
            "API_KEY_AUTH_FAILED: domain '%s' is inactive, path=%s, ip=%s",
            credential.service_domain.domain,
            request.path,
            request.META.get("REMOTE_ADDR"),
        )
        enforced = getattr(settings, "API_KEY_ENFORCED", False)
        if enforced:
            raise UnauthorizedException(
                "The service domain associated with this API key is inactive."
            )
        return None

    # Update last_used_at atomically (avoid race conditions)
    ServiceCredential.objects.filter(pk=credential.pk).update(
        last_used_at=_get_now()
    )

    # Attach to request for downstream use
    request.service_credential = credential
    request.service_domain_from_key = credential.service_domain

    logger.debug(
        "API_KEY_AUTH_OK: credential='%s', domain='%s', path=%s",
        credential.api_key_prefix,
        credential.service_domain.domain,
        request.path,
    )

    return credential


def _handle_missing_key(request: HttpRequest) -> None:
    """Handle requests without an API key.

    When enforcement is off (default), log a warning and allow.
    When enforcement is on, raise UnauthorizedException.
    """
    enforced = getattr(settings, "API_KEY_ENFORCED", False)
    if enforced:
        raise UnauthorizedException(
            "API key is required. Provide a valid X-API-Key header."
        )
    logger.debug(
        "API_KEY_AUTH: no X-API-Key header, path=%s (enforcement off)",
        request.path,
    )


def _get_now():
    """Return timezone-aware now for last_used_at updates."""
    from django.utils import timezone
    return timezone.now()
