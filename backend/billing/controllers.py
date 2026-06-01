"""Ninja Extra controllers for the billing app.

Controllers handle HTTP routing and delegate business logic to
``BillingService``.  They are auto-discovered by ninja_extra's
``auto_discover_controllers()``.

Architecture: **Stripe first, DB second**
-----------------------------------------
All subscription mutations (cancel, reactivate, change-plan) follow the
same two-step pattern to keep the local DB in sync with Stripe:

1.  **Call Stripe first.**  If the subscription has a ``stripe_subscription_id``,
    the relevant Stripe API call is made *before* any local DB write.
    If the Stripe call fails, a ``BadRequestException`` is raised and
    the local DB is **never touched**.
2.  **Update DB on success.**  Only after Stripe confirms the change do
    we persist the new status/plan to the local database via
    ``BillingService``.

This guarantees that our DB never drifts ahead of Stripe.  Webhooks
(``customer.subscription.updated``, etc.) serve as a safety net that
re-syncs state on every Stripe event, but the primary activation path
is always the controller acting *after* Stripe confirmation.

Four controllers are defined:

- **BillingPublicController** — public endpoints (no auth required):
  product & plan discovery for landing pages and registration flow.

- **BillingProtectedController** — authenticated endpoints (JWT required):
  auth/me with domain-aware subscription data, subscription listing,
  and subscription mutation actions (cancel, reactivate, change-plan,
  Stripe checkout/portal).

- **BillingAdminController** — admin-only endpoints (JWT + staff required):
  refunds, transaction history, and customer data sync.  Refunds
  are restricted to staff/superuser to prevent financial fraud (F1).

- **BillingWebhookController** — webhook endpoints (no JWT auth):
  receives Stripe events verified by request signature.

Security features utilised from ``common``:

- **Exceptions**: ``NotFoundException``, ``BadRequestException``,
  ``TooManyRequestsException``, ``AccountNotActiveException`` — raised
  instead of returning tuple responses, caught by registered exception
  handlers in ``api/views.py``.
- **Permissions**: ``IsAuthenticated`` at controller class level.
  Email verification checked per-method via ``require_verified_email()``
  for sensitive billing actions.
- **Rate limiting**: ``check_rate_limit_or_raise()`` from
  ``common.rate_limit`` — raises ``TooManyRequestsException`` when
  exceeded.
- **Schemas**: ``MessageResponse`` from ``common.schemas`` for
  standardised success responses.
"""

import logging
from typing import Optional
from decimal import Decimal, ROUND_HALF_UP

import stripe
from ninja import Query
from ninja_extra import api_controller, http_get, http_post
from django.http import HttpRequest
from django.db import transaction
from asgiref.sync import sync_to_async

from common.exceptions import (
    NotFoundException,
    BadRequestException,
    AccountNotActiveException,
)
from common.permissions import IsAuthenticated, IsServiceAuthenticated, IsAuthenticatedOrService, IsAdmin
from common.schemas import MessageResponse, PaginatedResponse, PaginationInput
from common.rate_limit import check_rate_limit_or_raise

# Import JWTAuth from users controllers — single auth class shared across apps
from users.controllers import JWTAuth

# Credit system models — used by user-facing and admin endpoints
from .models import Product, Plan, CreditPool, CreditInvoice, CreditTransaction, CreditPurchaseRequest, SubscriptionStatus, Subscription

# Credit system schemas — used by user-facing and admin endpoints
from .schemas import CreditRequestInputSchema

from .schemas import (
    ProductOutputSchema,
    ProductDetailSchema,
    PlanOutputSchema,
    SubscriptionOutputSchema,
    SubscriptionDetailSchema,
    AuthMeSchema,
    CheckoutOutputSchema,
    CheckoutConfirmInputSchema,
    CheckoutConfirmOutputSchema,
    PortalOutputSchema,
    PortalInputSchema,
    ChangePlanInputSchema,
    CheckoutInputSchema,
    ProrationPreviewOutputSchema,
    ConfirmPlanChangeInputSchema,
    ConfirmPlanChangeOutputSchema,
    RefundInputSchema,
    ExchangeRateListSchema,
    ExchangeRateConvertSchema,
    CurrenciesListSchema,
)
from .services import BillingService
from .stripe_errors import handle_stripe_error
from .stripe import (
    create_checkout as _create_checkout,
    confirm_checkout as _confirm_checkout,
    create_portal as _create_portal,
    verify_and_parse_webhook,
    record_webhook_event,
    process_webhook_event,
    update_subscription_plan_on_stripe,
    cancel_subscription_on_stripe,
    reactivate_subscription_on_stripe,
    create_stripe_refund,
    get_proration_preview,
    get_transaction_history,
    sync_stripe_customer_data,
    get_or_create_customer_id,
    retrieve_subscription,
    get_subscription_currency,
    get_first_item_id,
    export_user_billing_data as _export_user_billing_data,
    generate_preview_token,
    verify_preview_token,
    classify_plan_change,
    execute_safe_plan_change,
)

logger = logging.getLogger(__name__)


# =============================================================================
# CMP-09: Admin access logging
# =============================================================================


from functools import wraps


def log_admin_access(func):
    """Decorator that logs admin access to billing endpoints.

    CMP-09: All admin billing actions (refund, sync, transactions) must be
    logged with user ID, email, IP, endpoint name, and timestamp for
    financial compliance and audit trail.
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
        return await func(self, request, *args, **kwargs)
    return wrapper


# =============================================================================
# Helpers
# =============================================================================


def require_verified_email(request: HttpRequest) -> None:
    """Enforce email verification for sensitive billing actions.

    Raises ``AccountNotActiveException`` (403) with a clear message if
    the user's email has not been verified.  This is used as a
    method-level guard rather than a class-level permission so that
    read-only endpoints (listing, detail) remain accessible without
    verification while mutation endpoints are gated.

    Note: ``common.permissions.IsVerified`` could be used at the
    controller class level instead, but the permission-denied response
    from ninja_extra is generic (``"Permission denied"``).  Raising
    ``AccountNotActiveException`` gives a specific error code and
    message via our registered exception handler.
    """
    if not getattr(request.user, "is_email_verified", False):
        raise AccountNotActiveException(
            "Please verify your email address to perform billing actions."
        )


# =============================================================================
# Billing Public Controller — Product & Plan Discovery
# =============================================================================


@api_controller("/billing", tags=["Billing"], auth=None)
class BillingPublicController:
    """Public billing endpoints — no authentication required.

    These endpoints allow unauthenticated access to product and plan
    information, which is needed on marketing / landing pages and in
    the registration flow.  They are safe to expose publicly because
    they contain no user-specific data.
    """

    @http_get(
        "/products",
        response=list[ProductOutputSchema],
        summary="List products",
        description="Return all active products ordered by name.",
    )
    async def list_products(self):
        """List all active products."""
        products = await BillingService.aget_products(active_only=True)
        return products

    @http_get(
        "/products/{slug}",
        response={200: ProductDetailSchema, 404: dict},
        summary="Get product detail",
        description=(
            "Return a product with its plans and service domains. "
            "Accepts optional ?currency= query param to convert plan prices. "
            "Raises 404 if the product slug does not match an active product."
        ),
    )
    async def get_product(self, slug: str, currency: Optional[str] = None):
        """Get product detail by slug, including plans and service domains.

        If ?currency=BDT is provided, plan prices are converted from the plan's
        base currency to the requested currency using stored exchange rates.
        """
        product = await BillingService.aget_product_by_slug(slug)
        if not product:
            raise NotFoundException("Product not found.")

        plans = await BillingService.aget_plans_for_product(slug)
        domains = await BillingService.aget_service_domains_for_product(product)

        # Convert plan prices if currency param is provided
        if currency and plans:
            from .currency_service import convert_plan_prices

            plans = await sync_to_async(convert_plan_prices)(plans, currency)

        return {
            "id": product.id,
            "name": product.name,
            "slug": product.slug,
            "description": product.description,
            "home_url": product.home_url,
            "is_active": product.is_active,
            "created_at": product.created_at,
            "plans": plans or [],
            "service_domains": domains,
        }

    @http_get(
        "/products/{slug}/plans",
        response={200: list[PlanOutputSchema], 404: dict},
        summary="List plans for a product",
        description=(
            "Return all active plans for a given product, "
            "ordered by price ascending then sort order. "
            "Accepts optional ?currency= query param to convert prices."
        ),
    )
    async def list_plans(self, slug: str, currency: Optional[str] = None):
        """List plans for a product.

        If ?currency=BDT is provided, prices are converted from the plan's
        base currency to the requested currency using stored exchange rates.
        """
        plans = await BillingService.aget_plans_for_product(slug)
        if plans is None:
            raise NotFoundException("Product not found.")

        # Convert plan prices if currency param is provided
        if currency:
            from .currency_service import convert_plan_prices

            plans = await sync_to_async(convert_plan_prices)(plans, currency)

        return plans

    @http_get(
        "/exchange-rates",
        response=ExchangeRateListSchema,
        summary="List exchange rates",
        description=(
            "Return all available exchange rates from the base currency. "
            "Sister domains use this to cache rates locally for multi-currency "
            "transaction handling. Optional ?base= query param (defaults to USD)."
        ),
    )
    async def list_exchange_rates(self, base: str = "USD"):
        """List all exchange rates for a given base currency.

        Returns a compact map of target_currency → rate string,
        ideal for sister domains to cache locally.
        """
        from .models import ExchangeRate

        base_code = base.upper()

        rates_qs = ExchangeRate.objects.filter(
            base_currency=base_code
        ).order_by("target_currency")

        rates_list = await sync_to_async(list)(rates_qs.values("target_currency", "rate", "fetched_at"))

        rates_map = {}
        latest_fetched = None
        for entry in rates_list:
            rates_map[entry["target_currency"]] = str(entry["rate"])
            if entry["fetched_at"] and (latest_fetched is None or entry["fetched_at"] > latest_fetched):
                latest_fetched = entry["fetched_at"]

        return {
            "base_currency": base_code,
            "rates": rates_map,
            "fetched_at": latest_fetched,
            "count": len(rates_map),
        }

    @http_get(
        "/exchange-rates/{from_currency}/{to_currency}",
        response=ExchangeRateConvertSchema,
        summary="Get specific exchange rate",
        description=(
            "Get the exchange rate between two currencies. Handles direct, "
            "reverse, and cross-pair lookups. Returns the rate and a "
            "converted amount for 1 unit of the source currency."
        ),
    )
    async def get_exchange_rate(
        self,
        from_currency: str,
        to_currency: str,
    ):
        """Get exchange rate for a specific currency pair.

        Uses the currency_service which handles direct, reverse,
        and cross-pair (via base) lookups.
        """
        from .currency_service import get_exchange_rate as _get_rate

        from_code = from_currency.upper()
        to_code = to_currency.upper()

        rate = await sync_to_async(_get_rate)(from_code, to_code)

        if rate is not None:
            converted = (Decimal("1") * rate).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )
            return {
                "from_currency": from_code,
                "to_currency": to_code,
                "rate": str(rate),
                "converted_amount": str(converted),
                "available": True,
            }

        return {
            "from_currency": from_code,
            "to_currency": to_code,
            "rate": None,
            "converted_amount": None,
            "available": False,
        }

    @http_get(
        "/currencies",
        response=CurrenciesListSchema,
        summary="List supported currencies",
        description=(
            "Return metadata (symbol, name, decimal_digits) for all "
            "supported currencies. This is the single source of truth — "
            "sister domains MUST consume this endpoint instead of "
            "hardcoding their own currency symbol maps. The response is "
            "cacheable for extended periods (currency metadata changes "
            "very rarely)."
        ),
    )
    async def list_currencies(self):
        """Return all supported currency metadata.

        Used by sister domains to render currency symbols, names,
        and decimal formatting without duplicating data.
        """
        from .currency_service import get_all_currencies_meta

        meta = await sync_to_async(get_all_currencies_meta)()

        return {
            "currencies": meta,
            "count": len(meta),
        }

    @http_get(
        "/bank-settings",
        response={200: dict},
        summary="Get active bank settings",
        description="Fetch all active bank account details for manual credit payments.",
    )
    async def get_bank_settings(self, request: HttpRequest):
        """Return all active bank accounts for manual credit purchases.
        
        CRIT-07 FIX: Mask account numbers to show only last 4 digits for security.
        Full account numbers should only be visible to authenticated admins.
        """
        from .models import BankSettings

        settings = []
        async for bank in BankSettings.objects.filter(is_active=True).order_by("id"):
            # CRIT-07 FIX: Mask account number - show only last 4 digits
            account_num = bank.account_number or ""
            masked_account = "****" + account_num[-4:] if len(account_num) >= 4 else "****"
            
            settings.append({
                "id": bank.id,
                "bank_name": bank.bank_name,
                "account_holder_name": bank.account_holder_name,
                "account_number": masked_account,  # Masked for security
                "routing_number": bank.routing_number,  # Routing number is public info
            })

        if not settings:
            return {"active": False, "banks": []}
        return {"active": True, "banks": settings}


# =============================================================================
# Billing Protected Controller — Auth Me + Subscriptions
# =============================================================================


@api_controller(
    "/billing",
    tags=["Billing — Subscriptions"],
    auth=JWTAuth(),
    permissions=[IsAuthenticated],
)
class BillingProtectedController:
    """Authenticated billing endpoints — JWT Bearer token required.

    Read endpoints (auth/me, subscription listing/detail) are available
    to any authenticated user.  Mutation endpoints (cancel, reactivate,
    change-plan, checkout, portal) additionally require email
    verification, enforced via ``require_verified_email()``.

    All mutation endpoints follow the **Stripe-first** architecture:
    Stripe is called first, and the local DB is only updated on success.
    This prevents the DB from drifting ahead of Stripe.
    """

    # =========================================================================
    # Enhanced Auth Me (Domain-Aware)
    # =========================================================================

    @http_get(
        "/auth/me",
        response=AuthMeSchema,
        summary="Get user info with subscription and access",
        description=(
            "Enhanced auth/me endpoint.  Returns user profile, "
            "subscription info, and a domain-specific access map.  "
            "Requires the ``X-Service-Domain`` header to return "
            "subscription data.  Without the header, returns plain "
            "user profile with ``null`` subscription.  Accepts both "
            "JWT Bearer tokens (frontend) and X-API-Key headers (SDK)."
        ),
        permissions=[IsAuthenticatedOrService],
    )
    async def get_auth_me(self, request: HttpRequest):
        """Return user info + subscription + access for the requesting domain.

        Domain resolution priority:
        1. Service credential's domain (if X-API-Key was provided and valid)
        2. X-Service-Domain header (backward compatibility for direct calls)
        3. None (returns plain user profile without subscription data)

        Account status enforcement:
        Checks ``user.is_active`` and ``user.is_deleted`` before returning
        any data.  Deactivated or deleted accounts receive a 401 with a
        specific error code (``account_inactive`` / ``account_deleted``)
        so that SDK consumers can force-logout the user.
        """
        # Import here to avoid circular imports at module level
        from common.api_key_auth import validate_api_key

        # Enforce account status — must happen before any data is returned.
        # This closes the window where a deactivated/deleted user's JWT
        # (still valid for up to 60 minutes) could be used to access data
        # on sister domains via SDK proxy.
        if getattr(request.user, "is_deleted", False):
            from common.exceptions import AccountDeletedException
            raise AccountDeletedException()
        if not getattr(request.user, "is_active", True):
            from common.exceptions import AccountInactiveException
            raise AccountInactiveException()

        
        # Validate API key if provided (sets request.service_domain_from_key).
        # Only call validate_api_key when an X-API-Key header is present —
        # dashboard users authenticate via JWT Bearer token and don't send
        # an API key.  When enforcement is on (API_KEY_ENFORCED=True),
        # calling validate_api_key unconditionally would reject JWT-only
        # requests with "API key is required", breaking the main dashboard.
        if request.headers.get("X-API-Key", "").strip():
            validate_api_key(request)

        # Priority: credential domain > header > None
        domain = None
        if hasattr(request, "service_domain_from_key") and request.service_domain_from_key:
            domain = request.service_domain_from_key.domain
        else:
            domain = request.headers.get("X-Service-Domain", "").strip()
        result = await BillingService.aget_auth_me_data(request.user, domain or None)

        # ── Attach exchange rates + currency metadata for sister domains ────
        # When a service domain is identified, include:
        #   - exchange_rates: rate map for the user's base currency
        #   - currencies: metadata (symbol, name, decimal_digits) for all
        #     supported currencies
        # This eliminates the need for sister domains to hardcode symbol maps
        # or make extra API calls.
        if domain:
            from .currency_service import get_all_rates_for_base, get_all_currencies_meta

            user_currency = getattr(request.user, "currency", "USD") or "USD"
            result["exchange_rates"] = await sync_to_async(
                get_all_rates_for_base
            )(user_currency)
            result["currencies"] = await sync_to_async(
                get_all_currencies_meta
            )()

        return result

    # =========================================================================
    # Subscription Listing
    # =========================================================================

    @http_get(
        "/subscriptions",
        response=dict,
        summary="List user subscriptions",
        description=(
            "Return all subscriptions for the authenticated user "
            "across all products. CTR-08 Fix: Now supports pagination "
            "via limit/offset query parameters."
        ),
    )
    async def list_subscriptions(
        self,
        request: HttpRequest,
        limit: int = 50,
        offset: int = 0,
    ):
        """List all subscriptions for the current user.

        CTR-08 Fix: Added pagination support to prevent unbounded result
        sets for users with many subscriptions. Defaults to 50 per page,
        max 100.
        """
        limit = min(max(limit, 1), 100)
        offset = max(offset, 0)

        all_subscriptions = await BillingService.aget_user_subscriptions(request.user)
        paginated = all_subscriptions[offset:offset + limit]

        return {
            "items": [
                {
                    "id": sub.id,
                    "user_id": sub.user_id,
                    "status": sub.status,
                    "cancel_at_period_end": sub.cancel_at_period_end,
                    "currency": sub.currency or None,
                    "current_period_start": sub.current_period_start,
                    "current_period_end": sub.current_period_end,
                    "trial_start": sub.trial_start,
                    "trial_end": sub.trial_end,
                    "canceled_at": sub.canceled_at,
                    "expires_at": sub.expires_at,
                    "created_at": sub.created_at,
                    "updated_at": sub.updated_at,
                    "plan_name": sub.plan.name,
                    "plan_slug": sub.plan.slug,
                    "product_name": sub.product.name,
                    "product_slug": sub.product.slug,
                }
                for sub in paginated
            ],
            "total": len(all_subscriptions),
            "limit": limit,
            "offset": offset,
            "has_more": (offset + limit) < len(all_subscriptions),
        }

    # =========================================================================
    # Transaction History (UX-05: user-facing endpoint)
    # MUST be registered BEFORE /subscriptions/{product_slug} to avoid
    # "transactions" being captured as a product_slug by the path param.
    # =========================================================================

    @http_get(
        "/subscriptions/transactions",
        response=dict,
        summary="Get my billing history",
        description=(
            "Get the authenticated user's own transaction/invoice history "
            "from Stripe. Returns paginated transactions with charge details, "
            "card brand, tax, and period info."
        ),
    )
    async def get_my_transactions(
        self,
        request: HttpRequest,
        limit: int = 25,
        starting_after: Optional[str] = None,
    ):
        """Get the authenticated user's own transaction history from Stripe."""
        try:
            result = await sync_to_async(get_transaction_history)(
                user=request.user,
                limit=min(limit, 100),
                starting_after=starting_after,
            )
        except ValueError as e:
            raise BadRequestException(str(e))
        except stripe.error.StripeError as e:
            raise handle_stripe_error(e, context="get_transactions")
        return result

    @http_post(
        "/subscriptions/sync",
        response=list[SubscriptionOutputSchema],
        summary="Force-sync subscriptions from Stripe",
        description=(
            "Fetches the latest subscription state from Stripe for all of "
            "the user's subscriptions.  Use this after returning from the "
            "Stripe Customer Portal to ensure the local DB reflects any "
            "changes made in the portal (cancel, reactivate, payment method, "
            "etc.).  This eliminates webhook race conditions."
        ),
    )
    async def sync_subscriptions(self, request: HttpRequest):
        """Force-sync all user subscriptions from Stripe.

        Called by the frontend after returning from the Stripe Customer
        Portal.  Iterates all user subscriptions with a stripe_subscription_id,
        fetches the live state from Stripe, and overwrites the local DB.
        Returns the updated subscription list.
        """
        check_rate_limit_or_raise(request, "sync_subscriptions")

        logger.warning(
            "[SYNC-DIAG] sync_subscriptions called for user_id=%s",
            request.user.id,
        )
        try:
            subscriptions = await BillingService.async_sync_user_subscriptions_from_stripe(
                request.user
            )
        except Exception as e:
            logger.error(f"Failed to sync subscriptions: {e}", exc_info=True)
            raise BadRequestException("Failed to sync subscription state from Stripe.")

        # MED-18 FIX: Reduced logging detail to avoid potential PII exposure
        # Previously logged product slugs and full status - now just counts
        logger.info(
            "[SYNC-DIAG] sync_subscriptions completed: %d subscriptions synced for user_id=%s",
            len(subscriptions),
            request.user.id,
        )

        return [
            {
                "id": sub.id,
                "user_id": sub.user_id,
                "status": sub.status,
                "cancel_at_period_end": sub.cancel_at_period_end,
                "currency": sub.currency or None,
                "current_period_start": sub.current_period_start,
                "current_period_end": sub.current_period_end,
                "trial_start": sub.trial_start,
                "trial_end": sub.trial_end,
                "canceled_at": sub.canceled_at,
                "expires_at": sub.expires_at,
                "created_at": sub.created_at,
                "updated_at": sub.updated_at,
                "plan_name": sub.plan.name,
                "plan_slug": sub.plan.slug,
                "product_name": sub.product.name,
                "product_slug": sub.product.slug,
            }
            for sub in subscriptions
        ]

    @http_get(
        "/subscriptions/{product_slug}",
        response={200: SubscriptionDetailSchema, 404: dict},
        summary="Get subscription for a product",
        description=(
            "Return the user's subscription detail for a specific "
            "product, including plan and access entries."
        ),
    )
    async def get_subscription(self, request: HttpRequest, product_slug: str):
        """Get subscription detail for a specific product."""
        subscription = await BillingService.aget_subscription_for_product(
            request.user, product_slug
        )
        if not subscription:
            raise NotFoundException("No subscription found for this product.")

        return await BillingService.aget_subscription_detail(subscription)

    # =========================================================================
    # Subscription Actions (require verified email)
    #
    # ARCHITECTURE: Stripe first, DB second.
    #   1. If the subscription has a stripe_subscription_id, call Stripe
    #      first.  On failure, raise an error — the local DB is NEVER touched.
    #   2. Only after Stripe confirms, update the local DB via BillingService.
    #   3. Webhooks (customer.subscription.updated etc.) serve as a safety
    #      net that re-syncs state, but the primary path is always Stripe → DB.
    # =========================================================================

    @http_post(
        "/subscriptions/{product_slug}/cancel",
        response={200: MessageResponse, 400: dict, 404: dict},
        summary="Cancel subscription",
        description=(
            "Cancel the subscription at the end of the current billing "
            "period.  Access continues until the period end date.  "
            "Requires email verification."
        ),
    )
    async def cancel_subscription(self, request: HttpRequest, product_slug: str, reason: str = ""):
        """Cancel a subscription at period end.

        Stripe-first flow:
        1. Validate subscription state (active/trialing)
        2. If has Stripe sub → call cancel_subscription_on_stripe()
        3. On Stripe success → update local DB
        4. If Stripe fails → raise error, DB untouched

        SEC-02: Accepts optional ``reason`` query param for cancellation analytics.
        The reason is logged but not persisted to the subscription model (which
        has no reason field).  It is recorded via the cancellation metadata
        on Stripe and in the application log.
        """
        require_verified_email(request)
        check_rate_limit_or_raise(request, "cancel_sub")

        subscription = await BillingService.aget_subscription_for_product(
            request.user, product_slug
        )
        if not subscription:
            raise NotFoundException("No subscription found for this product.")

        if subscription.status not in ("active", "trialing"):
            raise BadRequestException(
                f"Cannot cancel a subscription with status '{subscription.status}'."
            )

        # SEC-02: Log cancellation reason for analytics
        if reason:
            logger.info(
                "CANCEL_REASON: user_id=%s, sub_id=%s, product=%s, reason=%s",
                request.user.id, subscription.id, product_slug, reason,
            )

        # ── Step 1: Stripe first ──────────────────────────────────────
        if subscription.stripe_subscription_id:
            try:
                await sync_to_async(cancel_subscription_on_stripe)(subscription)
            except stripe.error.StripeError as e:
                raise handle_stripe_error(e, context="cancel_subscription")

        # ── Step 2: DB update (only after Stripe confirms) ────────────
        await BillingService.acancel_subscription(subscription)

        return MessageResponse(
            message=(
                "Subscription canceled. You will retain access until "
                "the end of your current billing period."
            )
        )

    @http_post(
        "/subscriptions/{product_slug}/reactivate",
        response={200: MessageResponse, 400: dict, 404: dict},
        summary="Reactivate subscription",
        description=(
            "Reactivate a previously canceled subscription.  "
            "Requires email verification."
        ),
    )
    async def reactivate_subscription(self, request: HttpRequest, product_slug: str):
        """Reactivate a canceled subscription.

        Stripe-first flow:
        1. Validate subscription state (canceled)
        2. Check period has not expired (CTR-13)
        3. If has Stripe sub → call reactivate_subscription_on_stripe()
        4. On Stripe success → update local DB
        5. If Stripe fails → raise error, DB untouched
        
        CRIT-03 FIX: Added select_for_update() to prevent race conditions when
        multiple concurrent reactivation requests are made for the same subscription.
        """
        require_verified_email(request)
        check_rate_limit_or_raise(request, "reactivate_sub")

        # CRIT-03 FIX: Use select_for_update within transaction to prevent race conditions
        from django.db import transaction
        async with transaction.atomic():
            subscription = await BillingService.aget_subscription_for_product(
                request.user, product_slug, select_for_update=True
            )
            if not subscription:
                raise NotFoundException("No subscription found for this product.")

            if subscription.status != "canceled":
                raise BadRequestException("Only canceled subscriptions can be reactivated.")

            # CTR-13 Fix: Check if the billing period has already expired.
            # After period_end, the Stripe subscription cannot be meaningfully
            # reactivated — the customer would need to go through checkout again.
            if subscription.current_period_end:
                from django.utils import timezone as tz
                if subscription.current_period_end < tz.now():
                    raise BadRequestException(
                        "This subscription's billing period has expired. "
                        "Please subscribe to a new plan."
                    )

            # ── Step 1: Stripe first ──────────────────────────────────────
            if subscription.stripe_subscription_id:
                try:
                    await sync_to_async(reactivate_subscription_on_stripe)(
                        subscription, subscription.plan
                    )
                except stripe.error.StripeError as e:
                    raise handle_stripe_error(e, context="reactivate_subscription")

            # ── Step 2: DB update (only after Stripe confirms) ────────────
            await BillingService.areactivate_subscription(subscription)

        return MessageResponse(message="Subscription reactivated successfully.")

    @http_post(
        "/subscriptions/{product_slug}/change-plan",
        response={200: MessageResponse, 400: dict, 404: dict},
        summary="Change subscription plan",
        description=(
            "Switch to a different plan within the same product.  "
            "Requires email verification."
        ),
    )
    async def change_plan(
        self,
        request: HttpRequest,
        product_slug: str,
        payload: ChangePlanInputSchema,
    ):
        """DEPRECATED: Change the subscription plan.

        .. deprecated::
            Use ``preview-plan-change`` + ``confirm-plan-change`` instead.
            This endpoint now blocks paid→paid plan changes for safety.

        This endpoint is retained for backward compatibility with existing
        frontends.  For paid→paid plan changes, it returns a 400 error
        directing the caller to the safe preview→confirm flow.

        Still allows:
        - Paid → Free (cancels at period end)
        """
        require_verified_email(request)
        check_rate_limit_or_raise(request, "change_plan")

        subscription = await BillingService.aget_subscription_for_product(
            request.user, product_slug
        )
        if not subscription:
            raise NotFoundException("No subscription found for this product.")

        new_plan = await BillingService.aget_plan_by_slug(
            product_slug, payload.plan_slug
        )
        if not new_plan:
            raise NotFoundException(f"Plan '{payload.plan_slug}' not found.")

        # ── SAFETY GATE: Block paid→paid changes without preview+confirm ──
        if (
            not new_plan.is_free
            and not subscription.plan.is_free
            and subscription.stripe_subscription_id
        ):
            raise BadRequestException(
                "Unable to change plan directly. Please select a plan and "
                "confirm the change through the plan comparison page."
            )

        # ── Paid → Free: cancel the Stripe subscription at period end ──
        if subscription.stripe_subscription_id and new_plan.is_free:
            try:
                await sync_to_async(cancel_subscription_on_stripe)(subscription)
            except stripe.error.StripeError as e:
                raise handle_stripe_error(e, context="change_plan(paid→free)")

        # ── DB update ──
        old_plan = subscription.plan
        try:
            await BillingService.achange_subscription_plan(subscription, new_plan)
        except ValueError as e:
            raise BadRequestException(str(e))

        # Audit log
        try:
            from .models import PlanChangeLog

            await sync_to_async(PlanChangeLog.objects.create)(
                subscription=subscription,
                from_plan=old_plan,
                to_plan=new_plan,
                proration_amount_cents=0,
                currency=subscription.currency or new_plan.currency,
                proration_behavior="none",
                initiated_by=request.user,
            )
        except Exception as e:
            logger.warning(f"Failed to create PlanChangeLog: {e}")

        return MessageResponse(message=f"Plan changed to {new_plan.name} successfully.")

    # =========================================================================
    # Stripe Checkout & Portal
    # =========================================================================

    @staticmethod
    async def _get_stripe_customer_currency(
        user, current_product_slug: str, current_sub=None
    ) -> Optional[str]:
        """Detect the currency locked on the user's Stripe Customer.

        Stripe does not allow mixing currencies on a single Customer.  If the
        user has any active/trialing Stripe subscription (even for a different
        product), the Customer is locked to that currency.

        Checks:
        1. The current product's Stripe subscription (already fetched by caller).
        2. ALL other Stripe subscriptions for this user (different products).

        Returns the lowercase currency code (e.g. ``"eur"``) if a lock exists,
        or ``None`` if the customer is free to use any currency.
        """
        from .models import Subscription

        # 1. Check current product's sub (already fetched by caller)
        if current_sub and current_sub.stripe_subscription_id:
            try:
                stripe_sub = await sync_to_async(retrieve_subscription)(
                    current_sub.stripe_subscription_id
                )
                status = stripe_sub.get("status", "")
                if status in ("active", "trialing"):
                    return (stripe_sub.get("currency") or "").lower()
            except Exception:
                pass

        # 2. Check ALL other Stripe subscriptions for this user
        other_subs = await sync_to_async(
            lambda: list(
                Subscription.objects.filter(
                    user=user,
                    stripe_subscription_id__isnull=False,
                )
                .exclude(stripe_subscription_id="")
                .exclude(pk=current_sub.pk if current_sub else 0)
                .values_list("stripe_subscription_id", flat=True)
            )
        )()

        for stripe_sub_id in other_subs:
            try:
                stripe_sub = await sync_to_async(retrieve_subscription)(stripe_sub_id)
                status = stripe_sub.get("status", "")
                if status in ("active", "trialing"):
                    return (stripe_sub.get("currency") or "").lower()
            except Exception:
                continue

        return None

    @http_post(
        "/subscriptions/{product_slug}/checkout",
        response={200: CheckoutOutputSchema, 400: dict, 429: dict},
        summary="Create Stripe checkout session",
        description=(
            "Create a Stripe Checkout session for the given plan.  "
            "Returns the checkout URL to redirect the user to.  "
            "Requires email verification and a plan with a Stripe Price ID."
        ),
    )
    async def create_checkout(
        self,
        request: HttpRequest,
        product_slug: str,
        payload: CheckoutInputSchema,
    ):
        """Create a Stripe checkout session.

        Flow:
        1. Validate the plan exists, is active, and is not free
        2. If user has an existing live Stripe subscription for this
           product, reactivate it on Stripe (Stripe-first) then
           update local DB — no new checkout needed
        3. Otherwise create a new Stripe Checkout Session (no DB change;
           DB is updated later by confirm_checkout or webhook)
        4. Return the checkout_url (or None for reactivation)
        """
        require_verified_email(request)

        # Enforce Terms of Service acceptance
        if not payload.tos_accepted:
            raise BadRequestException(
                "You must accept the Terms of Service before checkout."
            )

        check_rate_limit_or_raise(request, "checkout")

        plan = await BillingService.aget_plan_by_slug(product_slug, payload.plan_slug)
        if not plan:
            raise NotFoundException(f"Plan '{payload.plan_slug}' not found.")

        if plan.is_free:
            raise BadRequestException(
                "Cannot checkout a free plan. Use the change-plan endpoint."
            )

        product = await BillingService.aget_product_by_slug(product_slug)
        if not product:
            raise NotFoundException("Product not found.")

        # --- HIGH-05: Race Condition Prevention --------------------------------
        # Use select_for_update() within transaction.atomic() to prevent
        # concurrent checkout requests from creating duplicate sessions or
        # causing inconsistent state. The lock is held during the critical
        # decision-making section and any Stripe reactivation operations.
        from django.utils import timezone as tz
        from django.conf import settings as django_settings

        @sync_to_async
        def _process_checkout_with_lock():
            """Process checkout with row-level lock to prevent race conditions.
            
            Returns a tuple: (action, sub, checkout_data)
            - action: 'reactivated', 'checkout', or 'error'
            - sub: the subscription object (or None)
            - checkout_data: dict with additional data for checkout path
            """
            with transaction.atomic():
                # HIGH-05: Lock the subscription row to prevent concurrent operations
                qs = Subscription.objects.select_related("plan", "product")
                try:
                    sub = qs.select_for_update().get(
                        user=request.user, product=product
                    )
                except Subscription.DoesNotExist:
                    sub = None

                # --- Subscription state machine --------------------------------
                # Check the LIVE Stripe subscription (not local DB) to determine
                # whether to reactivate, update, or create a new checkout.
                should_reactivate = False
                stripe_sub_data = None

                if sub and sub.stripe_subscription_id:
                    try:
                        # Fetch live Stripe sub (returns plain dict via client.py)
                        stripe_sub = retrieve_subscription(sub.stripe_subscription_id)
                        stripe_sub_data = {
                            "status": stripe_sub.get("status", ""),
                            "currency": (stripe_sub.get("currency") or "usd").upper(),
                        }

                        stripe_status = stripe_sub_data["status"]

                        if stripe_status in ("active", "trialing"):
                            # Stripe sub is live — reactivate/update, never create checkout
                            should_reactivate = True
                            logger.info(
                                f"Live Stripe sub {sub.stripe_subscription_id} "
                                f"(status={stripe_status}, currency={stripe_sub_data['currency']})"
                            )
                    except stripe.InvalidRequestError:
                        # Stripe sub gone — clear stale reference
                        logger.info(f"Stripe sub {sub.stripe_subscription_id} no longer exists")
                        sub.stripe_subscription_id = None
                        sub.save(update_fields=["stripe_subscription_id"])

                if should_reactivate:
                    # ── Stripe-first: reactivate on Stripe, then update DB ─────
                    # Note: Stripe call happens inside the lock to prevent
                    # double-reactivation from concurrent requests
                    try:
                        # Step 1: Stripe
                        reactivate_subscription_on_stripe(sub, plan)

                        # Step 2: DB (only after Stripe confirms)
                        sub.plan = plan
                        sub.status = SubscriptionStatus.ACTIVE
                        sub.cancel_at_period_end = False
                        sub.save(update_fields=["plan", "status", "cancel_at_period_end", "updated_at"])

                        # Record ToS acceptance
                        sub.tos_accepted_at = tz.now()
                        sub.tos_version = getattr(django_settings, "TOS_VERSION", "1.0")
                        sub.save(update_fields=["tos_accepted_at", "tos_version", "updated_at"])
                        
                        return ("reactivated", sub, None)
                    except (ValueError, stripe.error.StripeError) as e:
                        logger.error(
                            f"Reactivation failed for sub {sub.id}: {e}", exc_info=True
                        )
                        return ("error", None, {"error": str(e)})

                # --- New checkout (no existing Stripe sub) --------------------
                # Determine trial: only once per product
                trial_days = plan.trial_days if plan.trial_days > 0 else None
                if sub and sub.has_used_trial:
                    trial_days = None

                trial_granted = trial_days is not None and trial_days > 0

                # HIGH-06: Mark trial as used immediately when granted (inside lock)
                # This prevents timing attacks where a user could sign up for
                # multiple trials before the webhook sets the flag
                if sub and trial_granted:
                    sub.has_used_trial = True
                    sub.tos_accepted_at = tz.now()
                    sub.tos_version = getattr(django_settings, "TOS_VERSION", "1.0")
                    sub.save(update_fields=["has_used_trial", "tos_accepted_at", "tos_version", "updated_at"])
                elif sub:
                    # Record ToS acceptance even without trial
                    sub.tos_accepted_at = tz.now()
                    sub.tos_version = getattr(django_settings, "TOS_VERSION", "1.0")
                    sub.save(update_fields=["tos_accepted_at", "tos_version", "updated_at"])

                # Return data needed for checkout creation (happens outside lock)
                checkout_data = {
                    "trial_days": trial_days,
                    "trial_granted": trial_granted,
                    "sub_currency": getattr(sub, "currency", None) if sub else None,
                    "has_used_trial": sub.has_used_trial if sub else False,
                }
                return ("checkout", sub, checkout_data)

        # Execute the locked operation
        action, sub, checkout_data = await _process_checkout_with_lock()

        # Handle results
        if action == "reactivated":
            return {"checkout_url": None, "reactivated": True}
        elif action == "error":
            raise BadRequestException(
                "Unable to update your subscription. Contact support."
            )

        # --- New checkout (unlocked section) ---------------------------------
        # The Stripe checkout session creation happens outside the lock
        # because it's a longer operation and doesn't need to hold the DB lock.
        # The trial flag has already been set atomically above.
        
        # Determine currency: existing sub's locked currency > user pref > plan base
        user_currency = getattr(request.user, "currency", None) or plan.currency
        if checkout_data.get("sub_currency"):
            user_currency = checkout_data["sub_currency"]

        # ── Currency lock check ──────────────────────────────────────────
        # A single Stripe Customer cannot mix currencies across subscriptions.
        # If the user has ANY active Stripe subscription (even for another
        # product) with a different currency, we must block the checkout now
        # with a clear message instead of letting Stripe return a cryptic error.
        stripe_customer_currency = await self._get_stripe_customer_currency(
            request.user, product_slug, sub
        )
        if (
            stripe_customer_currency
            and stripe_customer_currency != user_currency.lower()
        ):
            raise BadRequestException(
                f"Currency mismatch: your existing subscription uses "
                f"{stripe_customer_currency.upper()}, but you are trying to "
                f"checkout with {user_currency.upper()}. Stripe does not allow "
                f"mixing currencies on the same billing account. Please change "
                f"your currency preference to {stripe_customer_currency.upper()} "
                f"before checking out, or cancel your existing subscription first."
            )

        trial_days = checkout_data["trial_days"]

        try:
            checkout_url = await sync_to_async(_create_checkout)(
                user=request.user,
                plan=plan,
                product=product,
                currency=user_currency,
                trial_days=trial_days,
                return_url=payload.return_url,
            )
        except ValueError as e:
            raise BadRequestException(str(e))
        except stripe.error.StripeError as e:
            raise handle_stripe_error(e, context="create_checkout")

        return {"checkout_url": checkout_url}

    @http_post(
        "/checkout/confirm",
        response={200: CheckoutConfirmOutputSchema, 400: dict},
        summary="Confirm Stripe checkout and activate subscription",
        description=(
            "Called by the frontend after a successful Stripe redirect. "
            "Fetches the checkout session from Stripe, validates payment "
            "status and user ownership, then activates the local subscription. "
            "This is the PRIMARY activation path — does NOT depend on webhooks."
        ),
    )
    async def confirm_checkout(
        self, request: HttpRequest, payload: CheckoutConfirmInputSchema
    ):
        """Confirm a Stripe checkout and activate the subscription.

        Stripe-first flow:
        1. Fetch the Stripe checkout session by session_id
        2. Validate payment_status == 'paid' and user ownership
        3. Update the local subscription (plan, status, Stripe IDs, period dates)
        4. Return the activated subscription data

        CTR-10 Fix: Requires email verification — unverified users should not
        be able to activate subscriptions (they could be fraudulent signups).
        """
        require_verified_email(request)
        check_rate_limit_or_raise(request, "confirm_checkout")

        try:
            result = await sync_to_async(_confirm_checkout)(
                session_id=payload.session_id,
                user=request.user,
            )
        except ValueError as e:
            raise BadRequestException(str(e))
        except stripe.error.StripeError as e:
            raise handle_stripe_error(e, context="confirm_checkout")

        return result

    @http_post(
        "/portal",
        response={200: PortalOutputSchema, 400: dict},
        summary="Create Stripe Customer Portal session",
        description=(
            "Create a Stripe Customer Portal session for managing "
            "billing.  Returns the portal URL to redirect the user to.  "
            "Requires the user to have at least one Stripe subscription."
        ),
    )
    async def create_portal(
        self, request: HttpRequest, payload: PortalInputSchema = Query(...)
    ):
        """Create a Stripe Customer Portal session.

        Flow:
        1. Get the user's Stripe Customer ID
        2. Validate return_url if provided (must match registered domain)
        3. Create a Customer Portal session with return_url
        4. Return the portal_url
        """
        require_verified_email(request)

        # Validate return_url if provided
        _return_url = payload.return_url
        if _return_url:
            from .stripe.checkout import validate_return_url
            if not validate_return_url(_return_url):
                raise BadRequestException(
                    "Invalid return_url. It must match a registered "
                    "service domain or the application's own domain."
                )

        try:
            portal_url = await sync_to_async(_create_portal)(
                user=request.user,
                return_url=_return_url,
            )
        except ValueError as e:
            raise BadRequestException(str(e))
        except stripe.error.StripeError as e:
            raise handle_stripe_error(e, context="create_portal")

        return {"portal_url": portal_url}

    @http_post(
        "/subscriptions/{product_slug}/preview-plan-change",
        response={200: ProrationPreviewOutputSchema, 400: dict, 404: dict},
        summary="Preview plan change proration",
        description=(
            "Get a proration preview for changing to a different plan. "
            "Shows the prorated charge/credit amount before the user confirms."
        ),
    )
    async def preview_plan_change(
        self,
        request: HttpRequest,
        product_slug: str,
        payload: ChangePlanInputSchema,
    ):
        """Preview the proration for a plan change.

        Returns the proration amounts plus a ``preview_token`` that must
        be passed to ``confirm-plan-change``.  The token expires after
        10 minutes and is bound to the user, subscription, target plan,
        and exact proration amount — preventing any tampering.

        The response also includes ``change_type`` (upgrade/downgrade/lateral)
        and ``is_upgrade`` so the frontend can tailor the confirmation UI.
        """
        require_verified_email(request)

        subscription = await BillingService.aget_subscription_for_product(
            request.user, product_slug
        )
        if not subscription:
            raise NotFoundException("No subscription found for this product.")

        new_plan = await BillingService.aget_plan_by_slug(
            product_slug, payload.plan_slug
        )
        if not new_plan:
            raise NotFoundException(f"Plan '{payload.plan_slug}' not found.")

        # Classify the change
        change_type = await sync_to_async(classify_plan_change)(
            subscription.plan, new_plan
        )
        is_upgrade = change_type == "upgrade"

        try:
            preview = await sync_to_async(get_proration_preview)(subscription, new_plan)
        except ValueError as e:
            raise BadRequestException(str(e))
        except stripe.error.StripeError as e:
            raise handle_stripe_error(e, context="preview_plan_change")

        # Generate a time-limited preview token bound to this exact change
        total_cents = int(preview.get("total", 0) * 100)
        currency_lower = preview.get("currency", "usd").lower()
        preview_token = await sync_to_async(generate_preview_token)(
            user_id=request.user.id,
            subscription_id=subscription.id,
            plan_slug=new_plan.slug,
            total_cents=total_cents,
            currency=currency_lower,
        )

        return {
            **preview,
            "change_type": change_type,
            "is_upgrade": is_upgrade,
            "preview_token": preview_token,
        }

    @http_post(
        "/subscriptions/{product_slug}/confirm-plan-change",
        response={200: ConfirmPlanChangeOutputSchema, 400: dict, 404: dict},
        summary="Confirm plan change (safe flow)",
        description=(
            "Confirm a plan change after previewing it.  Requires a valid "
            "preview_token from preview-plan-change.  For upgrades, a "
            "PaymentIntent is created and confirmed before the subscription "
            "is modified on Stripe — ensuring the user is only charged after "
            "explicit confirmation."
        ),
    )
    async def confirm_plan_change(
        self,
        request: HttpRequest,
        product_slug: str,
        payload: ConfirmPlanChangeInputSchema,
    ):
        """Confirm a plan change using the safe preview→confirm flow.

        Flow:
        1. Verify the preview_token (ensures user saw the amount).
        2. Re-classify the change (upgrade/downgrade/lateral).
        3. For upgrades: charge proration via PaymentIntent first.
        4. Modify subscription on Stripe.
        5. Update local DB.
        6. Create audit log.
        """
        require_verified_email(request)
        check_rate_limit_or_raise(
            request, key_prefix="confirm_plan_change", max_attempts=3, window_seconds=300
        )

        subscription = await BillingService.aget_subscription_for_product(
            request.user, product_slug
        )
        if not subscription:
            raise NotFoundException("No subscription found for this product.")

        new_plan = await BillingService.aget_plan_by_slug(
            product_slug, payload.plan_slug
        )
        if not new_plan:
            raise NotFoundException(f"Plan '{payload.plan_slug}' not found.")

        # ── Step 1: Get fresh preview to verify token against current amount ──
        try:
            preview = await sync_to_async(get_proration_preview)(subscription, new_plan)
        except ValueError as e:
            raise BadRequestException(str(e))
        except stripe.error.StripeError as e:
            raise handle_stripe_error(e, context="confirm_plan_change(preview)")

        total_cents = int(preview.get("total", 0) * 100)
        currency_lower = preview.get("currency", "usd").lower()

        # ── Step 2: Verify preview token ──
        token_valid = await sync_to_async(verify_preview_token)(
            token=payload.preview_token,
            user_id=request.user.id,
            subscription_id=subscription.id,
            plan_slug=new_plan.slug,
            total_cents=total_cents,
            currency=currency_lower,
        )

        if not token_valid:
            raise BadRequestException(
                "Invalid or expired preview token.  "
                "Please call preview-plan-change again to get a fresh token."
            )

        # ── Step 3: Classify change type ──
        change_type = await sync_to_async(classify_plan_change)(
            subscription.plan, new_plan
        )

        # ── Step 4: Execute safe plan change (charge first for upgrades) ──
        try:
            result = await sync_to_async(execute_safe_plan_change)(
                subscription=subscription,
                new_plan=new_plan,
                change_type=change_type,
                proration_total_cents=total_cents,
                proration_currency=currency_lower,
            )
        except stripe.error.StripeError as e:
            raise handle_stripe_error(e, context="confirm_plan_change(execute)")

        # ── Step 5: DB update ──
        old_plan = subscription.plan
        try:
            await BillingService.achange_subscription_plan(subscription, new_plan)
        except ValueError as e:
            # Rollback: if DB update fails after Stripe change, log but don't
            # reverse Stripe (webhook will eventually re-sync)
            logger.error(
                f"DB update failed after Stripe plan change: sub={subscription.id}, "
                f"error={e}. Webhook will re-sync."
            )
            raise BadRequestException(
                "Plan was changed on Stripe but local DB update failed. "
                "It will be synced automatically. Please contact support if "
                "you see inconsistencies."
            )

        # ── Step 6: Audit log ──
        try:
            from .models import PlanChangeLog

            effective_when = (
                "immediately" if change_type == "upgrade" else "next_billing_cycle"
            )
            proration_behavior_used = (
                "create_prorations" if change_type == "upgrade" else "none"
            )

            await sync_to_async(PlanChangeLog.objects.create)(
                subscription=subscription,
                from_plan=old_plan,
                to_plan=new_plan,
                proration_amount_cents=result.get("amount_charged", 0),
                currency=currency_lower,
                proration_behavior=proration_behavior_used,
                initiated_by=request.user,
                stripe_payment_intent_id=result.get("payment_intent_id"),
            )
        except Exception as e:
            logger.warning(f"Failed to create PlanChangeLog: {e}")

        effective_when = (
            "immediately" if change_type == "upgrade" else "next_billing_cycle"
        )

        return {
            "plan_name": new_plan.name,
            "plan_slug": new_plan.slug,
            "status": subscription.status,
            "change_type": change_type,
            "effective_when": effective_when,
            "amount_charged": result.get("amount_charged", 0) / 100,
            "currency": currency_lower.upper(),
        }

    @http_get(
        "/export-data",
        response=dict,
        summary="Export billing data (GDPR Art. 20)",
        description=(
            "Export all billing data for the authenticated user, including "
            "subscription history, refund records, and invoice history. "
            "Satisfies GDPR Article 20 (Right to Data Portability). "
            "Requires email verification."
        ),
    )
    async def export_billing_data(self, request: HttpRequest):
        """Export all billing data for the authenticated user.

        Returns a structured JSON object with subscription history,
        refund records, invoice records, and Stripe customer metadata.
        This endpoint satisfies GDPR Article 20 (Right to Data Portability).
        """
        require_verified_email(request)

        try:
            data = await sync_to_async(_export_user_billing_data)(request.user)
        except Exception as e:
            logger.error(
                f"GDPR export failed for user {request.user.id}: {e}",
                exc_info=True,
            )
            raise BadRequestException(
                "Failed to export billing data. Please try again or contact support."
            )

        return data

    # =========================================================================
    # User-Facing Credit Endpoints
    # =========================================================================

    @http_get(
        "/credits",
        response={200: list},
        summary="List my credit pools",
        description="List all credit pools for the authenticated user across all products.",
    )
    async def list_my_credit_pools(
        self,
        request: HttpRequest,
    ):
        # HIGH-04: Require email verification for credit operations
        require_verified_email(request)
        pools = [
            pool
            async for pool in CreditPool.objects.select_related(
                "product", "plan"
            )
            .filter(user=request.user)
            .order_by("-created_at")
            .all()
        ]
        return [
            {
                "id": p.id,
                "product_name": p.product.name,
                "plan_name": p.plan.name,
                "plan_slug": p.plan.slug,
                "display_amount": p.display_amount,
                "amount_cents": p.amount_cents,
                "currency": p.currency,
                "credit_periods": p.credit_periods,
                "periods_consumed": p.periods_consumed,
                "periods_remaining": p.periods_remaining,
                "source": p.source,
                "payment_reference": p.payment_reference,
                "status": p.status,
                "is_effectively_active": p.is_effectively_active,
                "current_period_start": p.current_period_start,
                "current_period_end": p.current_period_end,
                "expires_at": p.expires_at,
                "created_at": p.created_at,
            }
            for p in pools
        ]

    # NOTE: /credits/invoices and /credits/request must come BEFORE /credits/{credit_id}
    # Otherwise Django Ninja matches "invoices" or "request" as a credit_id parameter
    @http_get(
        "/credits/invoices",
        response={200: list},
        summary="List my credit invoices",
        description="List all credit invoices for the authenticated user.",
    )
    async def list_my_credit_invoices(
        self,
        request: HttpRequest,
    ):
        # HIGH-04: Require email verification for credit operations
        require_verified_email(request)
        invoices = [
            inv
            async for inv in CreditInvoice.objects.select_related(
                "product", "plan"
            )
            .filter(user=request.user)
            .order_by("-issued_at")
            .all()
        ]
        return [
            {
                "id": inv.id,
                "invoice_number": inv.invoice_number,
                "product_name": inv.product.name,
                "plan_name": inv.plan.name,
                "plan_slug": inv.plan.slug,
                "amount_cents": inv.amount_cents,
                "tax_cents": inv.tax_cents,
                "total_cents": inv.total_cents,
                "currency": inv.currency,
                "status": inv.status,
                "period_start": inv.period_start,
                "period_end": inv.period_end,
                "payment_reference": inv.payment_reference,
                "issued_at": inv.issued_at,
                "created_at": inv.created_at,
            }
            for inv in invoices
        ]

    # =========================================================================
    # Credit Purchase Request (User-Facing)
    # =========================================================================

    @http_post(
        "/credits/request",
        response={200: dict, 400: dict, 404: dict},
        summary="Submit credit purchase request",
        description="Submit a request to purchase credits via bank transfer. Admin will review and approve.",
    )
    async def request_credit_purchase(
        self,
        request: HttpRequest,
        payload: CreditRequestInputSchema,
    ):
        # HIGH-04: Require email verification for credit operations
        require_verified_email(request)
        # Validate product + plan
        try:
            product = await Product.objects.aget(slug=payload.product_slug, is_active=True)
        except Product.DoesNotExist:
            raise NotFoundException("Product '%s' not found." % payload.product_slug)

        plan = await Plan.objects.filter(
            product=product, slug=payload.plan_slug, is_active=True
        ).afirst()
        if not plan:
            raise NotFoundException("Plan '%s' not found." % payload.plan_slug)

        # HIGH-12: Validate bank details against active BankSettings
        from .models import BankSettings
        active_bank = await BankSettings.objects.filter(
            is_active=True,
            bank_name=payload.bank_name,
        ).afirst()
        
        if not active_bank:
            raise BadRequestException(
                f"Bank '{payload.bank_name}' is not recognized. "
                "Please select a bank from the available options."
            )

        credit_request = await CreditPurchaseRequest.objects.acreate(
            user=request.user,
            product=product,
            plan=plan,
            amount_cents=payload.amount_cents,
            currency=payload.currency or "USD",
            bank_name=payload.bank_name,
            account_holder_name=payload.account_holder_name,
            account_number=payload.account_number,
            routing_number=payload.routing_number or "",
            transaction_reference=payload.transaction_reference,
            payment_proof_note=payload.payment_proof_note or "",
            status=CreditPurchaseRequest.RequestStatus.PENDING,
        )

        return {
            "id": credit_request.id,
            "status": credit_request.status,
            "message": "Credit purchase request submitted. An admin will review your transaction.",
        }

    @http_get(
        "/credits/{credit_id}",
        response={200: dict, 404: dict},
        summary="Get credit pool detail",
        description="Get full credit pool detail with transaction history for the authenticated user.",
    )
    async def get_my_credit_pool(
        self,
        request: HttpRequest,
        credit_id: int,
    ):
        """Get credit pool details with transaction history for the authenticated user."""
        # HIGH-04: Require email verification for credit operations
        require_verified_email(request)
        try:
            pool = await CreditPool.objects.select_related(
                "product", "plan"
            ).aget(pk=credit_id, user=request.user)
        except CreditPool.DoesNotExist:
            raise NotFoundException("Credit pool not found.")

        transactions = [
            tx async for tx in pool.transactions.order_by("-created_at").all()
        ]

        return {
            "id": pool.id,
            "product_name": pool.product.name,
            "plan_name": pool.plan.name,
            "plan_slug": pool.plan.slug,
            "display_amount": pool.display_amount,
            "amount_cents": pool.amount_cents,
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


# =============================================================================
# Billing Admin Controller — Admin-only operations (F1)
# =============================================================================


@api_controller(
    "/billing/admin",
    tags=["Billing — Admin (Staff Only)"],
    auth=JWTAuth(),
    permissions=[IsAuthenticated, IsAdmin],  # HIGH-14: Added IsAdmin for defense-in-depth
)
class BillingAdminController:
    """Admin-only billing endpoints — staff/superuser access required.

    F1: Refunds are restricted to admin users to prevent financial fraud.
    Only authorized staff members can initiate refunds. Regular users
    must request refunds through support channels.
    
    HIGH-14: IsAdmin permission is checked at the controller level,
    providing automatic staff verification before any method is called.
    The _require_staff() method remains as an additional safety check.
    """

    # ── CTR-01: Class-level staff guard applied at every method ──────────
    def _require_staff(self, request: HttpRequest) -> None:
        """CTR-01: Enforce staff/superuser access for all admin endpoints."""
        if not getattr(request.user, "is_staff", False):
            from ninja.errors import HttpError

            raise HttpError(403, "This action requires admin access.")

    @http_post(
        "/subscriptions/{product_slug}/refund",
        response={200: dict, 400: dict, 404: dict, 403: dict},
        summary="Issue refund (Admin only)",
        description=(
            "Issue a refund for the latest payment. "
            "Requires staff/superuser access. "
            "Refunds are capped at the latest invoice payment amount. "
            "Accepts optional target_user_id to refund another user's subscription."
        ),
    )
    @log_admin_access
    async def refund_subscription(
        self,
        request: HttpRequest,
        product_slug: str,
        # CTR-09: Use proper schema instead of raw dict
        payload: RefundInputSchema,
    ):
        """Issue a refund for a subscription payment. Admin only.

        CTR-01: Staff guard enforced via _require_staff().
        CTR-02: Queries subscription for the target user (defaults to self).
        CTR-09: Uses RefundInputSchema for automatic validation.
        """
        # CTR-01: Staff-only guard
        self._require_staff(request)

        require_verified_email(request)

        from .models import Refund
        from .schemas import RefundInputSchema

        # CTR-02: Resolve target user — allow admin to refund another user's sub
        target_user_id = getattr(payload, "target_user_id", None)
        if target_user_id:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            try:
                target_user = await sync_to_async(User.objects.get)(pk=target_user_id)
            except User.DoesNotExist:
                raise NotFoundException("Target user not found.")
        else:
            target_user = request.user

        subscription = await BillingService.aget_subscription_for_product(
            target_user, product_slug
        )
        if not subscription:
            raise NotFoundException("No subscription found for this product.")

        if not subscription.stripe_subscription_id:
            raise BadRequestException(
                "Cannot refund a subscription without a Stripe payment."
            )

        try:
            refund = await sync_to_async(create_stripe_refund)(
                subscription=subscription,
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
        except stripe.error.StripeError as e:
            raise handle_stripe_error(e, context="refund")

        return {
            "refund_id": refund.id,
            "stripe_refund_id": refund.stripe_refund_id or "",
            "amount_cents": refund.amount_cents,
            "currency": refund.currency,
            "status": refund.status,
        }

    @http_post(
        "/transactions",
        response={200: dict, 400: dict},
        summary="Get transaction history (pull from Stripe)",
        description=(
            "Pulls invoice/charge history from Stripe. No local model needed — "
            "Stripe is the source of truth for financial records. "
            "Returns paginated transactions."
        ),
    )
    @log_admin_access
    async def get_transactions(
        self,
        request: HttpRequest,
        limit: int = 25,
        starting_after: Optional[str] = None,
    ):
        """Get transaction history pulled from Stripe. CTR-01: Admin only."""
        # CTR-01: Staff-only guard
        self._require_staff(request)
        try:
            result = await sync_to_async(get_transaction_history)(
                user=request.user,
                limit=min(limit, 100),  # Cap at 100
                starting_after=starting_after,
            )
        except ValueError as e:
            raise BadRequestException(str(e))
        except stripe.error.StripeError as e:
            raise handle_stripe_error(e, context="get_transactions")

        return result

    @http_post(
        "/sync-customer",
        response={200: dict, 400: dict},
        summary="Sync Stripe customer data to local profile",
        description=(
            "Pulls the latest customer data from Stripe (email, name, currency) "
            "and syncs it to the local user profile. Ensures consistency "
            "when users update their profile via Stripe Customer Portal."
        ),
    )
    @log_admin_access
    async def sync_customer(self, request: HttpRequest):
        """Sync Stripe customer data to local profile. CTR-01: Admin only."""
        # CTR-01: Staff-only guard
        self._require_staff(request)
        try:
            result = await sync_to_async(sync_stripe_customer_data)(
                user=request.user,
            )
        except ValueError as e:
            raise BadRequestException(str(e))
        except stripe.error.StripeError as e:
            raise handle_stripe_error(e, context="sync_customer")

        return result


# =============================================================================
# Billing Webhook Controller — Stripe Webhooks
# =============================================================================


@api_controller(
    "/billing",
    tags=["Billing — Webhooks"],
    auth=None,
)
class BillingWebhookController:
    """Webhook endpoints — no JWT auth (uses request signature verification).

    These endpoints receive and process webhook events from external
    services like Stripe.  Authentication is handled via request
    signature verification (e.g. Stripe-Signature header), not JWT
    tokens.  This is why ``auth=None`` is set — the endpoint is
    publicly accessible but verified by signature.
    """

    @http_post(
        "/webhooks/stripe",
        response={200: MessageResponse},
        summary="Stripe webhook handler",
        description=(
            "Handle Stripe webhook events.  Verifies the Stripe-Signature "
            "header, logs the event for audit, then routes to the "
            "appropriate handler to update subscription state."
        ),
    )
    async def stripe_webhook(self, request: HttpRequest):
        """Handle incoming Stripe webhooks.

        Flow:
        1. Rate-limit to prevent DoS from fake events
        2. Read raw request body and Stripe-Signature header
        3. Verify the webhook signature
        3. Record the event in WebhookEventLog (idempotent)
        4. Process the event (update subscription status)

        This is the SAFETY NET sync path: webhooks keep the local DB
        in sync with Stripe for events initiated outside our system
        (e.g. customer cancels via Stripe Portal, or Stripe auto-cancels
        for failed payment after retries).  The primary activation path
        for user-initiated actions is always the controller endpoints
        above, which follow Stripe-first ordering.
        """
        payload = request.body
        sig_header = request.headers.get("Stripe-Signature", "")

        if not sig_header:
            raise BadRequestException("Missing Stripe-Signature header.")

        # CMP-05: Rate limit webhook endpoint to prevent DoS from fake events.
        # Even invalid signatures consume verification resources.
        check_rate_limit_or_raise(
            request, "webhook",
            max_attempts=100, window_seconds=60,
        )

        try:
            event = await sync_to_async(verify_and_parse_webhook)(payload, sig_header)
        except ValueError as e:
            raise BadRequestException(str(e))
        except stripe.error.SignatureVerificationError:
            raise BadRequestException("Invalid webhook signature.")

        event_type = event.get("type", "unknown")
        event_id = event.get("id", "unknown")
        logger.warning(
            "[WEBHOOK-DIAG] Received: type=%s, id=%s",
            event_type, event_id,
        )

        # Record the event for audit (best-effort — never blocks processing)
        log_entry = await sync_to_async(record_webhook_event)(event)

        # Process the event if:
        #   - Recording succeeded AND it hasn't been processed yet, OR
        #   - Recording failed (log_entry is None) — process anyway as fallback
        if log_entry is None or not log_entry.processed:
            if log_entry is None:
                logger.warning(
                    "[WEBHOOK-DIAG] Recording failed — processing anyway: "
                    "%s (%s)",
                    event_type, event_id,
                )
            else:
                logger.warning(
                    "[WEBHOOK-DIAG] Recording OK (processed=%s) — processing: %s (%s)",
                    log_entry.processed, event_type, event_id,
                )
            await sync_to_async(process_webhook_event)(event)
        else:
            logger.warning(
                "[WEBHOOK-DIAG] Already processed, skipping: %s (%s)",
                event_type, event_id,
            )

        return MessageResponse(message="Webhook processed successfully.")
