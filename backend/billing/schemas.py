"""Pydantic schemas for the billing app.

These schemas define the request/response contracts for all billing-related
API endpoints. They enforce validation and provide automatic OpenAPI documentation.
"""

from typing import Optional, Any
from datetime import datetime
from ninja import Schema, ModelSchema
from pydantic import Field

from users.schemas import UserOutputSchema
from .models import ServiceDomain, Product, Plan, AccessEntry, Subscription


# =============================================================================
# ServiceDomain Schemas
# =============================================================================


class ServiceDomainOutputSchema(Schema):
    """Service domain data for public listing and product details.

    Defined as a plain ``Schema`` (not ``ModelSchema``) because
    ``product_id`` is a database column name, not a Django model field.
    ``ModelSchema`` only recognizes the FK field name ``product``, but
    we want to return the integer ID (not the full nested Product object).
    """

    id: int
    domain: str
    product_id: int
    is_primary: bool
    is_active: bool


# =============================================================================
# Access Entry Schemas
# =============================================================================


class AccessEntryOutputSchema(Schema):
    """Single access entry in API responses."""

    key: str = Field(..., description="Feature identifier, e.g. 'reports'")
    value: Any = Field(..., description="Access value (bool, int, or str)")
    description: Optional[str] = Field(None, description="Human-readable description")


# =============================================================================
# Plan Schemas
# =============================================================================


class PlanOutputSchema(ModelSchema):
    """Plan data for public listing and subscription responses."""

    display_price: str
    is_free: bool
    # Currency conversion fields — populated when ?currency= param is provided
    converted_price_cents: Optional[int] = Field(
        None, description="Price converted to user's currency (cents)"
    )
    user_currency: Optional[str] = Field(
        None, description="ISO 4217 code of the user's preferred currency"
    )
    exchange_rate: Optional[str] = Field(
        None, description="Exchange rate used for conversion"
    )

    class Meta:
        model = Plan
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "price_cents",
            "currency",
            "billing_cycle",
            "trial_days",
            "features",
            "sort_order",
            "is_active",
            "is_featured",
        ]


class PlanDetailSchema(PlanOutputSchema):
    """Plan detail with access entries included."""

    access_entries: list[AccessEntryOutputSchema] = Field(
        default_factory=list,
        description="List of access entries defining what this plan grants",
    )


# =============================================================================
# Product Schemas
# =============================================================================


class ProductOutputSchema(ModelSchema):
    """Product data for public listing."""

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "home_url",
            "is_active",
            "created_at",
        ]


class ProductDetailSchema(ProductOutputSchema):
    """Product detail with plans and service domains included."""

    plans: list[PlanOutputSchema] = Field(
        default_factory=list,
        description="Available plans for this product",
    )
    service_domains: list[ServiceDomainOutputSchema] = Field(
        default_factory=list,
        description="Domains linked to this product",
    )


# =============================================================================
# Subscription Schemas
# =============================================================================


class SubscriptionInfoSchema(Schema):
    """Subscription summary returned in auth/me response."""

    plan_name: str = Field(..., description="Name of the current plan")
    plan_slug: str = Field(..., description="Slug of the current plan")
    status: str = Field(..., description="Subscription status")
    current_period_end: Optional[datetime] = Field(
        None, description="End of the current billing period"
    )
    trial_end: Optional[datetime] = Field(None, description="End of the trial period")
    is_active: bool = Field(..., description="Whether subscription grants access")
    is_credit_based: bool = Field(
        False,
        description="True if active via prepaid credits rather than Stripe subscription",
    )


class SubscriptionOutputSchema(Schema):
    """Full subscription data for management endpoints.

    Defined as a plain ``Schema`` because we need computed fields
    (``plan_name``, ``plan_slug``, ``product_name``, ``product_slug``)
    that don't exist on the model, plus ``user_id`` which is a database
    column name rather than a Django model field.
    """

    id: int
    user_id: int
    status: str
    cancel_at_period_end: bool = False
    currency: Optional[str] = Field(
        None, description="Billing currency denormalized from user profile"
    )
    current_period_start: Optional[datetime] = None
    current_period_end: Optional[datetime] = None
    trial_start: Optional[datetime] = None
    trial_end: Optional[datetime] = None
    canceled_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    plan_name: str
    plan_slug: str
    product_name: str
    product_slug: str


class SubscriptionDetailSchema(SubscriptionOutputSchema):
    """Subscription detail with plan and access entries."""

    plan: PlanDetailSchema
    access: dict[str, Any] = Field(
        default_factory=dict,
        description="Flat key-value access map from the plan's access entries",
    )


# =============================================================================
# Auth Me Schema (enhanced)
# =============================================================================


class AuthMeSchema(Schema):
    """Enhanced auth/me response with subscription and access data.

    Returned when X-Service-Domain header is present.
    When no domain header is sent, subscription and access are null/empty.
    """

    user: UserOutputSchema = Field(..., description="User profile data")
    account_status: str = Field(
        "active",
        description=(
            "User account status: 'active', 'inactive', or 'deleted'. "
            "SDK consumers should treat 'inactive' and 'deleted' as "
            "force-logout signals.  Note: inactive/deleted accounts "
            "never reach the SDK — auth/me returns 401 with a specific "
            "error code (account_inactive / account_deleted) instead. "
            "This field is provided for defensive checks."
        ),
    )
    subscription: Optional[SubscriptionInfoSchema] = Field(
        None, description="Subscription info for the requesting domain"
    )
    access: dict[str, Any] = Field(
        default_factory=dict,
        description="Flat key-value access map from the plan's access entries",
    )
    exchange_rates: Optional[dict[str, str]] = Field(
        None,
        description=(
            "Exchange rates from the user's base currency to all available "
            "currencies. Only populated when X-Service-Domain header is present. "
            "Format: {'USD': '1.000000', 'EUR': '0.920000', 'BDT': '109.850000'}"
        ),
    )
    currencies: Optional[dict[str, dict[str, Any]]] = Field(
        None,
        description=(
            "Currency metadata (symbol, name, decimal_digits) for all supported "
            "currencies. Only populated when X-Service-Domain header is present. "
            "Sister domains MUST use this instead of hardcoding symbol maps. "
            "Format: {'USD': {'symbol': '$', 'name': 'US Dollar', 'decimal_digits': 2}, ...}"
        ),
    )


# =============================================================================
# Checkout & Portal Schemas
# =============================================================================


class CheckoutInputSchema(Schema):
    """Schema for creating a Stripe checkout session."""

    plan_slug: str = Field(
        ...,
        description="Slug of the plan to subscribe to",
        examples=["standard"],
    )
    billing_cycle: Optional[str] = Field(
        None,
        description="Billing cycle override (if plan supports multiple cycles)",
        examples=["monthly", "yearly"],
    )
    tos_accepted: bool = Field(
        False,
        description="Whether the user has accepted the Terms of Service",
    )
    return_url: Optional[str] = Field(
        None,
        description=(
            "Optional URL to redirect back to after checkout completes. "
            "Must match a registered ServiceDomain domain or the app's own domain. "
            "Passed through to Stripe success/cancel URLs so the frontend can "
            "redirect the user back to the originating sister domain."
        ),
    )


class CheckoutOutputSchema(Schema):
    """Schema for Stripe checkout session response."""

    checkout_url: Optional[str] = Field(
        None,
        description="Stripe Checkout URL to redirect user to. "
        "None when the existing subscription was reactivated directly.",
    )
    reactivated: bool = Field(
        False,
        description="True when an existing cancelled subscription was "
        "reactivated instead of creating a new checkout.",
    )


class CheckoutConfirmInputSchema(Schema):
    """Schema for confirming a Stripe checkout session."""

    session_id: str = Field(
        ...,
        description="Stripe Checkout Session ID from the success redirect URL",
        examples=["cs_test_xxxxxxxxxxxx"],
    )


class CheckoutConfirmOutputSchema(Schema):
    """Schema for checkout confirmation response."""

    plan_name: str = Field(..., description="Name of the activated plan")
    plan_slug: str = Field(..., description="Slug of the activated plan")
    status: str = Field(..., description="Subscription status (active/trialing)")
    trial_end: Optional[datetime] = Field(
        None, description="Trial end date if applicable"
    )
    current_period_end: Optional[datetime] = Field(
        None, description="End of the current billing period"
    )


class PortalOutputSchema(Schema):
    """Schema for Stripe Customer Portal session response."""

    portal_url: str = Field(..., description="Stripe Customer Portal URL")


class PortalInputSchema(Schema):
    """Schema for creating a Stripe Customer Portal session."""

    return_url: Optional[str] = Field(
        None,
        description=(
            "Optional URL to redirect back to after portal session. "
            "Must match a registered ServiceDomain domain or the app's own domain."
        ),
    )


class ChangePlanInputSchema(Schema):
    """Schema for changing subscription plan."""

    plan_slug: str = Field(
        ...,
        description="Slug of the new plan to switch to",
        examples=["pro"],
    )
    proration_behavior: str = Field(
        default="create_prorations",
        description=(
            "How to handle proration: 'create_prorations' (immediate with credit), "
            "'none' (change at next billing period), 'always_invoice' (immediate invoice)"
        ),
        examples=["create_prorations"],
    )


# =============================================================================
# Refund Schemas
# =============================================================================


class RefundInputSchema(Schema):
    """Schema for initiating a refund."""

    amount_cents: Optional[int] = Field(
        None,
        description=(
            "Refund amount in cents. If not provided, refunds the full amount "
            "of the latest invoice payment."
        ),
        examples=[900],
    )
    reason: str = Field(
        "",
        description="Reason for the refund (visible to customer)",
        examples=["Customer requested cancellation within 14-day period"],
    )
    # CTR-02: Allow admin to target another user's subscription
    target_user_id: Optional[int] = Field(
        None,
        description=(
            "Optional target user ID. Admin can refund another user's "
            "subscription. Defaults to the requesting admin's own subscription."
        ),
        examples=[42],
    )
    reason_category: str = Field(
        "",
        description=(
            "Structured reason category for audit trail: "
            "customer_request, billing_error, goodwill, policy, chargeback"
        ),
        examples=["customer_request"],
    )
    admin_notes: str = Field(
        "",
        description="Internal admin-only notes about the refund (not visible to customer)",
        examples=["User called support, approved by manager"],
    )


class RefundOutputSchema(Schema):
    """Schema for refund response."""

    refund_id: int = Field(..., description="Local refund record ID")
    stripe_refund_id: str = Field(..., description="Stripe Refund ID (re_...)")
    amount_cents: int = Field(..., description="Refund amount in cents")
    currency: str = Field(..., description="ISO 4217 currency code")
    status: str = Field(..., description="Refund status (pending/completed/failed)")


# =============================================================================
# Exchange Rate Schemas
# =============================================================================


class ExchangeRateOutputSchema(Schema):
    """Single exchange rate entry."""

    base_currency: str = Field(..., description="ISO 4217 base currency code")
    target_currency: str = Field(..., description="ISO 4217 target currency code")
    rate: str = Field(..., description="Exchange rate (1 base = ? target)")
    fetched_at: datetime = Field(..., description="When the rate was fetched")


class ExchangeRateListSchema(Schema):
    """Response for listing all exchange rates."""

    base_currency: str = Field(..., description="The base currency for these rates")
    rates: dict[str, str] = Field(
        default_factory=dict,
        description="Map of target_currency → rate string, e.g. {'BDT': '109.850000', 'EUR': '0.920000'}",
    )
    fetched_at: Optional[datetime] = Field(
        None, description="When the most recent rate was fetched"
    )
    count: int = Field(..., description="Number of rates returned")


class ExchangeRateConvertSchema(Schema):
    """Response for a currency conversion lookup."""

    from_currency: str = Field(..., description="Source currency code")
    to_currency: str = Field(..., description="Target currency code")
    rate: Optional[str] = Field(None, description="Exchange rate used (1 from = ? to)")
    converted_amount: Optional[str] = Field(
        None, description="Converted amount in major units (e.g. '109.85' for 1 USD → BDT)"
    )
    available: bool = Field(
        ..., description="Whether a rate was available for this pair"
    )


# =============================================================================
# Currency Metadata Schemas
# =============================================================================


class CurrencyMetaEntrySchema(Schema):
    """Metadata for a single currency."""

    symbol: str = Field(..., description="Display symbol (e.g. '$', '৳', '€')")
    name: str = Field(..., description="Human-readable name (e.g. 'US Dollar')")
    decimal_digits: int = Field(
        ..., description="Number of decimal places (0 for JPY/KRW/VND, 2 for most)"
    )


class CurrenciesListSchema(Schema):
    """Response for listing all supported currency metadata."""

    currencies: dict[str, CurrencyMetaEntrySchema] = Field(
        ...,
        description=(
            "Map of ISO 4217 code → metadata. "
            "e.g. {'USD': {'symbol': '$', 'name': 'US Dollar', 'decimal_digits': 2}}"
        ),
    )
    count: int = Field(..., description="Number of currencies returned")


# =============================================================================
# Proration Preview Schema
# =============================================================================


class ProrationPreviewOutputSchema(Schema):
    """Schema for proration preview response."""

    subtotal: float = Field(..., description="Prorated subtotal (before tax)")
    tax: float = Field(..., description="Estimated tax amount")
    total: float = Field(..., description="Total charge/credit amount")
    next_billing: float = Field(..., description="Amount due at next billing cycle")
    currency: str = Field(..., description="ISO 4217 currency code")
    preview_token: Optional[str] = Field(
        None,
        description=(
            "Server-signed, time-limited token that MUST be passed to "
            "confirm-plan-change.  Expires after 10 minutes.  Required for "
            "upgrades (total > 0) to prevent unconfirmed charges."
        ),
    )
    change_type: str = Field(
        ...,
        description="Type of plan change: 'upgrade', 'downgrade', or 'lateral'",
    )
    is_upgrade: bool = Field(
        ...,
        description="Whether this plan change requires immediate payment",
    )


class ConfirmPlanChangeInputSchema(Schema):
    """Schema for confirming a plan change.

    The ``preview_token`` is required when the change is an upgrade (total > 0).
    It is issued by ``preview_plan_change`` and expires after 10 minutes.
    For downgrades, the token is optional but still recommended for consistency.
    """

    plan_slug: str = Field(
        ...,
        description="Slug of the new plan to switch to",
        examples=["pro"],
    )
    preview_token: str = Field(
        ...,
        description=(
            "Token returned by preview_plan_change.  Proves the user "
            "saw the proration amount before confirming."
        ),
    )


class ConfirmPlanChangeOutputSchema(Schema):
    """Schema for confirmed plan change response."""

    plan_name: str = Field(..., description="Name of the new plan")
    plan_slug: str = Field(..., description="Slug of the new plan")
    status: str = Field(..., description="Subscription status after change")
    change_type: str = Field(
        ...,
        description="Type of change performed: upgrade, downgrade, or lateral"
    )
    effective_when: str = Field(
        ...,
        description="When the change takes effect: 'immediately' or 'next_billing_cycle'",
    )
    amount_charged: float = Field(
        0,
        description="Amount charged immediately (proration), in major units",
    )
    currency: str = Field(..., description="ISO 4217 currency code")


# =============================================================================
# Credit Schemas
# =============================================================================


class CreditPoolOutputSchema(Schema):
    """Credit pool in API responses."""

    id: int
    plan_name: str
    plan_slug: str
    product_name: str
    amount_cents: int
    display_amount: str
    currency: str
    credit_periods: int
    periods_consumed: int
    periods_remaining: int
    source: str
    payment_reference: str
    status: str
    is_effectively_active: bool
    current_period_start: Optional[str] = Field(None, description="Start of current period (ISO 8601)")
    current_period_end: Optional[str] = Field(None, description="End of current period (ISO 8601)")
    expires_at: Optional[str] = Field(None, description="Hard expiry (ISO 8601)")
    created_at: Optional[str] = Field(None, description="Creation timestamp (ISO 8601)")


class CreditInvoiceOutputSchema(Schema):
    """Credit invoice in API responses."""

    id: int
    invoice_number: str
    status: str
    amount_cents: int
    tax_cents: int
    total_cents: int
    currency: str
    plan_name: str
    plan_slug: str
    product_name: str
    period_start: Optional[str] = Field(None, description="Period start (ISO 8601)")
    period_end: Optional[str] = Field(None, description="Period end (ISO 8601)")
    payment_reference: str
    issued_at: Optional[str] = Field(null=True, description="Issue timestamp (ISO 8601)")
    created_at: Optional[str] = Field(None, description="Creation timestamp (ISO 8601)")


class CreditTransactionOutputSchema(Schema):
    """Credit transaction in API responses."""

    id: int
    action: str
    periods_delta: int
    amount_cents_delta: int
    periods_balance: int
    reason: str
    created_at: str = Field(..., description="Transaction timestamp (ISO 8601)")


class CreditPurchaseResponseSchema(Schema):
    """Response after creating a credit pool purchase."""

    pool: CreditPoolOutputSchema
    invoice: CreditInvoiceOutputSchema
    message: str = Field(..., description="Human-readable confirmation message")


class CreditPoolListResponse(Schema):
    """Paginated list of credit pools."""

    items: list[CreditPoolOutputSchema]
    total: int
    page: int
    page_size: int
    has_next: bool
    has_previous: bool


class CreditInvoiceListResponse(Schema):
    """Paginated list of credit invoices."""

    items: list[CreditInvoiceOutputSchema]
    total: int
    page: int
    page_size: int
    has_next: bool
    has_previous: bool


class CreditTransactionListResponse(Schema):
    """List of credit transactions for a pool."""

    items: list[CreditTransactionOutputSchema]


# =============================================================================
# Credit Request Schemas
# =============================================================================


class CreditRequestInputSchema(Schema):
    """Schema for a user submitting a credit purchase request.
    
    LOW-07 FIX: Added maximum limit to prevent excessively large credit purchases.
    Maximum is set to 10,000,000 cents ($100,000) which should cover most legitimate
    use cases while preventing accidental or malicious extreme values.
    """

    product_slug: str = Field(..., description="Product slug")
    plan_slug: str = Field(..., description="Plan slug")
    # LOW-07 FIX: Added maximum limit (10,000,000 cents = $100,000)
    amount_cents: int = Field(
        ...,
        ge=100,
        le=10_000_000,
        description="Amount in cents (min 100 = $1.00, max 10,000,000 = $100,000)"
    )
    currency: str = Field("USD", max_length=3)
    bank_name: str = Field(..., max_length=100, description="Name of the bank")
    account_holder_name: str = Field(..., max_length=200, description="Account holder full name")
    account_number: str = Field(..., max_length=50, description="Bank account number")
    routing_number: str = Field("", max_length=50, description="Routing/SWIFT code")
    transaction_reference: str = Field(..., max_length=255, description="Transaction ID or UPI reference")
    payment_proof_note: str = Field("", description="Optional note about the payment")
