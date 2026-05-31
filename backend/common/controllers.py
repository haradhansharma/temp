"""Common controllers for cross-app functionality.

Currently provides the admin API key management controller for the
ServiceCredential model. This lives in the ``common`` app because it
is used across multiple apps (billing auth/me, future SDK auth endpoints).
"""

import logging
from typing import Optional

from ninja_extra import api_controller, http_get, http_post, http_patch
from ninja import Query
from django.http import HttpRequest
from asgiref.sync import sync_to_async

from common.exceptions import (
    BadRequestException,
    NotFoundException,
    ConflictException,
)
from common.permissions import IsAuthenticated, IsAdmin
from common.schemas import (
    MessageResponse,
    PaginatedResponse,
    PaginationInput,
    ServiceDomainOptionSchema,
    ApiKeyCreateInputSchema,
    ApiKeyOutputSchema,
    ApiKeyCreateOutputSchema,
    ApiKeyRotateOutputSchema,
    ApiKeyAnalyticsResponse,
    ApiKeyAnalyticsOverviewSchema,
)

# Import JWTAuth from users controllers — single auth class shared across apps
from users.controllers import JWTAuth

from billing.models import ServiceCredential, ServiceDomain
from common.utils import generate_api_key
from common.rate_limit import check_rate_limit_or_raise

# Re-export from billing.admin_utils for consistency
# (admin_utils is in the billing app which may not always be available,
#  so common controllers use the rate_limit helper directly)
from functools import wraps


def _admin_write_rate_limit(func):
    """Admin write rate limit for common controllers."""
    @wraps(func)
    async def wrapper(self, request, *args, **kwargs):
        check_rate_limit_or_raise(request, "admin_write", max_attempts=30, window_seconds=60)
        return await func(self, request, *args, **kwargs)
    return wrapper


def _admin_read_rate_limit(func):
    """Admin read rate limit for common controllers."""
    @wraps(func)
    async def wrapper(self, request, *args, **kwargs):
        check_rate_limit_or_raise(request, "admin_read", max_attempts=120, window_seconds=60)
        return await func(self, request, *args, **kwargs)
    return wrapper

logger = logging.getLogger(__name__)


@api_controller(
    "/admin/api-keys",
    tags=["Admin — API Keys"],
    auth=JWTAuth(),
    permissions=[IsAuthenticated, IsAdmin],
)
class AdminApiKeyController:
    """Admin endpoints for managing service API keys (credentials).

    All endpoints require staff authentication. API keys are the primary
    mechanism for service-to-service authentication — sister concern
    backends use them to identify themselves when calling Sattabase.

    The raw API key is returned ONLY at creation time and during rotation.
    It is never stored in the database (only its SHA-256 hash is stored).
    """

    @http_get(
        "/",
        response=PaginatedResponse[ApiKeyOutputSchema],
        summary="List API keys",
        description=(
            "List all service credentials with pagination. "
            "Filterable by service_domain_id and is_active."
        ),
    )
    @_admin_read_rate_limit
    async def list_api_keys(
        self,
        request: HttpRequest,
        service_domain_id: Optional[int] = None,
        is_active: Optional[bool] = None,
        pagination: PaginationInput = Query(...),
    ):
        """List all service credentials."""
        qs = ServiceCredential.objects.select_related(
            "service_domain", "created_by"
        ).order_by("-created_at")

        if service_domain_id is not None:
            qs = qs.filter(service_domain_id=service_domain_id)
        if is_active is not None:
            qs = qs.filter(is_active=is_active)

        from common.utils import get_paginated_data_async
        results, meta = await get_paginated_data_async(
            qs, pagination.page, pagination.page_size
        )

        items = [
            {
                "id": cred.id,
                "name": cred.name,
                "api_key_prefix": cred.api_key_prefix,
                "service_domain_id": cred.service_domain_id,
                "service_domain": cred.service_domain.domain,
                "permissions": cred.permissions,
                "is_active": cred.is_active,
                "last_used_at": cred.last_used_at,
                "created_at": cred.created_at,
                "created_by": (
                    cred.created_by.email if cred.created_by else None
                ),
            }
            for cred in results
        ]
        return {"meta": meta, "results": items}

    @http_get(
        "/service-domains",
        response=list[ServiceDomainOptionSchema],
        summary="List service domains for key creation",
        description=(
            "Return all service domains with their parent product names. "
            "Used by the admin UI to populate the create-key dropdown. "
            "Domains that already have an active credential are still listed "
            "(the frontend can decide whether to disable them)."
        ),
    )
    @_admin_read_rate_limit
    async def list_service_domains(self, request: HttpRequest):
        """Return all service domains with product names for the admin dropdown.

        Uses select_related('product') for efficient joins. Returns both
        active and inactive domains so the admin has full visibility.
        """
        domains = await sync_to_async(
            lambda: list(
                ServiceDomain.objects.select_related("product")
                .order_by("product__name", "domain")
                .values(
                    "id",
                    "domain",
                    "product__name",
                    "is_active",
                )
            )
        )()

        return [
            {
                "id": d["id"],
                "domain": d["domain"],
                "product_name": d["product__name"],
                "is_active": d["is_active"],
            }
            for d in domains
        ]

    @_admin_write_rate_limit
    @http_post(
        "/",
        response={200: ApiKeyCreateOutputSchema, 400: dict, 409: dict},
        summary="Create API key",
        description=(
            "Create a new API key for a service domain. "
            "The raw key is returned ONLY in this response. "
            "Each domain can have only one active credential."
        ),
    )
    async def create_api_key(
        self, request: HttpRequest, payload: ApiKeyCreateInputSchema
    ):
        """Create a new API key credential.

        Flow:
        1. Validate the service_domain_id exists and is active.
        2. Check no active credential already exists for this domain.
        3. Generate the key (raw, prefix, hash).
        4. Create the ServiceCredential record.
        5. Return the raw key (shown ONLY this once).
        """
        # Validate service domain exists
        try:
            domain = await sync_to_async(
                ServiceDomain.objects.select_related("product").get
            )(id=payload.service_domain_id)
        except ServiceDomain.DoesNotExist:
            raise NotFoundException("Service domain not found.")

        # Check uniqueness (one credential per domain — OneToOne constraint)
        existing = await sync_to_async(
            ServiceCredential.objects.filter(
                service_domain_id=payload.service_domain_id,
            ).first
        )()

        # Generate the key
        raw_key, prefix, key_hash = generate_api_key()

        from django.utils import timezone

        if existing:
            if existing.is_active:
                raise ConflictException(
                    "An active API key already exists for this service domain. "
                    "Rotate the existing key to generate a new one."
                )
            # Reuse the revoked credential — update in place
            existing.api_key_hash = key_hash
            existing.api_key_prefix = prefix
            existing.name = payload.name
            existing.is_active = True
            existing.created_by = request.user
            await sync_to_async(existing.save)(
                update_fields=[
                    "api_key_hash", "api_key_prefix", "name",
                    "is_active", "created_by", "updated_at",
                ]
            )
            credential = existing
        else:
            # Create credential (IntegrityError safety-net for race conditions)
            from django.db.utils import IntegrityError

            try:
                credential = await sync_to_async(ServiceCredential.objects.create)(
                    name=payload.name,
                    service_domain=domain,
                    api_key_hash=key_hash,
                    api_key_prefix=prefix,
                    is_active=True,
                    created_by=request.user,
                )
            except IntegrityError:
                raise ConflictException(
                    "An API key already exists for this service domain. "
                    "Rotate the existing key to generate a new one."
                )

        logger.info(
            "ADMIN_API_KEY_CREATED: key_id=%s, prefix='%s', domain='%s', "
            "created_by=%s, ip=%s",
            credential.id,
            prefix,
            domain.domain,
            request.user.email,
            request.META.get("REMOTE_ADDR"),
        )

        # C4: Explicit audit log with request context.
        try:
            from common.audit import write_credential_audit
            await sync_to_async(write_credential_audit)(
                action="api_key.created",
                credential=credential,
                admin_user=request.user,
                method=request.method,
                path=request.path,
                ip_address=request.META.get("REMOTE_ADDR"),
                status_code=201,
            )
        except Exception:
            pass

        return {
            "id": credential.id,
            "name": credential.name,
            "api_key_prefix": prefix,
            "raw_api_key": raw_key,
            "service_domain_id": domain.id,
            "service_domain": domain.domain,
            "is_active": True,
            "created_at": credential.created_at,
            "warning": (
                "Save this API key now. It cannot be recovered after this response."
            ),
        }

    @_admin_write_rate_limit
    @http_patch(
        "/{key_id}/revoke",
        response={200: MessageResponse, 404: dict},
        summary="Revoke API key",
        description="Revoke a service API key. The key becomes immediately invalid.",
    )
    async def revoke_api_key(self, request: HttpRequest, key_id: int):
        """Revoke an API key by setting is_active=False."""
        try:
            credential = await sync_to_async(
                ServiceCredential.objects.select_related("service_domain").get
            )(id=key_id)
        except ServiceCredential.DoesNotExist:
            raise NotFoundException("API key not found.")

        if not credential.is_active:
            raise BadRequestException("This API key is already revoked.")

        credential.is_active = False
        await sync_to_async(credential.save)(
            update_fields=["is_active", "updated_at"]
        )

        logger.info(
            "ADMIN_API_KEY_REVOKED: key_id=%s, prefix='%s', domain='%s', "
            "revoked_by=%s, ip=%s",
            credential.id,
            credential.api_key_prefix,
            credential.service_domain.domain,
            request.user.email,
            request.META.get("REMOTE_ADDR"),
        )

        # C4: Explicit audit log with request context.
        try:
            from common.audit import write_credential_audit
            await sync_to_async(write_credential_audit)(
                action="api_key.revoked",
                credential=credential,
                admin_user=request.user,
                method=request.method,
                path=request.path,
                ip_address=request.META.get("REMOTE_ADDR"),
                status_code=200,
            )
        except Exception:
            pass

        # C5: Dispatch webhook notification to sister domain.
        try:
            from common.webhooks import dispatch_credential_webhook
            dispatch_credential_webhook(
                event_type="credential.revoked",
                credential=credential,
            )
        except Exception:
            pass

        return MessageResponse(
            message=f"API key '{credential.api_key_prefix}...' has been revoked."
        )

    @_admin_write_rate_limit
    @http_post(
        "/{key_id}/rotate",
        response={200: ApiKeyRotateOutputSchema, 404: dict},
        summary="Rotate API key",
        description=(
            "Rotate an API key: revoke the old key and create a new one. "
            "The new raw key is returned ONLY in this response."
        ),
    )
    async def rotate_api_key(self, request: HttpRequest, key_id: int):
        """Rotate an API key.

        Flow:
        1. Validate the existing credential exists.
        2. Revoke the old key (set is_active=False).
        3. Generate a new key.
        4. Create a new ServiceCredential for the same domain.
        5. Return the new raw key (shown ONLY this once).
        """
        try:
            old_credential = await sync_to_async(
                ServiceCredential.objects.select_related("service_domain").get
            )(id=key_id)
        except ServiceCredential.DoesNotExist:
            raise NotFoundException("API key not found.")

        domain = old_credential.service_domain

        # Revoke old key
        old_credential.is_active = False
        await sync_to_async(old_credential.save)(
            update_fields=["is_active", "updated_at"]
        )

        # Generate new key
        new_raw, new_prefix, new_hash = generate_api_key()

        # Create new credential for the same domain
        new_credential = await sync_to_async(ServiceCredential.objects.create)(
            name=old_credential.name,
            service_domain=domain,
            api_key_hash=new_hash,
            api_key_prefix=new_prefix,
            permissions=old_credential.permissions,
            is_active=True,
            created_by=request.user,
        )

        logger.info(
            "ADMIN_API_KEY_ROTATED: old_key_id=%s (prefix='%s'), "
            "new_key_id=%s (prefix='%s'), domain='%s', "
            "rotated_by=%s, ip=%s",
            old_credential.id,
            old_credential.api_key_prefix,
            new_credential.id,
            new_prefix,
            domain.domain,
            request.user.email,
            request.META.get("REMOTE_ADDR"),
        )

        # C4: Explicit audit log with request context.
        try:
            from common.audit import write_credential_audit
            await sync_to_async(write_credential_audit)(
                action="api_key.rotated",
                credential=new_credential,
                admin_user=request.user,
                method=request.method,
                path=request.path,
                ip_address=request.META.get("REMOTE_ADDR"),
                status_code=200,
                details={
                    "old_credential_id": old_credential.id,
                    "old_prefix": old_credential.api_key_prefix,
                    "new_prefix": new_prefix,
                },
            )
        except Exception:
            pass

        # C5: Dispatch webhook notification to sister domain.
        try:
            from common.webhooks import dispatch_credential_webhook
            dispatch_credential_webhook(
                event_type="credential.rotated",
                credential=new_credential,
                old_prefix=old_credential.api_key_prefix,
                new_prefix=new_prefix,
            )
        except Exception:
            pass

        return {
            "id": new_credential.id,
            "name": new_credential.name,
            "old_prefix": old_credential.api_key_prefix,
            "new_api_key": new_raw,
            "new_prefix": new_prefix,
            "service_domain_id": domain.id,
            "service_domain": domain.domain,
            "is_active": True,
            "warning": (
                "Save this new API key now. The old key is immediately "
                "revoked and cannot be recovered."
            ),
        }

    # =========================================================================
    # C6 — Analytics endpoints
    # =========================================================================

    @http_get(
        "/analytics",
        response=ApiKeyAnalyticsOverviewSchema,
        summary="API key analytics overview",
        description=(
            "Get aggregated API key usage statistics across all credentials "
            "for the last N days. Uses Redis counters for real-time data."
        ),
    )
    @_admin_read_rate_limit
    async def analytics_overview(
        self,
        request: HttpRequest,
        days: int = Query(7, ge=1, le=90),
    ):
        """Return aggregated usage stats across all credentials."""
        from common.analytics import get_all_usage_stats

        all_stats = await sync_to_async(get_all_usage_stats)(days=days)
        total = sum(all_stats.values())

        return {
            "total_requests": total,
            "period_days": days,
            "credentials": all_stats,
        }

    @http_get(
        "/{key_id}/analytics",
        response=ApiKeyAnalyticsResponse,
        summary="Single credential analytics",
        description=(
            "Get daily API key usage statistics for a specific credential. "
            "Returns daily request counts for the last N days."
        ),
    )
    @_admin_read_rate_limit
    async def credential_analytics(
        self,
        request: HttpRequest,
        key_id: int,
        days: int = Query(30, ge=1, le=90),
    ):
        """Return daily usage stats for a single credential."""
        try:
            credential = await sync_to_async(
                ServiceCredential.objects.select_related("service_domain").get
            )(id=key_id)
        except ServiceCredential.DoesNotExist:
            raise NotFoundException("API key not found.")

        from common.analytics import get_usage_stats

        daily = await sync_to_async(get_usage_stats)(
            credential_id=credential.id, days=days
        )
        total = sum(d["requests"] for d in daily)

        return {
            "credential_id": credential.id,
            "api_key_prefix": credential.api_key_prefix,
            "service_domain": credential.service_domain.domain,
            "period_days": days,
            "total_requests": total,
            "daily_usage": daily,
        }
