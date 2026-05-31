"""Django admin configuration for the billing app.

Provides admin interfaces for managing service domains, products, plans,
access entries, and subscriptions. Includes inline editing, custom actions,
and filters.
"""

from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from .models import (
    ServiceDomain,
    Product,
    Plan,
    AccessEntry,
    Subscription,
    ExchangeRate,
    WebhookEventLog,
    Refund,
    RefundStatus,
    BillingCycle,
    SubscriptionStatus,
    AccessValueType,
    ServiceCredential,
)


# =============================================================================
# AccessEntry Inline
# =============================================================================


class AccessEntryInline(admin.TabularInline):
    """Inline editor for access entries within a plan."""

    model = AccessEntry
    extra = 1
    fields = ("key", "value", "value_type", "description")
    ordering = ("key",)


# =============================================================================
# Plan Inline (on Product)
# =============================================================================


class PlanInline(admin.TabularInline):
    """Inline editor for plans within a product (summary view)."""

    model = Plan
    extra = 0
    fields = (
        "name",
        "slug",
        "price_cents",
        "currency",
        "billing_cycle",
        "is_active",
        "is_featured",
    )
    readonly_fields = ()
    ordering = ("sort_order", "price_cents")
    show_change_link = True


# =============================================================================
# ServiceDomain Inline (on Product)
# =============================================================================


class ServiceDomainInline(admin.TabularInline):
    """Inline editor for service domains within a product."""

    model = ServiceDomain
    extra = 0
    fields = ("domain", "is_primary", "is_active")
    ordering = ("-is_primary", "domain")


# =============================================================================
# ServiceDomain Admin (standalone)
# =============================================================================


@admin.register(ServiceDomain)
class ServiceDomainAdmin(admin.ModelAdmin):
    """Admin configuration for service domains."""

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "product",
                    "domain",
                    "is_primary",
                    "is_active",
                )
            },
        ),
    )

    list_display = (
        "domain",
        "product_link",
        "is_primary",
        "is_active",
        "credential_status",
        "created_at",
    )
    list_filter = ("product", "is_primary", "is_active", "created_at")
    search_fields = ("domain", "product__name", "product__slug")
    ordering = ("-is_primary", "domain")
    readonly_fields = ("created_at", "updated_at")

    @admin.display(description=_("Product"))
    def product_link(self, obj):
        """Show product name as a link."""
        url = reverse("admin:billing_product_change", args=[obj.product.id])
        return format_html('<a href="{}">{}</a>', url, obj.product.name)

    actions = ["set_as_primary", "create_api_key_credential"]

    @admin.action(description=_("Set selected domain(s) as primary"))
    def set_as_primary(self, request, queryset):
        """Set selected domains as primary, unsetting others on the same product."""
        count = 0
        for sd in queryset:
            # Unset any existing primary on the same product
            ServiceDomain.objects.filter(product=sd.product, is_primary=True).exclude(
                pk=sd.pk
            ).update(is_primary=False)
            sd.is_primary = True
            sd.save(update_fields=["is_primary"])
            count += 1
        self.message_user(request, _(f"Set {count} domain(s) as primary."))

    @admin.action(description=_("Create API key credential for selected domain(s)"))
    def create_api_key_credential(self, request, queryset):
        """Generate a new API key for each selected service domain.

        Uses the same key generation logic as POST /admin/api-keys/.
        The raw key is shown once in the admin message and cannot be
        recovered after that.  If a credential already exists for a
        domain, it is revoked and replaced.
        """
        from common.utils import generate_api_key

        created_keys = []
        for sd in queryset:
            raw_key, prefix, key_hash = generate_api_key()

            # Revoke any existing credential for this domain
            ServiceCredential.objects.filter(
                service_domain=sd, is_active=True
            ).update(is_active=False)

            # Create new credential
            ServiceCredential.objects.create(
                service_domain=sd,
                name=f"{sd.domain} — API Key",
                api_key_hash=key_hash,
                api_key_prefix=prefix,
                permissions={"auth": True, "billing_read": True},
                is_active=True,
                created_by=request.user,
            )
            created_keys.append((sd.domain, raw_key))

        if created_keys:
            key_lines = "\n".join(
                f"  {domain}: {key}" for domain, key in created_keys
            )
            self.message_user(
                request,
                _(
                    f"Created {len(created_keys)} API key credential(s). "
                    f"Save these keys now — they cannot be recovered:\n\n{key_lines}"
                ),
            )
        else:
            self.message_user(request, _("No domains selected."))

    @admin.display(description=_("API Key"))
    def credential_status(self, obj):
        """Show whether an active API key credential exists."""
        cred = ServiceCredential.objects.filter(
            service_domain=obj, is_active=True
        ).first()
        if cred:
            url = reverse(
                "admin:billing_servicecredential_change", args=[cred.id]
            )
            return format_html(
                '<a href="{}">{}</a>',
                url,
                cred.api_key_prefix,
            )
        return format_html(
            '<span style="color:#999;">No active key</span>'
        )


# =============================================================================
# Product Admin
# =============================================================================


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    """Admin configuration for products."""

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "name",
                    "slug",
                    "is_active",
                )
            },
        ),
        (
            _("Details"),
            {
                "fields": (
                    "description",
                    "icon",
                    "home_url",
                ),
                "classes": ("wide",),
            },
        ),
    )

    list_display = (
        "name",
        "slug",
        "primary_domain",
        "domain_count",
        "plan_count",
        "is_active",
        "created_at",
    )
    list_filter = ("is_active", "created_at")
    search_fields = ("name", "slug")
    ordering = ("name",)
    readonly_fields = ("created_at", "updated_at")
    inlines = [ServiceDomainInline, PlanInline]

    @admin.display(description=_("Primary Domain"))
    def primary_domain(self, obj):
        """Show the primary domain for this product."""
        primary = obj.get_primary_domain()
        if primary:
            url = reverse("admin:billing_servicedomain_change", args=[primary.id])
            return format_html('<a href="{}">{}</a>', url, primary.domain)
        return format_html('<span style="color:#999;">—</span>')

    @admin.display(description=_("Domains"))
    def domain_count(self, obj):
        """Show number of service domains for this product."""
        count = obj.service_domains.count()
        url = (
            reverse("admin:billing_servicedomain_changelist")
            + f"?product__id__exact={obj.id}"
        )
        return format_html('<a href="{}">{} domain(s)</a>', url, count)

    @admin.display(description=_("Plans"))
    def plan_count(self, obj):
        """Show number of plans for this product."""
        count = obj.plans.count()
        url = reverse("admin:billing_plan_changelist") + f"?product__id__exact={obj.id}"
        return format_html('<a href="{}">{} plan(s)</a>', url, count)


# =============================================================================
# Plan Admin
# =============================================================================


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    """Admin configuration for subscription plans."""

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "product",
                    "name",
                    "slug",
                    "description",
                    "is_active",
                    "is_featured",
                )
            },
        ),
        (
            _("Pricing"),
            {
                "fields": (
                    "price_cents",
                    "currency",
                    "tax_inclusive",
                    "billing_cycle",
                    "trial_days",
                    "sort_order",
                )
            },
        ),
        (
            _("Stripe"),
            {
                "fields": ("stripe_price_id",),
                "classes": ("collapse",),
            },
        ),
        (
            _("Display"),
            {
                "fields": ("features",),
                "classes": ("wide",),
            },
        ),
    )

    list_display = (
        "name",
        "product_link",
        "display_price_raw",
        "billing_cycle",
        "trial_days",
        "subscriber_count",
        "is_active",
        "is_featured",
    )
    list_filter = (
        "product",
        "billing_cycle",
        "is_active",
        "is_featured",
        "price_cents",
    )
    search_fields = ("name", "slug", "product__name")
    ordering = ("product", "sort_order", "price_cents")
    readonly_fields = ("created_at", "updated_at")
    inlines = [AccessEntryInline]

    @admin.display(description=_("Product"))
    def product_link(self, obj):
        """Show product name as a link."""
        url = reverse("admin:billing_product_change", args=[obj.product.id])
        return format_html('<a href="{}">{}</a>', url, obj.product.name)

    @admin.display(description=_("Price"))
    def display_price_raw(self, obj):
        """Show formatted price."""
        return obj.display_price

    @admin.display(description=_("Subscribers"))
    def subscriber_count(self, obj):
        """Show number of active subscribers."""
        count = Subscription.objects.filter(
            plan=obj,
            status__in=(
                SubscriptionStatus.ACTIVE,
                SubscriptionStatus.TRIALING,
            ),
        ).count()
        url = (
            reverse("admin:billing_subscription_changelist")
            + f"?plan__id__exact={obj.id}"
        )
        return format_html('<a href="{}">{}</a>', url, count)

    actions = ["duplicate_plan"]

    @admin.action(description=_("Duplicate selected plan(s)"))
    def duplicate_plan(self, request, queryset):
        """Create a copy of selected plans with '(Copy)' suffix."""
        count = 0
        for plan in queryset:
            original_entries = list(plan.access_entries.all())

            plan.pk = None
            plan.id = None
            plan.name = f"{plan.name} (Copy)"
            plan.slug = f"{plan.slug}-copy"
            plan.stripe_price_id = None
            plan.save()

            for entry in original_entries:
                entry.pk = None
                entry.id = None
                entry.plan = plan
                entry.save()

            count += 1
        self.message_user(request, _(f"Duplicated {count} plan(s)."))


# =============================================================================
# AccessEntry Admin
# =============================================================================


@admin.register(AccessEntry)
class AccessEntryAdmin(admin.ModelAdmin):
    """Admin configuration for access entries."""

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "plan",
                    "key",
                    "value",
                    "value_type",
                )
            },
        ),
        (
            _("Details"),
            {
                "fields": ("description",),
            },
        ),
    )

    list_display = (
        "key",
        "value",
        "value_type",
        "plan_link",
        "typed_value_display",
    )
    list_filter = ("plan__product", "plan", "value_type")
    search_fields = ("key", "value", "plan__name", "description")
    ordering = ("plan__product", "plan", "key")

    @admin.display(description=_("Plan"))
    def plan_link(self, obj):
        """Show plan name as a link."""
        url = reverse("admin:billing_plan_change", args=[obj.plan.id])
        return format_html('<a href="{}">{}</a>', url, obj.plan)

    @admin.display(description=_("Typed Value"))
    def typed_value_display(self, obj):
        """Show the value after type casting."""
        val = obj.typed_value
        return str(val)


# =============================================================================
# Subscription Admin
# =============================================================================


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    """Admin configuration for user subscriptions."""

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "user",
                    "product",
                    "plan",
                    "status",
                )
            },
        ),
        (
            _("Billing Period"),
            {
                "fields": (
                    "current_period_start",
                    "current_period_end",
                    "trial_start",
                    "trial_end",
                    "canceled_at",
                    "expires_at",
                    "has_used_trial",
                    "tos_accepted_at",
                    "tos_version",
                )
            },
        ),
        (
            _("Stripe"),
            {
                "fields": (
                    "stripe_customer_id",
                    "stripe_subscription_id",
                ),
                "classes": ("collapse",),
            },
        ),
    )

    list_display = (
        "user_email",
        "product_name",
        "plan_name",
        "status",
        "period_end",
        "is_effectively_active",
        "created_at",
    )
    list_filter = (
        "product",
        "plan",
        "status",
        "created_at",
    )
    search_fields = (
        "user__email",
        "user__first_name",
        "user__last_name",
        "stripe_subscription_id",
        "stripe_customer_id",
    )
    ordering = ("-created_at",)
    readonly_fields = (
        "user",
        "product",
        "created_at",
        "updated_at",
    )

    @admin.display(description=_("User"))
    def user_email(self, obj):
        """Show user email as a link."""
        url = reverse("admin:users_user_change", args=[obj.user.id])
        return format_html('<a href="{}">{}</a>', url, obj.user.email)

    @admin.display(description=_("Product"))
    def product_name(self, obj):
        """Show product name as a link."""
        url = reverse("admin:billing_product_change", args=[obj.product.id])
        return format_html('<a href="{}">{}</a>', url, obj.product.name)

    @admin.display(description=_("Plan"))
    def plan_name(self, obj):
        """Show plan name as a link."""
        url = reverse("admin:billing_plan_change", args=[obj.plan.id])
        return format_html('<a href="{}">{}</a>', url, obj.plan.name)

    @admin.display(description=_("Period End"), boolean=True)
    def period_end(self, obj):
        """Show period end date."""
        return obj.current_period_end

    @admin.display(description=_("Active"), boolean=True)
    def is_effectively_active(self, obj):
        """Show whether subscription grants access."""
        return obj.is_effectively_active()

    is_effectively_active.short_description = _("Active")

    actions = ["cancel_subscriptions", "expire_subscriptions", "activate_subscriptions"]

    @admin.action(description=_("Cancel selected subscription(s) at period end"))
    def cancel_subscriptions(self, request, queryset):
        """Cancel subscriptions at their current period end."""
        count = 0
        for sub in queryset:
            if sub.status == SubscriptionStatus.ACTIVE:
                sub.schedule_cancellation()
                count += 1
        self.message_user(request, _(f"Canceled {count} subscription(s)."))

    @admin.action(description=_("Mark selected subscription(s) as expired"))
    def expire_subscriptions(self, request, queryset):
        """Immediately expire subscriptions."""
        from django.utils import timezone

        count = 0
        for sub in queryset:
            sub.status = SubscriptionStatus.EXPIRED
            sub.current_period_end = timezone.now()
            sub.save(update_fields=["status", "current_period_end", "updated_at"])
            count += 1
        self.message_user(request, _(f"Expired {count} subscription(s)."))

    @admin.action(description=_("Activate selected subscription(s)"))
    def activate_subscriptions(self, request, queryset):
        """Reactivate subscriptions."""
        from django.utils import timezone

        count = 0
        for sub in queryset:
            sub.status = SubscriptionStatus.ACTIVE
            sub.canceled_at = None
            if not sub.current_period_end:
                sub.current_period_end = timezone.now()
            sub.save(
                update_fields=[
                    "status",
                    "canceled_at",
                    "current_period_end",
                    "updated_at",
                ]
            )
            count += 1
        self.message_user(request, _(f"Activated {count} subscription(s)."))


# =============================================================================
# WebhookEventLog Admin
# =============================================================================


@admin.register(WebhookEventLog)
class WebhookEventLogAdmin(admin.ModelAdmin):
    """Admin configuration for Stripe webhook event logs.

    Read-only by default — webhook events are created by the webhook
    handler, not manually. Admin can use this to debug failed events
    or re-process unprocessed ones.
    """

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "event_id",
                    "event_type",
                    "processed",
                )
            },
        ),
        (
            _("Details"),
            {
                "fields": (
                    "error_message",
                    "payload",
                ),
                "classes": ("wide",),
            },
        ),
    )

    list_display = (
        "event_type",
        "event_id_short",
        "processed",
        "created_at",
    )
    list_filter = ("event_type", "processed", "created_at")
    search_fields = ("event_id", "event_type")
    ordering = ("-created_at",)
    readonly_fields = (
        "event_id",
        "event_type",
        "processed",
        "error_message",
        "payload",
        "created_at",
    )

    @admin.display(description=_("Event ID"))
    def event_id_short(self, obj):
        """Show truncated event ID."""
        short = obj.event_id[:24] + "..." if len(obj.event_id) > 24 else obj.event_id
        return short

    def has_add_permission(self, request):
        """Prevent manual creation — events come from Stripe only."""
        return False

    def has_change_permission(self, request, obj=None):
        """Allow toggling processed status for re-processing."""
        return request.user.has_perm("billing.change_webhookeventlog")

    actions = ["mark_processed"]

    @admin.action(description=_("Mark selected events as processed"))
    def mark_processed(self, request, queryset):
        """Mark selected events as processed."""
        count = queryset.update(processed=True, error_message="")
        self.message_user(request, _(f"Marked {count} event(s) as processed."))


# =============================================================================
# Refund Admin
# =============================================================================


@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    """Admin configuration for refund records."""

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "subscription",
                    "status",
                    "amount_cents",
                    "currency",
                    "reason",
                    "initiated_by",
                )
            },
        ),
        (
            _("Stripe"),
            {
                "fields": (
                    "stripe_refund_id",
                    "stripe_charge_id",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            _("Debug"),
            {
                "fields": ("stripe_response",),
                "classes": ("wide", "collapse"),
            },
        ),
    )

    list_display = (
        "subscription_link",
        "amount_display",
        "currency",
        "status",
        "reason_short",
        "initiated_by",
        "created_at",
    )
    list_filter = ("status", "currency", "created_at")
    search_fields = (
        "stripe_refund_id",
        "stripe_charge_id",
        "reason",
        "subscription__user__email",
    )
    ordering = ("-created_at",)
    readonly_fields = (
        "subscription",
        "stripe_refund_id",
        "stripe_charge_id",
        "stripe_response",
        "created_at",
        "updated_at",
    )

    @admin.display(description=_("Subscription"))
    def subscription_link(self, obj):
        """Show subscription as a link."""
        url = reverse("admin:billing_subscription_change", args=[obj.subscription.id])
        return format_html(
            '<a href="{}">sub #{} — {}</a>',
            url,
            obj.subscription.id,
            obj.subscription.plan.name,
        )

    @admin.display(description=_("Amount"))
    def amount_display(self, obj):
        """Show formatted amount."""
        symbols = {
            "USD": "$",
            "EUR": "\u20ac",
            "GBP": "\u00a3",
            "INR": "\u20b9",
            "BDT": "\u09f3",
        }
        sym = symbols.get(obj.currency.upper(), obj.currency.upper() + " ")
        return f"{sym}{obj.amount_cents / 100:.2f}"

    @admin.display(description=_("Reason"))
    def reason_short(self, obj):
        """Show truncated reason."""
        return obj.reason[:60] + "..." if len(obj.reason) > 60 else obj.reason

    def has_add_permission(self, request):
        """Prevent manual creation — refunds created via admin action or API."""
        return False


# =============================================================================
# ExchangeRate Admin
# =============================================================================


@admin.register(ExchangeRate)
class ExchangeRateAdmin(admin.ModelAdmin):
    """Admin configuration for exchange rate records.

    Rates are auto-populated by the update_exchange_rates Celery task.
    Admin can manually trigger the task or view rates for debugging.
    """

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "base_currency",
                    "target_currency",
                    "rate",
                )
            },
        ),
        (
            _("Metadata"),
            {
                "fields": ("fetched_at",),
                "classes": ("collapse",),
            },
        ),
    )

    list_display = (
        "target_currency",
        "rate_display",
        "base_currency",
        "fetched_at",
    )
    list_filter = ("base_currency", "fetched_at")
    search_fields = ("target_currency", "base_currency")
    ordering = ("target_currency",)
    readonly_fields = (
        "base_currency",
        "fetched_at",
    )

    @admin.display(description=_("Rate"))
    def rate_display(self, obj):
        """Show rate with 6 decimal places."""
        return f"{obj.rate:.6f}"

    actions = ["refresh_selected_rates"]

    @admin.action(description=_("Re-fetch selected exchange rates"))
    def refresh_selected_rates(self, request, queryset):
        """Manually refresh selected rates by calling the update function."""
        from .currency_service import fetch_exchange_rates, update_exchange_rates

        count = queryset.count()
        try:
            result = update_exchange_rates()
            self.message_user(
                request,
                _(f"Refreshed all rates: {result['updated']} updated."),
            )
        except Exception as e:
            self.message_user(request, f"Refresh failed: {e}", level="error")


# =============================================================================
# ServiceCredential Admin
# =============================================================================


@admin.register(ServiceCredential)
class ServiceCredentialAdmin(admin.ModelAdmin):
    """Admin configuration for service credentials.

    Credentials are created via the API endpoint (POST /admin/api-keys),
    not through the Django admin. The admin provides a read-only list view
    for auditing and a revoke action. The raw API key is never shown here
    since it is only returned at creation time.
    """

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "name",
                    "service_domain",
                    "api_key_prefix",
                    "is_active",
                )
            },
        ),
        (
            _("Details"),
            {
                "fields": (
                    "permissions",
                    "last_used_at",
                    "created_by",
                ),
                "classes": ("wide",),
            },
        ),
    )

    list_display = (
        "name",
        "domain_display",
        "api_key_prefix",
        "is_active",
        "last_used_at",
        "created_by_email",
        "created_at",
    )
    list_filter = ("is_active", "service_domain", "created_at")
    search_fields = ("name", "api_key_prefix", "service_domain__domain")
    ordering = ("-created_at",)
    readonly_fields = (
        "name",
        "service_domain",
        "api_key_hash",
        "api_key_prefix",
        "permissions",
        "last_used_at",
        "created_by",
        "created_at",
        "updated_at",
    )

    @admin.display(description=_("Domain"))
    def domain_display(self, obj):
        """Show service domain."""
        return obj.service_domain.domain

    @admin.display(description=_("Created By"))
    def created_by_email(self, obj):
        """Show creator email."""
        if obj.created_by:
            url = reverse("admin:users_user_change", args=[obj.created_by.id])
            return format_html('<a href="{}">{}</a>', url, obj.created_by.email)
        return "—"

    def has_add_permission(self, request):
        """Prevent manual creation — use the API endpoint instead."""
        return False

    def has_change_permission(self, request, obj=None):
        """Prevent editing — use revoke/rotate via API endpoint."""
        return False

    actions = ["revoke_credentials"]

    @admin.action(description=_("Revoke selected credential(s)"))
    def revoke_credentials(self, request, queryset):
        """Revoke selected credentials by setting is_active=False."""
        count = queryset.update(is_active=False)
        self.message_user(request, _(f"Revoked {count} credential(s)."))
