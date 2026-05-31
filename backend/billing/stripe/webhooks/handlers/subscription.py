"""Webhook handlers for customer.subscription.* events."""

import logging

from ....models import Subscription, SubscriptionStatus
from ..sync import sync_subscription_from_stripe

logger = logging.getLogger(__name__)


def handle_subscription_created(event: dict) -> None:
    """Log new subscription — sync handles the rest."""
    obj = event["data"]["object"]
    metadata = obj.get("metadata") or {}
    logger.info(
        f"Stripe subscription created: {obj.get('id')} "
        f"for user={metadata.get('user_id')}"
    )


def handle_subscription_updated(event: dict) -> None:
    """Sync subscription state from Stripe (plan change, cancel, period update)."""
    obj = event["data"]["object"]
    stripe_sub_id = obj.get("id")
    cancel_at_end = obj.get("cancel_at_period_end", False)
    cancel_at_raw = obj.get("cancel_at")
    stripe_status = obj.get("status", "")
    logger.warning(
        "[WEBHOOK-DIAG] handle_subscription_updated: sub=%s, "
        "status=%s, cancel_at_period_end=%s, cancel_at=%s, schedule=%s",
        stripe_sub_id, stripe_status, cancel_at_end, cancel_at_raw,
        obj.get("schedule"),
    )
    if not stripe_sub_id:
        return

    try:
        sync_subscription_from_stripe(stripe_sub_id)
    except Subscription.DoesNotExist:
        logger.warning("subscription.updated: no local sub for %s", stripe_sub_id)


def handle_subscription_deleted(event: dict) -> None:
    """Mark local subscription as EXPIRED."""
    stripe_sub_id = event["data"]["object"].get("id")
    if not stripe_sub_id:
        return

    try:
        sub = Subscription.objects.select_for_update().get(
            stripe_subscription_id=stripe_sub_id
        )
    except Subscription.DoesNotExist:
        logger.warning(f"subscription.deleted: no local sub for {stripe_sub_id}")
        return

    from ...client import ts_to_dt
    from django.utils import timezone

    sub.status = SubscriptionStatus.EXPIRED
    sub.current_period_end = (
        ts_to_dt(event["data"]["object"].get("ended_at")) or timezone.now()
    )
    sub.save()
    logger.info(f"Subscription expired: sub={sub.id}")


def handle_trial_will_end(event: dict) -> None:
    """Log trial ending soon."""
    obj = event["data"]["object"]
    stripe_sub_id = obj.get("id")
    try:
        sub = Subscription.objects.select_for_update().get(
            stripe_subscription_id=stripe_sub_id
        )
        logger.info(f"Trial ending soon: user={sub.user_id}, plan={sub.plan.slug}")
    except Subscription.DoesNotExist:
        logger.warning(f"trial_will_end: no sub for {stripe_sub_id}")
