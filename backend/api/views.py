"""API configuration for the Sattabase project.

This module creates the NinjaExtraAPI instance, registers exception
handlers for all custom exceptions from ``common.exceptions``, and
auto-discovers all ``@api_controller`` decorated classes.
"""

import logging

from ninja_extra import NinjaExtraAPI
from ninja.errors import ValidationError as NinjaValidationError

from common.exceptions import (
    UnauthorizedException,
    ForbiddenException,
    NotFoundException,
    BadRequestException,
    ConflictException,
    TooManyRequestsException,
    AccountNotActiveException,
)

logger = logging.getLogger(__name__)

api = NinjaExtraAPI(
    title="Sattabase API",
    version="1.0.0",
    description=(
        "Sattabase API — Central Multi-Tenant Subscription Platform.\n\n"
        "## Authentication\n\n"
        "All protected endpoints require a JWT Bearer token in the "
        "``Authorization: Bearer <token>`` header.\n\n"
        "## Auth Endpoints (`/api/v1/auth/`)\n\n"
        "- `POST /auth/register`\n"
        "- `POST /auth/login`\n"
        "- `POST /auth/token/refresh`\n"
        "- `POST /auth/token/verify`\n"
        "- `POST /auth/token/blacklist`\n"
        "- `POST /auth/password-reset/request`\n"
        "- `POST /auth/password-reset/confirm`\n\n"
        "## Billing Endpoints (`/api/v1/billing/`)\n\n"
        "### Public\n"
        "- `GET /billing/products` — List all active products\n"
        "- `GET /billing/products/{slug}` — Product detail with plans & domains\n"
        "- `GET /billing/products/{slug}/plans` — Plans for a product\n\n"
        "### Protected (requires JWT)\n"
        "- `GET /billing/auth/me` — User info + subscription + access map\n"
        "- `GET /billing/subscriptions` — All user subscriptions\n"
        "- `GET /billing/subscriptions/{product_slug}` — Subscription detail\n"
        "- `POST /billing/subscriptions/{product_slug}/cancel`\n"
        "- `POST /billing/subscriptions/{product_slug}/reactivate`\n"
        "- `POST /billing/subscriptions/{product_slug}/change-plan`\n"
        "- `POST /billing/subscriptions/{product_slug}/checkout`\n"
        "- `POST /billing/portal`\n\n"
        "### Webhooks (signature-verified, no JWT)\n"
        "- `POST /billing/webhooks/stripe`\n\n"
        "## Admin Endpoints (`/api/v1/admin/`)  \n"
        "All admin endpoints require JWT authentication with ``is_staff=True``.  \n"
        "Write endpoints are rate-limited to 30 req/min; read endpoints to 120 req/min.\n\n"
        "### Products & Domains\n"
        "- `POST   /admin/products` — Create product\n"
        "- `GET    /admin/products` — List products (paginated)\n"
        "- `GET    /admin/products/{id}` — Product detail\n"
        "- `PUT    /admin/products/{id}` — Update product\n"
        "- `PATCH  /admin/products/{id}/toggle` — Activate/deactivate\n"
        "- `DELETE /admin/products/{id}` — Soft-delete\n"
        "- `POST   /admin/products/{id}/domains` — Add domain\n"
        "- `PUT    /admin/domains/{id}` — Update domain\n"
        "- `DELETE /admin/domains/{id}` — Remove domain\n\n"
        "### Plans & Access Entries\n"
        "- `POST   /admin/products/{id}/plans` — Create plan\n"
        "- `GET    /admin/products/{id}/plans` — List plans (paginated)\n"
        "- `GET    /admin/plans/{id}` — Plan detail with access entries\n"
        "- `PUT    /admin/plans/{id}` — Update plan\n"
        "- `PATCH  /admin/plans/{id}/toggle` — Toggle is_active\n"
        "- `PATCH  /admin/plans/{id}/feature` — Toggle is_featured\n"
        "- `POST   /admin/plans/{id}/duplicate` — Duplicate plan\n"
        "- `DELETE /admin/plans/{id}` — Delete plan\n"
        "- `POST   /admin/plans/{id}/access-entries` — Create access entry\n"
        "- `PUT    /admin/access-entries/{id}` — Update access entry\n"
        "- `DELETE /admin/access-entries/{id}` — Remove access entry\n"
        "- `POST   /admin/plans/{id}/access-entries/bulk` — Bulk replace\n"
        "- `GET    /admin/products/{id}/access-matrix` — Feature matrix\n\n"
        "### Subscriptions\n"
        "- `GET    /admin/subscriptions` — List (paginated, filterable)\n"
        "- `GET    /admin/subscriptions/{id}` — Detail with access map\n"
        "- `PATCH  /admin/subscriptions/{id}/override` — Override plan/status\n"
        "- `PATCH  /admin/subscriptions/{id}/cancel` — Force cancel\n"
        "- `PATCH  /admin/subscriptions/{id}/expire` — Force expire\n"
        "- `PATCH  /admin/subscriptions/{id}/extend` — Extend period\n"
        "- `GET    /admin/subscriptions/{id}/plan-changes` — Plan history (paginated)\n"
        "- `GET    /admin/subscriptions/{id}/invoices` — Invoices (paginated)\n"
        "- `GET    /admin/subscriptions/{id}/refunds` — Refunds (paginated)\n\n"
        "### Users\n"
        "- `GET    /admin/users` — List users (paginated, filterable)\n"
        "- `GET    /admin/users/{id}` — User detail\n"
        "- `PATCH  /admin/users/{id}/status` — Activate/deactivate\n"
        "- `PATCH  /admin/users/{id}/role` — Change role\n"
        "- `GET    /admin/users/{id}/audit` — User audit trail (paginated)\n\n"
        "### Refunds\n"
        "- `GET    /admin/refunds` — List refunds (paginated, filterable)\n"
        "- `PATCH  /admin/refunds/{id}/approve` — Approve (two-person rule)\n"
        "- `PATCH  /admin/refunds/{id}/reject` — Reject\n\n"
        "### Metrics\n"
        "- `GET  /admin/metrics/overview` — MRR, churn, trial conversion\n"
        "- `GET  /admin/metrics/revenue` — Revenue by product/plan/month\n"
        "- `GET  /admin/metrics/subscriptions` — Subscription funnel\n"
        "- `GET  /admin/metrics/products` — Per-product metrics\n\n"
        "### Audit Log\n"
        "- `GET  /admin/audit-log` — Admin action log (paginated)\n\n"
        "### Webhook Monitoring\n"
        "- `GET  /admin/webhooks` — List webhook events (paginated)\n"
        "- `POST /admin/webhooks/{id}/retry` — Retry failed webhook\n\n"
        "### API Keys\n"
        "- `GET   /admin/api-keys/` — List API keys (paginated)\n"
        "- `POST  /admin/api-keys/` — Create API key\n"
        "- `PATCH /admin/api-keys/{id}/revoke` — Revoke key\n"
        "- `POST  /admin/api-keys/{id}/rotate` — Rotate key"
    ),
    urls_namespace="sattabase",
    openapi_extra={
        "info": {
            "contact": {
                "name": "Sattabase Support",
                "email": "support@sattabase.com",
            },
            "license": {"name": "Private"},
        },
        "servers": [
            {"url": "http://localhost:8090", "description": "Local Development"}
        ],
    },
)


# =============================================================================
# Validation Error Handler
# =============================================================================


@api.exception_handler(NinjaValidationError)
def validation_exception_handler(request, exc: NinjaValidationError):
    """Handle Pydantic/Ninja validation errors with field-level details."""
    errors = []
    if hasattr(exc, "errors"):
        for err in exc.errors:
            field = " -> ".join(str(loc) for loc in err.get("loc", []))
            errors.append({"field": field, "message": err.get("msg", "Invalid value")})
    else:
        errors.append({"field": "non_field", "message": str(exc)})
    return api.create_response(
        request,
        {"detail": "Validation error", "errors": errors, "code": "validation_error"},
        status=400,
    )


# =============================================================================
# Custom Exception Handlers
# =============================================================================


def _error_response(request, exc):
    """Build a consistent error response for all custom exceptions.

    All custom exceptions from ``common.exceptions`` extend
    ``ninja_extra.exceptions.APIException`` which provides ``status_code``,
    ``detail`` (an ``ErrorDetail`` string subclass with a ``.code`` attribute),
    and ``default_code``.

    The ``code`` in the response envelope is read from ``exc.detail.code``,
    which comes from each exception's ``default_code`` class attribute.
    """
    return api.create_response(
        request,
        {"detail": str(exc.detail), "code": getattr(exc.detail, "code", "error")},
        status=exc.status_code,
    )


@api.exception_handler(UnauthorizedException)
def unauthorized_handler(request, exc):
    return _error_response(request, exc)


@api.exception_handler(ForbiddenException)
def forbidden_handler(request, exc):
    return _error_response(request, exc)


@api.exception_handler(NotFoundException)
def not_found_handler(request, exc):
    return _error_response(request, exc)


@api.exception_handler(BadRequestException)
def bad_request_handler(request, exc):
    return _error_response(request, exc)


@api.exception_handler(ConflictException)
def conflict_handler(request, exc):
    return _error_response(request, exc)


@api.exception_handler(TooManyRequestsException)
def too_many_requests_handler(request, exc):
    return _error_response(request, exc)


@api.exception_handler(AccountNotActiveException)
def account_not_active_handler(request, exc):
    return _error_response(request, exc)


# =============================================================================
# Catch-All Handler
# =============================================================================


@api.exception_handler(Exception)
def unhandled_exception_handler(request, exc: Exception):
    """Catch-all for truly unexpected errors. Logs full traceback."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return api.create_response(
        request,
        {
            "detail": "An unexpected error occurred. Please try again.",
            "code": "server_error",
        },
        status=500,
    )


# =============================================================================
# Explicitly import admin controllers that live outside the standard
# ``controllers.py`` naming convention so ninja_extra registers them.
# Must happen AFTER Django apps are loaded (here in api/views.py, not
# in billing/__init__.py which runs too early — AppRegistryNotReady).
# =============================================================================

from billing import (  # noqa: E402, F401
    admin_controller,  # 9.2–9.3 + 9.6: Products, Domains, Plans, Access Entries, Refunds
    admin_subscription_controller,  # 9.4: Subscriptions
    admin_user_controller,  # 9.5: Users
    admin_metrics_controller,  # 9.7: Metrics, Audit, Webhooks
)

api.auto_discover_controllers()
