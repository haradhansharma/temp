"""Billing models for Sattabase — central subscription management.

Models chain:
    ServiceDomain (represents a connected service, e.g. finance.sattabase.tld)
        └── Product (group of plans and access control)
              └── Plan (multiple tiers per product)
                    └── AccessEntry (key-value feature gates per plan)
                          └── Subscription (one per user per product)
"""

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings

from common.models import TimeStampedModel


# =============================================================================
# Choice Constants
# =============================================================================


class BillingCycle(models.TextChoices):
    """Billing cycle frequency for plans."""

    MONTHLY = "monthly", _("Monthly")
    YEARLY = "yearly", _("Yearly")
    LIFETIME = "lifetime", _("Lifetime")


class SubscriptionStatus(models.TextChoices):
    """Subscription lifecycle states."""

    ACTIVE = "active", _("Active")
    PAST_DUE = "past_due", _("Past Due")
    CANCELED = "canceled", _("Canceled")
    TRIALING = "trialing", _("Trialing")
    PAUSED = "paused", _("Paused")
    EXPIRED = "expired", _("Expired")


class AccessValueType(models.TextChoices):
    """Type casting for access entry values."""

    STRING = "string", _("String")
    BOOLEAN = "boolean", _("Boolean")
    INTEGER = "integer", _("Integer")


# =============================================================================
# ServiceDomain
# =============================================================================


class ServiceDomain(TimeStampedModel):
    """Represents a connected service domain (e.g., finance.sattabase.tld).

    Each service domain is a separate application that authenticates against
    Sattabase and receives domain-specific subscription access. One service
    domain maps to one product. A product can also have additional domains
    (e.g., a custom domain like app.myfinance.com alongside the subdomain).

    When a service calls auth/me with the X-Service-Domain header, Sattabase
    looks up the ServiceDomain by this field, then finds the associated product,
    then returns the user's subscription and access map.
    """

    id = models.BigAutoField(primary_key=True)
    domain = models.CharField(
        _("Domain"),
        max_length=255,
        unique=True,
        db_index=True,
        help_text=_(
            "Service domain, e.g. 'finance.sattabase.tld'. "
            "This is matched against the X-Service-Domain header."
        ),
    )
    product = models.ForeignKey(
        "billing.Product",
        on_delete=models.CASCADE,
        related_name="service_domains",
        db_index=True,
        verbose_name=_("Product"),
        help_text=_("The product this domain serves subscriptions for"),
    )
    is_primary = models.BooleanField(
        _("Primary Domain"),
        default=False,
        db_index=True,
        help_text=_(
            "The primary domain for the product. Used in product detail "
            "responses and admin displays."
        ),
    )
    is_active = models.BooleanField(
        _("Active"),
        default=True,
        db_index=True,
        help_text=_("Whether this domain is accepting requests"),
    )
    webhook_url = models.URLField(
        _("Webhook URL"),
        blank=True,
        default="",
        help_text=_(
            "URL to receive credential status change notifications "
            "(revocation, rotation). Must be HTTPS in production."
        ),
    )
    webhook_secret = models.CharField(
        _("Webhook Secret"),
        max_length=255,
        blank=True,
        default="",
        help_text=_(
            "HMAC-SHA256 secret for signing webhook payloads. "
            "Shared with the sister domain to verify webhook authenticity."
        ),
    )

    class Meta:
        db_table = "billing_service_domain"
        verbose_name = _("Service Domain")
        verbose_name_plural = _("Service Domains")
        ordering = ["-is_primary", "domain"]

    def __str__(self) -> str:
        return self.domain


class Product(TimeStampedModel):
    """Represents a product managed by Sattabase.

    A product is a logical grouping of subscription plans and their access
    entries. Service domains (e.g., finance.sattabase.tld) are linked to
    a product via the ServiceDomain model. This allows one product to have
    multiple domains (e.g., subdomain + custom domain).

    All subscription plans and access control for a product's domains are
    managed under this product.
    """

    id = models.BigAutoField(primary_key=True)
    name = models.CharField(
        _("Product Name"),
        max_length=100,
        unique=True,
        help_text=_("Display name, e.g. 'Satta Finance'"),
    )
    slug = models.SlugField(
        _("Slug"),
        max_length=50,
        unique=True,
        db_index=True,
        help_text=_("URL-safe identifier, e.g. 'finance'"),
    )
    description = models.TextField(
        _("Description"),
        blank=True,
        default="",
        help_text=_("Product description shown to users"),
    )
    icon = models.ImageField(
        _("Icon"),
        upload_to="products/%Y/%m/",
        blank=True,
        null=True,
        help_text=_("Product icon or logo"),
    )
    home_url = models.URLField(
        _("Home URL"),
        blank=True,
        default="",
        help_text=_("Landing page URL for this service"),
    )
    is_active = models.BooleanField(
        _("Active"),
        default=True,
        db_index=True,
        help_text=_("Whether this product is accepting new signups"),
    )
    stripe_product_id = models.CharField(
        _("Stripe Product ID"),
        max_length=100,
        blank=True,
        null=True,
        help_text=_("Auto-created when the first paid plan checkout is initiated"),
    )

    class Meta:
        db_table = "billing_product"
        verbose_name = _("Product")
        verbose_name_plural = _("Products")
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def get_primary_domain(self):
        """Return the primary domain for this product."""
        return self.service_domains.filter(is_primary=True, is_active=True).first()

    def get_free_plan(self):
        """Return the free plan (price_cents=0) for this product."""
        return self.plans.filter(price_cents=0, is_active=True).first()

    def get_plans(self):
        """Return active plans ordered by price ascending."""
        return self.plans.filter(is_active=True).order_by("price_cents", "sort_order")


# =============================================================================
# Plan
# =============================================================================


class Plan(TimeStampedModel):
    """Represents a subscription tier within a product.

    Each product has multiple plans (Free, Standard, Pro, etc.).
    Access entries define what each plan grants.
    """

    id = models.BigAutoField(primary_key=True)
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="plans",
        db_index=True,
        verbose_name=_("Product"),
    )
    name = models.CharField(
        _("Plan Name"),
        max_length=50,
        help_text=_("Plan name, e.g. 'Free', 'Standard'"),
    )
    slug = models.SlugField(
        _("Slug"),
        max_length=50,
        help_text=_("URL-safe identifier, e.g. 'standard'"),
    )
    description = models.TextField(
        _("Description"),
        blank=True,
        default="",
        help_text=_("Plan description shown to users"),
    )
    price_cents = models.PositiveIntegerField(
        _("Price (cents)"),
        default=0,
        help_text=_("Price in cents (0 = free plan). 900 = $9.00"),
    )
    currency = models.CharField(
        _("Currency"),
        max_length=3,
        default="USD",
        help_text=_("ISO 4217 currency code"),
    )
    billing_cycle = models.CharField(
        _("Billing Cycle"),
        max_length=20,
        choices=BillingCycle.choices,
        default=BillingCycle.MONTHLY,
        db_index=True,
        help_text=_("How often the user is billed"),
    )
    trial_days = models.PositiveIntegerField(
        _("Trial Days"),
        default=0,
        help_text=_("Free trial duration in days (0 = no trial)"),
    )
    features = models.JSONField(
        _("Public Features"),
        default=dict,
        blank=True,
        help_text=_(
            "Public feature list for display "
            '(e.g. {"reports": "Advanced", "storage": "10GB"})'
        ),
    )
    stripe_price_id = models.CharField(
        _("Stripe Price ID"),
        max_length=100,
        blank=True,
        null=True,
        help_text=_("Stripe Price ID (null for free plans)"),
    )
    sort_order = models.PositiveIntegerField(
        _("Sort Order"),
        default=0,
        help_text=_("Display order (lower = first)"),
    )
    is_active = models.BooleanField(
        _("Active"),
        default=True,
        db_index=True,
        help_text=_("Whether this plan is available for new subscriptions"),
    )
    is_featured = models.BooleanField(
        _("Featured"),
        default=False,
        help_text=_("Highlight this plan in comparison UI"),
    )
    tax_inclusive = models.BooleanField(
        _("Tax Inclusive"),
        default=False,
        db_index=True,
        help_text=_(
            "Whether the displayed price already includes tax. "
            "If True, Stripe will use tax_behavior='inclusive'. "
            "If False, tax_behavior='exclusive' (tax added at checkout)."
        ),
    )

    class Meta:
        db_table = "billing_plan"
        verbose_name = _("Plan")
        verbose_name_plural = _("Plans")
        ordering = ["product", "sort_order", "price_cents"]
        constraints = [
            models.UniqueConstraint(
                fields=["product", "slug"],
                name="unique_plan_slug_per_product",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.product.name} — {self.name}"

    @property
    def display_price(self) -> str:
        """Human-readable price string using the plan's currency, e.g. '$9.00/mo'."""
        amount = self.price_cents / 100
        if self.price_cents == 0:
            return str(_("Free"))

        cycle_labels = {
            BillingCycle.MONTHLY: "/mo",
            BillingCycle.YEARLY: "/yr",
            BillingCycle.LIFETIME: "",
        }
        cycle = cycle_labels.get(self.billing_cycle, "")

        # Use centralized currency metadata from currency_service
        from .currency_service import get_currency_symbol, get_currency_decimal_digits

        symbol = get_currency_symbol(self.currency)
        decimal_digits = get_currency_decimal_digits(self.currency)
        return f"{symbol}{amount:.{decimal_digits}f}{cycle}"

    @property
    def is_free(self) -> bool:
        """Whether this is a free plan."""
        return self.price_cents == 0


# =============================================================================
# Credit Purchase Request
# =============================================================================


class CreditPurchaseRequest(TimeStampedModel):
    """A subscriber's request to purchase credits via offline/local payment.

    The user fills in their bank account details and submits transaction proof.
    An admin reviews and approves, which creates a CreditPool + CreditInvoice.
    """

    class RequestStatus(models.TextChoices):
        PENDING = "pending", _("Pending Review")
        APPROVED = "approved", _("Approved")
        REJECTED = "rejected", _("Rejected")

    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="credit_requests",
        db_index=True,
        verbose_name=_("User"),
    )
    product = models.ForeignKey(
        "billing.Product",
        on_delete=models.CASCADE,
        related_name="credit_requests",
        db_index=True,
        verbose_name=_("Product"),
    )
    plan = models.ForeignKey(
        Plan,
        on_delete=models.PROTECT,
        related_name="credit_requests",
        db_index=True,
        verbose_name=_("Plan"),
    )

    # Financial
    amount_cents = models.PositiveIntegerField(
        _("Amount (cents)"),
        help_text=_("How many credits the user wants to buy, in cents"),
    )
    currency = models.CharField(_("Currency"), max_length=3, default="USD")

    # Bank details (submitted by user)
    bank_name = models.CharField(_("Bank Name"), max_length=100)
    account_holder_name = models.CharField(_("Account Holder Name"), max_length=200)
    account_number = models.CharField(_("Account Number"), max_length=50)
    routing_number = models.CharField(_("Routing Number"), max_length=50, blank=True, default="")
    transaction_reference = models.CharField(
        _("Transaction Reference"),
        max_length=255,
        help_text=_("Bank transaction ID or UPI reference"),
    )
    payment_proof_note = models.TextField(
        _("Payment Proof Note"),
        blank=True,
        default="",
        help_text=_("Optional note from the user about the payment"),
    )

    # Status tracking
    status = models.CharField(
        _("Status"),
        max_length=20,
        choices=RequestStatus.choices,
        default=RequestStatus.PENDING,
        db_index=True,
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="credit_requests_reviewed",
        verbose_name=_("Reviewed By"),
    )
    review_note = models.TextField(
        _("Review Note"),
        blank=True,
        default="",
        help_text=_("Admin notes (reason for approval/rejection)"),
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    # Link to created credit pool (once approved)
    created_credit_pool = models.ForeignKey(
        "CreditPool",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="source_request",
        verbose_name=_("Created Credit Pool"),
    )

    class Meta:
        db_table = "billing_credit_purchase_request"
        ordering = ["-created_at"]
        verbose_name = _("Credit Purchase Request")
        verbose_name_plural = _("Credit Purchase Requests")

    def __str__(self) -> str:
        return f"{self.user.email} → {self.amount_cents}c [{self.status}]"


# =============================================================================
# Bank Settings
# =============================================================================


class BankSettings(models.Model):
    """Admin-configured bank account details for manual credit purchases."""

    bank_name = models.CharField(_("Bank Name"), max_length=100)
    account_holder_name = models.CharField(_("Account Holder Name"), max_length=200)
    account_number = models.CharField(_("Account Number"), max_length=50)
    routing_number = models.CharField(_("Routing/SWIFT Number"), max_length=50, blank=True)
    is_active = models.BooleanField(_("Active"), default=True)

    class Meta:
        db_table = "billing_bank_settings"
        verbose_name = _("Bank Setting")
        verbose_name_plural = _("Bank Settings")

    def __str__(self) -> str:
        return f"{self.bank_name} ({self.account_number})"


# =============================================================================
# AccessEntry
# =============================================================================


class AccessEntry(models.Model):
    """Key-value pair defining what a plan grants.

    This is the core mechanism for feature gating. Each plan has many
    access entries. The `key` is the feature identifier (e.g. "reports"),
    and the `value` is the access level ("true", "5", "1000").

    Example entries for a Standard finance plan:
        key: "dashboard",        value: "true"
        key: "reports",          value: "true"
        key: "max_bank_accounts", value: "5"
        key: "priority_support",  value: "false"
    """

    id = models.BigAutoField(primary_key=True)
    plan = models.ForeignKey(
        Plan,
        on_delete=models.CASCADE,
        related_name="access_entries",
        db_index=True,
        verbose_name=_("Plan"),
    )
    key = models.CharField(
        _("Access Key"),
        max_length=100,
        help_text=_("Feature identifier, e.g. 'reports', 'max_accounts'"),
    )
    value = models.CharField(
        _("Access Value"),
        max_length=255,
        help_text=_("Access value, e.g. 'true', '5', '1000'"),
    )
    value_type = models.CharField(
        _("Value Type"),
        max_length=10,
        choices=AccessValueType.choices,
        default=AccessValueType.STRING,
        help_text=_("Determines how the value is cast (string, boolean, integer)"),
    )
    description = models.TextField(
        _("Description"),
        blank=True,
        default="",
        help_text=_("Human-readable description of this access entry"),
    )

    class Meta:
        db_table = "billing_access_entry"
        verbose_name = _("Access Entry")
        verbose_name_plural = _("Access Entries")
        ordering = ["plan", "key"]
        constraints = [
            models.UniqueConstraint(
                fields=["plan", "key"],
                name="unique_access_key_per_plan",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.plan} → {self.key}: {self.value}"

    @property
    def typed_value(self):
        """Return the value cast to its declared type."""
        if self.value_type == AccessValueType.BOOLEAN:
            return self.value.lower() in ("true", "1", "yes")
        if self.value_type == AccessValueType.INTEGER:
            try:
                return int(self.value)
            except (ValueError, TypeError):
                return self.value
        return self.value

    def as_dict(self) -> dict:
        """Return as a dictionary for serialization."""
        return {
            "key": self.key,
            "value": self.typed_value,
            "description": self.description,
        }


# =============================================================================
# Subscription
# =============================================================================


class Subscription(TimeStampedModel):
    """Join between a user and a plan for a specific product.

    One subscription per user per product. When a user subscribes to a
    product's plan, this record tracks the current plan, status, and
    billing period.
    """

    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="subscriptions",
        db_index=True,
        verbose_name=_("User"),
    )
    plan = models.ForeignKey(
        Plan,
        on_delete=models.PROTECT,
        db_index=True,
        verbose_name=_("Plan"),
        help_text=_("PROTECT prevents deleting plans with active subscribers"),
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        db_index=True,
        verbose_name=_("Product"),
        help_text=_("Denormalized from plan.product for query speed"),
    )
    status = models.CharField(
        _("Status"),
        max_length=20,
        choices=SubscriptionStatus.choices,
        default=SubscriptionStatus.ACTIVE,
        db_index=True,
    )
    stripe_subscription_id = models.CharField(
        _("Stripe Subscription ID"),
        max_length=100,
        blank=True,
        null=True,
        unique=True,
        db_index=True,
        help_text=_("Stripe Subscription ID for webhook correlation"),
    )
    stripe_customer_id = models.CharField(
        _("Stripe Customer ID"),
        max_length=100,
        blank=True,
        null=True,
        db_index=True,
        help_text=_("Stripe Customer ID for portal access"),
    )
    current_period_start = models.DateTimeField(
        _("Period Start"),
        null=True,
        blank=True,
        help_text=_("Start of the current billing period"),
    )
    current_period_end = models.DateTimeField(
        _("Period End"),
        null=True,
        blank=True,
        db_index=True,
        help_text=_("End of the current billing period"),
    )
    trial_start = models.DateTimeField(
        _("Trial Start"),
        null=True,
        blank=True,
        help_text=_("Start of the trial period"),
    )
    trial_end = models.DateTimeField(
        _("Trial End"),
        null=True,
        blank=True,
        help_text=_("End of the trial period"),
    )
    canceled_at = models.DateTimeField(
        _("Canceled At"),
        null=True,
        blank=True,
        help_text=_("When the user requested cancellation"),
    )
    expires_at = models.DateTimeField(
        _("Expires At"),
        null=True,
        blank=True,
        help_text=_("Hard expiration for lifetime plans"),
    )
    has_used_trial = models.BooleanField(
        _("Has Used Trial"),
        default=False,
        help_text=_(
            "Set to True once the user has consumed a trial for this "
            "product. Prevents trial abuse via repeated plan cycling."
        ),
    )
    tos_accepted_at = models.DateTimeField(
        _("ToS Accepted At"),
        null=True,
        blank=True,
        help_text=_(
            "When the user accepted the Terms of Service for this subscription"
        ),
    )
    tos_version = models.CharField(
        _("ToS Version"),
        max_length=20,
        blank=True,
        default="",
        help_text=_("Version of the Terms of Service the user accepted (e.g. '1.0')"),
    )
    currency = models.CharField(
        _("Billing Currency"),
        max_length=3,
        default="",
        blank=True,
        db_index=True,
        help_text=_(
            "ISO 4217 currency code denormalized from the user's profile "
            "at checkout time. Used for frontend price display. "
            "Empty = fallback to plan.currency."
        ),
    )
    last_dunning_email_at = models.DateTimeField(
        _("Last Dunning Email At"),
        null=True,
        blank=True,
        help_text=_(
            "Timestamp of the last dunning email sent for this "
            "subscription. Used to prevent duplicate emails."
        ),
    )
    dunning_step = models.PositiveIntegerField(
        _("Dunning Step"),
        default=0,
        help_text=_(
            "Current dunning workflow step (0=none, 1=reminder, "
            "2=urgent, 3=restrict, 4=cancel). Incremented by the "
            "dunning_retry Celery task."
        ),
    )
    cancel_at_period_end = models.BooleanField(
        _("Cancel at Period End"),
        default=False,
        help_text=_(
            "True when the subscription is scheduled to cancel at the end "
            "of the current billing period. Set by Stripe when the user cancels "
            "from the portal or via the cancel API."
        ),
    )
    past_due_at = models.DateTimeField(
        _("Past Due At"),
        null=True,
        blank=True,
        help_text=_(
            "Timestamp of when the subscription first transitioned to PAST_DUE. "
            "Used by the dunning workflow to calculate days_past_due accurately, "
            "since updated_at is modified by every save operation."
        ),
    )

    class Meta:
        db_table = "billing_subscription"
        verbose_name = _("Subscription")
        verbose_name_plural = _("Subscriptions")
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "product"],
                name="unique_subscription_per_user_product",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user.email} → {self.plan} ({self.status})"

    def is_effectively_active(self) -> bool:
        """Check if subscription grants access.

        Returns True if status is active/trialing and period hasn't ended.
        Past_due and canceled subscriptions remain active until period_end.
        """
        if self.status in (
            SubscriptionStatus.ACTIVE,
            SubscriptionStatus.TRIALING,
            SubscriptionStatus.PAST_DUE,
            SubscriptionStatus.CANCELED,
        ):
            if self.current_period_end and self.current_period_end:
                from django.utils import timezone

                return self.current_period_end > timezone.now()
            return True
        return False

    def get_access_map(self) -> dict:
        """Return {key: typed_value} dict from plan's access entries.

        Eagerly loads access entries to avoid N+1 queries.
        """
        entries = self.plan.access_entries.all()
        return {entry.key: entry.typed_value for entry in entries}

    def schedule_cancellation(self):
        """Mark subscription as canceled but keep active until period end."""
        from django.utils import timezone

        self.status = SubscriptionStatus.CANCELED
        self.canceled_at = timezone.now()
        self.cancel_at_period_end = True
        self.save(update_fields=["status", "canceled_at", "cancel_at_period_end", "updated_at"])

    def reactivate(self):
        """Reactivate a previously canceled subscription.

        If the subscription is still within its trial period, restores
        TRIALING status.  Otherwise restores ACTIVE.
        """
        from django.utils import timezone

        if self.trial_end and self.trial_end > timezone.now():
            self.status = SubscriptionStatus.TRIALING
        else:
            self.status = SubscriptionStatus.ACTIVE
        self.canceled_at = None
        self.cancel_at_period_end = False
        self.save(update_fields=["status", "canceled_at", "cancel_at_period_end", "updated_at"])

    def change_plan(self, new_plan):
        """Switch to a different plan within the same product."""
        self.plan = new_plan
        # If the new plan has a trial and current status is trialing, keep it
        if self.status != SubscriptionStatus.TRIALING:
            self.status = SubscriptionStatus.ACTIVE
        self.save(update_fields=["plan", "status", "updated_at"])


# =============================================================================
# Refund
# =============================================================================


class RefundStatus(models.TextChoices):
    """Refund lifecycle states."""

    PENDING = "pending", _("Pending")
    COMPLETED = "completed", _("Completed")
    FAILED = "failed", _("Failed")


class Refund(TimeStampedModel):
    """Tracks refund requests for a subscription.

    Each refund is initiated by an admin and creates a corresponding
    Stripe Refund object. The stripe_refund_id links back to the
    Stripe API record for reconciliation. Refund amounts are capped
    at the most recent invoice payment amount to prevent over-refunding.

    EU consumers have a 14-day right of withdrawal — this model
    provides the audit trail for compliance.

    CMP-02: Extended with full audit trail including IP, reason category,
    approval workflow, and admin notes for PCI-DSS compliance.
    """

    id = models.BigAutoField(primary_key=True)
    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.CASCADE,
        related_name="refunds",
        db_index=True,
        verbose_name=_("Subscription"),
        help_text=_("The subscription this refund is for"),
    )
    stripe_refund_id = models.CharField(
        _("Stripe Refund ID"),
        max_length=100,
        unique=True,
        blank=True,
        null=True,
        db_index=True,
        help_text=_("Stripe Refund ID (e.g. re_...)"),
    )
    stripe_charge_id = models.CharField(
        _("Stripe Charge ID"),
        max_length=100,
        blank=True,
        default="",
        help_text=_("The Stripe Charge/PaymentIntent ID that was refunded"),
    )
    amount_cents = models.PositiveIntegerField(
        _("Amount (cents)"),
        help_text=_("Refund amount in cents (e.g. 900 = $9.00)"),
    )
    currency = models.CharField(
        _("Currency"),
        max_length=3,
        default="USD",
        help_text=_("ISO 4217 currency code"),
    )
    reason = models.CharField(
        _("Reason"),
        max_length=255,
        blank=True,
        default="",
        help_text=_(
            "Reason for the refund (visible to customer on their bank statement)"
        ),
    )
    status = models.CharField(
        _("Status"),
        max_length=20,
        choices=RefundStatus.choices,
        default=RefundStatus.PENDING,
        db_index=True,
    )
    initiated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("Initiated By"),
        help_text=_("Admin user who initiated this refund"),
    )
    # CMP-02: Audit trail additions
    initiated_by_ip = models.GenericIPAddressField(
        _("Initiated By IP"),
        null=True,
        blank=True,
        help_text=_("IP address of the admin who initiated this refund"),
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approved_refunds",
        verbose_name=_("Approved By"),
        help_text=_("Admin who approved this refund (if multi-step approval)"),
    )
    approved_at = models.DateTimeField(
        _("Approved At"),
        null=True,
        blank=True,
        help_text=_("When this refund was approved"),
    )
    reason_category = models.CharField(
        _("Reason Category"),
        max_length=30,
        blank=True,
        default="",
        db_index=True,
        help_text=_(
            "Structured reason code for audit trail: customer_request, "
            "billing_error, goodwill, policy, chargeback"
        ),
    )
    admin_notes = models.TextField(
        _("Admin Notes"),
        blank=True,
        default="",
        help_text=_("Internal admin-only notes about this refund"),
    )
    stripe_response = models.JSONField(
        _("Stripe Response"),
        default=dict,
        blank=True,
        help_text=_("Full Stripe Refund API response for audit"),
    )

    class Meta:
        db_table = "billing_refund"
        verbose_name = _("Refund")
        verbose_name_plural = _("Refunds")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Refund {self.amount_cents/100:.2f} {self.currency} ({self.status}) for sub {self.subscription_id}"


# =============================================================================
# ExchangeRate
# =============================================================================


class ExchangeRate(models.Model):
    """Stores daily exchange rates for currency conversion.

    Rates are fetched from a free exchange rate API (e.g. open.er-api.com)
    and stored in the database. Each row represents the rate for converting
    from BASE_CURRENCY (default USD) to a target currency.

    Example: rate=109.85 for BDT means 1 USD = 109.85 BDT.

    Updated daily by the ``update_exchange_rates`` Celery task. Cached in
    the database so that the conversion API does not depend on an external
    service being available at request time.

    When BASE_CURRENCY == target_currency, the rate is always 1.0 and
    this row may not exist in the DB — the conversion service handles it.
    """

    base_currency = models.CharField(
        _("Base Currency"),
        max_length=3,
        default="USD",
        db_index=True,
        help_text=_("ISO 4217 code of the source currency (e.g. USD)"),
    )
    target_currency = models.CharField(
        _("Target Currency"),
        max_length=3,
        db_index=True,
        help_text=_("ISO 4217 code of the target currency (e.g. BDT)"),
    )
    rate = models.DecimalField(
        _("Rate"),
        max_digits=18,
        decimal_places=6,
        help_text=_(
            "Exchange rate: 1 unit of base_currency = ? units of target_currency"
        ),
    )
    fetched_at = models.DateTimeField(
        _("Fetched At"),
        auto_now_add=True,
        help_text=_("When this rate was last fetched from the API"),
    )

    class Meta:
        db_table = "billing_exchange_rate"
        verbose_name = _("Exchange Rate")
        verbose_name_plural = _("Exchange Rates")
        ordering = ["target_currency"]
        constraints = [
            models.UniqueConstraint(
                fields=["base_currency", "target_currency"],
                name="unique_exchange_rate_pair",
            ),
        ]

    def __str__(self) -> str:
        return f"1 {self.base_currency} = {self.rate} {self.target_currency}"


# =============================================================================
# Invoice
# =============================================================================


class InvoiceStatus(models.TextChoices):
    """Invoice lifecycle states."""

    DRAFT = "draft", _("Draft")
    OPEN = "open", _("Open")
    PAID = "paid", _("Paid")
    UNCOLLECTIBLE = "uncollectible", _("Uncollectible")
    VOID = "void", _("Void")


class Invoice(TimeStampedModel):
    """Stores invoice data synced from Stripe webhooks.

    Created/updated by ``invoice.payment_succeeded`` and ``invoice.created``
    webhook handlers.  Provides local access to invoice history without
    requiring real-time Stripe API calls for financial reporting,
    tax reconciliation, and dispute resolution.
    """

    stripe_invoice_id = models.CharField(
        _("Stripe Invoice ID"),
        max_length=100,
        unique=True,
        db_index=True,
        help_text=_("Stripe Invoice ID, e.g. in_1Pxxx..."),
    )
    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.CASCADE,
        related_name="invoices",
        db_index=True,
        verbose_name=_("Subscription"),
        help_text=_("The subscription this invoice belongs to"),
    )
    stripe_subscription_id = models.CharField(
        _("Stripe Subscription ID"),
        max_length=100,
        db_index=True,
        blank=True,
        default="",
        help_text=_("Denormalized for quick filtering without JOIN"),
    )
    number = models.CharField(
        _("Invoice Number"),
        max_length=50,
        blank=True,
        default="",
        help_text=_("Stripe invoice number, e.g. INV-0012"),
    )
    status = models.CharField(
        _("Status"),
        max_length=20,
        choices=InvoiceStatus.choices,
        default=InvoiceStatus.DRAFT,
        db_index=True,
    )
    amount_paid_cents = models.PositiveIntegerField(
        _("Amount Paid (cents)"),
        default=0,
        help_text=_("Amount paid by the customer in cents"),
    )
    amount_due_cents = models.PositiveIntegerField(
        _("Amount Due (cents)"),
        default=0,
        help_text=_("Amount still owed in cents"),
    )
    tax_cents = models.PositiveIntegerField(
        _("Tax (cents)"),
        default=0,
        help_text=_("Total tax amount in cents"),
    )
    discount_cents = models.PositiveIntegerField(
        _("Discount (cents)"),
        default=0,
        help_text=_("Total discount amount in cents"),
    )
    currency = models.CharField(
        _("Currency"),
        max_length=3,
        default="USD",
        help_text=_("ISO 4217 currency code"),
    )
    period_start = models.DateTimeField(
        _("Period Start"),
        null=True,
        blank=True,
        help_text=_("Start of the billing period this invoice covers"),
    )
    period_end = models.DateTimeField(
        _("Period End"),
        null=True,
        blank=True,
        help_text=_("End of the billing period this invoice covers"),
    )
    description = models.CharField(
        _("Description"),
        max_length=255,
        blank=True,
        default="",
        help_text=_("Invoice description line (e.g. plan name)"),
    )
    hosted_url = models.URLField(
        _("Hosted Invoice URL"),
        blank=True,
        default="",
        help_text=_("Stripe-hosted invoice page URL"),
    )
    pdf_url = models.URLField(
        _("PDF URL"),
        blank=True,
        default="",
        help_text=_("Stripe-hosted invoice PDF URL"),
    )
    stripe_fee_cents = models.PositiveIntegerField(
        _("Stripe Fee (cents)"),
        default=0,
        help_text=_("Stripe processing fee for this invoice (2.9% + $0.30)"),
    )
    stripe_fee_currency = models.CharField(
        _("Stripe Fee Currency"),
        max_length=3,
        blank=True,
        default="",
        help_text=_("Currency of the Stripe fee"),
    )
    attempt_count = models.PositiveIntegerField(
        _("Attempt Count"),
        default=1,
        help_text=_("Number of payment attempts for this invoice"),
    )
    next_payment_attempt = models.DateTimeField(
        _("Next Payment Attempt"),
        null=True,
        blank=True,
        help_text=_("When Stripe will next attempt payment"),
    )
    stripe_response = models.JSONField(
        _("Stripe Response"),
        default=dict,
        blank=True,
        help_text=_("Full Stripe Invoice object for audit/reconciliation"),
    )

    class Meta:
        db_table = "billing_invoice"
        verbose_name = _("Invoice")
        verbose_name_plural = _("Invoices")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Invoice {self.number or self.stripe_invoice_id} ({self.status})"


# FIN-01: Invoice Line Items
# =============================================================================


class InvoiceLineItem(models.Model):
    """Individual line items from a Stripe invoice.

    FIN-01 Fix: Provides structured access to invoice line items without
    parsing the full ``stripe_response`` JSON blob.  Populated by the
    ``invoice.*`` webhook handlers alongside the parent Invoice record.

    Each line item represents a subscription period charge, discount,
    tax, or proration adjustment.  The ``stripe_line_item_id`` provides
    a stable reference back to the Stripe LineItem object for reconciliation.
    """

    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name="line_items",
        db_index=True,
        verbose_name=_("Invoice"),
        help_text=_("The parent invoice this line item belongs to"),
    )
    stripe_line_item_id = models.CharField(
        _("Stripe Line Item ID"),
        max_length=100,
        blank=True,
        default="",
        db_index=True,
        help_text=_("Stripe LineItem ID (e.g. li_1Pxxx...)"),
    )
    description = models.CharField(
        _("Description"),
        max_length=255,
        blank=True,
        default="",
        help_text=_("Line item description (e.g. plan name, proration)"),
    )
    amount_cents = models.IntegerField(
        _("Amount (cents)"),
        default=0,
        help_text=_("Line item amount in cents (can be negative for credits)"),
    )
    currency = models.CharField(
        _("Currency"),
        max_length=3,
        default="USD",
        help_text=_("ISO 4217 currency code"),
    )
    quantity = models.PositiveIntegerField(
        _("Quantity"),
        default=1,
        help_text=_("Number of units (usually 1 for subscriptions)"),
    )
    period_start = models.DateTimeField(
        _("Period Start"),
        null=True,
        blank=True,
        help_text=_("Start of the service period for this line item"),
    )
    period_end = models.DateTimeField(
        _("Period End"),
        null=True,
        blank=True,
        help_text=_("End of the service period for this line item"),
    )
    proration = models.BooleanField(
        _("Proration"),
        default=False,
        help_text=_("Whether this line item is a proration adjustment"),
    )
    discount_amount_cents = models.IntegerField(
        _("Discount Amount (cents)"),
        default=0,
        help_text=_("Discount applied to this line item in cents"),
    )
    tax_amount_cents = models.IntegerField(
        _("Tax Amount (cents)"),
        default=0,
        help_text=_("Tax applied to this line item in cents"),
    )
    type = models.CharField(
        _("Type"),
        max_length=30,
        blank=True,
        default="",
        help_text=_("Line item type: subscription, invoiceitem, etc."),
    )

    class Meta:
        db_table = "billing_invoice_line_item"
        verbose_name = _("Invoice Line Item")
        verbose_name_plural = _("Invoice Line Items")
        ordering = ["id"]

    def __str__(self) -> str:
        sign = "-" if self.amount_cents < 0 else ""
        return f"{self.description or 'Line Item'} ({sign}{self.amount_cents / 100:.2f} {self.currency})"


# FIN-04: Plan Change Audit Log
# =============================================================================


class PlanChangeLog(TimeStampedModel):
    """Audit trail for subscription plan changes.

    Every time a user or admin changes a subscription's plan, this model
    records the from/to plans, the proration amount, and who initiated it.
    This provides a complete billing audit trail for reconciliation,
    dispute resolution, and revenue recognition.
    """

    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.CASCADE,
        related_name="plan_changes",
        db_index=True,
        verbose_name=_("Subscription"),
    )
    from_plan = models.ForeignKey(
        Plan,
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name=_("From Plan"),
        help_text=_("The plan being changed from"),
    )
    to_plan = models.ForeignKey(
        Plan,
        on_delete=models.PROTECT,
        related_name="+",
        verbose_name=_("To Plan"),
        help_text=_("The plan being changed to"),
    )
    proration_amount_cents = models.IntegerField(
        _("Proration Amount (cents)"),
        help_text=_(
            "Proration credit/charge amount in cents. "
            "Negative = credit to customer, Positive = charge."
        ),
    )
    currency = models.CharField(
        _("Currency"),
        max_length=3,
        default="USD",
        help_text=_("ISO 4217 currency code"),
    )
    stripe_proration_id = models.CharField(
        _("Stripe Proration ID"),
        max_length=100,
        blank=True,
        default="",
        help_text=_("ID of the Stripe proration line item"),
    )
    initiated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        verbose_name=_("Initiated By"),
        help_text=_("User who initiated the plan change (null for system/webhook)"),
    )
    proration_behavior = models.CharField(
        _("Proration Behavior"),
        max_length=30,
        blank=True,
        default="create_prorations",
        help_text=_(
            "How the proration was handled: create_prorations, none, "
            "or always_invoice"
        ),
    )

    class Meta:
        db_table = "billing_plan_change_log"
        verbose_name = _("Plan Change Log")
        verbose_name_plural = _("Plan Change Logs")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        sign = "+" if self.proration_amount_cents >= 0 else ""
        return (
            f"{self.subscription} [{self.from_plan} -> {self.to_plan}] "
            f"({sign}{self.proration_amount_cents / 100:.2f} {self.currency})"
        )


# =============================================================================
# WebhookEventLog
# =============================================================================


class WebhookEventLog(models.Model):
    """Logs every Stripe webhook event for idempotency and debugging.

    Each incoming webhook is recorded before processing. If processing
    succeeds, the entry is marked as ``processed``. Failed events remain
    unprocessed so the reconciliation task can retry them.

    FIN-08: Cleaned up by the ``cleanup_stale_webhook_events`` Celery task
    which deletes processed events older than the retention period.
    """

    id = models.BigAutoField(primary_key=True)
    event_id = models.CharField(
        _("Stripe Event ID"),
        max_length=255,
        unique=True,
        db_index=True,
        help_text=_("Stripe event ID, e.g. evt_1Pxxx..."),
    )
    event_type = models.CharField(
        _("Event Type"),
        max_length=100,
        db_index=True,
        help_text=_("Stripe event type, e.g. checkout.session.completed"),
    )
    processed = models.BooleanField(
        _("Processed"),
        default=False,
        db_index=True,
        help_text=_("Whether this event has been successfully processed"),
    )
    error_message = models.TextField(
        _("Error Message"),
        blank=True,
        default="",
        help_text=_("Error message if processing failed"),
    )
    payload = models.JSONField(
        _("Payload"),
        default=dict,
        help_text=_("Full Stripe event JSON payload"),
    )
    created_at = models.DateTimeField(
        _("Created At"),
        auto_now_add=True,
        db_index=True,
    )

    class Meta:
        db_table = "billing_webhook_event_log"
        verbose_name = _("Webhook Event Log")
        verbose_name_plural = _("Webhook Event Logs")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.event_type} ({self.event_id})"


# =============================================================================
# RevenueRecognitionEntry (FIN-07)
# =============================================================================


class RevenueRecognitionEntry(TimeStampedModel):
    """Tracks daily revenue recognition for SaaS subscriptions.

    For monthly/annual subscriptions, revenue should be recognized
    daily/monthly, not all at once at billing time. This model is
    populated by the `recognize_revenue` Celery task.

    Each row represents the revenue recognized for one subscription
    on one day. The UniqueConstraint prevents duplicate entries for
    the same subscription and date.

    Populated by:
      - `recognize_revenue` Celery task (source='scheduled', runs daily)
      - `handle_invoice_payment_succeeded` webhook (source='webhook')
    """

    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.CASCADE,
        related_name="revenue_entries",
        db_index=True,
        verbose_name=_("Subscription"),
        help_text=_("The subscription this revenue entry belongs to"),
    )
    plan = models.ForeignKey(
        Plan,
        on_delete=models.PROTECT,
        db_index=True,
        verbose_name=_("Plan"),
        help_text=_("The plan at the time of recognition"),
    )
    amount_cents = models.PositiveIntegerField(
        _("Amount (cents)"),
        default=0,
        help_text=_("Revenue recognized in cents for this day"),
    )
    currency = models.CharField(
        _("Currency"),
        max_length=3,
        default="USD",
        help_text=_("ISO 4217 currency code"),
    )
    period_start = models.DateTimeField(
        _("Period Start"),
        null=True,
        blank=True,
        help_text=_("Start of the billing period this entry covers"),
    )
    period_end = models.DateTimeField(
        _("Period End"),
        null=True,
        blank=True,
        help_text=_("End of the billing period this entry covers"),
    )
    recognized_date = models.DateField(
        _("Recognized Date"),
        db_index=True,
        help_text=_("The date this revenue is recognized for"),
    )
    stripe_invoice_id = models.CharField(
        _("Stripe Invoice ID"),
        max_length=100,
        blank=True,
        default="",
        db_index=True,
        help_text=_("The Stripe invoice that generated this revenue"),
    )
    source = models.CharField(
        _("Source"),
        max_length=30,
        blank=True,
        default="scheduled",
        db_index=True,
        help_text=_(
            "How this entry was created: 'scheduled' (Celery daily task), "
            "'webhook' (created immediately on payment), 'backfill' (manual)"
        ),
    )

    class Meta:
        db_table = "billing_revenue_recognition"
        verbose_name = _("Revenue Recognition Entry")
        verbose_name_plural = _("Revenue Recognition Entries")
        ordering = ["-recognized_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["subscription", "recognized_date"],
                name="unique_revenue_per_sub_per_day",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"{self.subscription} — {self.amount_cents / 100:.2f} "
            f"{self.currency} on {self.recognized_date}"
        )


# =============================================================================
# ServiceCredential (SDK — Service-to-Service Auth)
# =============================================================================


class ServiceCredential(TimeStampedModel):
    """API credential for service-to-service authentication.

    Each service domain (sister concern) receives one API key credential
    that identifies it when making API calls to Sattabase. The raw API key
    is shown ONCE at creation time and never stored — only its SHA-256
    hash is persisted.

    When a service calls Sattabase with the ``X-API-Key`` header, the
    middleware hashes the key, looks up the ``ServiceCredential`` record,
    and attaches the credential (and its associated ``ServiceDomain``)
    to the request object for downstream use.

    Security:
    - Raw key is NEVER stored in the database
    - ``api_key_hash`` uses SHA-256 with per-key randomness (from token_urlsafe)
    - Keys can be revoked instantly via ``is_active`` flag
    - Key rotation creates a new credential and deactivates the old one
    """

    name = models.CharField(
        _("Credential Name"),
        max_length=100,
        help_text=_("Human-readable name, e.g. 'Finance Backend Production'"),
    )
    service_domain = models.OneToOneField(
        ServiceDomain,
        on_delete=models.CASCADE,
        related_name="credential",
        db_index=True,
        verbose_name=_("Service Domain"),
        help_text=_("One credential per service domain"),
    )
    api_key_hash = models.CharField(
        _("API Key Hash"),
        max_length=255,
        unique=True,
        db_index=True,
        help_text=_("SHA-256 hash of the API key (raw key never stored)"),
    )
    api_key_prefix = models.CharField(
        _("API Key Prefix"),
        max_length=12,
        db_index=True,
        help_text=_("First 12 chars for identification (e.g. 'sb_live_a1Bc')"),
    )
    permissions = models.JSONField(
        _("Permissions"),
        default=dict,
        blank=True,
        help_text=_(
            "Scoped permissions: {'auth': True, 'billing_read': True}. "
            "Controls which API surface this credential can access."
        ),
    )
    is_active = models.BooleanField(
        _("Active"),
        default=True,
        db_index=True,
        help_text=_("Can be revoked instantly by setting to False"),
    )
    last_used_at = models.DateTimeField(
        _("Last Used At"),
        null=True,
        blank=True,
        help_text=_("When this credential was last used (audit)"),
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("Created By"),
        help_text=_("Admin who created this credential"),
    )

    class Meta:
        db_table = "billing_service_credential"
        verbose_name = _("Service Credential")
        verbose_name_plural = _("Service Credentials")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        status = "active" if self.is_active else "revoked"
        return f"{self.name} ({self.api_key_prefix}...) [{status}]"



# =============================================================================
# AdminAuditLog (9.7 — Admin Action Audit Trail)
# =============================================================================


class AdminAuditLog(models.Model):
    """Persists admin action audit trail for the billing admin endpoints.

    Every admin mutation (product/plan/user/subscription changes) is recorded
    here via the ``record_admin_action`` utility function or by the
    ``log_admin_access`` decorator enhanced with DB persistence.  This provides
    a queryable, paginated audit log that the admin dashboard can surface via
    ``GET /admin/audit-log``.

    The model intentionally uses ``auto_now_add`` for ``created_at`` (not
    ``TimeStampedModel``) because audit entries must be immutable — the
    ``updated_at`` field from ``TimeStampedModel`` would be misleading since
    audit records are never edited after creation.
    """

    admin_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="admin_audit_logs",
        db_index=True,
        verbose_name=_("Admin User"),
        help_text=_("The admin who performed this action"),
    )
    action = models.CharField(
        _("Action"),
        max_length=100,
        db_index=True,
        help_text=_(
            "Action identifier, e.g. 'product.create', 'plan.update', "
            "'subscription.override', 'refund.approve'"
        ),
    )
    method = models.CharField(
        _("HTTP Method"),
        max_length=10,
        blank=True,
        default="",
        help_text=_("HTTP method of the API call: GET, POST, PUT, PATCH, DELETE"),
    )
    path = models.CharField(
        _("API Path"),
        max_length=255,
        blank=True,
        default="",
        help_text=_("API path that was called, e.g. '/api/v1/admin/products/5'"),
    )
    ip_address = models.GenericIPAddressField(
        _("IP Address"),
        null=True,
        blank=True,
        help_text=_("IP address of the admin"),
    )
    status_code = models.PositiveIntegerField(
        _("Status Code"),
        null=True,
        blank=True,
        help_text=_("HTTP response status code"),
    )
    details = models.JSONField(
        _("Details"),
        default=dict,
        blank=True,
        help_text=_(
            "Additional details about the action: request body fields, "
            "changed fields, before/after state, reason strings, etc."
        ),
    )
    created_at = models.DateTimeField(
        _("Created At"),
        auto_now_add=True,
        db_index=True,
    )

    class Meta:
        db_table = "billing_admin_audit_log"
        verbose_name = _("Admin Audit Log")
        verbose_name_plural = _("Admin Audit Logs")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        admin = getattr(self.admin_user, "email", "unknown")
        return f"[{self.created_at:%Y-%m-%d %H:%M}] {admin} → {self.action}"


# =============================================================================
# Credit Pool
# =============================================================================


class CreditPool(TimeStampedModel):
    """Prepaid credit balance for a user, tied to a specific plan.

    Credits are purchased via manual/admin recording or local payment gateways.
    They grant access identical to a Stripe subscription for the covered periods.
    """

    class CreditSource(models.TextChoices):
        MANUAL = "manual", _("Manual (Admin)")
        LOCAL_GATEWAY = "local_gateway", _("Local Payment Gateway")
        BANK_TRANSFER = "bank_transfer", _("Bank Transfer")
        CASH = "cash", _("Cash Payment")

    class CreditPoolStatus(models.TextChoices):
        ACTIVE = "active", _("Active")
        EXHAUSTED = "exhausted", _("Exhausted")
        EXPIRED = "expired", _("Expired")
        REFUNDED = "refunded", _("Refunded")
        CANCELLED = "cancelled", _("Cancelled")

    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="credit_pools",
        db_index=True,
        verbose_name=_("User"),
    )
    product = models.ForeignKey(
        "billing.Product",
        on_delete=models.CASCADE,
        related_name="credit_pools",
        db_index=True,
        verbose_name=_("Product"),
    )
    plan = models.ForeignKey(
        "billing.Plan",
        on_delete=models.PROTECT,
        related_name="credit_pools",
        db_index=True,
        verbose_name=_("Plan"),
    )

    # Financial
    amount_cents = models.PositiveIntegerField(
        _("Amount Paid (cents)"),
        help_text=_("Total amount the user paid for this credit pool, in cents"),
    )
    currency = models.CharField(
        _("Currency"), max_length=3, default="USD"
    )
    credit_periods = models.PositiveIntegerField(
        _("Billing Periods Covered"),
        help_text=_("Number of billing periods this credit pool covers"),
    )
    periods_consumed = models.PositiveIntegerField(
        _("Periods Consumed"), default=0
    )

    # Source tracking
    source = models.CharField(
        _("Payment Source"),
        max_length=20,
        choices=CreditSource.choices,
        default=CreditSource.MANUAL,
    )
    payment_reference = models.CharField(
        _("Payment Reference"),
        max_length=255,
        blank=True,
        default="",
        help_text=_("Bank reference, transaction ID, or admin note"),
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="credits_created",
        verbose_name=_("Created By"),
        help_text=_("Admin who recorded this payment"),
    )

    # Lifecycle
    status = models.CharField(
        _("Status"),
        max_length=20,
        choices=CreditPoolStatus.choices,
        default=CreditPoolStatus.ACTIVE,
        db_index=True,
    )
    activated_at = models.DateTimeField(
        _("Activated At"),
        null=True,
        blank=True,
        help_text=_("When the first period begins"),
    )
    current_period_start = models.DateTimeField(
        null=True, blank=True, db_index=True
    )
    current_period_end = models.DateTimeField(
        null=True, blank=True, db_index=True
    )
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text=_("Hard expiry — credit pool expires even if periods remain"),
    )

    class Meta:
        db_table = "billing_credit_pool"
        ordering = ["-created_at"]
        verbose_name = _("Credit Pool")
        verbose_name_plural = _("Credit Pools")

    def __str__(self) -> str:
        return f"{self.user.email} → {self.plan} ({self.status}, {self.periods_remaining}d)"

    @property
    def periods_remaining(self) -> int:
        return max(0, self.credit_periods - self.periods_consumed)

    @property
    def is_effectively_active(self) -> bool:
        from django.utils import timezone

        if self.status != self.CreditPoolStatus.ACTIVE:
            return False
        if self.periods_remaining <= 0:
            return False
        if self.expires_at and self.expires_at <= timezone.now():
            return False
        return True

    @property
    def display_amount(self) -> str:
        return f"{self.amount_cents / 100:.2f} {self.currency}"


# =============================================================================
# Credit Invoice
# =============================================================================


class CreditInvoice(TimeStampedModel):
    """Locally-generated invoice/credit receipt for a credit pool purchase.

    Serves as the tax-compliant document for non-Stripe payments.
    Mirrors the structure of a subscription invoice for reporting uniformity.
    """

    class CreditInvoiceStatus(models.TextChoices):
        DRAFT = "draft", _("Draft")
        ISSUED = "issued", _("Issued")
        PAID = "paid", _("Paid")
        VOID = "void", _("Void")

    id = models.BigAutoField(primary_key=True)
    credit_pool = models.ForeignKey(
        CreditPool,
        on_delete=models.CASCADE,
        related_name="invoices",
        db_index=True,
        verbose_name=_("Credit Pool"),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="credit_invoices",
        db_index=True,
        verbose_name=_("User"),
    )
    product = models.ForeignKey(
        "billing.Product",
        on_delete=models.CASCADE,
        related_name="credit_invoices",
        verbose_name=_("Product"),
    )
    plan = models.ForeignKey(
        "billing.Plan",
        on_delete=models.PROTECT,
        related_name="credit_invoices",
        verbose_name=_("Plan"),
    )

    # Invoice fields (mirrors Stripe Invoice structure for uniformity)
    invoice_number = models.CharField(
        _("Invoice Number"),
        max_length=50,
        unique=True,
        db_index=True,
        help_text=_("Locally generated, e.g. SB-CRED-00001"),
    )
    status = models.CharField(
        _("Status"),
        max_length=20,
        choices=CreditInvoiceStatus.choices,
        default=CreditInvoiceStatus.ISSUED,
    )
    amount_cents = models.PositiveIntegerField(
        _("Amount (cents)")
    )
    currency = models.CharField(
        _("Currency"), max_length=3, default="USD"
    )
    tax_cents = models.PositiveIntegerField(
        _("Tax (cents)"), default=0
    )
    total_cents = models.PositiveIntegerField(
        _("Total (cents)"),
        help_text=_("amount + tax"),
    )

    # Billing period this invoice covers
    period_start = models.DateTimeField(null=True, blank=True)
    period_end = models.DateTimeField(null=True, blank=True)

    # Compliance
    payment_reference = models.CharField(
        _("Payment Reference"),
        max_length=255,
        blank=True,
        default="",
    )
    notes = models.TextField(
        blank=True,
        default="",
        help_text=_("Internal notes (not shown to user)"),
    )
    issued_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "billing_credit_invoice"
        ordering = ["-issued_at"]
        verbose_name = _("Credit Invoice")
        verbose_name_plural = _("Credit Invoices")

    def __str__(self) -> str:
        return f"{self.invoice_number} → {self.user.email} ({self.amount_cents}c)"


# =============================================================================
# Credit Transaction
# =============================================================================


class CreditTransaction(models.Model):
    """Immutable audit ledger for credit pool mutations.

    Records every purchase, period consumption, refund, adjustment, and expiry.
    Rows in this table are never updated or deleted.
    """

    class TransactionType(models.TextChoices):
        PURCHASE = "purchase", _("Purchase")
        PERIOD_CONSUME = "period_consume", _("Period Consumed")
        REFUND = "refund", _("Refund")
        ADJUST = "adjust", _("Admin Adjustment")
        EXPIRE = "expire", _("Expiry")

    id = models.BigAutoField(primary_key=True)
    credit_pool = models.ForeignKey(
        CreditPool,
        on_delete=models.CASCADE,
        related_name="transactions",
        db_index=True,
        verbose_name=_("Credit Pool"),
    )
    invoice = models.ForeignKey(
        CreditInvoice,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transactions",
        verbose_name=_("Invoice"),
    )

    action = models.CharField(
        _("Action"),
        max_length=20,
        choices=TransactionType.choices,
        db_index=True,
    )
    periods_delta = models.IntegerField(
        _("Periods Delta"),
        help_text=_("Positive for purchase, negative for consume/refund"),
    )
    amount_cents_delta = models.IntegerField(
        _("Amount Delta (cents)"),
        help_text=_("Positive for purchase, negative for refund/adjust"),
    )
    periods_balance = models.PositiveIntegerField(
        _("Running Period Balance"),
        help_text=_("Periods remaining after this transaction"),
    )

    reason = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="credit_transactions_created",
        verbose_name=_("Created By"),
    )

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "billing_credit_transaction"
        ordering = ["-created_at"]
        verbose_name = _("Credit Transaction")
        verbose_name_plural = _("Credit Transactions")

    def __str__(self) -> str:
        return f"[{self.created_at:%Y-%m-%d %H:%M}] {self.action}: {self.periods_delta}d (balance: {self.periods_balance})"

