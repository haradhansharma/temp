"""Shared admin utilities for billing admin controllers (Phase 9.8).

Centralises two pieces of infrastructure that were previously duplicated
across every admin controller file:

1. **``log_admin_access``** — Decorator that logs admin access to billing
   endpoints for structured logging / audit trails.  Was copy-pasted
   identically in ``admin_controller.py``, ``admin_user_controller.py``,
   ``admin_subscription_controller.py``, and ``admin_metrics_controller.py``.
   Now also writes to the ``AdminAuditLog`` database model so the audit-log
   API endpoint (``GET /admin/audit-log``) can return persisted entries.

2. **``admin_write_rate_limit``** / **``admin_read_rate_limit``** —
   Decorators that enforce stricter rate limits on admin endpoints.
   Write (mutation) endpoints use a tighter limit than read endpoints.

Both decorators are designed to be stacked with Django Ninja / NinjaExtra
route decorators.  They work on both sync and async handler functions
because they are thin wrappers that check a condition *before* delegating
to the original function.
"""

from functools import wraps
import logging

from asgiref.sync import sync_to_async
from django.http import HttpRequest

logger = logging.getLogger(__name__)


# =============================================================================
# Admin Access Logging Decorator
# =============================================================================


@sync_to_async
def _write_audit_log(
    admin_user_id: int,
    action: str,
    method: str,
    path: str,
    ip_address: str | None,
    status_code: int | None = None,
    details: dict | None = None,
) -> None:
    """Persist an admin action to the ``AdminAuditLog`` DB table.

    Wrapped in ``sync_to_async`` so it can be called from async handler
    wrappers without blocking the event loop.  Uses ``AdminAuditLog.objects.create``
    so that each insert is an independent round-trip — safe to call from
    concurrent request handlers.
    """
    from billing.models import AdminAuditLog

    AdminAuditLog.objects.create(
        admin_user_id=admin_user_id,
        action=action,
        method=method.upper() if method else "",
        path=path,
        ip_address=ip_address,
        status_code=status_code,
        details=details or {},
    )


def log_admin_access(func):
    """Decorator that logs admin access to billing endpoints.

    Performs **two** types of logging for every mutation request:

    1. **Python logger** (``logger.info``) — for application-level
       observability, shipped to log aggregation services.
    2. **``AdminAuditLog`` DB write** — for the admin audit-log API
       endpoint (``GET /admin/audit-log``), viewable from the admin
       dashboard UI (Phase 10).

    The DB write happens *after* the handler returns so that the response
    status code can be recorded alongside the audit entry.

    Usage::

        @http_post("/products")
        @log_admin_access
        async def create_product(self, request, ...):
            ...

    Log line format::

        ADMIN_BILLING_ACCESS: user_id=42, email=admin@example.com,
        action=create_product, ip=127.0.0.1, path=/api/v1/admin/products
    """
    @wraps(func)
    async def wrapper(self, request, *args, **kwargs):
        logger.info(
            "ADMIN_BILLING_ACCESS: user_id=%s, email=%s, action=%s, "
            "ip=%s, path=%s",
            request.user.id,
            getattr(request.user, "email", ""),
            func.__name__,
            request.META.get("REMOTE_ADDR"),
            request.path,
        )

        # Execute the actual handler and capture the response
        response = await func(self, request, *args, **kwargs)

        # Persist the audit entry to the database *after* the handler
        # completes so we can record the HTTP status code.
        status_code = getattr(response, "status_code", None)
        try:
            await _write_audit_log(
                admin_user_id=request.user.id,
                action=func.__name__,
                method=request.method,
                path=request.path,
                ip_address=request.META.get("REMOTE_ADDR"),
                status_code=status_code,
            )
        except Exception:
            # Audit logging must never break a real request — swallow and
            # log the error so an admin can investigate.
            logger.exception(
                "Failed to write AdminAuditLog for action=%s path=%s",
                func.__name__,
                request.path,
            )

        return response
    return wrapper


# =============================================================================
# Admin Rate Limiting Decorators
# =============================================================================


def _apply_rate_limit(request: HttpRequest, key_prefix: str, max_attempts: int, window_seconds: int) -> None:
    """Internal helper — check rate limit and raise TooManyRequestsException."""
    from common.rate_limit import check_rate_limit_or_raise

    check_rate_limit_or_raise(
        request,
        key_prefix=key_prefix,
        max_attempts=max_attempts,
        window_seconds=window_seconds,
    )


def admin_write_rate_limit(func=None, *, max_attempts: int = 30, window_seconds: int = 60):
    """Rate-limit decorator for admin WRITE (mutation) endpoints.

    Enforces a stricter limit on write operations to protect against
    accidental mass mutations or abuse.  Defaults to **30 requests
    per 60 seconds** per admin user + IP combination.

    Usage (with arguments)::

        @http_post("/products")
        @admin_write_rate_limit(max_attempts=20, window_seconds=60)
        async def create_product(self, request, ...):
            ...

    Usage (bare decorator — uses defaults)::

        @http_patch("/products/{id}/toggle")
        @admin_write_rate_limit
        async def toggle_product(self, request, ...):
            ...

    The key is built as ``admin_write:{user_id}:{ip}`` so each admin
    gets their own rate limit bucket per IP address.
    """
    def decorator(fn):
        @wraps(fn)
        async def wrapper(self, request, *args, **kwargs):
            _apply_rate_limit(
                request,
                key_prefix="admin_write",
                max_attempts=max_attempts,
                window_seconds=window_seconds,
            )
            return await fn(self, request, *args, **kwargs)
        return wrapper

    if func is not None:
        # Bare decorator: @admin_write_rate_limit
        return decorator(func)
    # Called with arguments: @admin_write_rate_limit(...)
    return decorator


def admin_read_rate_limit(func=None, *, max_attempts: int = 120, window_seconds: int = 60):
    """Rate-limit decorator for admin READ endpoints.

    Enforces a generous limit on read operations since admin dashboards
    make many parallel data requests.  Defaults to **120 requests per
    60 seconds** per admin user + IP combination.

    Usage::

        @http_get("/metrics/overview")
        @admin_read_rate_limit
        async def metrics_overview(self, request, ...):
            ...

    The key is built as ``admin_read:{user_id}:{ip}`` so each admin
    gets their own rate limit bucket per IP address.
    """
    def decorator(fn):
        @wraps(fn)
        async def wrapper(self, request, *args, **kwargs):
            _apply_rate_limit(
                request,
                key_prefix="admin_read",
                max_attempts=max_attempts,
                window_seconds=window_seconds,
            )
            return await fn(self, request, *args, **kwargs)
        return wrapper

    if func is not None:
        return decorator(func)
    return decorator
