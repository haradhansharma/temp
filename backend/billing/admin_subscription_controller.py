"""Admin controller for subscription management (Phase 9.4).

Provides admin-only CRUD and operational endpoints for subscriptions.
All endpoints require ``is_staff=True`` and every mutation is audit-logged
via the ``@log_admin_access`` decorator.

Endpoints:
    Subscriptions (9.4):
        GET    /admin/subscriptions                       — list (filterable, paginated)
        GET    /admin/subscriptions/{id}                  — detail with access map
        PATCH  /admin/subscriptions/{id}/override          — override plan/status/period
        PATCH  /admin/subscriptions/{id}/cancel            — force cancel
        PATCH  /admin/subscriptions/{id}/expire            — force expire
        PATCH  /admin/subscriptions/{id}/extend            — extend billing period
        GET    /admin/subscriptions/{id}/plan-changes      — plan change history
        GET    /admin/subscriptions/{id}/invoices          — invoice history
        GET    /admin/subscriptions/{id}/refunds           — refund history
        POST   /admin/subscriptions/{id}/refund             — issue refund
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from django.db import transaction
from django.db.models import Q, Prefetch
from django.http import HttpRequest
from django.utils import timezone
from asgiref.sync import sync_to_async

from ninja import Query
from ninja_extra import api_controller, http_get, http_patch, http_post

from common.exceptions import (
    NotFoundException,
    BadRequestException,
)
from common.permissions import IsAuthenticated, IsAdmin
from common.schemas import MessageResponse, PaginatedResponse, PaginationInput

from users.controllers import JWTAuth
from users.models import User

from .models import (
    Plan,
    Product,
    Subscription,
    SubscriptionStatus,
    PlanChangeLog,
    Invoice,
    InvoiceLineItem,
    Refund,
    RefundStatus,
    AccessEntry,
)
from .admin_schemas import (
    AdminSubscriptionListItemSchema,
    AdminSubscriptionDetailSchema,
    AdminSubscriptionOverrideSchema,
    AdminSubscriptionExtendSchema,
    AdminPlanChangeLogItemSchema,
    AdminInvoiceListItemSchema,
    AdminInvoiceDetailSchema,
    AdminInvoiceLineItemSchema,
    AdminRefundListItemSchema,
    AdminRefundApprovalSchema,
)
from .schemas import RefundInputSchema
from .admin_utils import log_admin_access, admin_write_rate_limit, admin_read_rate_limit

logger = logging.getLogger(__name__)


# =============================================================================
# Re-use the admin access logging decorator
# =============================================================================


# log_admin_access and admin_write_rate_limit are imported from .admin_utils


# =============================================================================
# Admin Controller — Subscriptions
# =============================================================================


@api_controller(
    "/admin",
    tags=["Admin — Subscriptions"],
    auth=JWTAuth(),
    permissions=[IsAuthenticated, IsAdmin],
)
class AdminSubscriptionController:
    """Admin endpoints for managing and monitoring subscriptions.

    All endpoints require JWT authentication with staff privileges.
    Every mutation is audit-logged via the ``@log_admin_access`` decorator.

    Subscription mutations (override, cancel, expire, extend) are powerful
    admin tools that bypass Stripe workflows. They should be used only for
    support escalations, grace periods, or manual corrections. When a
    subscription has an active ``stripe_subscription_id``, the admin is
    warned that Stripe state may diverge from the local override.
    """

    # =========================================================================
    # Helpers
    # =========================================================================

    async def _get_subscription_or_404(self, subscription_id: int) -> Subscription:
        """Fetch a subscription with related user/plan/product or raise 404."""
        try:
            return await sync_to_async(
                Subscription.objects.select_related(
                    "user", "plan", "plan__product", "product"
                ).get
            )(pk=subscription_id)
        except Subscription.DoesNotExist:
            raise NotFoundException("Subscription not found.")

    async def _serialize_subscription_list_item(
        self, sub: Subscription
    ) -> dict:
        """Serialize a subscription for admin list view."""
        return {
            "id": sub.id,
            "user_id": sub.user_id,
            "user_email": sub.user.email,
            "user_name": sub.user.full_name,
            "product_id": sub.product_id,
            "product_name": sub.product.name,
            "product_slug": sub.product.slug,
            "plan_id": sub.plan_id,
            "plan_name": sub.plan.name,
            "plan_slug": sub.plan.slug,
            "status": sub.status,
            "currency": sub.currency or sub.plan.currency,
            "current_period_start": sub.current_period_start,
            "current_period_end": sub.current_period_end,
            "cancel_at_period_end": sub.cancel_at_period_end,
            "dunning_step": sub.dunning_step,
            "stripe_subscription_id": sub.stripe_subscription_id,
            "created_at": sub.created_at,
            "updated_at": sub.updated_at,
        }

    async def _serialize_subscription_detail(
        self, sub: Subscription
    ) -> dict:
        """Serialize a subscription for admin detail view with access map."""
        data = await self._serialize_subscription_list_item(sub)

        # Additional detail fields
        data.update({
            "trial_start": sub.trial_start,
            "trial_end": sub.trial_end,
            "canceled_at": sub.canceled_at,
            "expires_at": sub.expires_at,
            "past_due_at": sub.past_due_at,
            "has_used_trial": sub.has_used_trial,
            "tos_accepted_at": sub.tos_accepted_at,
            "tos_version": sub.tos_version,
            "last_dunning_email_at": sub.last_dunning_email_at,
            "stripe_customer_id": sub.stripe_customer_id,
        })

        # Build access map from plan's access entries
        access_entries_qs = AccessEntry.objects.filter(plan=sub.plan).order_by("key")
        access_map = {}
        async for entry in access_entries_qs:
            access_map[entry.key] = entry.typed_value
        data["access"] = access_map

        return data

    # =========================================================================
    # List & Detail
    # =========================================================================

    @http_get(
        "/subscriptions",
        response=PaginatedResponse[AdminSubscriptionListItemSchema],
        summary="List subscriptions",
        description=(
            "List all subscriptions with user, plan, and product info. "
            "Supports ?product_id=, ?plan_id=, ?status=, ?search= (user email) "
            "filters. Paginated."
        ),
    )
    async def list_subscriptions(
        self,
        request: HttpRequest,
        product_id: Optional[int] = None,
        plan_id: Optional[int] = None,
        status: Optional[str] = None,
        search: Optional[str] = None,
        pagination: PaginationInput = Query(...),
    ):
        """List all subscriptions with admin-level filters.

        Returns subscriptions ordered by most recent first. Supports
        filtering by product, plan, status, and searching by user email.
        Each item includes user, plan, and product context for the
        admin list view.
        """
        qs = (
            Subscription.objects.select_related(
                "user", "plan", "plan__product", "product"
            )
            .order_by("-created_at")
        )

        if product_id is not None:
            qs = qs.filter(product_id=product_id)

        if plan_id is not None:
            qs = qs.filter(plan_id=plan_id)

        if status is not None:
            qs = qs.filter(status=status)

        if search:
            qs = qs.filter(
                Q(user__email__icontains=search)
                | Q(user__first_name__icontains=search)
                | Q(user__last_name__icontains=search)
            )

        from common.utils import get_paginated_data_async

        results, meta = await get_paginated_data_async(
            qs, pagination.page, pagination.page_size
        )

        items = []
        for sub in results:
            items.append(await self._serialize_subscription_list_item(sub))

        return {"meta": meta, "results": items}

    @http_get(
        "/subscriptions/{subscription_id}",
        response={200: AdminSubscriptionDetailSchema, 404: dict},
        summary="Get subscription detail",
        description=(
            "Return full subscription detail with user info, plan info, "
            "product info, access entries from plan, and all timestamps."
        ),
    )
    async def get_subscription_detail(
        self,
        request: HttpRequest,
        subscription_id: int,
    ):
        """Get subscription detail with access map and full metadata.

        Includes trial info, cancellation state, dunning step, ToS
        acceptance, and a flat access map derived from the plan's
        access entries.
        """
        sub = await self._get_subscription_or_404(subscription_id)
        return await self._serialize_subscription_detail(sub)

    # =========================================================================
    # Subscription Mutations
    # =========================================================================

    @http_patch(
        "/subscriptions/{subscription_id}/override",
        response={200: dict, 400: dict, 404: dict},
        summary="Override subscription",
        description=(
            "Admin override: change plan, status, or billing period. "
            "Logs before/after state. Warns if Stripe subscription exists "
            "(local override may diverge from Stripe state)."
        ),
    )
    @admin_write_rate_limit
    @log_admin_access
    async def override_subscription(
        self,
        request: HttpRequest,
        subscription_id: int,
        payload: AdminSubscriptionOverrideSchema,
    ):
        """Override a subscription's plan, status, or billing period.

        This is a powerful admin tool for manual corrections, grace
        periods, and support escalations. When the subscription has an
        active Stripe subscription ID, the response includes a warning
        that the local state may diverge from Stripe's source of truth.

        All changes are fully audit-logged with before/after state.
        """
        sub = await self._get_subscription_or_404(subscription_id)

        # Capture before state for audit
        before = {
            "plan_id": sub.plan_id,
            "status": sub.status,
            "period_start": str(sub.current_period_start) if sub.current_period_start else None,
            "period_end": str(sub.current_period_end) if sub.current_period_end else None,
        }

        update_fields = ["updated_at"]
        warnings = []

        # Validate plan_id if provided
        if payload.plan_id is not None:
            if payload.plan_id == sub.plan_id:
                raise BadRequestException(
                    "The subscription is already on this plan."
                )
            try:
                new_plan = await sync_to_async(Plan.objects.select_related("product").get)(
                    pk=payload.plan_id
                )
            except Plan.DoesNotExist:
                raise NotFoundException("Target plan not found.")

            # Plan must belong to the same product
            if new_plan.product_id != sub.product_id:
                raise BadRequestException(
                    f"Plan '{new_plan.name}' belongs to product "
                    f"'{new_plan.product.name}', not '{sub.product.name}'. "
                    f"Cross-product plan changes are not allowed."
                )

            old_plan = sub.plan
            sub.plan = new_plan
            update_fields.append("plan_id")

        # Validate status if provided
        if payload.status is not None:
            valid_statuses = [s.value for s in SubscriptionStatus]
            if payload.status not in valid_statuses:
                raise BadRequestException(
                    f"Invalid status '{payload.status}'. "
                    f"Must be one of: {', '.join(valid_statuses)}."
                )

            if payload.status == sub.status:
                raise BadRequestException(
                    f"Subscription is already in '{payload.status}' status."
                )

            sub.status = payload.status
            update_fields.append("status")

            # Handle status-specific side effects
            if payload.status == SubscriptionStatus.CANCELED:
                sub.canceled_at = timezone.now()
                sub.cancel_at_period_end = True
                update_fields.extend(["canceled_at", "cancel_at_period_end"])
            elif payload.status == SubscriptionStatus.EXPIRED:
                sub.expires_at = timezone.now()
                update_fields.append("expires_at")

        # Override period dates if provided
        if payload.period_start is not None:
            sub.current_period_start = payload.period_start
            update_fields.append("current_period_start")

        if payload.period_end is not None:
            sub.current_period_end = payload.period_end
            update_fields.append("current_period_end")

        # Warn if Stripe subscription exists
        if sub.stripe_subscription_id:
            warnings.append(
                "This subscription has an active Stripe subscription "
                f"(stripe_subscription_id={sub.stripe_subscription_id}). "
                "Local overrides may diverge from Stripe's state. "
                "Consider using Stripe Dashboard or Customer Portal "
                "for changes that should sync with Stripe."
            )

        await sync_to_async(sub.save)(update_fields=update_fields)

        # Log the override with before/after state
        after = {
            "plan_id": sub.plan_id,
            "status": sub.status,
            "period_start": str(sub.current_period_start) if sub.current_period_start else None,
            "period_end": str(sub.current_period_end) if sub.current_period_end else None,
        }

        logger.info(
            "ADMIN_SUBSCRIPTION_OVERRIDE: sub_id=%s, user=%s, "
            "before=%s, after=%s, reason='%s', "
            "overridden_by=%s, ip=%s",
            sub.id,
            sub.user.email,
            before,
            after,
            payload.reason,
            request.user.email,
            request.META.get("REMOTE_ADDR"),
        )

        result = await self._serialize_subscription_detail(sub)
        if warnings:
            result["warnings"] = warnings
        return result

    @http_patch(
        "/subscriptions/{subscription_id}/cancel",
        response={200: dict, 400: dict, 404: dict},
        summary="Force cancel subscription",
        description=(
            "Force-cancel a subscription. Sets status=canceled and records "
            "canceled_at. The subscription remains active until period_end "
            "(cancel_at_period_end=True)."
        ),
    )
    @admin_write_rate_limit
    @log_admin_access
    async def cancel_subscription(
        self,
        request: HttpRequest,
        subscription_id: int,
    ):
        """Force-cancel a subscription.

        Sets status to 'canceled', records the cancellation timestamp,
        and keeps the subscription active until the end of the current
        billing period. This mirrors the user-initiated cancel flow
        but can be performed by an admin for any reason.
        """
        sub = await self._get_subscription_or_404(subscription_id)

        if sub.status == SubscriptionStatus.CANCELED:
            raise BadRequestException(
                "This subscription is already canceled."
            )

        if sub.status == SubscriptionStatus.EXPIRED:
            raise BadRequestException(
                "This subscription has already expired. "
                "Cancellation is not applicable."
            )

        sub.status = SubscriptionStatus.CANCELED
        sub.canceled_at = timezone.now()
        sub.cancel_at_period_end = True
        await sync_to_async(sub.save)(
            update_fields=[
                "status", "canceled_at", "cancel_at_period_end", "updated_at"
            ]
        )

        logger.info(
            "ADMIN_SUBSCRIPTION_CANCELED: sub_id=%s, user=%s, "
            "product='%s', plan='%s', period_end=%s, "
            "canceled_by=%s, ip=%s",
            sub.id,
            sub.user.email,
            sub.product.name,
            sub.plan.name,
            sub.current_period_end,
            request.user.email,
            request.META.get("REMOTE_ADDR"),
        )

        return await self._serialize_subscription_detail(sub)

    @http_patch(
        "/subscriptions/{subscription_id}/expire",
        response={200: dict, 400: dict, 404: dict},
        summary="Force expire subscription",
        description=(
            "Force-expire a subscription immediately. Sets status=expired "
            "and expires_at=now. The user loses access right away."
        ),
    )
    @admin_write_rate_limit
    @log_admin_access
    async def expire_subscription(
        self,
        request: HttpRequest,
        subscription_id: int,
    ):
        """Force-expire a subscription immediately.

        Sets status to 'expired' and records expires_at as now. The user
        loses access immediately, regardless of whether the billing
        period has ended. Use this for severe violations, chargebacks,
        or when Stripe has already expired the subscription and the
        local state needs to catch up.
        """
        sub = await self._get_subscription_or_404(subscription_id)

        if sub.status == SubscriptionStatus.EXPIRED:
            raise BadRequestException(
                "This subscription is already expired."
            )

        now = timezone.now()
        sub.status = SubscriptionStatus.EXPIRED
        sub.expires_at = now
        sub.canceled_at = sub.canceled_at or now
        await sync_to_async(sub.save)(
            update_fields=["status", "expires_at", "canceled_at", "updated_at"]
        )

        logger.info(
            "ADMIN_SUBSCRIPTION_EXPIRED: sub_id=%s, user=%s, "
            "product='%s', plan='%s', "
            "expired_by=%s, ip=%s",
            sub.id,
            sub.user.email,
            sub.product.name,
            sub.plan.name,
            request.user.email,
            request.META.get("REMOTE_ADDR"),
        )

        return await self._serialize_subscription_detail(sub)

    @http_patch(
        "/subscriptions/{subscription_id}/extend",
        response={200: dict, 400: dict, 404: dict},
        summary="Extend subscription period",
        description=(
            "Extend the billing period end by a given number of days. "
            "Only works for active, trialing, or canceled subscriptions "
            "that have a period_end. Reason is recorded for audit."
        ),
    )
    @admin_write_rate_limit
    @log_admin_access
    async def extend_subscription(
        self,
        request: HttpRequest,
        subscription_id: int,
        payload: AdminSubscriptionExtendSchema,
    ):
        """Extend a subscription's billing period end.

        Adds the specified number of days to ``current_period_end``.
        This is useful for granting complimentary extension periods
        due to service outages, support escalations, or goodwill gestures.

        The extension only works when ``current_period_end`` is set.
        For lifetime plans (no period_end), use the override endpoint
        instead.
        """
        sub = await self._get_subscription_or_404(subscription_id)

        if not sub.current_period_end:
            raise BadRequestException(
                "This subscription has no billing period end set "
                "(possibly a lifetime plan). Use the override endpoint "
                "to set period dates manually."
            )

        # Prevent extending expired subscriptions (use expire→override instead)
        if sub.status == SubscriptionStatus.EXPIRED:
            raise BadRequestException(
                "Cannot extend an expired subscription. "
                "Use the override endpoint to change its status first."
            )

        old_period_end = sub.current_period_end
        sub.current_period_end = old_period_end + timedelta(days=payload.days)
        await sync_to_async(sub.save)(
            update_fields=["current_period_end", "updated_at"]
        )

        logger.info(
            "ADMIN_SUBSCRIPTION_EXTENDED: sub_id=%s, user=%s, "
            "product='%s', days=%s, old_end=%s, new_end=%s, "
            "reason='%s', extended_by=%s, ip=%s",
            sub.id,
            sub.user.email,
            sub.product.name,
            payload.days,
            old_period_end,
            sub.current_period_end,
            payload.reason,
            request.user.email,
            request.META.get("REMOTE_ADDR"),
        )

        return await self._serialize_subscription_detail(sub)

    # =========================================================================
    # Subscription History
    # =========================================================================

    @http_get(
        "/subscriptions/{subscription_id}/plan-changes",
        response=PaginatedResponse[AdminPlanChangeLogItemSchema],
        summary="Get plan change history",
        description=(
            "Return all plan changes for a subscription, ordered by "
            "most recent first. Includes from/to plan names, proration "
            "amounts, and who initiated the change. Paginated."
        ),
    )
    async def get_subscription_plan_changes(
        self,
        request: HttpRequest,
        subscription_id: int,
        pagination: PaginationInput = Query(...),
    ):
        """List plan change history for a subscription.

        Returns all PlanChangeLog entries ordered by created_at
        descending. Each entry includes the from/to plan names,
        proration amount, and who initiated the change. Paginated.
        """
        # Validate subscription exists
        await self._get_subscription_or_404(subscription_id)

        qs = (
            PlanChangeLog.objects.filter(subscription_id=subscription_id)
            .select_related("from_plan", "to_plan", "initiated_by")
            .order_by("-created_at")
        )

        from common.utils import get_paginated_data_async

        results, meta = await get_paginated_data_async(
            qs, pagination.page, pagination.page_size
        )

        items = []
        for change in results:
            items.append({
                "id": change.id,
                "from_plan_id": change.from_plan_id,
                "from_plan_name": change.from_plan.name,
                "to_plan_id": change.to_plan_id,
                "to_plan_name": change.to_plan.name,
                "proration_amount_cents": change.proration_amount_cents,
                "currency": change.currency,
                "stripe_proration_id": change.stripe_proration_id,
                "proration_behavior": change.proration_behavior,
                "initiated_by_id": (
                    change.initiated_by_id if change.initiated_by else None
                ),
                "initiated_by_email": (
                    change.initiated_by.email if change.initiated_by else None
                ),
                "created_at": change.created_at,
            })

        return {"meta": meta, "results": items}

    @http_get(
        "/subscriptions/{subscription_id}/invoices",
        response=PaginatedResponse[AdminInvoiceListItemSchema],
        summary="Get invoice history",
        description=(
            "List invoices for a subscription, ordered by most recent. "
            "Paginated."
        ),
    )
    async def get_subscription_invoices(
        self,
        request: HttpRequest,
        subscription_id: int,
        pagination: PaginationInput = Query(...),
    ):
        """List invoices for a subscription.

        Returns invoices ordered by creation date descending.
        Includes amount, status, Stripe hosted/PDF URLs, and
        fee information for reconciliation.
        """
        await self._get_subscription_or_404(subscription_id)

        qs = (
            Invoice.objects.filter(subscription_id=subscription_id)
            .order_by("-created_at")
        )

        from common.utils import get_paginated_data_async

        results, meta = await get_paginated_data_async(
            qs, pagination.page, pagination.page_size
        )

        items = []
        for inv in results:
            items.append({
                "id": inv.id,
                "stripe_invoice_id": inv.stripe_invoice_id,
                "subscription_id": inv.subscription_id,
                "number": inv.number,
                "status": inv.status,
                "amount_paid_cents": inv.amount_paid_cents,
                "amount_due_cents": inv.amount_due_cents,
                "tax_cents": inv.tax_cents,
                "discount_cents": inv.discount_cents,
                "currency": inv.currency,
                "period_start": inv.period_start,
                "period_end": inv.period_end,
                "hosted_url": inv.hosted_url,
                "pdf_url": inv.pdf_url,
                "stripe_fee_cents": inv.stripe_fee_cents,
                "attempt_count": inv.attempt_count,
                "created_at": inv.created_at,
            })

        return {"meta": meta, "results": items}

    @http_post(
        "/subscriptions/{subscription_id}/refund",
        response={200: dict, 400: dict, 404: dict, 403: dict},
        summary="Issue refund for subscription",
        description=(
            "Issue a refund for a subscription's latest payment via Stripe. "
            "Requires staff access. The refund will be in 'pending' status "
"until another admin approves it (two-person rule). "
            "Optionally specify amount_cents for partial refunds."
        ),
    )
    @admin_write_rate_limit
    @log_admin_access
    async def issue_refund(
        self,
        request: HttpRequest,
        subscription_id: int,
        payload: RefundInputSchema,
    ):
        """Issue a refund for a subscription from the admin panel.

        This endpoint creates a Stripe refund and records it in the
        database. The refund is created with status 'pending' and must
        be approved by a different admin (two-person rule) before it
        is marked 'completed'.

        The admin's IP address is captured for the audit trail (CMP-02).
        The amount is validated against the latest invoice's paid amount
        to prevent over-refunding (FIN-03).

        If amount_cents is not provided, the full amount of the latest
        invoice payment is refunded.
        """
        import stripe as stripe_lib
        from .stripe import create_stripe_refund
        from .controllers import BillingAdminController

        sub = await self._get_subscription_or_404(subscription_id)

        if not sub.stripe_subscription_id:
            raise BadRequestException(
                "Cannot refund a subscription without a Stripe payment."
            )

        # Use target_user_id from payload, or default to the subscription's user
        target_user_id = getattr(payload, "target_user_id", None)
        if target_user_id and target_user_id != sub.user_id:
            raise BadRequestException(
                f"Target user ID {target_user_id} does not match "
                f"the subscription's user (id={sub.user_id})."
            )

        try:
            refund = await sync_to_async(create_stripe_refund)(
                subscription=sub,
                amount_cents=payload.amount_cents,
                reason=payload.reason,
                initiated_by=request.user,
                reason_category=payload.reason_category,
                admin_notes=payload.admin_notes,
            )
            # CMP-02: Capture admin's IP for audit trail
            refund.initiated_by_ip = request.META.get("REMOTE_ADDR")
            await sync_to_async(refund.save)(update_fields=["initiated_by_ip"])
        except ValueError as e:
            raise BadRequestException(str(e))
        except stripe_lib.error.StripeError as e:
            from .controllers import handle_stripe_error
            raise handle_stripe_error(e, context="refund")

        logger.info(
            "ADMIN_REFUND_ISSUED: refund_id=%s, sub_id=%s, user=%s, "
            "product='%s', amount=%s %s, status=%s, reason_category='%s', "
            "initiated_by=%s, ip=%s",
            refund.id,
            sub.id,
            sub.user.email,
            sub.product.name,
            refund.amount_cents,
            refund.currency,
            refund.status,
            refund.reason_category,
            request.user.email,
            request.META.get("REMOTE_ADDR"),
        )

        return {
            "refund_id": refund.id,
            "stripe_refund_id": refund.stripe_refund_id or "",
            "amount_cents": refund.amount_cents,
            "currency": refund.currency,
            "status": refund.status,
            "reason_category": refund.reason_category,
            "message": (
                "Refund created successfully. It is pending approval "
                "by another admin (two-person rule)."
                if refund.status == RefundStatus.PENDING
                else "Refund processed."
            ),
        }

    @http_get(
        "/subscriptions/{subscription_id}/refunds",
        response=PaginatedResponse[AdminRefundListItemSchema],
        summary="Get refund history",
        description=(
            "List refunds for a subscription, ordered by most recent. "
            "Includes initiation and approval details. Paginated."
        ),
    )
    async def get_subscription_refunds(
        self,
        request: HttpRequest,
        subscription_id: int,
        pagination: PaginationInput = Query(...),
    ):
        """List refunds for a subscription.

        Returns all refund records ordered by creation date descending.
        Includes the initiation details, approval status, and reason
        category for the admin refund management view. Paginated.
        """
        sub = await self._get_subscription_or_404(subscription_id)

        qs = (
            Refund.objects.filter(subscription=sub)
            .select_related("initiated_by", "approved_by")
            .order_by("-created_at")
        )

        from common.utils import get_paginated_data_async

        results, meta = await get_paginated_data_async(
            qs, pagination.page, pagination.page_size
        )

        items = []
        for refund in results:
            items.append({
                "id": refund.id,
                "subscription_id": refund.subscription_id,
                "user_email": sub.user.email,
                "product_name": sub.product.name,
                "plan_name": sub.plan.name,
                "stripe_refund_id": refund.stripe_refund_id,
                "stripe_charge_id": refund.stripe_charge_id,
                "amount_cents": refund.amount_cents,
                "currency": refund.currency,
                "reason": refund.reason,
                "status": refund.status,
                "reason_category": refund.reason_category,
                "initiated_by_id": (
                    refund.initiated_by_id if refund.initiated_by else None
                ),
                "initiated_by_email": (
                    refund.initiated_by.email if refund.initiated_by else None
                ),
                "initiated_by_ip": refund.initiated_by_ip,
                "approved_by_id": (
                    refund.approved_by_id if refund.approved_by else None
                ),
                "approved_by_email": (
                    refund.approved_by.email if refund.approved_by else None
                ),
                "approved_at": refund.approved_at,
                "admin_notes": refund.admin_notes,
                "created_at": refund.created_at,
            })

        return {"meta": meta, "results": items}
