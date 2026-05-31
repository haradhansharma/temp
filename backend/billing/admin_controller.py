"""Admin controller for product, domain, plan, access entry, and refund management (Phase 9.2–9.6).

Provides admin-only CRUD endpoints for products, service domains, plans,
access entries, and refunds. All endpoints require ``is_staff=True`` and
every mutation is audit-logged via the ``@log_admin_access`` decorator.

Endpoints:
    Products (9.2):
        POST   /admin/products                  — create product
        GET    /admin/products                  — list with annotated counts
        GET    /admin/products/{id}             — detail with plans + domains
        PUT    /admin/products/{id}             — update product
        PATCH  /admin/products/{id}/toggle      — activate/deactivate
        DELETE /admin/products/{id}             — soft-delete

    Service Domains (9.2):
        POST   /admin/products/{product_id}/domains  — create domain
        PUT    /admin/domains/{id}                   — update domain
        DELETE /admin/domains/{id}                   — remove domain

    Plans (9.3):
        POST   /admin/products/{product_id}/plans  — create plan
        GET    /admin/products/{product_id}/plans  — list plans for product
        GET    /admin/plans/{id}                   — plan detail with access entries
        PUT    /admin/plans/{id}                   — update plan
        PATCH  /admin/plans/{id}/toggle            — toggle is_active
        PATCH  /admin/plans/{id}/feature           — toggle is_featured
        POST   /admin/plans/{id}/duplicate         — duplicate plan
        DELETE /admin/plans/{id}                   — delete plan

    Access Entries (9.3):
        POST   /admin/plans/{plan_id}/access-entries       — create entry
        PUT    /admin/access-entries/{id}                  — update entry
        DELETE /admin/access-entries/{id}                  — remove entry
        POST   /admin/plans/{plan_id}/access-entries/bulk  — bulk replace
        GET    /admin/products/{product_id}/access-matrix  — feature matrix
        PUT    /admin/products/{product_id}/access-matrix/row — atomic row save

    Refunds (9.6):
        GET    /admin/refunds                   — list refunds (filterable)
        PATCH  /admin/refunds/{id}/approve     — approve pending refund
        PATCH  /admin/refunds/{id}/reject      — reject pending refund
"""

import logging
from datetime import datetime
from django.utils import timezone as django_timezone
from typing import Optional

from django.db import transaction
from django.db.models import Count, Max, Q
from django.http import HttpRequest
from django.utils.text import slugify
from asgiref.sync import sync_to_async

from ninja import Query
from ninja_extra import api_controller, http_get, http_post, http_put, http_patch, http_delete

from common.exceptions import (
    NotFoundException,
    BadRequestException,
    ConflictException,
)
from common.permissions import IsAuthenticated, IsAdmin
from common.schemas import MessageResponse, PaginatedResponse, PaginationInput

from users.controllers import JWTAuth

from .models import (
    Product,
    ServiceDomain,
    Plan,
    AccessEntry,
    AccessValueType,
    Subscription,
    SubscriptionStatus,
    Refund,
    RefundStatus,
    CreditPool,
    CreditInvoice,
    CreditTransaction,
)
from .admin_schemas import (
    AdminProductCreateSchema,
    AdminProductUpdateSchema,
    AdminProductListItemSchema,
    AdminProductDetailSchema,
    AdminDomainCreateSchema,
    AdminDomainUpdateSchema,
    AdminPlanCreateSchema,
    AdminPlanUpdateSchema,
    AdminPlanListItemSchema,
    AdminPlanDetailSchema,
    AdminPlanDuplicateSchema,
    AdminAccessEntryCreateSchema,
    AdminAccessEntryUpdateSchema,
    AdminAccessEntryBulkSchema,
    AdminAccessMatrixSchema,
    AdminAccessMatrixRowSaveSchema,
    AdminRefundListItemSchema,
    AdminRefundDetailSchema,
    AdminRefundApprovalSchema,
    AdminCreditPurchaseSchema,
    AdminCreditRefundSchema,
    AdminCreditAdjustSchema,
)
from .admin_utils import log_admin_access, admin_write_rate_limit, admin_read_rate_limit
from .services import BillingService

logger = logging.getLogger(__name__)


# =============================================================================
# Admin Controller — Products & Domains
# =============================================================================


@api_controller(
    "/admin",
    tags=["Admin — Products & Domains"],
    auth=JWTAuth(),
    permissions=[IsAuthenticated, IsAdmin],
)
class AdminProductController:
    """Admin endpoints for managing products and service domains.

    All endpoints require JWT authentication with staff privileges.
    Every mutation is audit-logged via the ``@log_admin_access`` decorator.
    """

    # =========================================================================
    # Product Management
    # =========================================================================

    @http_post(
        "/products",
        response={200: dict, 400: dict, 409: dict},
        summary="Create product",
        description=(
            "Create a new product with optional slug auto-generation. "
            "Validates unique name and slug constraints."
        ),
    )
    @admin_write_rate_limit
    @log_admin_access
    async def create_product(
        self,
        request: HttpRequest,
        payload: AdminProductCreateSchema,
    ):
        """Create a new product.

        Auto-generates slug from name if not provided. Validates uniqueness
        of both name and slug before creation.
        """
        slug = payload.slug or slugify(payload.name)

        # Check uniqueness
        exists = await sync_to_async(
            Product.objects.filter(Q(name=payload.name) | Q(slug=slug)).exists
        )()
        if exists:
            raise ConflictException(
                "A product with this name or slug already exists."
            )

        product = await sync_to_async(Product.objects.create)(
            name=payload.name,
            slug=slug,
            description=payload.description,
            home_url=payload.home_url,
        )

        logger.info(
            "ADMIN_PRODUCT_CREATED: product_id=%s, name='%s', slug='%s', "
            "created_by=%s, ip=%s",
            product.id,
            product.name,
            product.slug,
            request.user.email,
            request.META.get("REMOTE_ADDR"),
        )

        return {
            "id": product.id,
            "name": product.name,
            "slug": product.slug,
            "description": product.description,
            "home_url": product.home_url,
            "is_active": product.is_active,
            "stripe_product_id": product.stripe_product_id,
            "created_at": product.created_at,
            "updated_at": product.updated_at,
        }

    @http_get(
        "/products",
        response=PaginatedResponse[AdminProductListItemSchema],
        summary="List products",
        description=(
            "List all products with annotated plan/subscriber/domain counts. "
            "Supports ?is_active= and ?search= (name/slug) filters."
        ),
    )
    async def list_products(
        self,
        request: HttpRequest,
        is_active: Optional[bool] = None,
        search: Optional[str] = None,
        pagination: PaginationInput = Query(...),
    ):
        """List all products with annotated counts.

        Returns plan_count, active_plan_count, subscriber_count, and
        domain_count for each product. Supports filtering by active status
        and searching by name or slug.
        """
        qs = (
            Product.objects.annotate(
                plan_count=Count("plans", distinct=True),
                active_plan_count=Count(
                    "plans", filter=Q(plans__is_active=True), distinct=True
                ),
                domain_count=Count("service_domains", distinct=True),
            )
            .order_by("name")
        )

        if is_active is not None:
            qs = qs.filter(is_active=is_active)

        if search:
            qs = qs.filter(
                Q(name__icontains=search) | Q(slug__icontains=search)
            )

        from common.utils import get_paginated_data_async

        results, meta = await get_paginated_data_async(
            qs, pagination.page, pagination.page_size
        )

        # Annotate subscriber counts for the paginated results
        items = []
        for product in results:
            subscriber_count = await sync_to_async(
                lambda pid: Subscription.objects.filter(
                    product_id=pid,
                    status__in=(
                        SubscriptionStatus.ACTIVE,
                        SubscriptionStatus.TRIALING,
                    ),
                ).count()
            )(product.id)

            items.append({
                "id": product.id,
                "name": product.name,
                "slug": product.slug,
                "description": product.description,
                "home_url": product.home_url,
                "is_active": product.is_active,
                "created_at": product.created_at,
                "updated_at": product.updated_at,
                "plan_count": product.plan_count,
                "active_plan_count": product.active_plan_count,
                "subscriber_count": subscriber_count,
                "domain_count": product.domain_count,
                "stripe_product_id": product.stripe_product_id,
            })

        return {"meta": meta, "results": items}

    @http_get(
        "/products/{product_id}",
        response={200: AdminProductDetailSchema, 404: dict},
        summary="Get product detail",
        description=(
            "Return full product detail with all plans and service domains. "
            "Includes annotated subscriber counts per plan."
        ),
    )
    async def get_product_detail(
        self,
        request: HttpRequest,
        product_id: int,
    ):
        """Get product detail with plans and domains.

        Prefetches plans (with subscriber counts) and service domains
        for the admin detail view.
        """
        try:
            product = await sync_to_async(
                lambda: Product.objects.annotate(
                    plan_count=Count("plans", distinct=True),
                    active_plan_count=Count(
                        "plans", filter=Q(plans__is_active=True), distinct=True
                    ),
                    domain_count=Count("service_domains", distinct=True),
                ).get(pk=product_id)
            )()
        except Product.DoesNotExist:
            raise NotFoundException("Product not found.")

        # Get plans with subscriber counts
        plans_qs = Plan.objects.filter(product=product).order_by(
            "sort_order", "price_cents"
        )
        plans = [p async for p in plans_qs.aiterator()]

        plan_data = []
        for plan in plans:
            subscriber_count = await sync_to_async(
                lambda pid: Subscription.objects.filter(
                    plan_id=pid,
                    status__in=(
                        SubscriptionStatus.ACTIVE,
                        SubscriptionStatus.TRIALING,
                    ),
                ).count()
            )(plan.id)

            plan_data.append({
                "id": plan.id,
                "name": plan.name,
                "slug": plan.slug,
                "description": plan.description,
                "price_cents": plan.price_cents,
                "currency": plan.currency,
                "billing_cycle": plan.billing_cycle,
                "trial_days": plan.trial_days,
                "features": plan.features,
                "sort_order": plan.sort_order,
                "is_active": plan.is_active,
                "is_featured": plan.is_featured,
                "display_price": plan.display_price,
                "is_free": plan.is_free,
                "product_id": product.id,
                "product_name": product.name,
                "subscriber_count": subscriber_count,
                "stripe_price_id": plan.stripe_price_id,
                "tax_inclusive": plan.tax_inclusive,
            })

        # Get service domains
        domains_qs = ServiceDomain.objects.filter(product=product).order_by(
            "-is_primary", "domain"
        )
        domains = [
            {
                "id": d.id,
                "domain": d.domain,
                "product_id": d.product_id,
                "is_primary": d.is_primary,
                "is_active": d.is_active,
            }
            async for d in domains_qs
        ]

        # Total subscriber count
        total_subscribers = await sync_to_async(
            lambda: Subscription.objects.filter(
                product=product,
                status__in=(
                    SubscriptionStatus.ACTIVE,
                    SubscriptionStatus.TRIALING,
                ),
            ).count()
        )()

        return {
            "id": product.id,
            "name": product.name,
            "slug": product.slug,
            "description": product.description,
            "home_url": product.home_url,
            "is_active": product.is_active,
            "created_at": product.created_at,
            "updated_at": product.updated_at,
            "plan_count": product.plan_count,
            "active_plan_count": product.active_plan_count,
            "subscriber_count": total_subscribers,
            "domain_count": product.domain_count,
            "stripe_product_id": product.stripe_product_id,
            "plans": plan_data,
            "service_domains": domains,
        }

    @http_put(
        "/products/{product_id}",
        response={200: dict, 400: dict, 404: dict, 409: dict},
        summary="Update product",
        description=(
            "Update product fields. Only provided fields are modified. "
            "Name and slug changes validate uniqueness."
        ),
    )
    @admin_write_rate_limit
    @log_admin_access
    async def update_product(
        self,
        request: HttpRequest,
        product_id: int,
        payload: AdminProductUpdateSchema,
    ):
        """Update an existing product.

        Partial update — only fields present in the payload are modified.
        Validates name/slug uniqueness if those fields are being changed.
        """
        try:
            product = await sync_to_async(Product.objects.get)(pk=product_id)
        except Product.DoesNotExist:
            raise NotFoundException("Product not found.")

        update_fields = ["updated_at"]

        if payload.name is not None:
            if payload.name != product.name:
                exists = await sync_to_async(
                    Product.objects.filter(name=payload.name)
                    .exclude(pk=product_id)
                    .exists
                )()
                if exists:
                    raise ConflictException(
                        "A product with this name already exists."
                    )
            product.name = payload.name
            update_fields.append("name")

        if payload.slug is not None:
            if payload.slug != product.slug:
                exists = await sync_to_async(
                    Product.objects.filter(slug=payload.slug)
                    .exclude(pk=product_id)
                    .exists
                )()
                if exists:
                    raise ConflictException(
                        "A product with this slug already exists."
                    )
            product.slug = payload.slug
            update_fields.append("slug")

        if payload.description is not None:
            product.description = payload.description
            update_fields.append("description")

        if payload.home_url is not None:
            product.home_url = payload.home_url
            update_fields.append("home_url")

        if payload.is_active is not None:
            product.is_active = payload.is_active
            update_fields.append("is_active")

        await sync_to_async(product.save)(update_fields=update_fields)

        logger.info(
            "ADMIN_PRODUCT_UPDATED: product_id=%s, fields=%s, "
            "updated_by=%s, ip=%s",
            product.id,
            update_fields,
            request.user.email,
            request.META.get("REMOTE_ADDR"),
        )

        return {
            "id": product.id,
            "name": product.name,
            "slug": product.slug,
            "description": product.description,
            "home_url": product.home_url,
            "is_active": product.is_active,
            "stripe_product_id": product.stripe_product_id,
            "created_at": product.created_at,
            "updated_at": product.updated_at,
        }

    @http_patch(
        "/products/{product_id}/toggle",
        response={200: MessageResponse, 400: dict, 404: dict},
        summary="Toggle product active status",
        description=(
            "Activate or deactivate a product. Rejects deactivation if the "
            "product has any active subscriptions."
        ),
    )
    @admin_write_rate_limit
    @log_admin_access
    async def toggle_product(
        self,
        request: HttpRequest,
        product_id: int,
    ):
        """Toggle the is_active flag on a product.

        Prevents deactivation if the product has any active or trialing
        subscriptions — those users would lose access without warning.
        """
        try:
            product = await sync_to_async(Product.objects.get)(pk=product_id)
        except Product.DoesNotExist:
            raise NotFoundException("Product not found.")

        new_state = not product.is_active

        # Prevent deactivation if active subscriptions exist
        if not new_state:
            active_count = await sync_to_async(
                Subscription.objects.filter(
                    product=product,
                    status__in=(
                        SubscriptionStatus.ACTIVE,
                        SubscriptionStatus.TRIALING,
                    ),
                ).count
            )()
            if active_count > 0:
                raise BadRequestException(
                    f"Cannot deactivate product '{product.name}' — it has "
                    f"{active_count} active subscription(s). Cancel or migrate "
                    f"them first."
                )

        product.is_active = new_state
        await sync_to_async(product.save)(update_fields=["is_active", "updated_at"])

        state_label = "activated" if new_state else "deactivated"
        logger.info(
            "ADMIN_PRODUCT_TOGGLED: product_id=%s, name='%s', state=%s, "
            "toggled_by=%s, ip=%s",
            product.id,
            product.name,
            state_label,
            request.user.email,
            request.META.get("REMOTE_ADDR"),
        )

        return MessageResponse(
            message=f"Product '{product.name}' has been {state_label}."
        )

    @http_delete(
        "/products/{product_id}",
        response={200: MessageResponse, 400: dict, 404: dict},
        summary="Delete product",
        description=(
            "Soft-delete a product by setting is_active=False. "
            "Rejects deletion if any active subscriptions exist."
        ),
    )
    @admin_write_rate_limit
    @log_admin_access
    async def delete_product(
        self,
        request: HttpRequest,
        product_id: int,
    ):
        """Soft-delete a product.

        Sets is_active=False. The product and its data are preserved in the
        database for audit and recovery purposes. Rejects deletion if any
        active or trialing subscriptions exist.
        """
        try:
            product = await sync_to_async(Product.objects.get)(pk=product_id)
        except Product.DoesNotExist:
            raise NotFoundException("Product not found.")

        if not product.is_active:
            raise BadRequestException(
                f"Product '{product.name}' is already inactive."
            )

        # Check for active subscriptions
        active_count = await sync_to_async(
            Subscription.objects.filter(
                product=product,
                status__in=(
                    SubscriptionStatus.ACTIVE,
                    SubscriptionStatus.TRIALING,
                ),
            ).count
        )()
        if active_count > 0:
            raise BadRequestException(
                f"Cannot delete product '{product.name}' — it has "
                f"{active_count} active subscription(s). Cancel or migrate "
                f"them first."
            )

        product.is_active = False
        await sync_to_async(product.save)(update_fields=["is_active", "updated_at"])

        logger.info(
            "ADMIN_PRODUCT_DELETED: product_id=%s, name='%s', slug='%s', "
            "deleted_by=%s, ip=%s",
            product.id,
            product.name,
            product.slug,
            request.user.email,
            request.META.get("REMOTE_ADDR"),
        )

        return MessageResponse(
            message=f"Product '{product.name}' has been soft-deleted."
        )

    # =========================================================================
    # Service Domain Management
    # =========================================================================

    @http_post(
        "/products/{product_id}/domains",
        response={200: dict, 400: dict, 404: dict, 409: dict},
        summary="Add service domain",
        description=(
            "Create a new service domain for a product. "
            "Auto-sets is_primary=True if this is the first domain for the product."
        ),
    )
    @admin_write_rate_limit
    @log_admin_access
    async def create_domain(
        self,
        request: HttpRequest,
        product_id: int,
        payload: AdminDomainCreateSchema,
    ):
        """Create a new service domain for a product.

        Validates that the product exists, the domain is unique, and
        auto-sets is_primary=True if this is the first domain for the product.
        """
        try:
            product = await sync_to_async(Product.objects.get)(pk=product_id)
        except Product.DoesNotExist:
            raise NotFoundException("Product not found.")

        # Check domain uniqueness
        exists = await sync_to_async(
            ServiceDomain.objects.filter(domain=payload.domain).exists
        )()
        if exists:
            raise ConflictException(
                f"A service domain with '{payload.domain}' already exists."
            )

        # Determine is_primary: True if this is the first domain for the product
        domain_count = await sync_to_async(
            ServiceDomain.objects.filter(product=product).count
        )()
        is_primary = payload.is_primary or (domain_count == 0)

        # If setting as primary, unset any existing primary
        if is_primary:
            await sync_to_async(
                ServiceDomain.objects.filter(
                    product=product, is_primary=True
                ).update
            )(is_primary=False)

        domain = await sync_to_async(ServiceDomain.objects.create)(
            product=product,
            domain=payload.domain,
            is_primary=is_primary,
        )

        logger.info(
            "ADMIN_DOMAIN_CREATED: domain_id=%s, domain='%s', product='%s', "
            "is_primary=%s, created_by=%s, ip=%s",
            domain.id,
            domain.domain,
            product.name,
            is_primary,
            request.user.email,
            request.META.get("REMOTE_ADDR"),
        )

        return {
            "id": domain.id,
            "domain": domain.domain,
            "product_id": domain.product_id,
            "is_primary": domain.is_primary,
            "is_active": domain.is_active,
            "created_at": domain.created_at,
            "updated_at": domain.updated_at,
        }

    @http_put(
        "/domains/{domain_id}",
        response={200: dict, 400: dict, 404: dict, 409: dict},
        summary="Update service domain",
        description=(
            "Update a service domain. Supports changing the domain URL, "
            "toggling is_primary (only one primary per product), "
            "and toggling is_active."
        ),
    )
    @admin_write_rate_limit
    @log_admin_access
    async def update_domain(
        self,
        request: HttpRequest,
        domain_id: int,
        payload: AdminDomainUpdateSchema,
    ):
        """Update an existing service domain.

        Handles primary domain uniqueness: when setting a domain as primary,
        automatically unsets the previous primary for the same product.
        Validates domain uniqueness if the domain URL is being changed.
        """
        try:
            domain = await sync_to_async(
                ServiceDomain.objects.select_related("product").get
            )(pk=domain_id)
        except ServiceDomain.DoesNotExist:
            raise NotFoundException("Service domain not found.")

        update_fields = []

        if payload.domain is not None:
            if payload.domain != domain.domain:
                # Check uniqueness
                exists = await sync_to_async(
                    ServiceDomain.objects.filter(domain=payload.domain)
                    .exclude(pk=domain_id)
                    .exists
                )()
                if exists:
                    raise ConflictException(
                        f"A service domain with '{payload.domain}' already exists."
                    )
            domain.domain = payload.domain
            update_fields.append("domain")

        if payload.is_primary is not None:
            if payload.is_primary and not domain.is_primary:
                # Unset existing primary for this product
                await sync_to_async(
                    ServiceDomain.objects.filter(
                        product=domain.product, is_primary=True
                    ).exclude(pk=domain_id).update
                )(is_primary=False)
            domain.is_primary = payload.is_primary
            update_fields.append("is_primary")

        if payload.is_active is not None:
            domain.is_active = payload.is_active
            update_fields.append("is_active")

        if update_fields:
            update_fields.append("updated_at")
            await sync_to_async(domain.save)(update_fields=update_fields)

        logger.info(
            "ADMIN_DOMAIN_UPDATED: domain_id=%s, domain='%s', fields=%s, "
            "updated_by=%s, ip=%s",
            domain.id,
            domain.domain,
            update_fields,
            request.user.email,
            request.META.get("REMOTE_ADDR"),
        )

        return {
            "id": domain.id,
            "domain": domain.domain,
            "product_id": domain.product_id,
            "is_primary": domain.is_primary,
            "is_active": domain.is_active,
            "created_at": domain.created_at,
            "updated_at": domain.updated_at,
        }

    @http_delete(
        "/domains/{domain_id}",
        response={200: MessageResponse, 400: dict, 404: dict},
        summary="Delete service domain",
        description=(
            "Remove a service domain. Prevents deleting the primary domain "
            "if other domains exist for the same product."
        ),
    )
    @admin_write_rate_limit
    @log_admin_access
    async def delete_domain(
        self,
        request: HttpRequest,
        domain_id: int,
    ):
        """Delete a service domain.

        Prevents deleting the primary domain if other domains exist for
        the same product — every product should always have a primary domain.
        """
        try:
            domain = await sync_to_async(
                ServiceDomain.objects.select_related("product").get
            )(pk=domain_id)
        except ServiceDomain.DoesNotExist:
            raise NotFoundException("Service domain not found.")

        # Prevent deleting primary domain if other domains exist
        if domain.is_primary:
            other_count = await sync_to_async(
                ServiceDomain.objects.filter(
                    product=domain.product
                )
                .exclude(pk=domain_id)
                .count
            )()
            if other_count > 0:
                raise BadRequestException(
                    f"Cannot delete the primary domain '{domain.domain}' — "
                    f"set another domain as primary first. "
                    f"({other_count} other domain(s) exist for "
                    f"'{domain.product.name}'.)"
                )

        domain_name = domain.domain
        await sync_to_async(domain.delete)()

        logger.info(
            "ADMIN_DOMAIN_DELETED: domain_id=%s, domain='%s', "
            "product='%s', deleted_by=%s, ip=%s",
            domain_id,
            domain_name,
            domain.product.name,
            request.user.email,
            request.META.get("REMOTE_ADDR"),
        )

        return MessageResponse(
            message=f"Service domain '{domain_name}' has been removed."
        )


# =============================================================================
# Admin Controller — Plans
# =============================================================================


@api_controller(
    "/admin",
    tags=["Admin — Plans & Access Entries"],
    auth=JWTAuth(),
    permissions=[IsAuthenticated, IsAdmin],
)
class AdminPlanController:
    """Admin endpoints for managing plans and their access entries.

    All endpoints require JWT authentication with staff privileges.
    Every mutation is audit-logged via the ``@log_admin_access`` decorator.
    """

    # =========================================================================
    # Helper: get plan with product and subscriber count
    # =========================================================================

    async def _get_plan_or_404(self, plan_id: int) -> Plan:
        """Fetch a plan by ID or raise NotFoundException."""
        try:
            return await sync_to_async(
                Plan.objects.select_related("product").get
            )(pk=plan_id)
        except Plan.DoesNotExist:
            raise NotFoundException("Plan not found.")

    async def _get_subscriber_count(self, plan_id: int) -> int:
        """Count active + trialing subscriptions for a plan."""
        return await sync_to_async(
            Subscription.objects.filter(
                plan_id=plan_id,
                status__in=(
                    SubscriptionStatus.ACTIVE,
                    SubscriptionStatus.TRIALING,
                ),
            ).count
        )()

    async def _serialize_plan_list_item(self, plan: Plan) -> dict:
        """Serialize a plan for admin list view with subscriber count."""
        subscriber_count = await self._get_subscriber_count(plan.id)
        return {
            "id": plan.id,
            "name": plan.name,
            "slug": plan.slug,
            "description": plan.description,
            "price_cents": plan.price_cents,
            "currency": plan.currency,
            "billing_cycle": plan.billing_cycle,
            "trial_days": plan.trial_days,
            "features": plan.features,
            "sort_order": plan.sort_order,
            "is_active": plan.is_active,
            "is_featured": plan.is_featured,
            "display_price": plan.display_price,
            "is_free": plan.is_free,
            "product_id": plan.product_id,
            "product_name": plan.product.name,
            "subscriber_count": subscriber_count,
            "stripe_price_id": plan.stripe_price_id,
            "tax_inclusive": plan.tax_inclusive,
        }

    async def _serialize_plan_detail(self, plan: Plan) -> dict:
        """Serialize a plan for admin detail view with access entries."""
        data = await self._serialize_plan_list_item(plan)

        # Prefetch access entries (include id and value_type for admin CRUD)
        entries_qs = AccessEntry.objects.filter(plan=plan).order_by("key")
        entries = [
            {
                "id": e.id,
                "key": e.key,
                "value": e.value,
                "value_type": e.value_type,
                "description": e.description,
                "plan_id": e.plan_id,
                "plan_name": plan.name,
            }
            async for e in entries_qs
        ]
        data["access_entries"] = entries

        return data

    # =========================================================================
    # Plan CRUD
    # =========================================================================

    @http_post(
        "/products/{product_id}/plans",
        response={200: dict, 400: dict, 404: dict, 409: dict},
        summary="Create plan",
        description=(
            "Create a new plan under a product. Auto-generates slug from name "
            "if not provided. Validates unique (product, slug). Sets default "
            "sort_order to max + 1."
        ),
    )
    @admin_write_rate_limit
    @log_admin_access
    async def create_plan(
        self,
        request: HttpRequest,
        product_id: int,
        payload: AdminPlanCreateSchema,
    ):
        """Create a new plan for a product.

        Auto-generates slug from name if not provided. Validates that the
        (product, slug) pair is unique. Defaults sort_order to the next
        available value (current max + 1).
        """
        # Validate product exists
        try:
            product = await sync_to_async(Product.objects.get)(pk=product_id)
        except Product.DoesNotExist:
            raise NotFoundException("Product not found.")

        # Auto-generate slug
        slug = payload.slug or slugify(payload.name)

        # Validate unique (product, slug)
        exists = await sync_to_async(
            Plan.objects.filter(product=product, slug=slug).exists
        )()
        if exists:
            raise ConflictException(
                f"A plan with slug '{slug}' already exists for product "
                f"'{product.name}'."
            )

        # Default sort_order: max + 1
        max_sort = await sync_to_async(
            lambda: Plan.objects.filter(product=product).aggregate(
                m=Max("sort_order")
            )["m"]
        )()
        sort_order = payload.sort_order if payload.sort_order > 0 else (max_sort + 1 if max_sort is not None else 0)

        plan = await sync_to_async(Plan.objects.create)(
            product=product,
            name=payload.name,
            slug=slug,
            description=payload.description,
            price_cents=payload.price_cents,
            currency=payload.currency,
            billing_cycle=payload.billing_cycle,
            trial_days=payload.trial_days,
            features=payload.features,
            sort_order=sort_order,
            is_active=payload.is_active,
            is_featured=payload.is_featured,
            tax_inclusive=payload.tax_inclusive,
        )

        logger.info(
            "ADMIN_PLAN_CREATED: plan_id=%s, name='%s', slug='%s', "
            "product='%s' (id=%s), created_by=%s, ip=%s",
            plan.id,
            plan.name,
            plan.slug,
            product.name,
            product.id,
            request.user.email,
            request.META.get("REMOTE_ADDR"),
        )

        return {
            "id": plan.id,
            "name": plan.name,
            "slug": plan.slug,
            "description": plan.description,
            "price_cents": plan.price_cents,
            "currency": plan.currency,
            "billing_cycle": plan.billing_cycle,
            "trial_days": plan.trial_days,
            "features": plan.features,
            "sort_order": plan.sort_order,
            "is_active": plan.is_active,
            "is_featured": plan.is_featured,
            "display_price": plan.display_price,
            "is_free": plan.is_free,
            "product_id": plan.product_id,
            "product_name": product.name,
            "subscriber_count": 0,
            "stripe_price_id": plan.stripe_price_id,
            "tax_inclusive": plan.tax_inclusive,
            "created_at": plan.created_at,
            "updated_at": plan.updated_at,
        }

    @http_get(
        "/products/{product_id}/plans",
        response=PaginatedResponse[AdminPlanListItemSchema],
        summary="List plans for product",
        description=(
            "List all plans for a product ordered by sort_order. "
            "Includes access entries via prefetch and subscriber counts. "
            "Paginated (default 20, max 100 per page)."
        ),
    )
    async def list_product_plans(
        self,
        request: HttpRequest,
        product_id: int,
        pagination: PaginationInput = Query(...),
    ):
        """List all plans for a product with subscriber counts.

        Returns plans ordered by sort_order, then price_cents. Each plan
        includes its subscriber count and product context. Paginated.
        """
        # Validate product exists
        try:
            product = await sync_to_async(Product.objects.get)(pk=product_id)
        except Product.DoesNotExist:
            raise NotFoundException("Product not found.")

        plans_qs = Plan.objects.filter(product=product).order_by(
            "sort_order", "price_cents"
        )

        from common.utils import get_paginated_data_async

        results, meta = await get_paginated_data_async(
            plans_qs, pagination.page, pagination.page_size
        )

        items = []
        for plan in results:
            item = await self._serialize_plan_list_item(plan)
            items.append(item)

        return {"meta": meta, "results": items}

    @http_get(
        "/plans/{plan_id}",
        response={200: AdminPlanDetailSchema, 404: dict},
        summary="Get plan detail",
        description=(
            "Return full plan detail with all access entries and "
            "annotated subscriber count."
        ),
    )
    async def get_plan_detail(
        self,
        request: HttpRequest,
        plan_id: int,
    ):
        """Get plan detail with access entries and subscriber count."""
        plan = await self._get_plan_or_404(plan_id)
        return await self._serialize_plan_detail(plan)

    @http_put(
        "/plans/{plan_id}",
        response={200: dict, 400: dict, 404: dict, 409: dict},
        summary="Update plan",
        description=(
            "Update plan fields. Only provided fields are modified. "
            "If price or billing_cycle changes and active subscribers exist, "
            "a warning is included in the response."
        ),
    )
    @admin_write_rate_limit
    @log_admin_access
    async def update_plan(
        self,
        request: HttpRequest,
        plan_id: int,
        payload: AdminPlanUpdateSchema,
    ):
        """Update an existing plan.

        Partial update — only fields present in the payload are modified.
        Validates slug uniqueness within the product. Warns (but does not
        block) if price or billing_cycle changes affect active subscribers.
        """
        plan = await self._get_plan_or_404(plan_id)
        subscriber_count = await self._get_subscriber_count(plan_id)

        update_fields = ["updated_at"]
        warnings = []

        if payload.name is not None:
            plan.name = payload.name
            update_fields.append("name")

        if payload.slug is not None:
            if payload.slug != plan.slug:
                exists = await sync_to_async(
                    Plan.objects.filter(product=plan.product, slug=payload.slug)
                    .exclude(pk=plan_id)
                    .exists
                )()
                if exists:
                    raise ConflictException(
                        f"A plan with slug '{payload.slug}' already exists "
                        f"for product '{plan.product.name}'."
                    )
            plan.slug = payload.slug
            update_fields.append("slug")

        if payload.description is not None:
            plan.description = payload.description
            update_fields.append("description")

        if payload.price_cents is not None:
            if payload.price_cents != plan.price_cents and subscriber_count > 0:
                warnings.append(
                    f"Price changed from {plan.price_cents} to "
                    f"{payload.price_cents} cents. {subscriber_count} active "
                    f"subscriber(s) will be affected at next billing cycle."
                )
            plan.price_cents = payload.price_cents
            update_fields.append("price_cents")

        if payload.currency is not None:
            plan.currency = payload.currency
            update_fields.append("currency")

        if payload.billing_cycle is not None:
            if payload.billing_cycle != plan.billing_cycle and subscriber_count > 0:
                warnings.append(
                    f"Billing cycle changed from '{plan.billing_cycle}' to "
                    f"'{payload.billing_cycle}'. {subscriber_count} active "
                    f"subscriber(s) will be affected at next billing cycle."
                )
            plan.billing_cycle = payload.billing_cycle
            update_fields.append("billing_cycle")

        if payload.trial_days is not None:
            plan.trial_days = payload.trial_days
            update_fields.append("trial_days")

        if payload.features is not None:
            plan.features = payload.features
            update_fields.append("features")

        if payload.sort_order is not None:
            plan.sort_order = payload.sort_order
            update_fields.append("sort_order")

        if payload.is_active is not None:
            plan.is_active = payload.is_active
            update_fields.append("is_active")

        if payload.is_featured is not None:
            plan.is_featured = payload.is_featured
            update_fields.append("is_featured")

        if payload.tax_inclusive is not None:
            plan.tax_inclusive = payload.tax_inclusive
            update_fields.append("tax_inclusive")

        await sync_to_async(plan.save)(update_fields=update_fields)

        logger.info(
            "ADMIN_PLAN_UPDATED: plan_id=%s, name='%s', product='%s', "
            "fields=%s, updated_by=%s, ip=%s",
            plan.id,
            plan.name,
            plan.product.name,
            update_fields,
            request.user.email,
            request.META.get("REMOTE_ADDR"),
        )

        result = {
            "id": plan.id,
            "name": plan.name,
            "slug": plan.slug,
            "description": plan.description,
            "price_cents": plan.price_cents,
            "currency": plan.currency,
            "billing_cycle": plan.billing_cycle,
            "trial_days": plan.trial_days,
            "features": plan.features,
            "sort_order": plan.sort_order,
            "is_active": plan.is_active,
            "is_featured": plan.is_featured,
            "display_price": plan.display_price,
            "is_free": plan.is_free,
            "product_id": plan.product_id,
            "product_name": plan.product.name,
            "subscriber_count": subscriber_count,
            "stripe_price_id": plan.stripe_price_id,
            "tax_inclusive": plan.tax_inclusive,
            "created_at": plan.created_at,
            "updated_at": plan.updated_at,
        }

        if warnings:
            result["warnings"] = warnings

        return result

    @http_patch(
        "/plans/{plan_id}/toggle",
        response={200: MessageResponse, 404: dict},
        summary="Toggle plan active status",
        description="Activate or deactivate a plan. Does not affect existing subscribers.",
    )
    @admin_write_rate_limit
    @log_admin_access
    async def toggle_plan(
        self,
        request: HttpRequest,
        plan_id: int,
    ):
        """Toggle the is_active flag on a plan.

        This controls whether the plan is available for new subscriptions.
        Existing active subscriptions on this plan are not affected.
        """
        plan = await self._get_plan_or_404(plan_id)

        new_state = not plan.is_active
        plan.is_active = new_state
        await sync_to_async(plan.save)(update_fields=["is_active", "updated_at"])

        state_label = "activated" if new_state else "deactivated"
        logger.info(
            "ADMIN_PLAN_TOGGLED: plan_id=%s, name='%s', product='%s', "
            "state=%s, toggled_by=%s, ip=%s",
            plan.id,
            plan.name,
            plan.product.name,
            state_label,
            request.user.email,
            request.META.get("REMOTE_ADDR"),
        )

        return MessageResponse(
            message=f"Plan '{plan.name}' has been {state_label}."
        )

    @http_patch(
        "/plans/{plan_id}/feature",
        response={200: MessageResponse, 404: dict},
        summary="Toggle plan featured status",
        description=(
            "Toggle the is_featured flag on a plan. "
            "Featured plans are highlighted in the comparison UI."
        ),
    )
    @admin_write_rate_limit
    @log_admin_access
    async def toggle_featured(
        self,
        request: HttpRequest,
        plan_id: int,
    ):
        """Toggle the is_featured flag on a plan.

        Featured plans are displayed with visual emphasis in the plan
        comparison UI (banners, highlights, etc.).
        """
        plan = await self._get_plan_or_404(plan_id)

        new_state = not plan.is_featured
        plan.is_featured = new_state
        await sync_to_async(plan.save)(update_fields=["is_featured", "updated_at"])

        state_label = "featured" if new_state else "unfeatured"
        logger.info(
            "ADMIN_PLAN_FEATURED_TOGGLED: plan_id=%s, name='%s', "
            "product='%s', state=%s, toggled_by=%s, ip=%s",
            plan.id,
            plan.name,
            plan.product.name,
            state_label,
            request.user.email,
            request.META.get("REMOTE_ADDR"),
        )

        return MessageResponse(
            message=f"Plan '{plan.name}' has been {state_label}."
        )

    @http_post(
        "/plans/{plan_id}/duplicate",
        response={200: dict, 404: dict},
        summary="Duplicate plan",
        description=(
            "Deep copy a plan including all AccessEntry records. "
            "Appends '(Copy)' to the name and increments sort_order."
        ),
    )
    @admin_write_rate_limit
    @log_admin_access
    async def duplicate_plan(
        self,
        request: HttpRequest,
        plan_id: int,
        payload: AdminPlanDuplicateSchema = None,
    ):
        """Duplicate a plan with all its access entries.

        Creates a new plan with the same settings as the original, plus
        all AccessEntry records. Appends "(Copy)" to the name (or uses
        the provided name). Increments sort_order to place after the
        original.
        """
        plan = await self._get_plan_or_404(plan_id)

        # Determine name for the duplicate
        new_name = (
            payload.name if payload and payload.name else f"{plan.name} (Copy)"
        )

        # Generate a unique slug
        base_slug = slugify(new_name)
        slug = base_slug
        counter = 1
        while await sync_to_async(
            Plan.objects.filter(product=plan.product, slug=slug).exists
        )():
            slug = f"{base_slug}-{counter}"
            counter += 1

        # Increment sort_order
        max_sort = await sync_to_async(
            Plan.objects.filter(product=plan.product).aggregate(
                m=Max("sort_order")
            )["m"]
        )()
        new_sort = (max_sort or plan.sort_order) + 1

        # Create the duplicated plan
        new_plan = await sync_to_async(Plan.objects.create)(
            product=plan.product,
            name=new_name,
            slug=slug,
            description=plan.description,
            price_cents=plan.price_cents,
            currency=plan.currency,
            billing_cycle=plan.billing_cycle,
            trial_days=plan.trial_days,
            features=plan.features.copy() if plan.features else {},
            sort_order=new_sort,
            is_active=False,  # Start inactive — admin should review before enabling
            is_featured=False,
            tax_inclusive=plan.tax_inclusive,
        )

        # Deep copy all access entries
        entries = [
            AccessEntry(
                plan=new_plan,
                key=e.key,
                value=e.value,
                value_type=e.value_type,
                description=e.description,
            )
            async for e in AccessEntry.objects.filter(plan=plan).aiterator()
        ]
        if entries:
            await sync_to_async(AccessEntry.objects.bulk_create)(entries)

        logger.info(
            "ADMIN_PLAN_DUPLICATED: original_id=%s, new_id=%s, "
            "original_name='%s', new_name='%s', product='%s', "
            "entries_copied=%s, duplicated_by=%s, ip=%s",
            plan.id,
            new_plan.id,
            plan.name,
            new_name,
            plan.product.name,
            len(entries),
            request.user.email,
            request.META.get("REMOTE_ADDR"),
        )

        return {
            "id": new_plan.id,
            "name": new_plan.name,
            "slug": new_plan.slug,
            "description": new_plan.description,
            "price_cents": new_plan.price_cents,
            "currency": new_plan.currency,
            "billing_cycle": new_plan.billing_cycle,
            "trial_days": new_plan.trial_days,
            "features": new_plan.features,
            "sort_order": new_plan.sort_order,
            "is_active": new_plan.is_active,
            "is_featured": new_plan.is_featured,
            "display_price": new_plan.display_price,
            "is_free": new_plan.is_free,
            "product_id": new_plan.product_id,
            "product_name": plan.product.name,
            "subscriber_count": 0,
            "stripe_price_id": new_plan.stripe_price_id,
            "tax_inclusive": new_plan.tax_inclusive,
            "access_entries_copied": len(entries),
            "created_at": new_plan.created_at,
            "updated_at": new_plan.updated_at,
        }

    @http_delete(
        "/plans/{plan_id}",
        response={200: MessageResponse, 400: dict, 404: dict},
        summary="Delete plan",
        description=(
            "Delete a plan permanently. Rejects if any Subscription references "
            "this plan (PROTECT FK constraint). Returns a user-friendly error."
        ),
    )
    @admin_write_rate_limit
    @log_admin_access
    async def delete_plan(
        self,
        request: HttpRequest,
        plan_id: int,
    ):
        """Delete a plan permanently.

        The Subscription model has ``on_delete=models.PROTECT`` on the plan
        FK, so Django will raise an IntegrityError if any subscriptions
        reference this plan. We catch that and return a user-friendly error
        message instead of a 500 server error.
        """
        plan = await self._get_plan_or_404(plan_id)

        # Check if any subscriptions reference this plan (before attempting delete)
        sub_count = await sync_to_async(
            Subscription.objects.filter(plan=plan).count
        )()
        if sub_count > 0:
            raise BadRequestException(
                f"Cannot delete plan '{plan.name}' — {sub_count} subscription(s) "
                f"reference this plan. Cancel or migrate them first."
            )

        plan_name = plan.name
        await sync_to_async(plan.delete)()

        logger.info(
            "ADMIN_PLAN_DELETED: plan_id=%s, name='%s', product='%s', "
            "deleted_by=%s, ip=%s",
            plan_id,
            plan_name,
            plan.product.name,
            request.user.email,
            request.META.get("REMOTE_ADDR"),
        )

        return MessageResponse(
            message=f"Plan '{plan_name}' has been deleted."
        )

    # =========================================================================
    # Access Matrix
    # =========================================================================

    @http_get(
        "/products/{product_id}/access-matrix",
        response={200: AdminAccessMatrixSchema, 404: dict},
        summary="Get access matrix",
        description=(
            "Return a 2D feature comparison matrix for all plans in a product. "
            "Rows = unique access keys across all plans. "
            "Columns = plan slugs. Cells = typed values or null."
        ),
    )
    async def get_access_matrix(
        self,
        request: HttpRequest,
        product_id: int,
    ):
        """Get the feature comparison matrix across all plans of a product.

        Returns a 2D grid where each row is a unique access key found in any
        plan, each column is a plan, and each cell contains the typed value
        for that key on that plan (or null if not defined).
        """
        # Validate product exists
        try:
            product = await sync_to_async(Product.objects.get)(pk=product_id)
        except Product.DoesNotExist:
            raise NotFoundException("Product not found.")

        # Get all plans for this product
        plans = [
            p
            async for p in Plan.objects.filter(product=product)
            .order_by("sort_order", "price_cents")
            .aiterator()
        ]

        plan_headers = [
            {"slug": p.slug, "name": p.name, "is_active": p.is_active}
            for p in plans
        ]

        # Collect all access entries for all plans
        all_entries = {}
        for plan in plans:
            entries_qs = AccessEntry.objects.filter(plan=plan).order_by("key")
            async for entry in entries_qs:
                key = entry.key
                if key not in all_entries:
                    all_entries[key] = {
                        "description": entry.description,
                        "values": {},
                        "entry_ids": {},
                    }
                # Only set description from the first plan that defines it
                if not all_entries[key]["description"] and entry.description:
                    all_entries[key]["description"] = entry.description
                all_entries[key]["values"][plan.slug] = entry.value
                all_entries[key]["entry_ids"][plan.slug] = entry.id

        # Build rows sorted by key
        rows = [
            {
                "key": key,
                "description": data["description"],
                "values": data["values"],
                "entry_ids": data["entry_ids"],
            }
            for key, data in sorted(all_entries.items())
        ]

        return {
            "product_id": product.id,
            "product_name": product.name,
            "plans": plan_headers,
            "rows": rows,
        }

    @http_put(
        "/products/{product_id}/access-matrix/row",
        response={200: dict, 400: dict, 404: dict},
        summary="Save access matrix row",
        description=(
            "Atomically save a single access key across all plans of a product. "
            "Creates or updates entries for the listed plans; removes the key "
            "from any plan of the product that is NOT listed. If original_key "
            "is provided and differs from key, all entries with original_key "
            "are renamed first. All operations run in a single database "
            "transaction so the matrix is never left in a partial state."
        ),
    )
    @admin_write_rate_limit
    @log_admin_access
    async def save_access_matrix_row(
        self,
        request: HttpRequest,
        product_id: int,
        payload: AdminAccessMatrixRowSaveSchema,
    ):
        """Atomically save one access key row across all plans of a product.

        This is the primary endpoint for the spreadsheet-like access matrix
        UI.  Instead of making N separate per-plan API calls (which can leave
        the matrix partially saved on failure), the frontend sends a single
        request with the desired state for one key and the backend reconciles
        the database in one transaction.

        Steps (all inside ``transaction.atomic()``):
          1. Validate product exists.
          2. Resolve each ``plan_id`` to a Plan belonging to this product.
          3. If ``original_key`` differs from ``key``, rename all entries.
          4. For each plan listed in ``entries``:
             - If an entry for (plan, key) exists → update it.
             - If not → create it.
          5. For each plan of the product NOT listed in ``entries``:
             - Delete the entry for (plan, key) if it exists.
        """
        # 1. Validate product
        try:
            product = await sync_to_async(Product.objects.get)(pk=product_id)
        except Product.DoesNotExist:
            raise NotFoundException("Product not found.")

        # 2. Validate all plan_ids belong to this product
        plan_ids_in_payload = [e.plan_id for e in payload.entries]
        product_plan_ids = {
            p.id
            async for p in Plan.objects.filter(product=product).only("id").aiterator()
        }
        for pid in plan_ids_in_payload:
            if pid not in product_plan_ids:
                raise BadRequestException(
                    f"Plan id {pid} does not belong to product "
                    f"'{product.name}' (id={product.id})."
                )

        # Validate value_types
        valid_types = set(vt.value for vt in AccessValueType)
        for item in payload.entries:
            if item.value_type not in valid_types:
                raise BadRequestException(
                    f"Invalid value_type '{item.value_type}' for key "
                    f"'{payload.key}'. Must be one of: {', '.join(sorted(valid_types))}."
                )

        target_key = payload.key
        original_key = payload.original_key or target_key
        is_rename = original_key != target_key

        # 3-5. Execute inside a single transaction
        def _do_save():
            with transaction.atomic():
                # 3. Rename if key changed
                if is_rename:
                    # Check new key doesn't collide with existing entries
                    # (for plans that already have the new key)
                    conflicting = AccessEntry.objects.filter(
                        plan__product=product,
                        key=target_key,
                    ).exclude(key=original_key)
                    if conflicting.exists():
                        raise ConflictException(
                            f"Cannot rename '{original_key}' to '{target_key}': "
                            f"an entry with key '{target_key}' already exists "
                            f"for one or more plans."
                        )
                    AccessEntry.objects.filter(
                        plan__product=product, key=original_key
                    ).update(key=target_key)

                # Collect existing entries for this key across all product plans
                existing_qs = AccessEntry.objects.filter(
                    plan__product=product, key=target_key
                ).select_related("plan")
                existing_map = {}  # plan_id → entry
                for entry in existing_qs:
                    existing_map[entry.plan_id] = entry

                # 4. Upsert listed plans
                created_count = 0
                updated_count = 0
                result_entries = []
                for item in payload.entries:
                    entry = existing_map.pop(item.plan_id, None)
                    if entry:
                        # Update existing
                        entry.value = item.value
                        entry.value_type = item.value_type
                        entry.description = payload.description
                        entry.save(update_fields=["value", "value_type", "description"])
                        updated_count += 1
                    else:
                        # Create new
                        entry = AccessEntry(
                            plan_id=item.plan_id,
                            key=target_key,
                            value=item.value,
                            value_type=item.value_type,
                            description=payload.description,
                        )
                        entry.save()
                        created_count += 1
                    result_entries.append({
                        "id": entry.id,
                        "plan_id": entry.plan_id,
                        "key": entry.key,
                        "value": entry.value,
                        "value_type": entry.value_type,
                        "description": entry.description,
                    })

                # 5. Delete entries for plans NOT listed in payload
                deleted_count = 0
                for plan_id, entry in existing_map.items():
                    entry.delete()
                    deleted_count += 1

                return created_count, updated_count, deleted_count, result_entries

        created, updated, deleted, result_entries = await sync_to_async(_do_save)()

        logger.info(
            "ADMIN_ACCESS_MATRIX_ROW_SAVED: product='%s' (id=%s), "
            "key='%s'%s, created=%s, updated=%s, deleted=%s, "
            "saved_by=%s, ip=%s",
            product.name,
            product.id,
            target_key,
            f" (renamed from '{original_key}')" if is_rename else "",
            created,
            updated,
            deleted,
            request.user.email,
            request.META.get("REMOTE_ADDR"),
        )

        return {
            "product_id": product.id,
            "key": target_key,
            "original_key": original_key if is_rename else None,
            "entries_created": created,
            "entries_updated": updated,
            "entries_deleted": deleted,
            "entries": result_entries,
        }

    # =========================================================================
    # Access Entry CRUD
    # =========================================================================

    @http_post(
        "/plans/{plan_id}/access-entries",
        response={200: dict, 400: dict, 404: dict, 409: dict},
        summary="Create access entry",
        description=(
            "Add a single access entry to a plan. "
            "Validates unique (plan, key) constraint."
        ),
    )
    @admin_write_rate_limit
    @log_admin_access
    async def create_access_entry(
        self,
        request: HttpRequest,
        plan_id: int,
        payload: AdminAccessEntryCreateSchema,
    ):
        """Create a single access entry on a plan.

        Validates that the plan exists and the (plan, key) pair is unique.
        Validates that value_type is a known AccessValueType.
        """
        plan = await self._get_plan_or_404(plan_id)

        # Validate value_type
        valid_types = [vt.value for vt in AccessValueType]
        if payload.value_type not in valid_types:
            raise BadRequestException(
                f"Invalid value_type '{payload.value_type}'. "
                f"Must be one of: {', '.join(valid_types)}."
            )

        # Check unique (plan, key)
        exists = await sync_to_async(
            AccessEntry.objects.filter(plan=plan, key=payload.key).exists
        )()
        if exists:
            raise ConflictException(
                f"Access entry with key '{payload.key}' already exists "
                f"for plan '{plan.name}'. Use PUT to update it."
            )

        entry = await sync_to_async(AccessEntry.objects.create)(
            plan=plan,
            key=payload.key,
            value=payload.value,
            value_type=payload.value_type,
            description=payload.description,
        )

        logger.info(
            "ADMIN_ACCESS_ENTRY_CREATED: entry_id=%s, key='%s', "
            "plan='%s' (id=%s), value_type=%s, created_by=%s, ip=%s",
            entry.id,
            entry.key,
            plan.name,
            plan.id,
            entry.value_type,
            request.user.email,
            request.META.get("REMOTE_ADDR"),
        )

        return {
            "id": entry.id,
            "plan_id": plan.id,
            "key": entry.key,
            "value": entry.value,
            "value_type": entry.value_type,
            "description": entry.description,
        }

    @http_put(
        "/access-entries/{entry_id}",
        response={200: dict, 400: dict, 404: dict, 409: dict},
        summary="Update access entry",
        description=(
            "Update an existing access entry. Supports changing key, value, "
            "value_type, and description. Validates key uniqueness within plan."
        ),
    )
    @admin_write_rate_limit
    @log_admin_access
    async def update_access_entry(
        self,
        request: HttpRequest,
        entry_id: int,
        payload: AdminAccessEntryUpdateSchema,
    ):
        """Update an existing access entry.

        Partial update — only provided fields are modified. If the key is
        being changed, validates uniqueness within the same plan.
        """
        try:
            entry = await sync_to_async(
                AccessEntry.objects.select_related("plan").get
            )(pk=entry_id)
        except AccessEntry.DoesNotExist:
            raise NotFoundException("Access entry not found.")

        update_fields = []

        if payload.key is not None:
            if payload.key != entry.key:
                # Check uniqueness within the same plan
                exists = await sync_to_async(
                    AccessEntry.objects.filter(
                        plan=entry.plan, key=payload.key
                    )
                    .exclude(pk=entry_id)
                    .exists
                )()
                if exists:
                    raise ConflictException(
                        f"Access entry with key '{payload.key}' already exists "
                        f"for plan '{entry.plan.name}'."
                    )
            entry.key = payload.key
            update_fields.append("key")

        if payload.value is not None:
            entry.value = payload.value
            update_fields.append("value")

        if payload.value_type is not None:
            valid_types = [vt.value for vt in AccessValueType]
            if payload.value_type not in valid_types:
                raise BadRequestException(
                    f"Invalid value_type '{payload.value_type}'. "
                    f"Must be one of: {', '.join(valid_types)}."
                )
            entry.value_type = payload.value_type
            update_fields.append("value_type")

        if payload.description is not None:
            entry.description = payload.description
            update_fields.append("description")

        if update_fields:
            await sync_to_async(entry.save)(update_fields=update_fields)

        logger.info(
            "ADMIN_ACCESS_ENTRY_UPDATED: entry_id=%s, plan='%s' (id=%s), "
            "fields=%s, updated_by=%s, ip=%s",
            entry.id,
            entry.plan.name,
            entry.plan.id,
            update_fields,
            request.user.email,
            request.META.get("REMOTE_ADDR"),
        )

        return {
            "id": entry.id,
            "plan_id": entry.plan_id,
            "key": entry.key,
            "value": entry.value,
            "value_type": entry.value_type,
            "description": entry.description,
        }

    @http_delete(
        "/access-entries/{entry_id}",
        response={200: MessageResponse, 404: dict},
        summary="Delete access entry",
        description="Remove an access entry from a plan.",
    )
    @admin_write_rate_limit
    @log_admin_access
    async def delete_access_entry(
        self,
        request: HttpRequest,
        entry_id: int,
    ):
        """Delete a single access entry.

        Removes the entry permanently. This immediately affects the access
        map returned by auth/me for all subscribers on this plan.
        """
        try:
            entry = await sync_to_async(
                AccessEntry.objects.select_related("plan").get
            )(pk=entry_id)
        except AccessEntry.DoesNotExist:
            raise NotFoundException("Access entry not found.")

        entry_key = entry.key
        plan_name = entry.plan.name
        plan_id = entry.plan_id
        await sync_to_async(entry.delete)()

        logger.info(
            "ADMIN_ACCESS_ENTRY_DELETED: entry_id=%s, key='%s', "
            "plan='%s' (id=%s), deleted_by=%s, ip=%s",
            entry_id,
            entry_key,
            plan_name,
            plan_id,
            request.user.email,
            request.META.get("REMOTE_ADDR"),
        )

        return MessageResponse(
            message=f"Access entry '{entry_key}' has been removed from "
            f"plan '{plan_name}'."
        )

    @http_post(
        "/plans/{plan_id}/access-entries/bulk",
        response={200: dict, 400: dict, 404: dict},
        summary="Bulk replace access entries",
        description=(
            "Replace all access entries for a plan in a single transaction. "
            "Deletes all existing entries, then creates the provided entries. "
            "Validates value_type for each entry."
        ),
    )
    @admin_write_rate_limit
    @log_admin_access
    async def bulk_set_access_entries(
        self,
        request: HttpRequest,
        plan_id: int,
        payload: AdminAccessEntryBulkSchema,
    ):
        """Bulk replace all access entries on a plan.

        Runs in a single database transaction: deletes all existing entries
        for the plan, then creates the provided entries. This is useful for
        editing access entries in a spreadsheet-like interface and saving
        all changes at once.
        """
        plan = await self._get_plan_or_404(plan_id)

        # Validate all value_types upfront
        valid_types = set(vt.value for vt in AccessValueType)
        for item in payload.entries:
            if item.value_type not in valid_types:
                raise BadRequestException(
                    f"Invalid value_type '{item.value_type}' for key "
                    f"'{item.key}'. Must be one of: {', '.join(sorted(valid_types))}."
                )

        def _do_bulk():
            """Execute the bulk replace in a transaction."""
            with transaction.atomic():
                # Delete all existing entries
                deleted = AccessEntry.objects.filter(plan=plan).delete()
                deleted_count = deleted[0] if deleted else 0

                # Create new entries
                new_entries = [
                    AccessEntry(
                        plan=plan,
                        key=item.key,
                        value=item.value,
                        value_type=item.value_type,
                        description=item.description,
                    )
                    for item in payload.entries
                ]
                if new_entries:
                    AccessEntry.objects.bulk_create(new_entries)

                return deleted_count, len(new_entries)

        deleted_count, created_count = await sync_to_async(_do_bulk)()

        logger.info(
            "ADMIN_ACCESS_ENTRIES_BULK_SET: plan='%s' (id=%s), "
            "deleted=%s, created=%s, set_by=%s, ip=%s",
            plan.name,
            plan.id,
            deleted_count,
            created_count,
            request.user.email,
            request.META.get("REMOTE_ADDR"),
        )

        return {
            "plan_id": plan.id,
            "plan_name": plan.name,
            "entries_deleted": deleted_count,
            "entries_created": created_count,
            "total_entries": created_count,
        }


# =============================================================================
# Admin Controller — Refunds (Phase 9.6)
# =============================================================================


@api_controller(
    "/admin",
    tags=["Admin — Refunds"],
    auth=JWTAuth(),
    permissions=[IsAuthenticated, IsAdmin],
)
class AdminRefundController:
    """Admin endpoints for managing refunds with two-person approval workflow.

    All endpoints require JWT authentication with staff privileges.
    Every mutation is audit-logged via the ``@log_admin_access`` decorator.

    Refunds follow a two-person rule: the admin who initiates a refund
    cannot be the same admin who approves it. This prevents unauthorized
    self-approval of financial transactions.
    """

    # =========================================================================
    # Helper: serialize refund for list/detail views
    # =========================================================================

    async def _serialize_refund_list_item(self, refund: Refund) -> dict:
        """Serialize a refund for admin list view.

        Extracts user email, product name, and plan name from related
        objects pre-fetched via select_related.
        """
        sub = refund.subscription
        user = sub.user if hasattr(sub, "user") else None
        plan = sub.plan if hasattr(sub, "plan") else None
        product = plan.product if plan and hasattr(plan, "product") else None

        return {
            "id": refund.id,
            "subscription_id": refund.subscription_id,
            "user_email": getattr(user, "email", ""),
            "product_name": getattr(product, "name", None),
            "plan_name": getattr(plan, "name", None),
            "stripe_refund_id": refund.stripe_refund_id,
            "stripe_charge_id": refund.stripe_charge_id,
            "amount_cents": refund.amount_cents,
            "currency": refund.currency,
            "reason": refund.reason,
            "status": refund.status,
            "reason_category": refund.reason_category,
            "initiated_by_id": getattr(refund.initiated_by, "id", None),
            "initiated_by_email": (
                getattr(refund.initiated_by, "email", None)
            ),
            "initiated_by_ip": refund.initiated_by_ip,
            "approved_by_id": getattr(refund.approved_by, "id", None),
            "approved_by_email": (
                getattr(refund.approved_by, "email", None)
            ),
            "approved_at": refund.approved_at,
            "admin_notes": refund.admin_notes,
            "created_at": refund.created_at,
            "updated_at": refund.updated_at,
        }

    async def _serialize_refund_detail(self, refund: Refund) -> dict:
        """Serialize a refund with full Stripe response for detail view."""
        data = await self._serialize_refund_list_item(refund)
        data["stripe_response"] = refund.stripe_response or {}
        return data

    async def _get_refund_or_404(self, refund_id: int) -> Refund:
        """Fetch a refund by ID with related objects or raise NotFoundException."""
        try:
            return await sync_to_async(
                Refund.objects.select_related(
                    "subscription__user",
                    "subscription__plan__product",
                    "initiated_by",
                    "approved_by",
                ).get
            )(pk=refund_id)
        except Refund.DoesNotExist:
            raise NotFoundException("Refund not found.")

    # =========================================================================
    # 9.6.1 — List Refunds
    # =========================================================================

    @http_get(
        "/refunds",
        response=PaginatedResponse[AdminRefundListItemSchema],
        summary="List refunds",
        description=(
            "List all refunds with user, product, and approval info. "
            "Supports filtering by status, reason category, subscription ID, "
            "and date range. Paginated."
        ),
    )
    async def list_refunds(
        self,
        request: HttpRequest,
        status: Optional[str] = None,
        reason_category: Optional[str] = None,
        subscription_id: Optional[int] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        pagination: PaginationInput = Query(...),
    ):
        """List all refunds with filters and pagination.

        Returns refunds ordered by most recent first. Supports filtering
        by status (pending, completed, failed), reason category,
        subscription ID, and date range (created_at). Results include
        user email, product name, plan name, and approval details
        via select_related joins.
        """
        qs = Refund.objects.select_related(
            "subscription__user",
            "subscription__plan__product",
            "initiated_by",
            "approved_by",
        ).order_by("-created_at")

        if status:
            qs = qs.filter(status=status)

        if reason_category:
            qs = qs.filter(reason_category=reason_category)

        if subscription_id:
            qs = qs.filter(subscription_id=subscription_id)

        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)

        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)

        from common.utils import get_paginated_data_async

        results, meta = await get_paginated_data_async(
            qs, pagination.page, pagination.page_size
        )

        items = []
        for refund in results:
            item = await self._serialize_refund_list_item(refund)
            items.append(item)

        return {"meta": meta, "results": items}

    # =========================================================================
    # 9.6.2 — Approve Refund
    # =========================================================================

    @http_patch(
        "/refunds/{refund_id}/approve",
        response={200: AdminRefundDetailSchema, 400: dict, 404: dict, 409: dict},
        summary="Approve pending refund",
        description=(
            "Approve a pending refund (two-person rule). The approving admin "
            "cannot be the same person who initiated the refund. Sets "
            "approved_by, approved_at, and status to 'completed'."
        ),
    )
    @admin_write_rate_limit
    @log_admin_access
    async def approve_refund(
        self,
        request: HttpRequest,
        refund_id: int,
        payload: AdminRefundApprovalSchema,
    ):
        """Approve a pending refund.

        Enforces the two-person rule: the admin who approves the refund
        must be a different person from the admin who initiated it. This
        prevents self-approval of financial transactions for PCI-DSS
        compliance.

        On approval, sets approved_by to the current user, records the
        approval timestamp, and transitions the refund status to
        'completed'. Admin notes are appended for audit trail.
        """
        refund = await self._get_refund_or_404(refund_id)

        # Validate status is pending
        if refund.status != RefundStatus.PENDING:
            raise BadRequestException(
                f"Cannot approve refund in '{refund.status}' status. "
                f"Only pending refunds can be approved."
            )

        # Enforce two-person rule
        if (
            refund.initiated_by
            and refund.initiated_by_id == request.user.id
        ):
            raise BadRequestException(
                "Two-person rule violation: the admin who approves a refund "
                "cannot be the same person who initiated it. Another staff "
                "member must perform the approval."
            )

        # Apply approval
        refund.approved_by = request.user
        refund.approved_at = django_timezone.now()
        refund.status = RefundStatus.COMPLETED

        # Append approval notes
        if payload.notes:
            if refund.admin_notes:
                refund.admin_notes += f"\n\n[APPROVAL by {request.user.email}] {payload.notes}"
            else:
                refund.admin_notes = f"[APPROVAL by {request.user.email}] {payload.notes}"

        await sync_to_async(refund.save)(
            update_fields=[
                "approved_by",
                "approved_at",
                "status",
                "admin_notes",
                "updated_at",
            ]
        )

        logger.info(
            "ADMIN_REFUND_APPROVED: refund_id=%s, subscription_id=%s, "
            "amount=%s %s, approved_by=%s (id=%s), initiated_by=%s (id=%s), "
            "ip=%s",
            refund.id,
            refund.subscription_id,
            refund.amount_cents,
            refund.currency,
            request.user.email,
            request.user.id,
            getattr(refund.initiated_by, "email", None),
            getattr(refund.initiated_by, "id", None),
            request.META.get("REMOTE_ADDR"),
        )

        return await self._serialize_refund_detail(refund)

    # =========================================================================
    # 9.6.3 — Reject Refund
    # =========================================================================

    @http_patch(
        "/refunds/{refund_id}/reject",
        response={200: AdminRefundDetailSchema, 400: dict, 404: dict},
        summary="Reject pending refund",
        description=(
            "Reject a pending refund. Sets status to 'failed' and records "
            "the rejection notes for audit trail."
        ),
    )
    @admin_write_rate_limit
    @log_admin_access
    async def reject_refund(
        self,
        request: HttpRequest,
        refund_id: int,
        payload: AdminRefundApprovalSchema,
    ):
        """Reject a pending refund.

        Transitions the refund status from 'pending' to 'failed' and
        records the rejection reason in admin_notes for the audit trail.
        Unlike approval, rejection does not enforce the two-person rule
        since the funds remain with the customer (no financial impact).
        """
        refund = await self._get_refund_or_404(refund_id)

        # Validate status is pending
        if refund.status != RefundStatus.PENDING:
            raise BadRequestException(
                f"Cannot reject refund in '{refund.status}' status. "
                f"Only pending refunds can be rejected."
            )

        # Apply rejection
        refund.status = RefundStatus.FAILED

        # Record rejection notes
        notes = payload.notes or "No reason provided."
        if refund.admin_notes:
            refund.admin_notes += f"\n\n[REJECTED by {request.user.email}] {notes}"
        else:
            refund.admin_notes = f"[REJECTED by {request.user.email}] {notes}"

        await sync_to_async(refund.save)(
            update_fields=[
                "status",
                "admin_notes",
                "updated_at",
            ]
        )

        logger.info(
            "ADMIN_REFUND_REJECTED: refund_id=%s, subscription_id=%s, "
            "amount=%s %s, rejected_by=%s (id=%s), initiated_by=%s (id=%s), "
            "notes='%s', ip=%s",
            refund.id,
            refund.subscription_id,
            refund.amount_cents,
            refund.currency,
            request.user.email,
            request.user.id,
            getattr(refund.initiated_by, "email", None),
            getattr(refund.initiated_by, "id", None),
            notes[:100],  # Truncate for log readability
            request.META.get("REMOTE_ADDR"),
        )

        return await self._serialize_refund_detail(refund)


# =============================================================================
# Admin Controller — Credit Pool Management
# =============================================================================


@api_controller(
    "/admin",
    tags=["Admin — Credits"],
    auth=JWTAuth(),
    permissions=[IsAuthenticated, IsAdmin],
)
class AdminCreditController:
    """Admin endpoints for credit pool management.

    All endpoints require JWT authentication with staff privileges.
    Every mutation is audit-logged via @log_admin_access.
    """

    @http_get(
        "/credits",
        response={200: dict},
        summary="List credit pools",
        description="List all credit pools with filters and pagination.",
    )
    @admin_read_rate_limit
    async def list_credit_pools(
        self,
        request: HttpRequest,
        status: Optional[str] = Query(None, description="Filter by status: active, exhausted, expired, refunded, cancelled"),
        source: Optional[str] = Query(None, description="Filter by payment source: manual, local_gateway, bank_transfer, cash"),
        product_id: Optional[int] = Query(None, description="Filter by product ID"),
        search: Optional[str] = Query(None, description="Search by user email"),
        pagination: PaginationInput = Query(...),
    ):
        qs = CreditPool.objects.select_related(
            "user", "product", "plan"
        ).order_by("-created_at")

        if status:
            qs = qs.filter(status=status)
        if source:
            qs = qs.filter(source=source)
        if product_id:
            qs = qs.filter(product_id=product_id)
        if search:
            qs = qs.filter(user__email__icontains=search)

        from common.utils import get_paginated_data_async

        results, meta = await get_paginated_data_async(
            qs, pagination.page, pagination.page_size
        )

        items = []
        for pool in results:
            items.append({
                "id": pool.id,
                "user_email": pool.user.email,
                "plan_name": pool.plan.name,
                "plan_slug": pool.plan.slug,
                "product_name": pool.product.name,
                "amount_cents": pool.amount_cents,
                "display_amount": pool.display_amount,
                "currency": pool.currency,
                "credit_periods": pool.credit_periods,
                "periods_consumed": pool.periods_consumed,
                "periods_remaining": pool.periods_remaining,
                "source": pool.source,
                "payment_reference": pool.payment_reference,
                "status": pool.status,
                "is_effectively_active": pool.is_effectively_active,
                "current_period_start": pool.current_period_start.isoformat() if pool.current_period_start else None,
                "current_period_end": pool.current_period_end.isoformat() if pool.current_period_end else None,
                "expires_at": pool.expires_at.isoformat() if pool.expires_at else None,
                "created_at": pool.created_at.isoformat() if pool.created_at else None,
            })

        return {"meta": meta, "results": items}

    @http_get(
        "/credits/{credit_id}",
        response={200: dict, 404: dict},
        summary="Credit pool detail",
        description="Get full credit pool detail with transaction history.",
    )
    @admin_read_rate_limit
    async def get_credit_pool(
        self,
        request: HttpRequest,
        credit_id: int,
    ):
        try:
            pool = await CreditPool.objects.select_related(
                "user", "product", "plan"
            ).aget(pk=credit_id)
        except CreditPool.DoesNotExist:
            raise NotFoundException("Credit pool not found.")

        transactions = [tx async for tx in pool.transactions.order_by("-created_at").all()]

        return {
            "id": pool.id,
            "user_email": pool.user.email,
            "plan_name": pool.plan.name,
            "plan_slug": pool.plan.slug,
            "product_name": pool.product.name,
            "amount_cents": pool.amount_cents,
            "display_amount": pool.display_amount,
            "currency": pool.currency,
            "credit_periods": pool.credit_periods,
            "periods_consumed": pool.periods_consumed,
            "periods_remaining": pool.periods_remaining,
            "source": pool.source,
            "payment_reference": pool.payment_reference,
            "status": pool.status,
            "is_effectively_active": pool.is_effectively_active,
            "current_period_start": pool.current_period_start,
            "current_period_end": pool.current_period_end,
            "expires_at": pool.expires_at,
            "created_at": pool.created_at,
            "transactions": [
                {
                    "id": tx.id,
                    "action": tx.action,
                    "periods_delta": tx.periods_delta,
                    "amount_cents_delta": tx.amount_cents_delta,
                    "periods_balance": tx.periods_balance,
                    "reason": tx.reason,
                    "created_at": tx.created_at,
                }
                for tx in transactions
            ],
        }

    @http_post(
        "/credits",
        response={200: dict, 400: dict, 404: dict},
        summary="Create credit purchase",
        description="Record a manual/offline credit purchase for a user.",
    )
    @admin_write_rate_limit
    @log_admin_access
    async def create_credit_purchase(
        self,
        request: HttpRequest,
        payload: AdminCreditPurchaseSchema,
    ):
        from django.contrib.auth import get_user_model
        User = get_user_model()

        try:
            user = await User.objects.aget(email=payload.user_email)
        except User.DoesNotExist:
            raise NotFoundException("User with email '%s' not found." % payload.user_email)

        try:
            product = await Product.objects.aget(slug=payload.product_slug, is_active=True)
        except Product.DoesNotExist:
            raise NotFoundException("Product '%s' not found or inactive." % payload.product_slug)

        plan = await Plan.objects.filter(
            product=product, slug=payload.plan_slug, is_active=True
        ).afirst()
        if not plan:
            raise NotFoundException(
                "Plan '%s' not found or inactive in product '%s'."
                % (payload.plan_slug, product.slug)
            )

        try:
            pool, invoice = await sync_to_async(BillingService.create_credit_pool)(
                user=user,
                plan=plan,
                amount_cents=payload.amount_cents,
                source=payload.source,
                payment_reference=payload.payment_reference,
                created_by=request.user,
                currency=payload.currency,
                tax_cents=payload.tax_cents,
                notes=payload.notes,
            )
        except ValueError as e:
            raise BadRequestException(str(e))

        return {
            "pool": {
                "id": pool.id,
                "plan_name": pool.plan.name,
                "plan_slug": pool.plan.slug,
                "product_name": pool.product.name,
                "amount_cents": pool.amount_cents,
                "display_amount": pool.display_amount,
                "currency": pool.currency,
                "credit_periods": pool.credit_periods,
                "periods_remaining": pool.periods_remaining,
                "status": pool.status,
                "is_effectively_active": pool.is_effectively_active,
                "current_period_end": pool.current_period_end,
            },
            "invoice": {
                "id": invoice.id,
                "invoice_number": invoice.invoice_number,
                "status": invoice.status,
                "amount_cents": invoice.amount_cents,
                "tax_cents": invoice.tax_cents,
                "total_cents": invoice.total_cents,
                "currency": invoice.currency,
                "issued_at": invoice.issued_at,
            },
            "message": f"Credit purchase recorded. Invoice #{invoice.invoice_number} for {pool.display_amount} covering {pool.credit_periods} period(s).",
        }

    @http_post(
        "/credits/{credit_id}/refund",
        response={200: dict, 400: dict, 404: dict},
        summary="Refund credit pool",
        description="Refund a credit pool and void remaining periods.",
    )
    @admin_write_rate_limit
    @log_admin_access
    async def refund_credit_pool(
        self,
        request: HttpRequest,
        credit_id: int,
        payload: AdminCreditRefundSchema,
    ):
        try:
            pool = await CreditPool.objects.select_related(
                "user", "plan"
            ).aget(pk=credit_id)
        except CreditPool.DoesNotExist:
            raise NotFoundException("Credit pool not found.")

        if pool.status in (
            CreditPool.CreditPoolStatus.REFUNDED,
            CreditPool.CreditPoolStatus.CANCELLED,
        ):
            raise BadRequestException(
                "Cannot refund a credit pool with status '%s'." % pool.status
            )

        from django.utils import timezone as dj_timezone
        now = dj_timezone.now()
        remaining = pool.periods_remaining
        refund_amount = (
            remaining * pool.plan.price_cents if pool.plan.price_cents > 0 else 0
        )

        pool.status = CreditPool.CreditPoolStatus.REFUNDED
        pool.expires_at = now
        pool.current_period_end = now
        await pool.asave(
            update_fields=["status", "expires_at", "current_period_end", "updated_at"]
        )

        await CreditTransaction.objects.acreate(
            credit_pool=pool,
            action=CreditTransaction.TransactionType.REFUND,
            periods_delta=-remaining,
            amount_cents_delta=-refund_amount,
            periods_balance=0,
            reason=payload.reason,
            created_by=request.user,
        )

        logger.info(
            "ADMIN_CREDIT_REFUND: credit_id=%s, user=%s, refund_amount=%sc, reason='%s', by=%s",
            pool.id,
            pool.user.email,
            refund_amount,
            payload.reason[:100],
            request.user.email,
        )

        return {
            "id": pool.id,
            "status": pool.status,
            "periods_remaining": 0,
            "message": "Credit pool refunded. %s period(s) voided." % remaining,
        }

    @http_post(
        "/credits/{credit_id}/adjust",
        response={200: dict, 400: dict, 404: dict},
        summary="Adjust credit balance",
        description="Add or remove periods from a credit pool.",
    )
    @admin_write_rate_limit
    @log_admin_access
    async def adjust_credit_pool(
        self,
        request: HttpRequest,
        credit_id: int,
        payload: AdminCreditAdjustSchema,
    ):
        try:
            pool = await CreditPool.objects.select_related(
                "user", "plan"
            ).aget(pk=credit_id)
        except CreditPool.DoesNotExist:
            raise NotFoundException("Credit pool not found.")

        if pool.status != CreditPool.CreditPoolStatus.ACTIVE:
            raise BadRequestException(
                "Cannot adjust a credit pool with status '%s'." % pool.status
            )

        new_credit_periods = pool.credit_periods + payload.periods_delta
        if new_credit_periods < 0:
            raise BadRequestException(
                "Adjustment would result in negative credit periods."
            )

        old_periods = pool.credit_periods
        pool.credit_periods = new_credit_periods
        pool.periods_consumed = min(pool.periods_consumed, new_credit_periods)

        if pool.periods_remaining <= 0 and pool.status == CreditPool.CreditPoolStatus.ACTIVE:
            pool.status = CreditPool.CreditPoolStatus.EXHAUSTED

        await pool.asave(
            update_fields=["credit_periods", "periods_consumed", "status", "updated_at"]
        )

        amount_delta = (
            payload.amount_cents_delta
            if payload.amount_cents_delta is not None
            else (
                payload.periods_delta * pool.plan.price_cents
                if pool.plan.price_cents > 0
                else 0
            )
        )

        await CreditTransaction.objects.acreate(
            credit_pool=pool,
            action=CreditTransaction.TransactionType.ADJUST,
            periods_delta=payload.periods_delta,
            amount_cents_delta=amount_delta,
            periods_balance=pool.periods_remaining,
            reason=payload.reason,
            created_by=request.user,
        )

        logger.info(
            "ADMIN_CREDIT_ADJUST: credit_id=%s, delta=%s, old=%s, new=%s, by=%s",
            pool.id,
            payload.periods_delta,
            old_periods,
            new_credit_periods,
            request.user.email,
        )

        return {
            "id": pool.id,
            "credit_periods": pool.credit_periods,
            "periods_remaining": pool.periods_remaining,
            "status": pool.status,
            "message": "Credit pool adjusted by %+d periods." % payload.periods_delta,
        }


# =============================================================================
# Admin Controller — Credit Purchase Request Management
# =============================================================================


@api_controller(
    "/admin",
    tags=["Admin — Credit Requests"],
    auth=JWTAuth(),
    permissions=[IsAuthenticated, IsAdmin],
)
class AdminCreditRequestController:
    """Admin endpoints for managing credit purchase requests."""

    @http_get(
        "/credit-requests",
        response={200: dict},
        summary="List credit purchase requests",
    )
    @admin_read_rate_limit
    async def list_credit_requests(
        self,
        request: HttpRequest,
        status: Optional[str] = Query(None),
        search: Optional[str] = Query(None),
        pagination: PaginationInput = Query(...),
    ):
        from .models import CreditPurchaseRequest
        qs = CreditPurchaseRequest.objects.select_related("user", "product", "plan").order_by("-created_at")
        if status:
            qs = qs.filter(status=status)
        if search:
            qs = qs.filter(user__email__icontains=search)

        from common.utils import get_paginated_data_async
        results, meta = await get_paginated_data_async(qs, pagination.page, pagination.page_size)

        return {"meta": meta, "results": [{
            "id": r.id, "user_email": r.user.email,
            "product_name": r.product.name, "plan_name": r.plan.name,
            "amount_cents": r.amount_cents, "currency": r.currency,
            "bank_name": r.bank_name, "account_holder_name": r.account_holder_name,
            "account_number": r.account_number,
            "transaction_reference": r.transaction_reference,
            "payment_proof_note": r.payment_proof_note,
            "status": r.status, "created_at": r.created_at,
        } for r in results]}

    @http_post(
        "/credit-requests/{request_id}/approve",
        response={200: dict, 400: dict, 404: dict},
        summary="Approve credit request",
    )
    @admin_write_rate_limit
    @log_admin_access
    async def approve_credit_request(self, request: HttpRequest, request_id: int):
        from .models import CreditPurchaseRequest
        from .services import BillingService
        from django.utils import timezone as dj_tz

        try:
            cr = await CreditPurchaseRequest.objects.select_related("user", "product", "plan").aget(pk=request_id)
        except CreditPurchaseRequest.DoesNotExist:
            raise NotFoundException("Credit request not found.")

        if cr.status != CreditPurchaseRequest.RequestStatus.PENDING:
            raise BadRequestException(f"Cannot approve request with status '{cr.status}'.")

        pool, invoice = await sync_to_async(BillingService.create_credit_pool)(
            user=cr.user, plan=cr.plan, amount_cents=cr.amount_cents,
            source="bank_transfer", payment_reference=cr.transaction_reference,
            created_by=request.user, currency=cr.currency, tax_cents=0,
            notes=f"Approved from credit request #{cr.id}. Bank: {cr.bank_name}",
        )

        cr.status = CreditPurchaseRequest.RequestStatus.APPROVED
        cr.reviewed_by = request.user
        cr.reviewed_at = dj_tz.now()
        cr.created_credit_pool = pool
        await cr.asave(update_fields=["status", "reviewed_by", "reviewed_at", "created_credit_pool", "updated_at"])

        return {"id": cr.id, "status": cr.status, "credit_pool_id": pool.id,
                "invoice_number": invoice.invoice_number, "message": "Approved."}

    @http_post(
        "/credit-requests/{request_id}/reject",
        response={200: dict, 400: dict, 404: dict},
        summary="Reject credit request",
    )
    @admin_write_rate_limit
    @log_admin_access
    async def reject_credit_request(self, request: HttpRequest, request_id: int):
        from .models import CreditPurchaseRequest
        from django.utils import timezone as dj_tz

        try:
            cr = await CreditPurchaseRequest.objects.aget(pk=request_id)
        except CreditPurchaseRequest.DoesNotExist:
            raise NotFoundException("Credit request not found.")

        if cr.status != CreditPurchaseRequest.RequestStatus.PENDING:
            raise BadRequestException(f"Cannot reject request with status '{cr.status}'.")

        cr.status = CreditPurchaseRequest.RequestStatus.REJECTED
        cr.reviewed_by = request.user
        cr.reviewed_at = dj_tz.now()
        await cr.asave(update_fields=["status", "reviewed_by", "reviewed_at", "updated_at"])

        return {"id": cr.id, "status": cr.status, "message": "Rejected."}


# =============================================================================
# Admin Controller — Credit Invoice Endpoints
# =============================================================================


@api_controller(
    "/admin",
    tags=["Admin — Credit Invoices"],
    auth=JWTAuth(),
    permissions=[IsAuthenticated, IsAdmin],
)
class AdminCreditInvoiceController:
    """Admin endpoints for credit invoice management."""

    @http_get(
        "/credit-invoices",
        response={200: dict},
        summary="List credit invoices",
        description="List all credit invoices with filters and pagination.",
    )
    @admin_read_rate_limit
    async def list_credit_invoices(
        self,
        request: HttpRequest,
        status: Optional[str] = Query(None),
        search: Optional[str] = Query(
            None, description="Search by invoice number or email"
        ),
        pagination: PaginationInput = Query(...),
    ):
        qs = CreditInvoice.objects.select_related(
            "user", "product", "plan"
        ).order_by("-issued_at")

        if status:
            qs = qs.filter(status=status)
        if search:
            qs = qs.filter(
                models.Q(invoice_number__icontains=search)
                | models.Q(user__email__icontains=search)
            )

        from common.utils import get_paginated_data_async

        results, meta = await get_paginated_data_async(
            qs, pagination.page, pagination.page_size
        )

        items = []
        for inv in results:
            items.append({
                "id": inv.id,
                "invoice_number": inv.invoice_number,
                "user_email": inv.user.email,
                "product_name": inv.product.name,
                "plan_name": inv.plan.name,
                "amount_cents": inv.amount_cents,
                "tax_cents": inv.tax_cents,
                "total_cents": inv.total_cents,
                "currency": inv.currency,
                "status": inv.status,
                "issued_at": inv.issued_at,
            })

        return {"meta": meta, "results": items}

    @http_get(
        "/credit-invoices/{invoice_number}",
        response={200: dict, 404: dict},
        summary="Credit invoice detail",
        description="Get full credit invoice detail.",
    )
    @admin_read_rate_limit
    async def get_credit_invoice(
        self,
        request: HttpRequest,
        invoice_number: str,
    ):
        try:
            inv = await CreditInvoice.objects.select_related(
                "user", "product", "plan", "credit_pool"
            ).aget(invoice_number=invoice_number)
        except CreditInvoice.DoesNotExist:
            raise NotFoundException(
                "Credit invoice '%s' not found." % invoice_number
            )

        return {
            "id": inv.id,
            "invoice_number": inv.invoice_number,
            "user_email": inv.user.email,
            "product_name": inv.product.name,
            "plan_name": inv.plan.name,
            "amount_cents": inv.amount_cents,
            "tax_cents": inv.tax_cents,
            "total_cents": inv.total_cents,
            "currency": inv.currency,
            "status": inv.status,
            "period_start": inv.period_start,
            "period_end": inv.period_end,
            "payment_reference": inv.payment_reference,
            "notes": inv.notes,
            "issued_at": inv.issued_at,
            "credit_pool_id": inv.credit_pool_id,
        }
