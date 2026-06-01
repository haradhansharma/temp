"""Webhook handlers for invoice.* events."""

import logging

from ....models import Subscription, SubscriptionStatus, Invoice, InvoiceStatus, RevenueRecognitionEntry, InvoiceLineItem
from ...client import ts_to_dt, get_api_key, retrieve_charge, retrieve_balance_transaction
from ..utils import sanitize_for_json

logger = logging.getLogger(__name__)


def _extract_invoice_description(invoice: dict) -> str:
    """Extract a human-readable description from the first invoice line item."""
    lines = invoice.get("lines", {}).get("data", [])
    if lines:
        return lines[0].get("description", "") or "Subscription"
    return invoice.get("description", "") or "Invoice"


def _sync_invoice_line_items(inv: Invoice, invoice: dict) -> None:
    """Sync Stripe invoice line items to local InvoiceLineItem records.

    FIN-01 Fix: Creates structured InvoiceLineItem records from the
    Stripe invoice's ``lines.data`` array.  These provide queryable,
    structured access to individual charges without parsing the full
    ``stripe_response`` JSON blob.

    Uses bulk_create with a clear-and-recreate pattern for simplicity
    (Stripe line items are immutable once created).
    """
    lines = invoice.get("lines", {}).get("data", [])
    if not lines:
        return

    # Clear existing line items and recreate
    inv.line_items.all().delete()

    items_to_create = []
    for line in lines:
        amount = line.get("amount", 0) or 0
        period = line.get("period") or {}
        discount_amounts = line.get("discount_amounts", []) or []
        tax_amounts = line.get("tax_amounts", []) or []
        total_discount = sum(
            d.get("amount", 0) or 0 for d in discount_amounts
        )
        total_tax = sum(t.get("amount", 0) or 0 for t in tax_amounts)

        items_to_create.append(InvoiceLineItem(
            invoice=inv,
            stripe_line_item_id=line.get("id", ""),
            description=line.get("description", ""),
            amount_cents=amount,
            currency=(line.get("currency") or inv.currency).upper(),
            quantity=line.get("quantity", 1) or 1,
            period_start=ts_to_dt(period.get("start")),
            period_end=ts_to_dt(period.get("end")),
            proration=line.get("proration", False) or False,
            discount_amount_cents=total_discount,
            tax_amount_cents=total_tax,
            type=line.get("type", "") or "",
        ))

    if items_to_create:
        InvoiceLineItem.objects.bulk_create(items_to_create)
        logger.debug(
            f"FIN-01: Synced {len(items_to_create)} line items "
            f"for invoice {inv.stripe_invoice_id}"
        )


def _upsert_invoice(sub: Subscription, invoice: dict) -> Invoice:
    """Create or update a local Invoice record from Stripe event data."""
    stripe_invoice_id = invoice.get("id", "")

    # Calculate discount total from invoice discounts
    total_discount_cents = 0
    subtotal_cents = invoice.get("subtotal") or 0
    for discount in invoice.get("discounts", []):
        coupon = discount.get("coupon", {}) or {}
        if coupon.get("amount_off"):
            total_discount_cents += coupon["amount_off"]
        # IN-03 Fix: Calculate percentage-based discounts from subtotal
        if coupon.get("percent_off"):
            pct = coupon["percent_off"]
            total_discount_cents += int(subtotal_cents * pct / 100)

    defaults = {
        "number": invoice.get("number", ""),
        "status": invoice.get("status", "draft"),
        "amount_paid_cents": invoice.get("amount_paid", 0),
        "amount_due_cents": invoice.get("amount_due", 0),
        "tax_cents": invoice.get("tax", 0),
        "discount_cents": total_discount_cents,
        "currency": (invoice.get("currency") or "usd").upper(),
        "period_start": ts_to_dt(invoice.get("period_start")),
        "period_end": ts_to_dt(invoice.get("period_end")),
        "description": _extract_invoice_description(invoice),
        "hosted_url": invoice.get("hosted_invoice_url", ""),
        "pdf_url": invoice.get("invoice_pdf", ""),
        "attempt_count": invoice.get("attempt_count", 1),
        "next_payment_attempt": ts_to_dt(invoice.get("next_payment_attempt")),
        "stripe_subscription_id": invoice.get("subscription", ""),
        "stripe_response": sanitize_for_json(invoice),
    }

    inv, created = Invoice.objects.update_or_create(
        stripe_invoice_id=stripe_invoice_id,
        defaults=defaults,
    )
    if created:
        inv.subscription = sub
        inv.save(update_fields=["subscription"])

    # FIN-01 Fix: Populate InvoiceLineItem records from Stripe line items.
    # This provides structured access to individual charges without parsing
    # the full stripe_response JSON.  We clear and recreate line items on
    # each upsert to stay in sync with Stripe (line items are immutable).
    _sync_invoice_line_items(inv, invoice)

    action = "Created" if created else "Updated"
    logger.info(
        f"{action} invoice {inv.number or inv.stripe_invoice_id} "
        f"for sub={sub.id}, status={inv.status}, "
        f"amount={inv.amount_paid_cents/100:.2f} {inv.currency}"
    )
    return inv


def handle_invoice_payment_succeeded(event: dict) -> None:
    """Mark past_due subscriptions as active on successful payment.

    Also creates/updates the local Invoice record with payment details
    and resets the dunning step on the subscription (payment recovered).
    """
    invoice = event["data"]["object"]
    stripe_sub_id = invoice.get("subscription")
    if not stripe_sub_id:
        return

    try:
        sub = Subscription.objects.select_for_update().get(
            stripe_subscription_id=stripe_sub_id
        )
    except Subscription.DoesNotExist:
        return

    if sub.status == SubscriptionStatus.PAST_DUE:
        sub.status = SubscriptionStatus.ACTIVE

    sub.current_period_start = ts_to_dt(invoice.get("period_start"))
    sub.current_period_end = ts_to_dt(invoice.get("period_end"))

    # Reset dunning state — payment recovered
    sub.last_dunning_email_at = None
    sub.dunning_step = 0

    sub.save()

    # Persist invoice locally (FIN-01)
    _upsert_invoice(sub, invoice)

    # FIN-09: Fetch and store Stripe processing fee from BalanceTransaction
    # IN-02 Fix: Use client.py wrappers (return plain dicts) and consistent
    # dict.get() access — no more mixing of attribute access and .get()
    charge = invoice.get("charge")
    if charge:
        try:
            charge_dict = retrieve_charge(charge)
            bt_id = charge_dict.get("balance_transaction")
            if bt_id:
                # LOW-11 FIX: Use centralized retrieve_balance_transaction from client.py
                # instead of direct stripe import for consistent error handling
                bt_dict = retrieve_balance_transaction(bt_id)
                fee = int(bt_dict.get("fee", 0) or 0)
                fee_currency = (bt_dict.get("currency") or "usd").upper()
                Invoice.objects.filter(
                    stripe_invoice_id=invoice.get("id")
                ).update(stripe_fee_cents=fee, stripe_fee_currency=fee_currency)
                logger.info(f"FIN-09: Stored fee={fee/100:.2f} {fee_currency} for invoice {invoice.get('id')}")
        except Exception as e:
            logger.warning(f"FIN-09: Could not fetch Stripe fee for invoice {invoice.get('id')}: {e}")

    # FIN-07: Create immediate revenue recognition entry for the payment date.
    # The daily recognize_revenue Celery task handles the remaining days in
    # the billing period (source='scheduled'). This webhook entry covers the
    # payment day itself (source='webhook') so revenue is never missed if the
    # Celery task fails or is delayed.
    try:
        from django.utils import timezone as tz
        period_start = ts_to_dt(invoice.get("period_start"))
        period_end = ts_to_dt(invoice.get("period_end"))
        amount_paid = invoice.get("amount_paid", 0)

        if amount_paid and period_start and period_end:
            total_days = max((period_end.date() - period_start.date()).days, 1)
            # Recognize 1/Nth of the total on the payment date
            import math
            daily_cents = math.ceil(amount_paid / total_days)

            today = tz.now().date()
            RevenueRecognitionEntry.objects.update_or_create(
                subscription=sub,
                recognized_date=today,
                defaults={
                    "plan": sub.plan,
                    "amount_cents": daily_cents,
                    "currency": (invoice.get("currency") or "usd").upper(),
                    "period_start": period_start,
                    "period_end": period_end,
                    "stripe_invoice_id": invoice.get("id", ""),
                    "source": "webhook",
                },
            )
            logger.info(
                f"FIN-07: Created revenue entry ({daily_cents/100:.2f}) "
                f"for sub={sub.id} on {today}"
            )
    except Exception as e:
        # Non-fatal: revenue recognition failure should not block payment processing
        logger.warning(f"FIN-07: Revenue recognition failed for sub={sub.id}: {e}")

    logger.info(f"Payment succeeded: sub={sub.id}")


def handle_invoice_payment_failed(event: dict) -> None:
    """Mark subscription as past_due.

    Also creates/updates the local Invoice record and resets dunning
    step to 0 so the dunning workflow starts fresh for this failure cycle.
    """
    invoice = event["data"]["object"]
    stripe_sub_id = invoice.get("subscription")
    if not stripe_sub_id:
        return

    try:
        sub = Subscription.objects.select_for_update().get(
            stripe_subscription_id=stripe_sub_id
        )
    except Subscription.DoesNotExist:
        return

    sub.status = SubscriptionStatus.PAST_DUE
    sub.dunning_step = 0
    sub.last_dunning_email_at = None
    # Set past_due_at on first transition only (MED-04 support field)
    if not sub.past_due_at:
        from django.utils import timezone
        sub.past_due_at = timezone.now()

    # IN-01 Fix: Single save instead of two separate saves.
    # Previously: save() at line 184 (status), then save() at line 188 (dunning_step).
    # Between these two saves, a concurrent webhook handler could modify the same
    # subscription, causing field overwrites (race condition).
    sub.save()

    # Persist invoice locally
    _upsert_invoice(sub, invoice)

    next_retry = ts_to_dt(invoice.get("next_payment_attempt"))
    logger.warning(
        f"Payment failed: sub={sub.id}, attempt={invoice.get('attempt_count', 1)}, "
        f"next_retry={next_retry}"
    )


def handle_invoice_created(event: dict) -> None:
    """Create local invoice record for audit trail.

    Logs invoice creation and persists it locally so that financial
    reporting, tax reconciliation, and dispute resolution don't require
    real-time Stripe API calls.
    """
    invoice = event["data"]["object"]
    stripe_sub_id = invoice.get("subscription")
    if not stripe_sub_id:
        return

    try:
        sub = Subscription.objects.get(stripe_subscription_id=stripe_sub_id)
    except Subscription.DoesNotExist:
        logger.warning(
            f"Invoice created for unknown subscription: {stripe_sub_id}"
        )
        return

    _upsert_invoice(sub, invoice)
