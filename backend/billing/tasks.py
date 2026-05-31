"""Celery tasks for the billing app.

Periodic tasks run by Celery Beat:
  - reconcile_webhooks: Retry failed webhook events (every 6 hours)
  - sync_customer_data: Sync Stripe customer data to local profiles (daily)
  - dunning_retry: Process past_due subscriptions with staged email + action workflow (daily)
  - update_exchange_rates: Fetch latest currency exchange rates (daily)
  - recognize_revenue: Daily revenue recognition for active subscriptions (daily)
"""

import logging
from celery import shared_task

logger = logging.getLogger(__name__)


# =============================================================================
# Dunning Configuration
# =============================================================================

# Staged dunning workflow: each step triggers at the given day threshold.
# Steps are cumulative — if a subscription reaches day 5, both step 1 and
# step 2 actions will fire (unless already sent).
DUNNING_STEPS = [
    {
        "step": 1,
        "days": 3,
        "action": "email_reminder",
        "subject": "Payment Issue: Update Your Payment Method",
        "body_template": (
            "Hi {first_name},\n\n"
            "We were unable to process the payment for your {plan_name} "
            "subscription ({product_name}). This may be due to an expired "
            "or changed payment method.\n\n"
            "Please update your payment method as soon as possible to avoid "
            "service interruption:\n\n"
            "{portal_link}\n\n"
            "If you believe this is an error, please contact our support team.\n\n"
            "Thank you for being a valued customer."
        ),
    },
    {
        "step": 2,
        "days": 5,
        "action": "email_urgent",
        "subject": "URGENT: Payment Still Required — Action Needed",
        "body_template": (
            "Hi {first_name},\n\n"
            "This is a reminder that your {plan_name} subscription "
            "({product_name}) payment has still not been processed.\n\n"
            "Your access will be suspended in 2 days if payment is not updated.\n\n"
            "Update your payment method now:\n\n"
            "{portal_link}\n\n"
            "We don't want to lose you — please take a moment to resolve this."
        ),
    },
    {
        "step": 3,
        "days": 7,
        "action": "restrict_access",
        # No email for restrict — the system handles it silently
    },
    {
        "step": 4,
        "days": 14,
        "action": "cancel_subscription",
        "subject": "Subscription Cancelled: Payment Not Received",
        "body_template": (
            "Hi {first_name},\n\n"
            "We were unable to process your payment for {plan_name} "
            "({product_name}) after multiple attempts over 14 days.\n\n"
            "Your subscription has been cancelled. If you'd like to "
            "resubscribe, you can do so from your billing page:\n\n"
            "{portal_link}\n\n"
            "We're sorry to see you go. If you have any questions, "
            "our support team is here to help."
        ),
    },
]

# Minimum interval (in hours) between dunning emails to prevent spam
DUNNING_EMAIL_MIN_INTERVAL_HOURS = 24


def _send_dunning_email(sub, step_config):
    """Send a dunning email to the subscriber.

    Returns True if email was sent, False if skipped (too recent).
    """
    from django.utils import timezone
    from django.core.mail import send_mail
    from django.conf import settings

    # Skip if no email body (restrict_access has no email)
    if not step_config.get("body_template"):
        return False

    # Prevent duplicate emails within the minimum interval
    min_interval = timezone.timedelta(hours=DUNNING_EMAIL_MIN_INTERVAL_HOURS)
    if sub.last_dunning_email_at and (
        timezone.now() - sub.last_dunning_email_at
    ) < min_interval:
        logger.info(
            f"DUNNING: Skipped email for sub={sub.id} — "
            f"last email sent {sub.last_dunning_email_at}"
        )
        return False

    portal_link = f"{getattr(settings, 'STRIPE_APP_DOMAIN', '')}/dashboard/billing"
    first_name = sub.user.first_name or sub.user.email

    body = step_config["body_template"].format(
        first_name=first_name,
        plan_name=sub.plan.name,
        product_name=sub.product.name,
        portal_link=portal_link,
    )

    sent = send_mail(
        subject=step_config["subject"],
        message=body,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@sattabase.com"),
        recipient_list=[sub.user.email],
        fail_silently=True,
    )

    if sent:
        sub.last_dunning_email_at = timezone.now()
        sub.save(update_fields=["last_dunning_email_at", "updated_at"])
        logger.info(
            f"DUNNING: Sent {step_config['action']} email to "
            f"{sub.user.email} for sub={sub.id}"
        )
        return True

    logger.error(
        f"DUNNING: Failed to send {step_config['action']} email to "
        f"{sub.user.email} for sub={sub.id}"
    )
    return False


def _execute_dunning_step(sub, step_config):
    """Execute a single dunning step for a subscription.

    Actions:
      - email_reminder: Send friendly payment reminder
      - email_urgent: Send urgent payment notice
      - restrict_access: Downgrade to free features (log warning)
      - cancel_subscription: Cancel the subscription on Stripe
    """
    action = step_config["action"]

    if action in ("email_reminder", "email_urgent"):
        return _send_dunning_email(sub, step_config)

    elif action == "restrict_access":
        logger.warning(
            f"DUNNING: Restricting access for sub={sub.id} "
            f"(user={sub.user.email}, past_due > 7 days). "
            f"Subscription remains active but flagged for review."
        )
        # NOTE: Actual access restriction should be implemented in the
        # auth/me access map check. The subscription stays past_due so
        # is_effectively_active() will return False after period_end.

    elif action == "cancel_subscription":
        logger.warning(
            f"DUNNING: Auto-cancelling sub={sub.id} "
            f"(user={sub.user.email}, past_due > 14 days)."
        )
        try:
            from django.utils import timezone
            from .stripe import cancel_subscription_on_stripe
            from .models import SubscriptionStatus

            if sub.stripe_subscription_id:
                cancel_subscription_on_stripe(sub)
            sub.status = SubscriptionStatus.CANCELED
            sub.canceled_at = timezone.now()
            sub.save(
                update_fields=[
                    "status",
                    "canceled_at",
                    "updated_at",
                ]
            )
            logger.info(f"DUNNING: Cancelled sub={sub.id} via dunning workflow")
        except Exception as e:
            logger.error(
                f"DUNNING: Failed to cancel sub={sub.id}: {e}", exc_info=True
            )
            # MED-04/HIGH-01 Fix: Return failure status so caller does NOT
            # advance dunning_step. Previously, this function always returned
            # None (implicit success), causing the caller to advance to step 4
            # even when the Stripe cancel failed.
            return False

    # MED-04 Fix: Return True to indicate success for all non-cancel actions
    return True


# =============================================================================
# Celery Tasks
# =============================================================================


@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=300,  # 5 min between retries
)
def reconcile_webhooks(self, max_age_hours: int = 24):
    """Periodic task to retry failed webhook events.

    Called every 6 hours by Celery Beat. Finds webhook events that were
    recorded but failed during processing, and retries them.

    Args:
        max_age_hours: Only retry events within this time window.
    """
    from .stripe import reconcile_unprocessed_webhooks

    try:
        result = reconcile_unprocessed_webhooks(max_age_hours=max_age_hours)
        logger.info(f"Webhook reconciliation task completed: {result}")
        return result
    except Exception as exc:
        logger.error(f"Webhook reconciliation task failed: {exc}", exc_info=True)
        raise self.retry(exc=exc)


@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=600,  # 10 min between retries
)
def sync_customer_data(self):
    """Periodic task to sync Stripe customer data to local user profiles.

    Called daily by Celery Beat. Iterates over all subscriptions with
    a Stripe customer ID and pulls the latest data from Stripe to
    keep email, name, and currency in sync. This is critical for
    data integrity when users update their profile via Stripe Customer Portal.

    F8: Ensures Stripe Portal changes propagate to the local database
    even if the customer.updated webhook was missed.
    """
    from django.contrib.auth import get_user_model
    from .models import Subscription
    from .stripe import sync_stripe_customer_data

    User = get_user_model()

    try:
        # Get all unique users with a Stripe customer ID
        subs = (
            Subscription.objects.exclude(stripe_customer_id="")
            .exclude(stripe_customer_id__isnull=True)
            .select_related("user")
            .only("user", "stripe_customer_id")
            .distinct("user_id")
        )

        synced_count = 0
        failed_count = 0
        total = subs.count()

        for sub in subs:
            try:
                result = sync_stripe_customer_data(sub.user)
                if result.get("synced"):
                    synced_count += 1
                else:
                    failed_count += 1
            except Exception as e:
                failed_count += 1
                logger.error(f"Customer sync failed for user {sub.user_id}: {e}")

        logger.info(
            f"Customer sync task completed: "
            f"{synced_count}/{total} synced, {failed_count} failed"
        )
        return {"synced": synced_count, "failed": failed_count, "total": total}

    except Exception as exc:
        logger.error(f"Customer sync task failed: {exc}", exc_info=True)
        raise self.retry(exc=exc)


@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=600,  # 10 min between retries
)
def dunning_retry(self):
    """Periodic task to process past_due subscriptions with staged dunning workflow.

    Called daily by Celery Beat. Finds subscriptions that are past_due
    and processes them through the DUNNING_STEPS workflow:

      Day 3  → email_reminder (friendly)
      Day 5  → email_urgent (stronger language)
      Day 7  → restrict_access (flag for access restriction)
      Day 14 → cancel_subscription (auto-cancel)

    Each subscription tracks its current ``dunning_step`` and
    ``last_dunning_email_at`` to prevent duplicate actions and emails.

    When a payment succeeds (invoice.payment_succeeded), the dunning
    step is reset to 0 automatically.
    """
    from django.utils import timezone
    from .models import Subscription, SubscriptionStatus

    try:
        past_due_subs = (
            Subscription.objects.filter(
                status=SubscriptionStatus.PAST_DUE,
            )
            .select_related("user", "plan", "product")
            .order_by("updated_at")
        )

        now = timezone.now()
        stats = {"processed": 0, "emails_sent": 0, "restricted": 0, "cancelled": 0}

        for sub in past_due_subs:
            # MED-04 Fix: Use past_due_at timestamp instead of updated_at.
            # updated_at advances on every save (including dunning task saves),
            # which artificially keeps days_past_due low and delays step escalation.
            # past_due_at is set once when status first transitions to PAST_DUE.
            past_due_at = sub.past_due_at or sub.updated_at
            days_past_due = (now - past_due_at).days

            for step_config in DUNNING_STEPS:
                step_num = step_config["step"]
                threshold_days = step_config["days"]

                # Only trigger if past threshold AND not already done
                if days_past_due >= threshold_days and sub.dunning_step < step_num:
                    try:
                        step_success = _execute_dunning_step(sub, step_config)
                        # MED-04/HIGH-02 Fix: Only advance dunning_step if the
                        # action succeeded. Previously, step was always advanced
                        # even if email failed to send or cancel failed.
                        if step_success:
                            sub.dunning_step = step_num
                            sub.save(update_fields=["dunning_step", "updated_at"])
                        stats["processed"] += 1

                        action = step_config["action"]
                        if "email" in action:
                            stats["emails_sent"] += 1
                        elif action == "restrict_access":
                            stats["restricted"] += 1
                        elif action == "cancel_subscription":
                            stats["cancelled"] += 1
                    except Exception as e:
                        logger.error(
                            f"DUNNING: Error processing step {step_num} "
                            f"for sub={sub.id}: {e}",
                            exc_info=True,
                        )

        logger.info(
            f"Dunning retry task completed: {stats['processed']} actions, "
            f"{stats['emails_sent']} emails, {stats['restricted']} restricted, "
            f"{stats['cancelled']} cancelled"
        )
        return stats

    except Exception as exc:
        logger.error(f"Dunning retry task failed: {exc}", exc_info=True)
        raise self.retry(exc=exc)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=300,  # 5 min between retries
)
def update_exchange_rates(self):
    """Periodic task to fetch and store exchange rates.

    Called daily by Celery Beat. Fetches rates from the free open.er-api.com
    API with fallback to frankfurter.app. Upserts rates into the ExchangeRate
    table. These rates are used by the currency conversion service to display
    plan prices in the user's preferred currency.
    """
    from .currency_service import update_exchange_rates as _update_rates

    try:
        result = _update_rates()
        logger.info(
            f"Exchange rates updated: {result['updated']} rates "
            f"(base={result['base']}, {result['skipped']} skipped)"
        )
        return result
    except Exception as exc:
        logger.error(f"Exchange rate update task failed: {exc}", exc_info=True)
        raise self.retry(exc=exc)


@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=600,  # 10 min between retries
)
def cleanup_stale_webhook_events(self, retention_days: int = 90):
    """Periodic task to clean up old processed webhook events.

    Called weekly by Celery Beat. Deletes webhook events that have been
    successfully processed and are older than the retention period (default
    90 days). This prevents the WebhookEventLog table from growing
    unboundedly as each event can be several KB of JSON.

    Args:
        retention_days: Only delete events older than this many days.

    Returns:
        {"deleted": int} — number of events deleted.
    """
    from django.utils import timezone
    from .models import WebhookEventLog

    try:
        cutoff = timezone.now() - timezone.timedelta(days=retention_days)
        deleted, _ = WebhookEventLog.objects.filter(
            processed=True,
            created_at__lte=cutoff,
        ).delete()
        logger.info(
            f"Cleaned up {deleted} stale webhook events (retention={retention_days}d)"
        )
        return {"deleted": deleted}
    except Exception as exc:
        logger.error(f"Webhook cleanup task failed: {exc}", exc_info=True)
        raise self.retry(exc=exc)


@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=600,  # 10 min between retries
)
def recognize_revenue(self, target_date: str = None):
    """Periodic task to recognize daily revenue for active subscriptions.

    Called daily by Celery Beat. For each active subscription with a paid
    plan, this task creates (or updates) a RevenueRecognitionEntry for
    the target date. The daily amount is calculated as:

        amount_cents = plan.price_cents / days_in_billing_period

    The UniqueConstraint on (subscription, recognized_date) prevents
    duplicate entries if the task runs more than once for the same date.

    Args:
        target_date: ISO date string (YYYY-MM-DD). Defaults to yesterday
            so that the task always processes the most recent complete day.

    Returns:
        {"created": int, "skipped": int, "errors": int}
    """
    from django.utils import timezone
    from .models import (
        Subscription,
        SubscriptionStatus,
        RevenueRecognitionEntry,
        BillingCycle,
    )

    try:
        if target_date:
            recognized = timezone.datetime.strptime(target_date, "%Y-%m-%d").date()
        else:
            # Default to yesterday — the most recent complete day
            recognized = (timezone.now() - timezone.timedelta(days=1)).date()

        # MED-05 Fix: Exclude PAST_DUE from revenue recognition.
        # ASC 606 revenue recognition principles require that revenue
        # should only be recognized when it is probable that payment will
        # be collected. Including PAST_DUE subscriptions overstates revenue.
        # Revenue for these subscriptions is recognized retroactively when
        # payment succeeds via the invoice.payment_succeeded webhook handler.
        subs = Subscription.objects.filter(
            status__in=[
                SubscriptionStatus.ACTIVE,
                SubscriptionStatus.TRIALING,
                SubscriptionStatus.CANCELED,
            ],
            plan__price_cents__gt=0,  # Skip free plans
            current_period_start__lte=timezone.datetime.combine(
                recognized, timezone.datetime.max.time()
            ),
            current_period_end__gte=timezone.datetime.combine(
                recognized, timezone.datetime.min.time()
            ),
        ).select_related("plan")

        stats = {"created": 0, "skipped": 0, "errors": 0}
        batch = []

        for sub in subs:
            try:
                plan = sub.plan
                period_start = sub.current_period_start
                period_end = sub.current_period_end

                if not period_start or not period_end:
                    stats["skipped"] += 1
                    continue

                # Skip lifetime plans — recognize all revenue on payment day
                if plan.billing_cycle == BillingCycle.LIFETIME:
                    stats["skipped"] += 1
                    continue

                # Calculate total days in the billing period
                total_days = (period_end.date() - period_start.date()).days
                if total_days <= 0:
                    stats["skipped"] += 1
                    continue

                # Daily revenue = total plan price / days in period
                # Use integer division with rounding to avoid cent drift
                import math
                daily_cents = math.ceil(plan.price_cents / total_days)

                # For the last day of the period, adjust to capture any
                # remaining cents lost to ceiling rounding on prior days
                is_last_day = (period_end.date() - recognized).days == 0
                if is_last_day:
                    # CRIT-02 Fix: Guard against negative daily_cents.
                    # Edge case: if price_cents < total_days (e.g. a $0.01
                    # plan with a 30-day period), ceiling rounding on prior
                    # days may accumulate more than price_cents total.
                    # max(0, ...) ensures we never recognize negative revenue.
                    daily_cents = max(0, plan.price_cents - (daily_cents * (total_days - 1)))

                currency = sub.currency or plan.currency

                batch.append(RevenueRecognitionEntry(
                    subscription=sub,
                    plan=plan,
                    amount_cents=daily_cents,
                    currency=currency,
                    period_start=period_start,
                    period_end=period_end,
                    recognized_date=recognized,
                    stripe_invoice_id="",
                    source="scheduled",
                ))

            except Exception as e:
                stats["errors"] += 1
                logger.error(
                    f"REVENUE: Error calculating for sub={sub.id}: {e}",
                    exc_info=True,
                )

        # Bulk create with conflict handling (ignore duplicates)
        if batch:
            created = RevenueRecognitionEntry.objects.bulk_create(
                batch,
                ignore_conflicts=True,
            )
            stats["created"] = len(created)
            stats["skipped"] += len(batch) - len(created)

        logger.info(
            f"Revenue recognition for {recognized}: "
            f"{stats['created']} entries, {stats['skipped']} skipped, "
            f"{stats['errors']} errors"
        )
        return stats

    except Exception as exc:
        logger.error(f"Revenue recognition task failed: {exc}", exc_info=True)
        raise self.retry(exc=exc)
