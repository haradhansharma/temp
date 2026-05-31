"""billing.stripe — Clean public API for Stripe integration.

Controllers and tasks should ONLY import from this package.
Never import from submodules directly — this is the stable interface.

Usage in controllers::

    from billing.stripe import (
        create_checkout,
        confirm_checkout,
        create_portal,
        get_or_create_customer_id,
        sync_customer_to_local,
        cancel_subscription_on_stripe,
        update_subscription_plan_on_stripe,
        reactivate_subscription_on_stripe,
        get_proration_preview,
        create_stripe_refund,
        get_transaction_history,
        delete_or_anonymize_customer,
        verify_and_parse_webhook,
        record_webhook_event,
        process_webhook_event,
        reconcile_unprocessed_webhooks,
    )
"""

import logging
import hashlib
import hmac
import json
import time as _time
from typing import Optional

from django.conf import settings

from ..models import Plan, Subscription
from .client import (
    retrieve_subscription,
    modify_subscription,
    retrieve_invoice,
    retrieve_charge,
    list_invoices,
    retrieve_upcoming_invoice,
    get_first_item_id,
    get_subscription_currency,
    create_refund,
    get_api_key,
    ts_to_dt,
    get_subscription_items,
    to_dict,
    create_and_confirm_payment_intent,
)
from .prices import resolve_price_id
from .customer import (
    get_or_create_customer_id,
    sync_customer_to_local,
    find_customer_id,
)
from .checkout import create_checkout, confirm_checkout
from .portal import create_portal
from .gdpr import delete_or_anonymize_customer, export_user_billing_data
from .webhooks.router import (
    verify_and_parse as verify_and_parse_webhook,
    record_event as record_webhook_event,
    process_event as process_webhook_event,
    reconcile_unprocessed as reconcile_unprocessed_webhooks,
)
from .webhooks.utils import sanitize_for_json as _sanitize_stripe_dict
from .webhooks.sync import sync_subscription_from_stripe

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Subscription management (thin wrappers over client + prices)
# ---------------------------------------------------------------------------


def cancel_subscription_on_stripe(subscription: Subscription) -> None:
    """Set cancel_at_period_end=True on Stripe."""
    if not subscription.stripe_subscription_id:
        return
    modify_subscription(
        subscription.stripe_subscription_id,
        cancel_at_period_end=True,
    )
    logger.info(
        f"Cancelled Stripe sub {subscription.stripe_subscription_id} at period end"
    )


def update_subscription_plan_on_stripe(
    subscription: Subscription,
    new_plan: Plan,
    proration_behavior: str = "create_prorations",
) -> None:
    """Swap the plan price on an existing Stripe subscription.

    Uses the existing subscription's currency for the new price.
    """
    if not subscription.stripe_subscription_id:
        return

    sub_dict = retrieve_subscription(subscription.stripe_subscription_id)
    currency = get_subscription_currency(sub_dict)
    item_id = get_first_item_id(sub_dict)

    if not item_id:
        logger.warning(f"Stripe sub {subscription.stripe_subscription_id} has no items")
        return

    price_id = resolve_price_id(new_plan, currency)

    modify_subscription(
        subscription.stripe_subscription_id,
        cancel_at_period_end=False,
        items=[{"id": item_id, "price": price_id}],
        metadata={
            "plan_slug": new_plan.slug,
            "product_slug": new_plan.product.slug,
        },
        proration_behavior=proration_behavior,
    )
    logger.info(
        f"Updated Stripe sub {subscription.stripe_subscription_id} "
        f"-> {new_plan.slug} (currency={currency})"
    )


def reactivate_subscription_on_stripe(
    subscription: Subscription,
    new_plan: Plan,
) -> None:
    """Remove cancel_at_period_end and swap plan price on Stripe.

    Uses the existing subscription's currency for the new price.
    """
    if not subscription.stripe_subscription_id:
        raise ValueError("No Stripe subscription to reactivate.")

    sub_dict = retrieve_subscription(subscription.stripe_subscription_id)
    currency = get_subscription_currency(sub_dict)
    item_id = get_first_item_id(sub_dict)

    if not item_id:
        raise ValueError("Stripe subscription has no items.")

    price_id = resolve_price_id(new_plan, currency)

    modify_subscription(
        subscription.stripe_subscription_id,
        cancel_at_period_end=False,
        items=[{"id": item_id, "price": price_id}],
        metadata={
            "plan_slug": new_plan.slug,
            "product_slug": new_plan.product.slug,
            "user_id": str(subscription.user.id),
        },
        proration_behavior="create_prorations",
    )
    logger.info(
        f"Reactivated Stripe sub {subscription.stripe_subscription_id} "
        f"-> {new_plan.slug} (currency={currency})"
    )


# ---------------------------------------------------------------------------
# Proration preview
# ---------------------------------------------------------------------------


def get_proration_preview(subscription: Subscription, new_plan: Plan) -> dict:
    """Preview proration for a plan change."""
    if not subscription.stripe_subscription_id:
        raise ValueError("No Stripe subscription — cannot preview.")

    sub_dict = retrieve_subscription(subscription.stripe_subscription_id)
    currency = get_subscription_currency(sub_dict)
    item_id = get_first_item_id(sub_dict)

    if not item_id:
        raise ValueError("Stripe subscription has no items.")

    price_id = resolve_price_id(new_plan, currency)

    preview = retrieve_upcoming_invoice(
        customer=subscription.stripe_customer_id,
        subscription=subscription.stripe_subscription_id,
        subscription_items=[{"id": item_id, "price": price_id}],
    )

    preview_currency = preview.get("currency", currency) or currency
    return {
        "subtotal": (preview.get("subtotal_excluding_tax") or 0) / 100,
        "tax": (preview.get("tax") or 0) / 100,
        "total": (preview.get("total") or 0) / 100,
        "next_billing": (preview.get("amount_due") or 0) / 100,
        "currency": preview_currency.upper(),
    }


# ---------------------------------------------------------------------------
# Refunds
# ---------------------------------------------------------------------------


def create_stripe_refund(subscription, amount_cents=None, reason="", initiated_by=None,
                         charge_id=None, reason_category="", admin_notes=""):
    """Create a Stripe refund for a payment on a subscription.

    Args:
        subscription: Subscription object.
        amount_cents: Optional refund amount. If None, refunds full amount.
        reason: Free-text reason visible to customer.
        initiated_by: Admin user who initiated the refund.
        charge_id: Optional specific Stripe Charge ID to refund (for historical
            payments). If None, uses the latest invoice's payment intent.
        reason_category: Structured reason code for audit trail.
        admin_notes: Internal admin-only notes about the refund.

    Raises:
        ValueError: If no Stripe subscription, no invoices, no payment,
            or refund amount exceeds chargeable amount.
    """
    from ..models import Refund, RefundStatus
    import time as _time

    if not subscription.stripe_subscription_id:
        raise ValueError("No Stripe subscription ID.")

    # --- Determine the payment intent to refund ---
    payment_intent_id = None
    refund_max = 0

    if charge_id:
        # FIN-03: Support refunding a specific historical charge
        # STP-02: Use client.py wrapper instead of direct stripe import
        charge_dict = retrieve_charge(charge_id)
        payment_intent_id = charge_dict.get("payment_intent")
        refund_max = charge_dict.get("amount", 0)
        if not payment_intent_id:
            raise ValueError(f"Charge {charge_id} has no payment intent.")
    else:
        # Default: use the latest invoice's payment
        sub_dict = retrieve_subscription(subscription.stripe_subscription_id)
        latest_invoice_id = sub_dict.get("latest_invoice")
        if not latest_invoice_id:
            raise ValueError("No invoices for this subscription.")

        invoice = retrieve_invoice(latest_invoice_id)
        payment_intent_id = invoice.get("payment_intent")
        if not payment_intent_id:
            raise ValueError("No payment on latest invoice.")

        # FIN-03: Cap refund at the actual amount paid (not amount_due)
        refund_max = invoice.get("amount_paid") or invoice.get("amount_due") or 0

    currency = getattr(subscription, "currency", None) or "usd"

    # FIN-03: Validate refund amount does not exceed chargeable amount
    if amount_cents and amount_cents > refund_max:
        raise ValueError(
            f"Refund amount ({amount_cents / 100:.2f} {currency.upper()}) exceeds "
            f"the maximum chargeable amount ({refund_max / 100:.2f} {currency.upper()})."
        )

    # STP-03 Fix: Deterministic idempotency key — no timestamp.
    # Using amount_cents ensures the key is unique per refund amount while
    # being stable across retries. Retries with the same amount will be
    # idempotent instead of creating duplicate refunds.
    idempotency_key = (
        f"refund-{subscription.id}-{payment_intent_id}-{amount_cents or 'full'}"
    )

    refund = create_refund(
        payment_intent=payment_intent_id,
        amount=amount_cents,
        reason=reason,
        metadata={
            "subscription_id": str(subscription.id),
            "reason": reason,
            "initiated_by": str(initiated_by.id) if initiated_by else "system",
            "reason_category": reason_category,
        },
        idempotency_key=idempotency_key,
    )

    record = Refund.objects.create(
        subscription=subscription,
        stripe_refund_id=refund["id"],
        stripe_charge_id=payment_intent_id,
        amount_cents=amount_cents or refund.get("amount", 0),
        currency=currency,
        reason=reason,
        status=(
            RefundStatus.COMPLETED
            if refund.get("status") == "succeeded"
            else RefundStatus.PENDING
        ),
        initiated_by=initiated_by,
        reason_category=reason_category,
        admin_notes=admin_notes,
        stripe_response=_sanitize_stripe_dict(refund),
    )
    logger.info(f"Refund created: {refund['id']} (amount={amount_cents or 'full'}, charge={charge_id or 'latest'})")
    return record


# ---------------------------------------------------------------------------
# Transaction history
# ---------------------------------------------------------------------------


def get_transaction_history(user, limit=25, starting_after=None) -> dict:
    """Pull invoice/charge history from Stripe.

    Returns enriched transaction data matching the frontend TransactionItemSchema
    including charge details, payment method info, card brand, tax, and periods.
    """
    customer_id = find_customer_id(user)
    if not customer_id:
        return {"transactions": [], "has_more": False, "currency": "USD"}

    default_currency = getattr(user, "currency", "USD")

    result = list_invoices(
        customer_id=customer_id,
        limit=min(limit, 100),
        starting_after=starting_after,
        expand=["data.charge"],
    )

    transactions = []
    for inv in result["data"]:
        # Extract charge and payment method details from expanded data
        charge = inv.get("charge") or {}
        charge_obj = charge if isinstance(charge, dict) else {}
        payment_method_details = charge_obj.get("payment_method_details") or {}
        card = payment_method_details.get("card") or {}

        # Extract description from invoice lines
        lines_data = (inv.get("lines") or {}).get("data") or []
        line_desc = (
            lines_data[0].get("description", "Subscription")
            if lines_data
            else "Invoice"
        )

        transactions.append(
            {
                "id": inv.get("id"),
                "type": "invoice",
                "number": inv.get("number"),
                "status": inv.get("status"),
                "amount_paid": (inv.get("amount_paid") or 0) / 100,
                "amount_due": (inv.get("amount_due") or 0) / 100,
                "tax": (inv.get("tax") or 0) / 100,
                "currency": (inv.get("currency") or "usd").upper(),
                "description": inv.get("description") or line_desc,
                "hosted_url": inv.get("hosted_invoice_url"),
                "pdf_url": inv.get("invoice_pdf"),
                "created": inv.get("created"),
                "period_start": inv.get("period_start"),
                "period_end": inv.get("period_end"),
                "paid": inv.get("status") == "paid",
                "attempt_count": inv.get("attempt_count", 1),
                "charge_id": charge_obj.get("id", ""),
                "payment_method": card.get("last4", ""),
                "card_brand": card.get("brand", ""),
            }
        )

    return {
        "transactions": transactions,
        "has_more": result["has_more"],
        "currency": default_currency,
    }


# ---------------------------------------------------------------------------
# Backward-compatible aliases (for tasks.py)
# ---------------------------------------------------------------------------

sync_stripe_customer_data = sync_customer_to_local


# ---------------------------------------------------------------------------
# Safe Plan Change with Preview Token
# ---------------------------------------------------------------------------

# Token expiry: 10 minutes
_PREVIEW_TOKEN_TTL = 600


def _get_signing_secret() -> str:
    """Return a secret for signing preview tokens.

    Uses the same Django SECRET_KEY.  This is fine because the token is
    short-lived (10 min) and bound to user_id + subscription_id + plan_slug.
    """
    return settings.SECRET_KEY


def generate_preview_token(
    user_id: int,
    subscription_id: int,
    plan_slug: str,
    total_cents: int,
    currency: str,
) -> str:
    """Generate a time-limited HMAC token for plan change confirmation.

    The token binds together user_id, subscription_id, plan_slug, and the
    exact proration amount + currency.  Any tampering with these values
    invalidates the token.

    Args:
        user_id: The user performing the change.
        subscription_id: The subscription being changed.
        plan_slug: The target plan slug.
        total_cents: Proration total in cents (as returned by preview).
        currency: Currency code (lowercase).

    Returns:
        HMAC hex string.
    """
    payload = f"{user_id}:{subscription_id}:{plan_slug}:{total_cents}:{currency}:{int(_time.time())}"
    secret = _get_signing_secret()
    sig = hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{sig}:{int(_time.time())}"


def verify_preview_token(
    token: str,
    user_id: int,
    subscription_id: int,
    plan_slug: str,
    total_cents: int,
    currency: str,
) -> bool:
    """Verify a preview token.

    Checks:
    1.  HMAC signature matches the payload.
    2.  Token has not expired (10 minute TTL).
    3.  Bound values (user_id, subscription_id, plan_slug, amount, currency)
        match what was signed.
    4.  CTR-04 Fix: ±1 cent tolerance on total_cents to handle Stripe's
        floating-point rounding edge cases where the preview amount may
        differ by 1 cent between preview and confirm calls.

    Args:
        token: The token string from preview_plan_change.
        user_id: The user confirming the change.
        subscription_id: The subscription being changed.
        plan_slug: The target plan slug.
        total_cents: Expected proration total in cents.
        currency: Expected currency code.

    Returns:
        True if valid, False otherwise.
    """
    try:
        sig_part, ts_part = token.rsplit(":", 1)
        ts = int(ts_part)
    except (ValueError, AttributeError):
        return False

    # Check expiry
    if _time.time() - ts > _PREVIEW_TOKEN_TTL:
        return False

    secret = _get_signing_secret()

    # CTR-04 Fix: Check ±1 cent tolerance for Stripe rounding drift.
    # The proration amount may differ by 1 cent between the preview call
    # and the confirm call due to floating-point arithmetic differences.
    # We verify the exact signed amount first (fast path), then fall back
    # to checking the ±1 cent range.
    for candidate_cents in (total_cents, total_cents - 1, total_cents + 1):
        payload = f"{user_id}:{subscription_id}:{plan_slug}:{candidate_cents}:{currency}:{ts}"
        expected_sig = hmac.new(
            secret.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        if hmac.compare_digest(sig_part, expected_sig):
            return True

    return False


def classify_plan_change(old_plan: Plan, new_plan: Plan) -> str:
    """Classify a plan change as upgrade, downgrade, or lateral.

    Compares the price in the same currency.  Falls back to comparing
    price_cents if currencies differ.

    Args:
        old_plan: Current plan.
        new_plan: Target plan.

    Returns:
        One of: 'upgrade', 'downgrade', 'lateral'.
    """
    if old_plan.currency == new_plan.currency:
        if new_plan.price_cents > old_plan.price_cents:
            return "upgrade"
        elif new_plan.price_cents < old_plan.price_cents:
            return "downgrade"
        else:
            return "lateral"
    # Different currencies — compare price_cents as a rough heuristic
    # (in production you'd convert, but this is a safety gate not a quote)
    if new_plan.price_cents > old_plan.price_cents:
        return "upgrade"
    elif new_plan.price_cents < old_plan.price_cents:
        return "downgrade"
    return "lateral"


def execute_safe_plan_change(
    subscription: Subscription,
    new_plan: Plan,
    change_type: str,
    proration_total_cents: int,
    proration_currency: str,
) -> dict:
    """Execute a plan change with proper payment gating.

    Flow:
    1. **Downgrade / lateral**: Modify subscription with
       ``proration_behavior='none'`` so the change takes effect at the
       next billing cycle.  No immediate charge.
    2. **Upgrade**: Create and confirm a PaymentIntent for the proration
       amount first.  Only if payment succeeds, modify the subscription.

    Args:
        subscription: The Subscription model instance.
        new_plan: The target Plan model instance.
        change_type: One of 'upgrade', 'downgrade', 'lateral'.
        proration_total_cents: Total proration amount in cents.
        proration_currency: Currency code (lowercase).

    Returns:
        Dict with keys: status, payment_intent_id, amount_charged.

    Raises:
        ValueError: If subscription has no Stripe ID or no items.
        stripe.error.StripeError: If any Stripe call fails.
    """
    if not subscription.stripe_subscription_id:
        raise ValueError("No Stripe subscription — cannot change plan.")

    sub_dict = retrieve_subscription(subscription.stripe_subscription_id)
    currency = get_subscription_currency(sub_dict)
    item_id = get_first_item_id(sub_dict)

    if not item_id:
        raise ValueError("Stripe subscription has no items.")

    price_id = resolve_price_id(new_plan, currency)
    payment_intent_id = None
    amount_charged = 0

    if change_type == "upgrade" and proration_total_cents > 0:
        # ── UPGRADE: Charge first, then change ──
        # STP-04 Fix: Deterministic idempotency key — no timestamp.
        # Using the subscription+plan slug ensures the key is unique per
        # plan change while being stable across retries.  A retry after a
        # transient failure will be idempotent instead of creating a
        # duplicate charge.
        idempotency_key = (
            f"plan-change-{subscription.id}-{new_plan.slug}-{price_id}"
        )
        pi_result = create_and_confirm_payment_intent(
            customer_id=subscription.stripe_customer_id,
            amount=proration_total_cents,
            currency=proration_currency.lower(),
            metadata={
                "subscription_id": str(subscription.id),
                "plan_change": f"{subscription.plan.slug}->{new_plan.slug}",
                "type": "proration",
            },
            idempotency_key=idempotency_key,
            description=(
                f"Plan upgrade proration: {subscription.plan.name} → {new_plan.name}"
            ),
        )
        payment_intent_id = pi_result.get("id")

        if pi_result.get("status") not in ("succeeded", "processing"):
            raise stripe.error.StripeError(
                f"Payment for upgrade failed: {pi_result.get('status')}. "
                f"PaymentIntent: {payment_intent_id}"
            )

        amount_charged = proration_total_cents
        # For upgrades, apply the change immediately with prorations
        modify_subscription(
            subscription.stripe_subscription_id,
            cancel_at_period_end=False,
            items=[{"id": item_id, "price": price_id}],
            metadata={
                "plan_slug": new_plan.slug,
                "product_slug": new_plan.product.slug,
                "payment_intent": payment_intent_id,
            },
            proration_behavior="create_prorations",
        )
    else:
        # ── DOWNGRADE / LATERAL: Change at next billing ──
        modify_subscription(
            subscription.stripe_subscription_id,
            cancel_at_period_end=False,
            items=[{"id": item_id, "price": price_id}],
            metadata={
                "plan_slug": new_plan.slug,
                "product_slug": new_plan.product.slug,
            },
            proration_behavior="none",
        )

    logger.info(
        f"Safe plan change: sub={subscription.id}, "
        f"{subscription.plan.slug}->{new_plan.slug}, "
        f"type={change_type}, charged={amount_charged/100:.2f} {proration_currency}"
    )

    return {
        "status": "succeeded",
        "payment_intent_id": payment_intent_id,
        "amount_charged": amount_charged,
    }
