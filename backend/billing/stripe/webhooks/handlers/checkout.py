"""Webhook handler for checkout.session.completed."""

import logging

from django.utils import timezone

from ....models import Plan, Product, CreditPool
from ...client import ts_to_dt
from ..sync import sync_subscription_from_stripe
from ....services import BillingService

logger = logging.getLogger(__name__)


def handle_checkout_completed(event: dict) -> None:
    """Activate local subscription after Stripe checkout payment.

    Also cancels any active credit pools for the same user+product
    to prevent double-access.
    """
    session = event["data"]["object"]
    metadata = session.get("metadata") or {}
    user_id = metadata.get("user_id")
    product_slug = metadata.get("product_slug")
    plan_slug = metadata.get("plan_slug")

    if not all([user_id, product_slug, plan_slug]):
        logger.warning(
            f"checkout.session.completed missing metadata: {session.get('id')}"
        )
        return

    stripe_sub_id = session.get("subscription")
    if not stripe_sub_id:
        logger.warning(f"checkout.session.completed no sub ID: {session.get('id')}")
        return

    # Cancel any active credit pools for this user+product
    try:
        product = Product.objects.get(slug=product_slug)
        credit_pools = CreditPool.objects.filter(
            user_id=user_id,
            product=product,
            status=CreditPool.CreditPoolStatus.ACTIVE,
        )
        for pool in credit_pools:
            pool.status = CreditPool.CreditPoolStatus.CANCELLED
            pool.expires_at = timezone.now()
            pool.current_period_end = timezone.now()
            pool.save(update_fields=["status", "expires_at", "current_period_end", "updated_at"])
            logger.info(
                "CREDIT_POOL_CANCELLED_ON_STRIPE_SUB: "
                "credit_id=%s, user_id=%s, product=%s, stripe_sub=%s",
                pool.id, user_id, product_slug, stripe_sub_id,
            )
    except Product.DoesNotExist:
        logger.warning(f"Product '{product_slug}' not found during credit pool cancellation")
    except Exception as e:
        logger.error(f"Error cancelling credit pools on Stripe checkout: {e}")

    # Sync from Stripe — the single source of truth
    try:
        sync_subscription_from_stripe(stripe_sub_id)
    except Exception as e:
        logger.error(f"Failed to sync subscription after checkout: {e}")
