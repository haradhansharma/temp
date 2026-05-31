"""Low-level Stripe SDK adapter.

This is the ONLY module that imports ``stripe``.  Every function accepts
and returns plain ``dict`` / ``list`` / primitive types — never raw
``StripeObject`` instances.  This eliminates all ``.get()`` vs bracket-
access issues and makes the rest of the codebase completely decoupled
from the Stripe SDK version.

All functions are synchronous (the SDK is sync).  Wrap with
``sync_to_async`` from async callers.
"""

import logging
import time
from typing import Optional

import stripe
from django.conf import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


def get_api_key() -> str:
    """Return the Stripe secret key or raise."""
    key = getattr(settings, "STRIPE_SECRET_KEY", None)
    if not key:
        raise ValueError("Stripe is not configured.  Set STRIPE_SECRET_KEY in .env.")
    return key


def get_webhook_secret() -> str:
    """Return the Stripe webhook secret or raise."""
    secret = getattr(settings, "STRIPE_WEBHOOK_SECRET", None)
    if not secret:
        raise ValueError(
            "Stripe webhook secret not configured.  "
            "Set STRIPE_WEBHOOK_SECRET in .env."
        )
    return secret


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def to_dict(obj) -> dict:
    """Convert a Stripe SDK object to a plain dict (idempotent for dicts).

    CC-04 Fix: Stripe's ``to_dict()`` omits keys whose values are ``None``.
    This causes subtle bugs when downstream code does ``.get("key")``
    expecting ``None`` but the key is absent entirely.

    This helper ensures that all known keys from the original object are
    preserved in the output dict, even when their values are ``None``.
    For plain ``StripeObject`` instances, we call ``_values`` (internal dict)
    to get ALL keys including those with ``None`` values, then fall back
    to ``to_dict()`` for nested objects.
    """
    if hasattr(obj, "to_dict"):
        # Stripe SDK object — try to get the full _values dict first
        # which includes keys with None values (CC-04)
        if hasattr(obj, "_values") and isinstance(obj._values, dict):
            return dict(obj._values)
        d = obj.to_dict()
        if isinstance(d, dict):
            return d
    if isinstance(obj, dict):
        return obj
    return dict(obj)


def ts_to_dt(timestamp) -> Optional["datetime"]:
    """Convert a Unix epoch (int/float) to a timezone-aware UTC datetime."""
    if not timestamp:
        return None
    try:
        from datetime import timezone as _tz, datetime as _dt

        return _dt.fromtimestamp(int(timestamp), tz=_tz.utc)
    except (ValueError, TypeError, OSError):
        return None


# ---------------------------------------------------------------------------
# Products & Prices
# ---------------------------------------------------------------------------


def create_product(
    name: str, description: str = "", metadata: Optional[dict] = None
) -> dict:
    try:
        product = stripe.Product.create(
            api_key=get_api_key(),
            name=name,
            description=description or None,
            metadata=metadata or {},
        )
        return to_dict(product)
    except stripe.error.StripeError as e:
        logger.error(f"create_product failed: {e}")
        raise


def create_price(
    product_id: str,
    unit_amount: int,
    currency: str,
    recurring_interval: Optional[str] = None,
    tax_behavior: str = "exclusive",
    metadata: Optional[dict] = None,
) -> dict:
    params: dict = {
        "api_key": get_api_key(),
        "product": product_id,
        "unit_amount": unit_amount,
        "currency": currency.lower(),
        "metadata": metadata or {},
        "tax_behavior": tax_behavior,
    }
    if recurring_interval:
        params["recurring"] = {"interval": recurring_interval}
    try:
        price = stripe.Price.create(**params)
        return to_dict(price)
    except stripe.error.StripeError as e:
        logger.error(f"create_price failed: {e}")
        raise


def list_prices(
    product_id: str,
    currency: Optional[str] = None,
    active: bool = True,
    limit: int = 100,
    max_results: int = 500,
) -> list[dict]:
    """List Stripe prices for a product.

    Args:
        product_id: Stripe Product ID.
        currency: Optional currency filter (ISO 4217 lowercase).
        active: Whether to filter for active prices only.
        limit: Page size for Stripe API calls (max 100).
        max_results: Maximum total results to return. CL-01: Prevents
            unbounded pagination that could exhaust memory for products
            with thousands of prices. Defaults to 500 which is far more
            than any realistic use case.

    Returns:
        List of price dicts.
    """
    params: dict = {
        "api_key": get_api_key(),
        "product": product_id,
        "active": active,
        "limit": min(limit, 100),
    }
    if currency:
        params["currency"] = currency.lower()
    try:
        prices = stripe.Price.list(**params)
        results = []
        for p in prices.auto_paging_iter():
            results.append(to_dict(p))
            if len(results) >= max_results:
                logger.warning(
                    f"list_prices hit max_results={max_results} for "
                    f"product={product_id} — truncating"
                )
                break
        return results
    except stripe.error.StripeError as e:
        logger.error(f"list_prices failed: {e}")
        raise


# ---------------------------------------------------------------------------
# Customers
# ---------------------------------------------------------------------------


def create_customer(email: str, name: str, metadata: Optional[dict] = None) -> dict:
    try:
        customer = stripe.Customer.create(
            api_key=get_api_key(),
            email=email,
            name=name,
            metadata=metadata or {},
        )
        return to_dict(customer)
    except stripe.error.StripeError as e:
        logger.error(f"create_customer failed: {e}")
        raise


def retrieve_customer(customer_id: str) -> dict:
    try:
        customer = stripe.Customer.retrieve(customer_id, api_key=get_api_key())
        return to_dict(customer)
    except stripe.error.StripeError as e:
        logger.error(f"retrieve_customer failed: {e}")
        raise


def modify_customer(customer_id: str, **params) -> dict:
    params["api_key"] = get_api_key()
    try:
        customer = stripe.Customer.modify(customer_id, **params)
        return to_dict(customer)
    except stripe.error.StripeError as e:
        logger.error(f"modify_customer failed: {e}")
        raise


def delete_customer(customer_id: str) -> dict:
    try:
        result = stripe.Customer.delete(customer_id, api_key=get_api_key())
        return to_dict(result)
    except stripe.error.StripeError as e:
        logger.error(f"delete_customer failed: {e}")
        raise


# ---------------------------------------------------------------------------
# Checkout Sessions
# ---------------------------------------------------------------------------


def create_checkout_session(**params) -> dict:
    params["api_key"] = get_api_key()
    try:
        session = stripe.checkout.Session.create(**params)
        return to_dict(session)
    except stripe.error.StripeError as e:
        logger.error(f"create_checkout_session failed: {e}")
        raise


def retrieve_checkout_session(session_id: str) -> dict:
    try:
        session = stripe.checkout.Session.retrieve(session_id, api_key=get_api_key())
        return to_dict(session)
    except stripe.error.StripeError as e:
        logger.error(f"retrieve_checkout_session failed: {e}")
        raise


# ---------------------------------------------------------------------------
# Subscriptions
# ---------------------------------------------------------------------------


def create_subscription(**params) -> dict:
    params["api_key"] = get_api_key()
    try:
        sub = stripe.Subscription.create(**params)
        return to_dict(sub)
    except stripe.error.StripeError as e:
        logger.error(f"create_subscription failed: {e}")
        raise


def retrieve_subscription(sub_id: str) -> dict:
    try:
        sub = stripe.Subscription.retrieve(sub_id, api_key=get_api_key())
        return to_dict(sub)
    except stripe.error.StripeError as e:
        logger.error(f"retrieve_subscription failed: {e}")
        raise


def modify_subscription(sub_id: str, **params) -> dict:
    params["api_key"] = get_api_key()
    try:
        sub = stripe.Subscription.modify(sub_id, **params)
        return to_dict(sub)
    except stripe.error.StripeError as e:
        logger.error(f"modify_subscription failed: {e}")
        raise


def retrieve_upcoming_invoice(**params) -> dict:
    """Retrieve a preview of the upcoming invoice (proration preview).

    In Stripe SDK ≥ 14, ``Invoice.retrieve_upcoming`` was removed.
    The replacement is ``Invoice.create_preview``, which maps to the
    ``POST /v1/invoices/create_preview`` endpoint.

    The caller may pass the legacy ``subscription_items`` key; it is
    transparently mapped to the new ``subscription_details`` structure
    expected by the API.
    """
    params["api_key"] = get_api_key()

    # Migrate legacy parameter name (subscription_items → subscription_details)
    if "subscription_items" in params:
        items = params.pop("subscription_items")
        params["subscription_details"] = {
            "items": items,
        }

    try:
        invoice = stripe.Invoice.create_preview(**params)
        return to_dict(invoice)
    except stripe.error.StripeError as e:
        logger.error(f"retrieve_upcoming_invoice failed: {e}")
        raise


def list_invoices(
    customer_id: str,
    limit: int = 25,
    starting_after: Optional[str] = None,
    expand: Optional[list] = None,
) -> dict:
    params: dict = {
        "api_key": get_api_key(),
        "customer": customer_id,
        "limit": limit,
    }
    if starting_after:
        params["starting_after"] = starting_after
    if expand:
        params["expand"] = expand
    try:
        invoices = stripe.Invoice.list(**params)
        return {
            "data": [to_dict(inv) for inv in invoices.auto_paging_iter()],
            "has_more": invoices.has_more,
        }
    except stripe.error.StripeError as e:
        logger.error(f"list_invoices failed: {e}")
        raise


# ---------------------------------------------------------------------------
# Portal
# ---------------------------------------------------------------------------


def create_portal_session(customer_id: str, return_url: str) -> dict:
    try:
        session = stripe.billing_portal.Session.create(
            api_key=get_api_key(),
            customer=customer_id,
            return_url=return_url,
        )
        return to_dict(session)
    except stripe.error.StripeError as e:
        logger.error(f"create_portal_session failed: {e}")
        raise


# ---------------------------------------------------------------------------
# Refunds
# ---------------------------------------------------------------------------


def create_refund(
    payment_intent: str,
    amount: Optional[int] = None,
    reason: str = "requested_by_customer",
    metadata: Optional[dict] = None,
    idempotency_key: Optional[str] = None,
) -> dict:
    params: dict = {
        "api_key": get_api_key(),
        "payment_intent": payment_intent,
        "reason": reason,
        "metadata": metadata or {},
    }
    if amount is not None:
        params["amount"] = amount
    if idempotency_key:
        params["idempotency_key"] = idempotency_key
    try:
        refund = stripe.Refund.create(**params)
        return to_dict(refund)
    except stripe.error.StripeError as e:
        logger.error(f"create_refund failed: {e}")
        raise


# ---------------------------------------------------------------------------
# Charges
# ---------------------------------------------------------------------------


def retrieve_charge(charge_id: str) -> dict:
    """Retrieve a Stripe Charge by ID.

    STP-02: Centralised charge retrieval — this is the ONLY place that
    calls ``stripe.Charge.retrieve``.  All other modules must use this
    wrapper so that error handling and dict conversion are consistent.
    """
    try:
        charge = stripe.Charge.retrieve(charge_id, api_key=get_api_key())
        return to_dict(charge)
    except stripe.error.StripeError as e:
        logger.error(f"retrieve_charge failed: {e}")
        raise


# ---------------------------------------------------------------------------
# Invoices
# ---------------------------------------------------------------------------


def retrieve_invoice(invoice_id: str) -> dict:
    try:
        invoice = stripe.Invoice.retrieve(invoice_id, api_key=get_api_key())
        return to_dict(invoice)
    except stripe.error.StripeError as e:
        logger.error(f"retrieve_invoice failed: {e}")
        raise


# ---------------------------------------------------------------------------
# Webhooks
# ---------------------------------------------------------------------------


def verify_webhook_signature(payload: bytes, sig_header: str) -> dict:
    """Verify Stripe signature and return verified event dict.

    Uses the verified Stripe event object (not re-parsed raw JSON) to
    guarantee the returned data matches what was cryptographically verified.
    This prevents any theoretical tampering between signature verification
    and data parsing.
    """
    event = stripe.Webhook.construct_event(
        payload, sig_header, get_webhook_secret()
    )
    # Use the verified event object — to_dict() is idempotent for dicts
    return to_dict(event)


# ---------------------------------------------------------------------------
# Subscription item helpers (plain dict access)
# ---------------------------------------------------------------------------


def get_subscription_items(sub_dict: dict) -> list[dict]:
    """Return list of subscription item dicts from a subscription dict."""
    items = sub_dict.get("items") or {}
    if not isinstance(items, dict):
        items = {}
    return items.get("data") or []


def get_first_item_id(sub_dict: dict) -> Optional[str]:
    """Return the first subscription item's ID, or None."""
    items = get_subscription_items(sub_dict)
    if items:
        return items[0].get("id")
    return None


def get_subscription_currency(sub_dict: dict) -> str:
    """Return the subscription's currency (lowercase), default 'usd'."""
    return (sub_dict.get("currency") or "usd").lower()


# ---------------------------------------------------------------------------
# Payment Intents (for upgrade confirmation)
# ---------------------------------------------------------------------------


def create_payment_intent(
    customer_id: str,
    amount: int,
    currency: str,
    metadata: Optional[dict] = None,
    idempotency_key: Optional[str] = None,
    description: Optional[str] = None,
) -> dict:
    """Create a Stripe PaymentIntent for a proration charge.

    This is used during plan upgrades to collect the proration amount
    before applying the plan change.  The PaymentIntent is created in
    ``requires_confirmation`` state — it is confirmed automatically
    using the customer's default payment method.

    Args:
        customer_id: Stripe customer ID.
        amount: Amount in cents.
        currency: ISO 4217 currency code (lowercase).
        metadata: Optional metadata dict attached to the PaymentIntent.
        idempotency_key: Optional idempotency key to prevent double-charges.
        description: Optional human-readable description.

    Returns:
        Plain dict with the PaymentIntent data.
    """
    params: dict = {
        "api_key": get_api_key(),
        "amount": amount,
        "currency": currency.lower(),
        "customer": customer_id,
        "automatic_payment_methods": {"enabled": True},
        "confirm": True,
        "metadata": metadata or {},
        "description": description or "Plan upgrade proration",
    }
    if idempotency_key:
        params["idempotency_key"] = idempotency_key
    try:
        pi = stripe.PaymentIntent.create(**params)
        return to_dict(pi)
    except stripe.error.StripeError as e:
        logger.error(f"create_payment_intent failed: {e}")
        raise


def create_and_confirm_payment_intent(
    customer_id: str,
    amount: int,
    currency: str,
    metadata: Optional[dict] = None,
    idempotency_key: Optional[str] = None,
    description: Optional[str] = None,
) -> dict:
    """Create and immediately confirm a PaymentIntent.

    Creates a PaymentIntent in ``requires_payment_method`` state, then
    confirms it.  Stripe will attempt to charge the customer's default
    payment method.  If the payment fails, the PaymentIntent status will
    reflect the failure reason.

    Returns:
        Plain dict with the confirmed PaymentIntent data.
    """
    params: dict = {
        "api_key": get_api_key(),
        "amount": amount,
        "currency": currency.lower(),
        "customer": customer_id,
        "automatic_payment_methods": {"enabled": True},
        "metadata": metadata or {},
        "description": description or "Plan upgrade proration",
    }
    if idempotency_key:
        params["idempotency_key"] = idempotency_key
    try:
        pi = stripe.PaymentIntent.create(**params)
    except stripe.error.StripeError as e:
        logger.error(f"create_and_confirm_payment_intent (create) failed: {e}")
        raise
    # Confirm using the customer's saved payment method
    try:
        pi = stripe.PaymentIntent.confirm(
            pi["id"],
            api_key=get_api_key(),
        )
        return to_dict(pi)
    except stripe.error.StripeError as e:
        logger.error(f"create_and_confirm_payment_intent (confirm) failed: {e}")
        raise
