"""Stripe Price resolution.

Responsible for:
  - Ensuring Stripe Product exists for a Plan
  - Creating / reusing Stripe Prices in any currency
  - No currency conversion here — amounts come from the exchange-rate
    service before calling in.

All functions return plain price_id strings.
"""

import logging
from typing import Optional
from datetime import datetime, timezone

from django.conf import settings

from ..models import Plan, BillingCycle
from .client import get_api_key, create_product, create_price, list_prices, to_dict

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    """Return current UTC time as ISO 8601 string for metadata timestamps."""
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Product
# ---------------------------------------------------------------------------


def ensure_product(plan: Plan) -> str:
    """Return the Stripe Product ID for *plan*'s product, creating it if missing."""
    product = plan.product  # Plan -> Product FK
    if product.stripe_product_id:
        return product.stripe_product_id

    result = create_product(
        name=product.name,
        description=product.description or f"{product.name} subscription",
        metadata={"product_slug": product.slug},
    )
    product.stripe_product_id = result["id"]
    product.save(update_fields=["stripe_product_id"])
    logger.info(f"Created Stripe product {result['id']} for '{product.slug}'")
    return product.stripe_product_id


# ---------------------------------------------------------------------------
# Prices
# ---------------------------------------------------------------------------

_INTERVAL_MAP = {
    BillingCycle.MONTHLY: "month",
    BillingCycle.YEARLY: "year",
    BillingCycle.LIFETIME: None,
}


def _billing_interval(plan: Plan) -> Optional[str]:
    return _INTERVAL_MAP.get(plan.billing_cycle)


def _tax_behavior(plan: Plan) -> str:
    return "inclusive" if getattr(plan, "tax_inclusive", False) else "exclusive"


def ensure_base_price(plan: Plan) -> str:
    """Return the plan's base-currency Stripe Price ID, creating it if missing."""
    if plan.stripe_price_id:
        return plan.stripe_price_id

    product_id = ensure_product(plan)
    interval = _billing_interval(plan)

    result = create_price(
        product_id=product_id,
        unit_amount=plan.price_cents,
        currency=plan.currency,
        recurring_interval=interval,
        tax_behavior=_tax_behavior(plan),
        metadata={"plan_slug": plan.slug, "product_slug": plan.product.slug},
    )
    plan.stripe_price_id = result["id"]
    plan.save(update_fields=["stripe_price_id"])
    logger.info(
        f"Created Stripe price {result['id']} for plan '{plan.slug}' "
        f"({plan.price_cents / 100:.2f} {plan.currency})"
    )
    return plan.stripe_price_id


def resolve_price_id(plan: Plan, currency: str) -> str:
    """Get or create a Stripe Price for *plan* in *currency*.

    This is the single entry-point used by checkout, reactivation, and
    plan-change flows.  It guarantees the returned price_id is in the
    requested currency and matches the plan's billing interval.

    PR-01 Fix: Uses Django's ``select_for_update()`` row-level lock on
    the Plan record to prevent a TOCTOU race condition where two concurrent
    requests both list_prices() (finding no match), then both create_price()
    (creating duplicate Stripe prices).  The lock serializes the check-then-create
    sequence so only one request proceeds at a time per plan.

    If *currency* matches the plan's base currency, the base price is
    returned directly.  Otherwise an existing price is looked up on
    Stripe, or a new one is created (after converting the amount via
    ``currency_service``).

    Returns:
        Stripe price_id string (``price_...``).
    Raises:
        ValueError: If the exchange rate is unavailable.
    """
    target = currency.upper()
    base = plan.currency.upper()

    if target == base:
        return ensure_base_price(plan)

    # PR-01 Fix: Lock the plan row to prevent duplicate price creation
    from django.db import transaction
    from ..models import Plan as PlanModel

    with transaction.atomic():
        # Re-fetch the plan with a row-level lock
        locked_plan = PlanModel.objects.select_for_update().get(pk=plan.pk)

        # Check if base price was created while we waited for the lock
        if locked_plan.stripe_price_id and target == locked_plan.currency.upper():
            return locked_plan.stripe_price_id

        product_id = ensure_product(locked_plan)
        interval = _billing_interval(locked_plan)

        # Search for an existing price in the target currency
        existing = list_prices(product_id=product_id, currency=target, active=True)
        for ep in existing:
            ep_recurring = ep.get("recurring") or {}
            ep_interval = (
                ep_recurring.get("interval") if isinstance(ep_recurring, dict) else None
            )
            if ep_interval == interval:
                logger.info(
                    f"Reusing Stripe price {ep['id']} ({target}) for plan '{locked_plan.slug}'"
                )
                return ep["id"]

        # No match — convert amount and create
        from ..currency_service import convert_price

        converted_cents, rate = convert_price(locked_plan.price_cents, base, target)
        if not converted_cents or converted_cents <= 0:
            raise ValueError(
                f"No exchange rate for {base} -> {target}. " f"Seed exchange rates first."
            )

        result = create_price(
            product_id=product_id,
            unit_amount=converted_cents,
            currency=target,
            recurring_interval=interval,
            tax_behavior=_tax_behavior(locked_plan),
            metadata={
                "plan_slug": locked_plan.slug,
                "product_slug": locked_plan.product.slug,
                "converted_from": base,
                # FIN-05 Fix: Store exchange rate at price creation time.
                # This rate is immutable once the Stripe price is created,
                # providing an audit trail for historical price accuracy.
                # Previously, only the price amount was stored without the
                # rate, making it impossible to verify conversions later.
                "exchange_rate": str(rate) if rate else "",
                "exchange_rate_fetched_at": _now_iso(),
            },
        )
        logger.info(
            f"Created Stripe price {result['id']} for plan '{locked_plan.slug}' in "
            f"{target} ({locked_plan.price_cents} {base} -> {converted_cents} {target}, "
            f"rate={rate})"
        )
        return result["id"]
