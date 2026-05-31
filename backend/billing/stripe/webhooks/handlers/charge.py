"""Webhook handlers for charge.refunded and customer.updated."""

import logging

from ....models import Subscription, Refund, RefundStatus
from ...client import ts_to_dt, retrieve_invoice
from ..utils import sanitize_for_json

logger = logging.getLogger(__name__)


def handle_charge_refunded(event: dict) -> None:
    """Create local Refund record from Stripe-initiated refund.

    CH-01 Fix: Resolve the correct subscription by tracing the chain:
    charge -> payment_intent -> invoice -> subscription_details.stripe_subscription_id
    This replaces the previous broken .first() which returned an arbitrary
    subscription from the entire database.
    """
    charge = event["data"]["object"]
    charge_id = charge.get("id")
    refunds = charge.get("refunds") or {}
    refund_data = (refunds.get("data") or [None])[0] if refunds else None

    if not refund_data or not refund_data.get("id"):
        logger.info(f"charge.refunded {charge_id}: no refund object")
        return

    refund_id = refund_data["id"]
    payment_intent_id = charge.get("payment_intent")
    if not payment_intent_id:
        return

    # Avoid duplicate
    if Refund.objects.filter(stripe_refund_id=refund_id).exists():
        return

    # CH-01 Fix: Resolve subscription from charge -> payment_intent -> invoice -> subscription
    sub = _resolve_subscription_from_charge(charge)
    if not sub:
        logger.warning(
            f"charge.refunded {charge_id}: could not resolve subscription "
            f"from payment_intent={payment_intent_id}"
        )
        return

    Refund.objects.create(
        subscription=sub,
        stripe_refund_id=refund_id,
        stripe_charge_id=payment_intent_id,
        amount_cents=refund_data.get("amount", 0),
        currency=charge.get("currency", "USD"),
        reason=f"Refund via Stripe Dashboard (charge {charge_id})",
        status=(
            RefundStatus.COMPLETED
            if refund_data.get("status") == "succeeded"
            else RefundStatus.PENDING
        ),
        initiated_by=None,
        stripe_response=sanitize_for_json(refund_data),
    )
    logger.info(f"Refund record created: {refund_id} for sub={sub.id}")


def _resolve_subscription_from_charge(charge: dict):
    """Resolve the correct subscription from a charge object.

    Traces the chain: charge -> payment_intent -> invoice -> subscription.
    Falls back to: charge -> invoice -> subscription (for direct charges).
    Returns None if no subscription can be found.
    """
    payment_intent_id = charge.get("payment_intent")
    invoice_id = charge.get("invoice")

    stripe_sub_id = None

    # Path 1: charge -> invoice -> subscription_details
    if invoice_id:
        try:
            invoice = retrieve_invoice(invoice_id)
            # subscription_details is the reliable field in modern Stripe
            sub_details = invoice.get("subscription_details") or {}
            stripe_sub_id = sub_details.get("subscription")
            # Fallback: top-level subscription field
            if not stripe_sub_id:
                stripe_sub_id = invoice.get("subscription")
        except Exception as e:
            logger.warning(f"CH-01: Could not retrieve invoice {invoice_id}: {e}")

    # Path 2: If no invoice, try from the charge's expandable invoice
    if not stripe_sub_id and not invoice_id:
        # charge may have expanded invoice data
        expanded_invoice = charge.get("invoice")
        if expanded_invoice and isinstance(expanded_invoice, dict):
            stripe_sub_id = expanded_invoice.get("subscription")

    if not stripe_sub_id:
        return None

    try:
        return Subscription.objects.get(stripe_subscription_id=stripe_sub_id)
    except Subscription.DoesNotExist:
        logger.warning(
            f"CH-01: No local subscription found for "
            f"stripe_subscription_id={stripe_sub_id}"
        )
        return None


def handle_customer_updated(event: dict) -> None:
    """Sync Stripe customer data changes to local user."""
    customer = event["data"]["object"]
    customer_id = customer.get("id")
    if not customer_id:
        return

    try:
        sub = (
            Subscription.objects.select_for_update()
            .filter(stripe_customer_id=customer_id)
            .first()
        )
        if not sub:
            return

        user = sub.user
        updated = False

        email = customer.get("email")
        if email and email != user.email:
            user.email = email
            updated = True

        name = customer.get("name")
        if name:
            parts = name.strip().split(" ", 1)
            if parts[0] and parts[0] != user.first_name:
                user.first_name = parts[0]
                updated = True
            if len(parts) > 1 and parts[1] != user.last_name:
                user.last_name = parts[1]
                updated = True

        metadata = customer.get("metadata") or {}
        currency = (
            metadata.get("preferred_currency") if isinstance(metadata, dict) else None
        )
        if currency and hasattr(user, "currency"):
            choices = [
                c[0]
                for c in getattr(
                    user.__class__, "CurrencyChoices", type("C", (), {"choices": ()})
                )
            ]
            if currency in choices and currency != user.currency:
                user.currency = currency
                updated = True

        if updated:
            user.save()
            logger.info(f"Customer synced from webhook for user {user.id}")

    except Exception as e:
        logger.error(f"customer.updated sync failed for {customer_id}: {e}")

# lat done