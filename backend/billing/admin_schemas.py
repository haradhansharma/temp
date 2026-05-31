"""Pydantic schemas for the admin API endpoints (Phase 9).

These schemas define the request/response contracts for all admin-only
billing endpoints. They extend and reuse the public schemas from
``billing.schemas`` where appropriate, adding admin-specific fields like
annotated counts, audit metadata, and bulk operation payloads.

All admin endpoints require ``is_staff=True`` and every mutation is
audit-logged via the ``@log_admin_access`` decorator.
"""

from typing import Optional, Any
from datetime import datetime, date
from ninja import Schema
from pydantic import Field

from .schemas import (
    AccessEntryOutputSchema,
    PlanOutputSchema,
    PlanDetailSchema,
    ProductOutputSchema,
    ServiceDomainOutputSchema,
)

# =============================================================================
# 9.1.2 — Product Schemas
# =============================================================================


class AdminProductCreateSchema(Schema):
    """Input schema for creating a new product."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Product display name, e.g. 'Satta Finance'",
    )
    slug: Optional[str] = Field(
        None,
        max_length=50,
        description=(
            "URL-safe identifier. Auto-generated from name if not provided. "
            "Must be unique across all products."
        ),
    )
    description: str = Field(
        "",
        description="Product description shown to users",
    )
    home_url: str = Field(
        "",
        description="Landing page URL for this service",
    )


class AdminProductUpdateSchema(Schema):
    """Input schema for updating an existing product. All fields optional."""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    slug: Optional[str] = Field(None, max_length=50)
    description: Optional[str] = Field(None)
    home_url: Optional[str] = Field(None)
    is_active: Optional[bool] = Field(
        None,
        description="Activate or deactivate the product",
    )


class AdminProductListItemSchema(ProductOutputSchema):
    """Product in admin list view with annotated counts."""

    plan_count: int = Field(
        0,
        description="Total number of plans (active + inactive) for this product",
    )
    active_plan_count: int = Field(
        0,
        description="Number of active plans",
    )
    subscriber_count: int = Field(
        0,
        description="Total active subscriptions across all plans",
    )
    domain_count: int = Field(
        0,
        description="Number of registered service domains",
    )
    stripe_product_id: Optional[str] = Field(
        None,
        description="Stripe Product ID (set when first paid plan is created)",
    )


class AdminProductDetailSchema(AdminProductListItemSchema):
    """Full product detail with plans and service domains for admin view."""

    plans: list[PlanOutputSchema] = Field(
        default_factory=list,
        description="All plans for this product",
    )
    service_domains: list[ServiceDomainOutputSchema] = Field(
        default_factory=list,
        description="All registered service domains",
    )


# =============================================================================
# 9.1.3 — Plan Schemas
# =============================================================================


class AdminPlanCreateSchema(Schema):
    """Input schema for creating a new plan under a product."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Plan name, e.g. 'Free', 'Standard', 'Pro'",
    )
    slug: Optional[str] = Field(
        None,
        max_length=50,
        description=(
            "URL-safe identifier. Auto-generated from name if not provided. "
            "Must be unique within the product."
        ),
    )
    description: str = Field(
        "",
        description="Plan description shown to users",
    )
    price_cents: int = Field(
        0,
        ge=0,
        description="Price in cents (0 = free plan). 900 = $9.00",
    )
    currency: str = Field(
        "USD",
        max_length=3,
        description="ISO 4217 currency code",
    )
    billing_cycle: str = Field(
        "monthly",
        description="Billing frequency: monthly, yearly, or lifetime",
    )
    trial_days: int = Field(
        0,
        ge=0,
        description="Free trial duration in days (0 = no trial)",
    )
    features: dict[str, Any] = Field(
        default_factory=dict,
        description="Public feature list for display, e.g. {'reports': 'Advanced'}",
    )
    sort_order: int = Field(
        0,
        ge=0,
        description="Display order (lower = first)",
    )
    is_active: bool = Field(
        True,
        description="Whether this plan is available for new subscriptions",
    )
    is_featured: bool = Field(
        False,
        description="Highlight this plan in comparison UI",
    )
    tax_inclusive: bool = Field(
        False,
        description="Whether the displayed price already includes tax",
    )


class AdminPlanUpdateSchema(Schema):
    """Input schema for updating an existing plan. All fields optional."""

    name: Optional[str] = Field(None, min_length=1, max_length=50)
    slug: Optional[str] = Field(None, max_length=50)
    description: Optional[str] = Field(None)
    price_cents: Optional[int] = Field(None, ge=0)
    currency: Optional[str] = Field(None, max_length=3)
    billing_cycle: Optional[str] = Field(None)
    trial_days: Optional[int] = Field(None, ge=0)
    features: Optional[dict[str, Any]] = Field(None)
    sort_order: Optional[int] = Field(None, ge=0)
    is_active: Optional[bool] = Field(None)
    is_featured: Optional[bool] = Field(None)
    tax_inclusive: Optional[bool] = Field(None)


class AdminPlanListItemSchema(PlanOutputSchema):
    """Plan in admin list view with annotated subscriber count."""

    product_id: int = Field(..., description="Parent product ID")
    product_name: str = Field(..., description="Parent product name")
    subscriber_count: int = Field(
        0,
        description="Number of active subscriptions on this plan",
    )
    stripe_price_id: Optional[str] = Field(
        None,
        description="Stripe Price ID (null for free plans)",
    )
    tax_inclusive: bool = Field(
        False,
        description="Whether the price includes tax",
    )


class AdminPlanDetailSchema(AdminPlanListItemSchema):
    """Full plan detail with access entries for admin view."""

    access_entries: list[AccessEntryOutputSchema] = Field(
        default_factory=list,
        description="Access entries defining what this plan grants",
    )


class AdminPlanDuplicateSchema(Schema):
    """Input schema for duplicating a plan."""

    name: Optional[str] = Field(
        None,
        max_length=50,
        description=(
            "Name for the duplicated plan. Defaults to '{original} (Copy)' "
            "if not provided."
        ),
    )


# =============================================================================
# 9.1.4 — Access Entry Schemas
# =============================================================================


class AdminAccessEntryCreateSchema(Schema):
    """Input schema for creating a single access entry on a plan."""

    key: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Feature identifier, e.g. 'reports', 'max_accounts'",
    )
    value: str = Field(
        ...,
        max_length=255,
        description="Access value, e.g. 'true', '5', '1000'",
    )
    value_type: str = Field(
        "string",
        description="How the value is cast: string, boolean, or integer",
    )
    description: str = Field(
        "",
        description="Human-readable description of this access entry",
    )


class AdminAccessEntryUpdateSchema(Schema):
    """Input schema for updating an existing access entry."""

    key: Optional[str] = Field(None, min_length=1, max_length=100)
    value: Optional[str] = Field(None, max_length=255)
    value_type: Optional[str] = Field(None)
    description: Optional[str] = Field(None)


class AdminAccessEntryItemSchema(AccessEntryOutputSchema):
    """Access entry with ID and value_type for admin views."""

    id: int
    plan_id: int
    value_type: str = Field(
        "string",
        description="Declared value type: string, boolean, or integer",
    )


class AdminAccessEntryBulkItemSchema(Schema):
    """Single item in the bulk access entry update payload."""

    key: str = Field(
        ...,
        min_length=1,
        max_length=100,
    )
    value: str = Field(
        ...,
        max_length=255,
    )
    value_type: str = Field(
        "string",
    )
    description: str = Field(
        "",
    )


class AdminAccessEntryBulkSchema(Schema):
    """Input schema for bulk-replacing all access entries on a plan.

    Deletes all existing entries for the plan, then creates the provided
    entries in a single database transaction.
    """

    entries: list[AdminAccessEntryBulkItemSchema] = Field(
        ...,
        description="Complete list of access entries to set on the plan",
    )


class AdminAccessMatrixRowSchema(Schema):
    """One row in the access comparison matrix (one access key across plans)."""

    key: str = Field(..., description="Access key identifier")
    description: Optional[str] = Field(
        None,
        description="Description from the first plan that defines this key",
    )
    values: dict[str, Any] = Field(
        default_factory=dict,
        description="Map of plan slug to value for this key",
    )
    entry_ids: dict[str, Any] = Field(
        default_factory=dict,
        description="Map of plan slug to access entry ID (null if not defined for that plan)",
    )


class AdminAccessMatrixSchema(Schema):
    """Feature comparison matrix across all plans of a product.

    Rows = unique access keys across all plans.
    Columns = plan slugs.
    Cells = typed values or null if not defined for that plan.
    """

    product_id: int
    product_name: str
    plans: list[dict[str, Any]] = Field(
        default_factory=list,
        description="List of {slug, name, is_active} for column headers",
    )
    rows: list[AdminAccessMatrixRowSchema] = Field(
        default_factory=list,
        description="Access key rows with per-plan values",
    )


class AdminAccessMatrixRowEntrySchema(Schema):
    """Single plan entry in a matrix row save request."""

    plan_id: int = Field(
        ...,
        description="Plan ID to set this entry on",
    )
    value: str = Field(
        ...,
        max_length=255,
        description="Access value as a string, e.g. 'true', '5', 'unlimited'",
    )
    value_type: str = Field(
        "string",
        description="How the value is cast: string, boolean, or integer",
    )


class AdminAccessMatrixRowSaveSchema(Schema):
    """Input schema for atomically saving a single access key across all plans.

    Creates/updates entries for the listed plans and removes the key from
    any plan of the same product that is NOT listed. If ``original_key`` is
    provided and differs from ``key``, all entries with ``original_key`` are
    renamed to ``key`` before the upsert.

    All operations run inside a single database transaction, so the matrix
    is never left in a partial state.
    """

    original_key: Optional[str] = Field(
        None,
        min_length=1,
        max_length=100,
        description=(
            "Original key name when renaming. If omitted or equal to ``key``, "
            "no rename occurs."
        ),
    )
    key: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Access key identifier",
    )
    description: str = Field(
        "",
        description="Human-readable description of this access key",
    )
    entries: list[AdminAccessMatrixRowEntrySchema] = Field(
        ...,
        description=(
            "Per-plan entries. Plans of this product NOT listed here will "
            "have the key removed. Plans listed here will be created or updated."
        ),
    )


# =============================================================================
# 9.1.7 — Credit Pool Schemas
# =============================================================================


class AdminCreditPurchaseSchema(Schema):
    """Input schema for admin creating a credit purchase record.

    This records a manual/offline payment and activates credits immediately.
    """

    user_email: str = Field(
        ...,
        description="Email of the user receiving credits",
        examples=["user@example.com"],
    )
    product_slug: str = Field(
        ...,
        description="Product slug",
        examples=["finance"],
    )
    plan_slug: str = Field(
        ...,
        description="Plan slug",
        examples=["standard"],
    )
    amount_cents: int = Field(
        ...,
        ge=0,
        description="Amount paid in cents (e.g. 900 = $9.00)",
        examples=[900],
    )
    currency: str = Field("USD", max_length=3, description="ISO 4217 currency code")
    source: str = Field(
        "manual",
        description="Payment source: manual, local_gateway, bank_transfer, cash",
    )
    payment_reference: str = Field(
        "",
        description="Bank reference, TXN ID, or admin note",
        examples=["TXN-20260529-001"],
    )
    tax_cents: int = Field(
        0,
        ge=0,
        description="Tax amount in cents for compliance reporting",
    )
    notes: str = Field(
        "",
        description="Admin internal notes (not shown to user)",
    )


class AdminCreditRefundSchema(Schema):
    """Input schema for refunding a credit pool."""

    reason: str = Field(
        ...,
        description="Reason for the refund (audit trail)",
        examples=["Service discontinued"],
    )


class AdminCreditAdjustSchema(Schema):
    """Input schema for adjusting a credit pool balance."""

    periods_delta: int = Field(
        ...,
        description="Positive to add periods, negative to remove",
    )
    reason: str = Field(
        ...,
        description="Reason for the adjustment (audit trail)",
    )
    amount_cents_delta: Optional[int] = Field(
        None,
        description="Monetary equivalent of the adjustment (positive or negative)",
    )



class AdminSubscriptionListItemSchema(Schema):
    """Subscription in admin list view with user and product info."""

    id: int
    user_id: int
    user_email: str = Field(..., description="Email of the subscribed user")
    user_name: Optional[str] = Field(None, description="Full name of the user")
    product_id: int
    product_name: str
    product_slug: str
    plan_id: int
    plan_name: str
    plan_slug: str
    status: str
    currency: Optional[str] = None
    current_period_start: Optional[datetime] = None
    current_period_end: Optional[datetime] = None
    cancel_at_period_end: bool = False
    dunning_step: int = Field(
        0,
        description="Current dunning workflow step (0=none)",
    )
    stripe_subscription_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class AdminSubscriptionDetailSchema(AdminSubscriptionListItemSchema):
    """Full subscription detail for admin view."""

    trial_start: Optional[datetime] = None
    trial_end: Optional[datetime] = None
    canceled_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    past_due_at: Optional[datetime] = None
    has_used_trial: bool = False
    tos_accepted_at: Optional[datetime] = None
    tos_version: Optional[str] = None
    last_dunning_email_at: Optional[datetime] = None
    stripe_customer_id: Optional[str] = None
    access: dict[str, Any] = Field(
        default_factory=dict,
        description="Flat access map from the plan's access entries",
    )


class AdminSubscriptionOverrideSchema(Schema):
    """Input schema for admin overriding a subscription's plan or status.

    Used for manual corrections, grace periods, or support escalations.
    All mutations are audit-logged with before/after state.
    """

    plan_id: Optional[int] = Field(
        None,
        description="New plan ID. Must belong to the same product.",
    )
    status: Optional[str] = Field(
        None,
        description="New status: active, past_due, canceled, trialing, paused, expired",
    )
    period_start: Optional[datetime] = Field(
        None,
        description="Override billing period start",
    )
    period_end: Optional[datetime] = Field(
        None,
        description="Override billing period end",
    )
    reason: str = Field(
        "",
        description="Reason for the override (audit trail)",
    )


class AdminSubscriptionExtendSchema(Schema):
    """Input schema for extending a subscription's billing period."""

    days: int = Field(
        ...,
        ge=1,
        le=730,
        description="Number of days to extend the current period end by",
    )
    reason: str = Field(
        "",
        description="Reason for the extension (audit trail)",
    )


class AdminPlanChangeLogItemSchema(Schema):
    """Plan change history entry for admin view."""

    id: int
    from_plan_id: int
    from_plan_name: str
    to_plan_id: int
    to_plan_name: str
    proration_amount_cents: int = Field(
        0,
        description="Proration amount in cents (negative = credit)",
    )
    currency: str
    stripe_proration_id: Optional[str] = None
    proration_behavior: str
    initiated_by_id: Optional[int] = None
    initiated_by_email: Optional[str] = None
    created_at: Optional[datetime] = None


# =============================================================================
# 9.1.6 — User Schemas (Admin View)
# =============================================================================


class AdminUserListItemSchema(Schema):
    """User in admin list view with subscription count and last activity."""

    id: int
    email: str
    first_name: str = ""
    last_name: str = ""
    full_name: str = ""
    is_active: bool
    is_email_verified: bool = Field(
        False,
        description="Whether the user has verified their email address",
    )
    is_staff: bool = Field(
        False,
        description="Whether the user has admin access",
    )
    role: str = Field(
        "member",
        description="User role: owner, admin, or member",
    )
    avatar: Optional[str] = None
    subscription_count: int = Field(
        0,
        description="Total subscriptions across all products",
    )
    active_subscription_count: int = Field(
        0,
        description="Number of active/trialing subscriptions",
    )
    last_login_at: Optional[datetime] = Field(
        None,
        description="Timestamp of the most recent login",
    )
    created_at: Optional[datetime] = None


class AdminUserSubscriptionItemSchema(Schema):
    """Simplified subscription info embedded in admin user detail."""

    id: int
    product_name: str
    product_slug: str
    plan_name: str
    plan_slug: str
    status: str
    current_period_end: Optional[datetime] = None
    cancel_at_period_end: bool = False
    created_at: Optional[datetime] = None


class AdminUserDetailSchema(AdminUserListItemSchema):
    """Full user detail for admin view with all subscriptions."""

    phone: Optional[str] = None
    timezone: Optional[str] = None
    currency: Optional[str] = None
    language: Optional[str] = None
    subscriptions: list[AdminUserSubscriptionItemSchema] = Field(
        default_factory=list,
        description="All subscriptions across products",
    )


class AdminUserStatusUpdateSchema(Schema):
    """Input schema for activating/deactivating a user account."""

    is_active: bool = Field(
        ...,
        description="Whether the user account should be active",
    )
    reason: str = Field(
        "",
        description="Reason for the status change (audit trail)",
    )


class AdminUserRoleUpdateSchema(Schema):
    """Input schema for changing a user's role."""

    role: str = Field(
        ...,
        description="New role: owner, admin, or member",
    )
    reason: str = Field(
        "",
        description="Reason for the role change (audit trail)",
    )


class AdminAuditEventSchema(Schema):
    """Single audit event item for user audit trail."""

    event_type: str = Field(
        ...,
        description="Type of event: login, plan_change, subscription_status, refund",
    )
    description: str = Field(
        ...,
        description="Human-readable description of what happened",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Event-specific details (e.g. old_plan, new_plan, amount)",
    )
    ip_address: Optional[str] = None
    timestamp: Optional[datetime] = None


# =============================================================================
# 9.1.7 — Refund Schemas
# =============================================================================


class AdminRefundListItemSchema(Schema):
    """Refund in admin list view with user and approval info."""

    id: int
    subscription_id: int
    user_email: str = Field(..., description="Email of the subscribed user")
    product_name: Optional[str] = None
    plan_name: Optional[str] = None
    stripe_refund_id: Optional[str] = None
    stripe_charge_id: str = ""
    amount_cents: int
    currency: str
    reason: str = ""
    status: str = Field(
        ...,
        description="Refund status: pending, completed, failed",
    )
    reason_category: str = ""
    initiated_by_id: Optional[int] = None
    initiated_by_email: Optional[str] = None
    initiated_by_ip: Optional[str] = None
    approved_by_id: Optional[int] = None
    approved_by_email: Optional[str] = None
    approved_at: Optional[datetime] = None
    admin_notes: str = ""
    created_at: Optional[datetime] = None


class AdminRefundDetailSchema(AdminRefundListItemSchema):
    """Full refund detail for admin view."""

    stripe_response: dict[str, Any] = Field(
        default_factory=dict,
        description="Full Stripe Refund API response for audit",
    )


class AdminRefundApprovalSchema(Schema):
    """Input schema for approving or rejecting a pending refund.

    Enforces the two-person rule: the approver cannot be the same person
    who initiated the refund.
    """

    approved: bool = Field(
        ...,
        description="True to approve the refund, False to reject it",
    )
    notes: str = Field(
        "",
        description="Notes on the approval/rejection decision",
    )


# =============================================================================
# 9.1.8 — Metrics Schemas
# =============================================================================


class AdminMetricsOverviewSchema(Schema):
    """Key business metrics for the admin dashboard."""

    mrr_cents: int = Field(
        0,
        description="Monthly Recurring Revenue in cents (sum of active plan prices)",
    )
    mrr_display: str = Field(
        "$0.00",
        description="Formatted MRR string with currency symbol",
    )
    active_subscriptions: int = Field(
        0,
        description="Total active + trialing subscriptions",
    )
    trial_subscriptions: int = Field(
        0,
        description="Subscriptions currently in trial period",
    )
    past_due_subscriptions: int = Field(
        0,
        description="Subscriptions with past-due payments",
    )
    canceled_subscriptions: int = Field(
        0,
        description="Subscriptions canceled but not yet expired",
    )
    total_users: int = Field(
        0,
        description="Total registered user accounts",
    )
    churn_rate: float = Field(
        0.0,
        description=(
            "Churn rate: subscriptions canceled in last 30 days "
            "divided by total active 30 days ago"
        ),
    )
    trial_conversion_rate: float = Field(
        0.0,
        description="Percentage of trials that converted to paid subscriptions",
    )
    currency: str = Field(
        "USD",
        description="Currency of the MRR calculation",
    )


class AdminMetricsRevenueByProductSchema(Schema):
    """Revenue breakdown for a single product."""

    product_id: int
    product_name: str
    product_slug: str
    mrr_cents: int = Field(
        0,
        description="Monthly Recurring Revenue for this product in cents",
    )
    active_subscriptions: int = 0
    trial_subscriptions: int = 0


class AdminMetricsRevenueByPlanSchema(Schema):
    """Revenue breakdown for a single plan."""

    plan_id: int
    plan_name: str
    plan_slug: str
    product_name: str
    price_cents: int
    subscriber_count: int = 0
    mrr_contribution_cents: int = Field(
        0,
        description="MRR contributed by this plan (price x subscribers)",
    )


class AdminMetricsRevenueByMonthSchema(Schema):
    """Revenue for a single month."""

    month: str = Field(
        ...,
        description="Month in YYYY-MM format",
    )
    revenue_cents: int = Field(
        0,
        description="Recognized revenue in cents for this month",
    )
    new_subscriptions: int = Field(
        0,
        description="New subscriptions started this month",
    )
    churned_subscriptions: int = Field(
        0,
        description="Subscriptions churned this month",
    )
    net_mrr_change_cents: int = Field(
        0,
        description="Net MRR change from previous month in cents",
    )


class AdminMetricsRevenueSchema(Schema):
    """Full revenue breakdown by product, plan, and period."""

    by_product: list[AdminMetricsRevenueByProductSchema] = Field(
        default_factory=list,
        description="Revenue breakdown per product",
    )
    by_plan: list[AdminMetricsRevenueByPlanSchema] = Field(
        default_factory=list,
        description="Revenue breakdown per plan",
    )
    by_month: list[AdminMetricsRevenueByMonthSchema] = Field(
        default_factory=list,
        description="Monthly revenue trend (last 12 months)",
    )


class AdminMetricsSubscriptionFunnelSchema(Schema):
    """Subscription funnel metrics for conversion analysis."""

    period_days: int = Field(
        30,
        description="Analysis period in days",
    )
    new_registrations: int = Field(
        0,
        description="New user registrations in the period",
    )
    trial_starts: int = Field(
        0,
        description="Subscriptions that entered trial in the period",
    )
    trial_conversions: int = Field(
        0,
        description="Trials that converted to paid in the period",
    )
    trial_conversion_rate: float = Field(
        0.0,
        description="Trial to paid conversion rate percentage",
    )
    active_to_canceled: int = Field(
        0,
        description="Active subscriptions canceled in the period",
    )
    active_to_past_due: int = Field(
        0,
        description="Active subscriptions that became past due in the period",
    )
    past_due_to_active: int = Field(
        0,
        description="Past due subscriptions that recovered in the period",
    )
    by_product: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Funnel breakdown per product",
    )


class AdminMetricsProductsSchema(Schema):
    """Per-product metrics summary."""

    products: list[dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "List of product metrics: {id, name, slug, total_subscribers, "
            "active_subscribers, mrr_cents, plan_distribution: [{plan_name, count}]}"
        ),
    )


# =============================================================================
# 9.1.9 — Audit Log Schemas
# =============================================================================


class AdminAuditLogItemSchema(Schema):
    """Single admin action audit log entry."""

    id: int
    admin_user_id: int
    admin_email: str = Field(
        ...,
        description="Email of the admin who performed the action",
    )
    action: str = Field(
        ...,
        description="Action performed, e.g. 'product.create', 'plan.update'",
    )
    method: str = Field(
        ...,
        description="HTTP method: GET, POST, PUT, PATCH, DELETE",
    )
    path: str = Field(
        ...,
        description="API path that was called",
    )
    ip_address: Optional[str] = Field(
        None,
        description="IP address of the admin",
    )
    status_code: Optional[int] = Field(
        None,
        description="HTTP response status code",
    )
    details: Optional[dict[str, Any]] = Field(
        None,
        description="Additional details about the action (request body, changed fields)",
    )
    timestamp: datetime = Field(
        ...,
        description="When the action was performed",
    )


class AdminAuditLogListSchema(Schema):
    """Paginated admin audit log."""

    items: list[AdminAuditLogItemSchema] = Field(
        default_factory=list,
        description="Audit log entries",
    )
    total: int = Field(
        0,
        description="Total number of matching entries",
    )


# =============================================================================
# Webhook Event Log Schemas (admin view)
# =============================================================================


class AdminWebhookEventItemSchema(Schema):
    """Single webhook event for admin monitoring."""

    id: int
    event_id: str = Field(
        ...,
        description="Stripe event ID, e.g. evt_1Pxxx...",
    )
    event_type: str = Field(
        ...,
        description="Stripe event type, e.g. checkout.session.completed",
    )
    processed: bool = Field(
        ...,
        description="Whether this event has been successfully processed",
    )
    error_message: str = Field(
        "",
        description="Error message if processing failed",
    )
    created_at: Optional[datetime] = None


class AdminWebhookEventListSchema(Schema):
    """Paginated webhook event list for admin monitoring."""

    items: list[AdminWebhookEventItemSchema] = Field(
        default_factory=list,
    )
    total: int = 0
    failed_count: int = Field(
        0,
        description="Number of failed (unprocessed) events in this page",
    )


# =============================================================================
# Invoice Schemas (admin view)
# =============================================================================


class AdminInvoiceLineItemSchema(Schema):
    """Invoice line item for admin detail view."""

    id: int
    stripe_line_item_id: str = ""
    description: str = ""
    amount_cents: int = 0
    currency: str = "USD"
    quantity: int = 1
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
    proration: bool = False
    discount_amount_cents: int = 0
    tax_amount_cents: int = 0
    type: str = ""


class AdminInvoiceListItemSchema(Schema):
    """Invoice in admin list view."""

    id: int
    stripe_invoice_id: str
    subscription_id: int
    number: str = ""
    status: str
    amount_paid_cents: int = 0
    amount_due_cents: int = 0
    tax_cents: int = 0
    discount_cents: int = 0
    currency: str = "USD"
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
    hosted_url: str = ""
    pdf_url: str = ""
    stripe_fee_cents: int = 0
    attempt_count: int = 1
    created_at: Optional[datetime] = None


class AdminInvoiceDetailSchema(AdminInvoiceListItemSchema):
    """Full invoice detail with line items for admin view."""

    stripe_subscription_id: str = ""
    description: str = ""
    stripe_fee_currency: str = ""
    next_payment_attempt: Optional[datetime] = None
    line_items: list[AdminInvoiceLineItemSchema] = Field(
        default_factory=list,
        description="Individual line items from Stripe",
    )


# =============================================================================
# Service Domain Schemas (admin management)
# =============================================================================


class AdminDomainCreateSchema(Schema):
    """Input schema for adding a service domain to a product."""

    domain: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Service domain URL, e.g. 'finance.sattabase.tld'",
    )
    is_primary: bool = Field(
        False,
        description="Set as the primary domain for this product",
    )


class AdminDomainUpdateSchema(Schema):
    """Input schema for updating a service domain."""

    domain: Optional[str] = Field(None, min_length=1, max_length=255)
    is_primary: Optional[bool] = Field(None)
    is_active: Optional[bool] = Field(None)
