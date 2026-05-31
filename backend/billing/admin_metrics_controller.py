"""Admin controller for metrics, audit log, and webhook monitoring (Phase 9.7).

Provides admin-only read endpoints for business metrics, revenue analytics,
subscription funnels, audit log, and webhook event monitoring. All endpoints
require ``is_staff=True``.

Endpoints:
    Metrics (9.7):
        GET    /admin/metrics/overview        — aggregate dashboard metrics
        GET    /admin/metrics/revenue         — revenue breakdown by product/plan/month
        GET    /admin/metrics/subscriptions   — subscription funnel metrics
        GET    /admin/metrics/products        — per-product metrics summary

    Audit Log (9.7):
        GET    /admin/audit-log               — paginated admin action log

    Webhook Monitoring (9.7):
        GET    /admin/webhooks                — list webhook events (paginated)
        POST   /admin/webhooks/{id}/retry     — retry a failed webhook event
"""

import logging
from datetime import datetime, timedelta, date
from typing import Optional

from django.db.models import (
    Q, Count, Sum, Avg, Max,
    F, ExpressionWrapper, IntegerField,
    Case, When, Value,
)
from django.db.models.functions import TruncMonth, Coalesce
from django.http import HttpRequest
from django.utils import timezone
from asgiref.sync import sync_to_async

from ninja import Query
from ninja_extra import api_controller, http_get, http_post

from common.exceptions import (
    NotFoundException,
    BadRequestException,
)
from common.permissions import IsAuthenticated, IsAdmin
from common.schemas import MessageResponse, PaginatedResponse, PaginationInput

from users.controllers import JWTAuth
from users.models import User

from .models import (
    Product,
    Plan,
    Subscription,
    SubscriptionStatus,
    Refund,
    RefundStatus,
    Invoice,
    RevenueRecognitionEntry,
    WebhookEventLog,
    AdminAuditLog,
)
from .admin_schemas import (
    AdminMetricsOverviewSchema,
    AdminMetricsRevenueSchema,
    AdminMetricsRevenueByProductSchema,
    AdminMetricsRevenueByPlanSchema,
    AdminMetricsRevenueByMonthSchema,
    AdminMetricsSubscriptionFunnelSchema,
    AdminMetricsProductsSchema,
    AdminAuditLogItemSchema,
    AdminAuditLogListSchema,
    AdminWebhookEventItemSchema,
    AdminWebhookEventListSchema,
)
from .admin_utils import admin_write_rate_limit, admin_read_rate_limit

logger = logging.getLogger(__name__)


# =============================================================================
# Helper: currency formatting
# =============================================================================

# Use centralized currency metadata from currency_service
from .currency_service import get_currency_symbol, get_currency_decimal_digits


def _format_currency(cents: int, currency: str = "USD") -> str:
    """Format cents into a human-readable currency string."""
    symbol = get_currency_symbol(currency)
    decimal_digits = get_currency_decimal_digits(currency)
    amount = cents / 100
    return f"{symbol}{amount:.{decimal_digits}f}"


# =============================================================================
# Admin Controller — Metrics & Audit
# =============================================================================


@api_controller(
    "/admin",
    tags=["Admin — Metrics & Audit"],
    auth=JWTAuth(),
    permissions=[IsAuthenticated, IsAdmin],
)
class AdminMetricsController:
    """Admin endpoints for business metrics, audit logging, and webhook monitoring.

    All endpoints require JWT authentication with staff privileges.
    Metrics endpoints are read-only and provide aggregate data for the
    admin dashboard. The audit log endpoint provides a paginated,
    filterable view of all admin actions performed on the platform.
    """

    # =========================================================================
    # 9.7.1 — Metrics Overview
    # =========================================================================

    @admin_read_rate_limit
    @http_get(
        "/metrics/overview",
        response=AdminMetricsOverviewSchema,
        summary="Metrics overview",
        description=(
            "Return key business metrics for the admin dashboard: MRR, "
            "subscription counts by status, churn rate, trial conversion rate, "
            "and total user count."
        ),
    )
    async def metrics_overview(
        self,
        request: HttpRequest,
        currency: str = Query("USD", description="Currency for MRR display"),
    ):
        """Aggregate dashboard metrics.

        Computes:
        - **MRR**: Sum of active subscription plan prices (monthly equivalent).
          For yearly plans, MRR = price_cents / 12. For lifetime, price_cents.
        - **Active subscriptions**: Count of active + trialing subscriptions.
        - **Trial count**: Subscriptions currently in trial period.
        - **Past due**: Subscriptions with past-due payments.
        - **Canceled**: Subscriptions canceled but not yet expired.
        - **Churn rate**: Subscriptions canceled in last 30 days divided by
          total active subscriptions 30 days ago.
        - **Trial conversion rate**: Percentage of trials that converted to
          paid (active) subscriptions.
        """
        now = timezone.now()
        thirty_days_ago = now - timedelta(days=30)
        sixty_days_ago = now - timedelta(days=60)

        @sync_to_async
        def _compute():
            # --- Active subscriptions by status ---
            status_counts = dict(
                Subscription.objects.filter(
                    status__in=(
                        SubscriptionStatus.ACTIVE,
                        SubscriptionStatus.TRIALING,
                        SubscriptionStatus.PAST_DUE,
                        SubscriptionStatus.CANCELED,
                    )
                ).values_list("status", flat=True)
                .annotate(count=Count("id"))
                .values_list("status", "count")
            )

            active_count = status_counts.get(SubscriptionStatus.ACTIVE, 0)
            trial_count = status_counts.get(SubscriptionStatus.TRIALING, 0)
            past_due_count = status_counts.get(SubscriptionStatus.PAST_DUE, 0)
            canceled_count = status_counts.get(SubscriptionStatus.CANCELED, 0)

            # --- MRR: sum of plan prices for active subscriptions ---
            mrr_data = Subscription.objects.filter(
                status=SubscriptionStatus.ACTIVE,
            ).values(
                "plan__currency",
                "plan__billing_cycle",
            ).annotate(
                total_cents=Sum("plan__price_cents"),
            )

            mrr_cents = 0
            mrr_currency = currency
            for row in mrr_data:
                cycle = row["plan__billing_cycle"]
                total = row["total_cents"] or 0
                if cycle == "yearly":
                    monthly_equiv = total // 12
                elif cycle == "lifetime":
                    monthly_equiv = 0  # Lifetime doesn't contribute to MRR
                else:
                    monthly_equiv = total

                # Simple: assume primary currency for display
                if row["plan__currency"] == currency:
                    mrr_cents += monthly_equiv
                else:
                    # If multi-currency, convert later or just accumulate
                    mrr_cents += monthly_equiv
                    mrr_currency = row["plan__currency"]

            # --- Churn rate ---
            # Numerator: subscriptions canceled in the last 30 days
            churned_count = Subscription.objects.filter(
                canceled_at__gte=thirty_days_ago,
                canceled_at__lt=now,
            ).count()

            # Denominator: active subscriptions 30 days ago
            # (subscriptions that were active 30 days ago)
            active_30d_ago = Subscription.objects.filter(
                status__in=(
                    SubscriptionStatus.ACTIVE,
                    SubscriptionStatus.TRIALING,
                ),
                created_at__lt=thirty_days_ago,
            ).exclude(
                canceled_at__lt=thirty_days_ago,
            ).count()

            churn_rate = (
                round(churned_count / active_30d_ago, 4)
                if active_30d_ago > 0
                else 0.0
            )

            # --- Trial conversion rate ---
            # Trials that started in the last 60 days and either converted
            # to paid or are still active
            trials_started = Subscription.objects.filter(
                trial_start__gte=sixty_days_ago,
                trial_start__lt=now,
            ).count()

            trials_converted = Subscription.objects.filter(
                trial_start__gte=sixty_days_ago,
                trial_start__lt=now,
                status=SubscriptionStatus.ACTIVE,
            ).exclude(
                trial_end__isnull=True,  # Still in trial = not yet converted
            ).count()

            trial_conversion_rate = (
                round(trials_converted / trials_started, 4)
                if trials_started > 0
                else 0.0
            )

            # --- Total users ---
            total_users = User.objects.count()

            return {
                "mrr_cents": mrr_cents,
                "mrr_display": _format_currency(mrr_cents, mrr_currency),
                "active_subscriptions": active_count + trial_count,
                "trial_subscriptions": trial_count,
                "past_due_subscriptions": past_due_count,
                "canceled_subscriptions": canceled_count,
                "total_users": total_users,
                "churn_rate": churn_rate,
                "trial_conversion_rate": trial_conversion_rate,
                "currency": mrr_currency,
            }

        return await _compute()

    # =========================================================================
    # 9.7.2 — Revenue Breakdown
    # =========================================================================

    @admin_read_rate_limit
    @http_get(
        "/metrics/revenue",
        response=AdminMetricsRevenueSchema,
        summary="Revenue breakdown",
        description=(
            "Return revenue breakdown by product, plan, and month (last 12 "
            "months). Uses the RevenueRecognitionEntry table for accurate "
            "daily recognized revenue."
        ),
    )
    async def metrics_revenue(
        self,
        request: HttpRequest,
        currency: Optional[str] = Query(
            None,
            description="Filter by currency (default: all currencies)",
        ),
    ):
        """Revenue breakdown by product, plan, and month.

        Queries the ``RevenueRecognitionEntry`` table which is populated by
        the daily ``recognize_revenue`` Celery task and the
        ``invoice.payment_succeeded`` webhook handler.

        Returns three breakdowns:
        - **by_product**: MRR and subscription counts per product.
        - **by_plan**: MRR contribution per plan.
        - **by_month**: Monthly revenue trend for the last 12 months,
          including new subscriptions, churned subscriptions, and net MRR
          change.
        """
        now = timezone.now()
        twelve_months_ago = now - timedelta(days=365)

        @sync_to_async
        def _compute():
            # --- By product ---
            product_qs = (
                RevenueRecognitionEntry.objects.filter(
                    recognized_date__gte=twelve_months_ago.date(),
                )
                .values(
                    product_id=F("subscription__product__id"),
                    product_name=F("subscription__product__name"),
                    product_slug=F("subscription__product__slug"),
                )
                .annotate(
                    revenue=Sum("amount_cents"),
                    active_subs=Count(
                        "subscription",
                        filter=Q(
                            subscription__status__in=(
                                SubscriptionStatus.ACTIVE,
                                SubscriptionStatus.TRIALING,
                            )
                        ),
                        distinct=True,
                    ),
                    trial_subs=Count(
                        "subscription",
                        filter=Q(subscription__status=SubscriptionStatus.TRIALING),
                        distinct=True,
                    ),
                )
                .order_by("-revenue")
            )

            by_product = []
            for row in product_qs:
                by_product.append({
                    "product_id": row["product_id"],
                    "product_name": row["product_name"],
                    "product_slug": row["product_slug"],
                    "mrr_cents": (row["revenue"] or 0),
                    "active_subscriptions": row["active_subs"] or 0,
                    "trial_subscriptions": row["trial_subs"] or 0,
                })

            # --- By plan ---
            plan_qs = (
                RevenueRecognitionEntry.objects.filter(
                    recognized_date__gte=twelve_months_ago.date(),
                )
                .values(
                    plan_id_val=F("plan__id"),
                    plan_name=F("plan__name"),
                    plan_slug=F("plan__slug"),
                    product_name=F("plan__product__name"),
                    price_cents=F("plan__price_cents"),
                )
                .annotate(
                    total_revenue=Sum("amount_cents"),
                    subscriber_count=Count(
                        "subscription",
                        filter=Q(
                            subscription__status__in=(
                                SubscriptionStatus.ACTIVE,
                                SubscriptionStatus.TRIALING,
                            )
                        ),
                        distinct=True,
                    ),
                )
                .order_by("-total_revenue")
            )

            by_plan = []
            for row in plan_qs:
                by_plan.append({
                    "plan_id": row["plan_id_val"],
                    "plan_name": row["plan_name"],
                    "plan_slug": row["plan_slug"],
                    "product_name": row["product_name"],
                    "price_cents": row["price_cents"] or 0,
                    "subscriber_count": row["subscriber_count"] or 0,
                    "mrr_contribution_cents": row["total_revenue"] or 0,
                })

            # --- By month (last 12 months) ---
            monthly_qs = (
                RevenueRecognitionEntry.objects.filter(
                    recognized_date__gte=twelve_months_ago.date(),
                )
                .annotate(month=TruncMonth("recognized_date"))
                .values("month")
                .annotate(
                    revenue=Sum("amount_cents"),
                )
                .order_by("month")
            )

            # For new_subs and churned_subs, query separately for accuracy
            by_month = []
            months = list(monthly_qs)

            for month_row in months:
                month_date = month_row["month"]
                month_start = month_date
                month_end = month_start + timedelta(days=31)

                new_subs = Subscription.objects.filter(
                    created_at__gte=month_start,
                    created_at__lt=month_end,
                ).count()

                churned_subs = Subscription.objects.filter(
                    canceled_at__gte=month_start,
                    canceled_at__lt=month_end,
                ).count()

                # Net MRR change: revenue this month - previous month
                prev_month = month_start - timedelta(days=32)
                prev_revenue = RevenueRecognitionEntry.objects.filter(
                    recognized_date__year=prev_month.year,
                    recognized_date__month=prev_month.month,
                ).aggregate(total=Sum("amount_cents"))["total"] or 0

                curr_revenue = month_row["revenue"] or 0

                by_month.append({
                    "month": month_date.strftime("%Y-%m"),
                    "revenue_cents": curr_revenue,
                    "new_subscriptions": new_subs,
                    "churned_subscriptions": churned_subs,
                    "net_mrr_change_cents": curr_revenue - prev_revenue,
                })

            return {
                "by_product": by_product,
                "by_plan": by_plan,
                "by_month": by_month,
            }

        return await _compute()

    # =========================================================================
    # 9.7.3 — Subscription Funnel
    # =========================================================================

    @admin_read_rate_limit
    @http_get(
        "/metrics/subscriptions",
        response=AdminMetricsSubscriptionFunnelSchema,
        summary="Subscription funnel",
        description=(
            "Return subscription funnel metrics for conversion analysis: "
            "registrations, trial starts, trial conversions, cancellations, "
            "past-due transitions, and recoveries. Supports filtering by "
            "analysis period (default 30 days)."
        ),
    )
    async def metrics_subscriptions(
        self,
        request: HttpRequest,
        period_days: int = Query(
            30,
            ge=1,
            le=365,
            description="Analysis period in days",
        ),
    ):
        """Subscription funnel metrics.

        Tracks the full subscription lifecycle over the analysis period:
        new user registrations, trial starts, trial-to-paid conversions,
        active-to-canceled transitions, active-to-past-due transitions,
        and past-due-to-active recoveries.

        Also provides a per-product breakdown of the funnel metrics.
        """
        now = timezone.now()
        period_start = now - timedelta(days=period_days)

        @sync_to_async
        def _compute():
            # --- New registrations ---
            new_registrations = User.objects.filter(
                created_at__gte=period_start,
            ).count()

            # --- Trial starts ---
            trial_starts = Subscription.objects.filter(
                trial_start__gte=period_start,
                trial_start__lt=now,
            ).count()

            # --- Trial conversions: trials that became active/paid ---
            trial_conversions = Subscription.objects.filter(
                trial_start__gte=period_start,
                trial_start__lt=now,
                status=SubscriptionStatus.ACTIVE,
            ).exclude(
                trial_end__isnull=True,
            ).count()

            trial_conversion_rate = (
                round(trial_conversions / trial_starts, 4)
                if trial_starts > 0
                else 0.0
            )

            # --- Active to canceled ---
            active_to_canceled = Subscription.objects.filter(
                canceled_at__gte=period_start,
                canceled_at__lt=now,
            ).count()

            # --- Active to past due ---
            active_to_past_due = Subscription.objects.filter(
                past_due_at__gte=period_start,
                past_due_at__lt=now,
            ).count()

            # --- Past due to active (recovery) ---
            # Subscriptions that are currently active but had a past_due_at
            # within the period (they recovered)
            past_due_to_active = Subscription.objects.filter(
                past_due_at__gte=period_start,
                past_due_at__lt=now,
                status=SubscriptionStatus.ACTIVE,
            ).count()

            # --- By product breakdown ---
            products = Product.objects.filter(is_active=True)
            by_product = []

            for product in products:
                prod_trial_starts = Subscription.objects.filter(
                    product=product,
                    trial_start__gte=period_start,
                    trial_start__lt=now,
                ).count()

                prod_conversions = Subscription.objects.filter(
                    product=product,
                    trial_start__gte=period_start,
                    trial_start__lt=now,
                    status=SubscriptionStatus.ACTIVE,
                ).exclude(trial_end__isnull=True).count()

                prod_active = Subscription.objects.filter(
                    product=product,
                    status__in=(
                        SubscriptionStatus.ACTIVE,
                        SubscriptionStatus.TRIALING,
                    ),
                ).count()

                prod_canceled = Subscription.objects.filter(
                    product=product,
                    canceled_at__gte=period_start,
                    canceled_at__lt=now,
                ).count()

                prod_past_due = Subscription.objects.filter(
                    product=product,
                    past_due_at__gte=period_start,
                    past_due_at__lt=now,
                ).count()

                by_product.append({
                    "product_id": product.id,
                    "product_name": product.name,
                    "product_slug": product.slug,
                    "trial_starts": prod_trial_starts,
                    "trial_conversions": prod_conversions,
                    "active_subscribers": prod_active,
                    "canceled": prod_canceled,
                    "past_due": prod_past_due,
                })

            return {
                "period_days": period_days,
                "new_registrations": new_registrations,
                "trial_starts": trial_starts,
                "trial_conversions": trial_conversions,
                "trial_conversion_rate": trial_conversion_rate,
                "active_to_canceled": active_to_canceled,
                "active_to_past_due": active_to_past_due,
                "past_due_to_active": past_due_to_active,
                "by_product": by_product,
            }

        return await _compute()

    # =========================================================================
    # 9.7.4 — Per-Product Metrics
    # =========================================================================

    @admin_read_rate_limit
    @http_get(
        "/metrics/products",
        response=AdminMetricsProductsSchema,
        summary="Per-product metrics",
        description=(
            "Return per-product metrics: total subscribers, active subscribers, "
            "MRR, and plan distribution (count per plan)."
        ),
    )
    async def metrics_products(
        self,
        request: HttpRequest,
    ):
        """Per-product metrics summary.

        For each product, returns:
        - Total subscriber count (all statuses)
        - Active subscriber count (active + trialing)
        - MRR contribution (from revenue recognition entries)
        - Plan distribution: count of active subscriptions per plan
        """
        @sync_to_async
        def _compute():
            products = Product.objects.all().order_by("name")
            result = []

            for product in products:
                # Total subscribers (all statuses)
                total_subscribers = Subscription.objects.filter(
                    product=product,
                ).count()

                # Active subscribers
                active_subscribers = Subscription.objects.filter(
                    product=product,
                    status__in=(
                        SubscriptionStatus.ACTIVE,
                        SubscriptionStatus.TRIALING,
                    ),
                ).count()

                # MRR: sum of active plan prices (monthly equivalent)
                mrr_data = Subscription.objects.filter(
                    product=product,
                    status=SubscriptionStatus.ACTIVE,
                ).values("plan__billing_cycle").annotate(
                    total=Sum("plan__price_cents"),
                )

                mrr_cents = 0
                for row in mrr_data:
                    total = row["total"] or 0
                    if row["plan__billing_cycle"] == "yearly":
                        mrr_cents += total // 12
                    elif row["plan__billing_cycle"] != "lifetime":
                        mrr_cents += total

                # Plan distribution
                plans = Plan.objects.filter(product=product).order_by(
                    "sort_order", "price_cents"
                )
                plan_distribution = []
                for plan in plans:
                    count = Subscription.objects.filter(
                        plan=plan,
                        status__in=(
                            SubscriptionStatus.ACTIVE,
                            SubscriptionStatus.TRIALING,
                        ),
                    ).count()
                    plan_distribution.append({
                        "plan_name": plan.name,
                        "plan_slug": plan.slug,
                        "count": count,
                    })

                result.append({
                    "id": product.id,
                    "name": product.name,
                    "slug": product.slug,
                    "total_subscribers": total_subscribers,
                    "active_subscribers": active_subscribers,
                    "mrr_cents": mrr_cents,
                    "plan_distribution": plan_distribution,
                })

            return {"products": result}

        return await _compute()

    # =========================================================================
    # 9.7.5 — Admin Audit Log
    # =========================================================================

    @admin_read_rate_limit
    @http_get(
        "/audit-log",
        response=PaginatedResponse[AdminAuditLogItemSchema],
        summary="List admin audit log",
        description=(
            "Return paginated list of admin actions. Filterable by admin user, "
            "action type, and date range. Ordered by most recent first."
        ),
    )
    async def list_audit_log(
        self,
        request: HttpRequest,
        admin_user_id: Optional[int] = Query(
            None,
            description="Filter by admin user ID",
        ),
        action: Optional[str] = Query(
            None,
            description="Filter by action type (e.g. 'product.create')",
        ),
        date_from: Optional[datetime] = Query(
            None,
            description="Filter from date (ISO format)",
        ),
        date_to: Optional[datetime] = Query(
            None,
            description="Filter to date (ISO format)",
        ),
        pagination: PaginationInput = Query(...),
    ):
        """List admin audit log entries.

        Returns a paginated list of admin actions, most recent first.
        Each entry includes the admin's email, action type, HTTP method,
        API path, IP address, response status code, and action details.

        Supports filtering by:
        - **admin_user_id**: Only show actions by a specific admin.
        - **action**: Filter by action prefix (e.g., 'product' matches
          'product.create', 'product.update', etc.).
        - **date_from/date_to**: Restrict to a date range.
        """
        qs = AdminAuditLog.objects.select_related("admin_user").order_by(
            "-created_at"
        )

        if admin_user_id is not None:
            qs = qs.filter(admin_user_id=admin_user_id)

        if action is not None:
            qs = qs.filter(action__icontains=action)

        if date_from is not None:
            qs = qs.filter(created_at__gte=date_from)

        if date_to is not None:
            qs = qs.filter(created_at__lte=date_to)

        from common.utils import get_paginated_data_async

        results, meta = await get_paginated_data_async(
            qs, pagination.page, pagination.page_size
        )

        items = []
        for entry in results:
            items.append({
                "id": entry.id,
                "admin_user_id": entry.admin_user_id,
                "admin_email": (
                    entry.admin_user.email if entry.admin_user else "system"
                ),
                "action": entry.action,
                "method": entry.method,
                "path": entry.path,
                "ip_address": entry.ip_address,
                "status_code": entry.status_code,
                "details": entry.details or {},
                "timestamp": entry.created_at,
            })

        return {"meta": meta, "results": items}

    # =========================================================================
    # 9.7.6 — Webhook Event Monitoring
    # =========================================================================

    @admin_read_rate_limit
    @http_get(
        "/webhooks",
        response=AdminWebhookEventListSchema,
        summary="List webhook events",
        description=(
            "Return paginated list of Stripe webhook events. Filterable by "
            "event type and processed status. Includes failed count for "
            "monitoring."
        ),
    )
    async def list_webhooks(
        self,
        request: HttpRequest,
        event_type: Optional[str] = Query(
            None,
            description="Filter by Stripe event type (e.g. 'invoice.payment_succeeded')",
        ),
        processed: Optional[bool] = Query(
            None,
            description="Filter by processed status (true/false)",
        ),
        pagination: PaginationInput = Query(...),
    ):
        """List Stripe webhook event log entries.

        Returns a paginated list of all webhook events received from Stripe.
        Each entry includes the Stripe event ID, event type, processing
        status, error message (if any), and timestamp.

        Supports filtering by:
        - **event_type**: Exact match on Stripe event type.
        - **processed**: Boolean filter — True for successfully processed,
          False for failed events.

        The response includes a ``failed_count`` field indicating how many
        entries in the current page have failed processing, making it easy
        to spot issues at a glance.
        """
        qs = WebhookEventLog.objects.all().order_by("-created_at")

        if event_type is not None:
            qs = qs.filter(event_type=event_type)

        if processed is not None:
            qs = qs.filter(processed=processed)

        from common.utils import get_paginated_data_async

        results, meta = await get_paginated_data_async(
            qs, pagination.page, pagination.page_size
        )

        items = []
        failed_count = 0
        for entry in results:
            if not entry.processed:
                failed_count += 1

            items.append({
                "id": entry.id,
                "event_id": entry.event_id,
                "event_type": entry.event_type,
                "processed": entry.processed,
                "error_message": entry.error_message or "",
                "created_at": entry.created_at,
            })

        return {
            "items": items,
            "total": meta["total_items"],
            "failed_count": failed_count,
        }

    # =========================================================================
    # 9.7.7 — Retry Failed Webhook
    # =========================================================================

    @admin_write_rate_limit
    @http_post(
        "/webhooks/{event_id}/retry",
        response={200: dict, 404: dict, 400: dict},
        summary="Retry failed webhook",
        description=(
            "Re-process a failed Stripe webhook event. Only events that "
            "have not been successfully processed can be retried. Calls "
            "the existing process_event handler from the webhook router."
        ),
    )
    async def retry_webhook(
        self,
        request: HttpRequest,
        event_id: int,
    ):
        """Retry a failed webhook event.

        Looks up the ``WebhookEventLog`` entry by ID and, if the event
        has not been successfully processed, re-dispatches it to the
        appropriate webhook handler via ``process_event``.

        Returns the updated event status, event type, and any error
        message. If the event was already processed, returns an error.
        """
        @sync_to_async
        def _get_event():
            try:
                return WebhookEventLog.objects.get(pk=event_id)
            except WebhookEventLog.DoesNotExist:
                return None

        event_log = await _get_event()
        if event_log is None:
            raise NotFoundException("Webhook event not found.")

        if event_log.processed:
            raise BadRequestException(
                f"Event {event_log.event_id} has already been processed "
                f"successfully. Retrying is not needed."
            )

        if not event_log.payload:
            raise BadRequestException(
                f"Event {event_log.event_id} has no stored payload. "
                f"Cannot retry."
            )

        # Re-process the event using the existing webhook router
        from .stripe.webhooks.router import process_event

        try:
            await sync_to_async(process_event)(event_log.payload)

            # Refresh from DB to get the updated processed status
            event_log = await sync_to_async(
                lambda: WebhookEventLog.objects.get(pk=event_id)
            )()

            logger.info(
                "ADMIN_WEBHOOK_RETRY: event_id=%s, type=%s, "
                "processed=%s, retried_by=%s, ip=%s",
                event_log.event_id,
                event_log.event_type,
                event_log.processed,
                request.user.email,
                request.META.get("REMOTE_ADDR"),
            )

            return {
                "id": event_log.id,
                "event_id": event_log.event_id,
                "event_type": event_log.event_type,
                "processed": event_log.processed,
                "error_message": event_log.error_message or "",
                "message": (
                    "Webhook event re-processed successfully."
                    if event_log.processed
                    else "Webhook event re-processing failed. "
                       "Check the error message for details."
                ),
            }
        except Exception as e:
            logger.error(
                "ADMIN_WEBHOOK_RETRY_FAILED: event_id=%s, error=%s, "
                "retried_by=%s, ip=%s",
                event_log.event_id,
                str(e),
                request.user.email,
                request.META.get("REMOTE_ADDR"),
            )

            return {
                "id": event_log.id,
                "event_id": event_log.event_id,
                "event_type": event_log.event_type,
                "processed": False,
                "error_message": str(e)[:500],
                "message": f"Webhook event re-processing failed: {str(e)[:200]}",
            }
