"""Stripe Checkout session creation and confirmation.

Pure Stripe orchestration — no business logic.
All functions return plain dicts / strings.
"""

import logging
from typing import Optional
from urllib.parse import urlencode, urlparse, urlunparse, parse_qs

from django.conf import settings
from django.db import transaction

from ..models import Plan, Product, Subscription, SubscriptionStatus
from .prices import resolve_price_id
from .customer import get_or_create_customer_id
from .client import (
    create_checkout_session as _create_checkout,
    retrieve_checkout_session as _retrieve_checkout,
    retrieve_subscription as _retrieve_subscription,
    get_api_key,
    ts_to_dt,
)

logger = logging.getLogger(__name__)


def validate_return_url(return_url: str) -> bool:
    """Validate a return_url against registered ServiceDomain entries.

    Prevents open redirect attacks by ensuring the return URL's origin
    matches an active ServiceDomain domain. The URL must use http/https
    scheme and its netloc (host+port) must exactly match a registered
    ServiceDomain.domain.

    Also allows the app's own domain (STRIPE_APP_DOMAIN) for internal
    redirects when no sister domain is involved.

    Args:
        return_url: The URL to validate.

    Returns:
        True if the URL is safe to redirect to, False otherwise.
    """
    if not return_url:
        return False

    try:
        parsed = urlparse(return_url)
    except Exception:
        return False

    # Only allow http/https schemes
    if parsed.scheme not in ("http", "https"):
        return False

    origin = parsed.netloc  # e.g. "finance.sattabase.tld" or "finance.sattabase.tld:3000"

    # Allow the app's own domain
    app_domain = getattr(settings, "STRIPE_APP_DOMAIN", "")
    if app_domain:
        app_parsed = urlparse(app_domain)
        if origin == app_parsed.netloc:
            return True

    # Check against registered service domains
    from django.core.cache import cache

    cache_key = "sattabase_allowed_cors_origins"
    allowed = cache.get(cache_key)
    if allowed is None:
        from ..models import ServiceDomain
        allowed = set(
            ServiceDomain.objects.filter(is_active=True).values_list("domain", flat=True)
        )
        cache.set(cache_key, allowed, timeout=300)

    # Exact match against registered domains (including port)
    if origin in allowed:
        return True

    # Also check origin without port (e.g. "finance.sattabase.tld" matches
    # even if return_url is "finance.sattabase.tld:3000")
    origin_without_port = origin.split(":")[0]
    if origin_without_port in allowed:
        return True

    # Check if allowed domains have ports
    for domain in allowed:
        if domain.split(":")[0] == origin_without_port:
            return True

    return False


def build_success_url(product_slug: str, plan_slug: str, return_url: str = None) -> str:
    """Build the success redirect URL with Stripe's {CHECKOUT_SESSION_ID}.

    Args:
        product_slug: Product slug for the checkout.
        plan_slug: Plan slug for the checkout.
        return_url: Optional sister-domain URL to redirect back to after
            checkout. If provided and valid, it is stored as a query param.
            The frontend will read it and perform the actual redirect after
            confirming the checkout.
    """
    base = settings.STRIPE_SUCCESS_URL.rstrip("/")
    parsed = urlparse(base)
    params = {
        k: v[0] if isinstance(v, list) else v
        for k, v in parse_qs(parsed.query, keep_blank_values=True).items()
    }
    params["product"] = product_slug
    params["plan"] = plan_slug

    # Append validated return_url so the frontend can redirect back
    if return_url and validate_return_url(return_url):
        params["return_url"] = return_url

    url = urlunparse(parsed._replace(query=urlencode(params)))
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}session_id={{CHECKOUT_SESSION_ID}}"


def build_cancel_url(product_slug: str, return_url: str = None) -> str:
    """Build the cancel redirect URL.

    Args:
        product_slug: Product slug for the checkout.
        return_url: Optional sister-domain URL to redirect back to after
            cancel. Validated before inclusion.
    """
    base = settings.STRIPE_CANCEL_URL.rstrip("/")
    parsed = urlparse(base)
    params = {
        k: v[0] if isinstance(v, list) else v
        for k, v in parse_qs(parsed.query, keep_blank_values=True).items()
    }
    params["product"] = product_slug

    if return_url and validate_return_url(return_url):
        params["return_url"] = return_url

    return urlunparse(parsed._replace(query=urlencode(params)))


def create_checkout(
    user,
    plan: Plan,
    product: Product,
    currency: str,
    trial_days: Optional[int] = None,
    return_url: Optional[str] = None,
) -> str:
    """Create a Stripe Checkout session.  Returns the checkout URL.

    Args:
        user: Django user.
        plan: Plan to subscribe to.
        product: Product the plan belongs to.
        currency: ISO 4217 code.  The checkout MUST use this exact currency.
        trial_days: Optional trial period (None = no trial).

    Raises:
        ValueError: If plan is free or tax not configured.
    """
    if plan.is_free:
        raise ValueError("Cannot checkout a free plan. Use change-plan.")

    tax_enabled = getattr(settings, "STRIPE_TAX_ENABLED", False)
    if not tax_enabled:
        logger.critical("Stripe Tax not enabled — blocking checkout.")
        raise ValueError(
            "Tax collection not configured. "
            "Contact support — checkout is temporarily disabled."
        )

    price_id = resolve_price_id(plan, currency)
    customer_id = get_or_create_customer_id(user)

    # CMP-07: Checkout deduplication — prevent double-checkout if user
    # rapidly clicks "Subscribe" or "Upgrade Now". Uses Django cache to
    # detect a recent checkout for the same user+plan+product within
    # 5 minutes. Returns the cached URL instead of creating a duplicate.
    from django.core.cache import cache

    cache_key = f"checkout_recent_{user.id}_{product.id}_{plan.slug}"
    cached_url = cache.get(cache_key)
    if cached_url:
        logger.info(
            f"CMP-07: Returning cached checkout URL for user={user.id}, "
            f"plan={plan.slug} (prevents double-checkout)"
        )
        return cached_url

    # CMP-06: ToS version tracking per checkout
    tos_version = getattr(settings, "TOS_VERSION", "1.0")

    session = _create_checkout(
        mode="subscription",
        customer=customer_id,
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=build_success_url(product.slug, plan.slug, return_url=return_url),
        cancel_url=build_cancel_url(product.slug, return_url=return_url),
        automatic_tax={"enabled": tax_enabled},
        customer_update={"address": "auto"},
        consent_collection={"terms_of_service": "required"},
        metadata={
            "user_id": str(user.id),
            "product_slug": product.slug,
            "plan_slug": plan.slug,
            "tos_version": tos_version,
        },
        subscription_data={
            "trial_period_days": trial_days,
            "metadata": {
                "user_id": str(user.id),
                "product_slug": product.slug,
                "plan_slug": plan.slug,
            },
        },
        allow_promotion_codes=True,
    )

    # FIN-05: Log exchange rate used for checkout (for reconciliation)
    if currency.upper() != plan.currency.upper():
        from ..currency_service import get_exchange_rate
        rate = get_exchange_rate(plan.currency, currency)
        logger.info(
            f"Checkout session {session['id']} currency conversion: "
            f"{plan.currency} -> {currency}, rate={rate}"
        )

    # CMP-07: Cache the checkout URL for 5 minutes to prevent double-checkout
    cache.set(cache_key, session["url"], timeout=300)

    logger.info(
        f"Checkout session {session['id']} for {user.email}, "
        f"plan={plan.slug}, currency={currency}"
    )
    return session["url"]


def confirm_checkout(session_id: str, user) -> dict:
    """Confirm a completed checkout and return activated subscription data.

    Validates payment, user ownership, then uses sync_subscription
    to update local DB from Stripe.

    Returns:
        Dict with plan_name, plan_slug, status, trial_end, current_period_end.

    Raises:
        ValueError: If session invalid, not paid, or user mismatch.
    """
    try:
        session = _retrieve_checkout(session_id)
    except stripe.error.InvalidRequestError as e:
        raise ValueError(f"Invalid checkout session: {session_id}") from e
    except stripe.error.AuthenticationError as e:
        logger.error(f"Stripe auth failed retrieving checkout {session_id}: {e}")
        raise ValueError("Payment service configuration error. Please contact support.") from e
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error retrieving checkout {session_id}: {e}")
        raise ValueError(f"Unable to verify checkout session. Please try again.") from e

    if session.get("payment_status") != "paid":
        raise ValueError(
            f"Session {session_id} not paid (status: {session.get('payment_status')})"
        )

    metadata = session.get("metadata") or {}
    if str(metadata.get("user_id")) != str(user.id):
        raise ValueError("Checkout session does not belong to this user.")

    product_slug = metadata.get("product_slug")
    plan_slug = metadata.get("plan_slug")

    # CMP-06: Validate ToS version at confirmation time
    checkout_tos_version = metadata.get("tos_version")
    current_tos_version = getattr(settings, "TOS_VERSION", "1.0")
    if checkout_tos_version and current_tos_version and checkout_tos_version != current_tos_version:
        logger.warning(
            f"ToS version mismatch for checkout {session_id}: "
            f"checkout={checkout_tos_version}, current={current_tos_version}. "
            f"Proceeding — payment already completed."
        )

    if not product_slug or not plan_slug:
        raise ValueError(f"Session {session_id} missing metadata.")

    from ..services import BillingService

    product = BillingService.get_product_by_slug(product_slug)
    if not product:
        raise ValueError(f"Product not found: {product_slug}")

    plan = BillingService.get_plan_by_slug(product_slug, plan_slug)
    if not plan:
        raise ValueError(f"Plan not found: {product_slug}/{plan_slug}")

    # Use the shared sync function to update local DB from Stripe
    from .webhooks.sync import sync_subscription_from_stripe

    stripe_sub_id = session.get("subscription")
    stripe_customer_id = session.get("customer", "")
    user_currency = getattr(user, "currency", plan.currency)

    with transaction.atomic():
        sub = (
            Subscription.objects.select_for_update()
            .filter(user=user, product=product)
            .first()
        )
        if not sub:
            sub = BillingService.get_or_create_free_subscription(user, product)
        if not sub:
            raise ValueError(f"Could not get/create subscription for {user.email}")

        if stripe_sub_id:
            sub = sync_subscription_from_stripe(
                stripe_sub_id,
                subscription=sub,
            )
        else:
            sub.plan = plan
            sub.status = SubscriptionStatus.ACTIVE
            sub.stripe_customer_id = stripe_customer_id
            if not getattr(sub, "currency", None):
                sub.currency = user_currency
            sub.save()

    return {
        "plan_name": plan.name,
        "plan_slug": plan.slug,
        "status": sub.status,
        "trial_end": sub.trial_end,
        "current_period_end": sub.current_period_end,
    }
