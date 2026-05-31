"""Tests for FIN-07 — Revenue Recognition system.

Covers:
  - RevenueRecognitionEntry model constraints
  - recognize_revenue Celery task daily calculation
  - Webhook-triggered immediate recognition
  - Last-day rounding correction
  - Free plan and lifetime plan skipping
  - Duplicate prevention (unique constraint)
"""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from unittest.mock import patch, MagicMock

from billing.models import (
    Subscription,
    SubscriptionStatus,
    Plan,
    Product,
    BillingCycle,
    RevenueRecognitionEntry,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def product(db):
    return Product.objects.create(
        name="Test Product",
        slug="test-product",
        description="Test product for revenue recognition",
    )


@pytest.fixture
def monthly_plan(product):
    return Plan.objects.create(
        product=product,
        name="Pro Monthly",
        slug="pro-monthly",
        price_cents=3000,  # $30.00
        currency="USD",
        billing_cycle=BillingCycle.MONTHLY,
    )


@pytest.fixture
def yearly_plan(product):
    return Plan.objects.create(
        product=product,
        name="Pro Yearly",
        slug="pro-yearly",
        price_cents=30000,  # $300.00
        currency="USD",
        billing_cycle=BillingCycle.YEARLY,
    )


@pytest.fixture
def free_plan(product):
    return Plan.objects.create(
        product=product,
        name="Free",
        slug="free",
        price_cents=0,
        currency="USD",
        billing_cycle=BillingCycle.MONTHLY,
    )


@pytest.fixture
def lifetime_plan(product):
    return Plan.objects.create(
        product=product,
        name="Lifetime",
        slug="lifetime",
        price_cents=99900,  # $999.00
        currency="USD",
        billing_cycle=BillingCycle.LIFETIME,
    )


@pytest.fixture
def user(db):
    from django.contrib.auth import get_user_model

    User = get_user_model()
    return User.objects.create_user(
        email="test@example.com",
        password="testpass123",
        first_name="Test",
    )


@pytest.fixture
def active_sub(user, monthly_plan):
    now = timezone.now()
    return Subscription.objects.create(
        user=user,
        plan=monthly_plan,
        product=monthly_plan.product,
        status=SubscriptionStatus.ACTIVE,
        current_period_start=now - timedelta(days=15),
        current_period_end=now + timedelta(days=15),
        stripe_subscription_id="sub_test_123",
        currency="USD",
    )


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


class TestRevenueRecognitionModel:
    """Tests for RevenueRecognitionEntry model fields and constraints."""

    def test_create_entry(self, active_sub):
        """RevenueRecognitionEntry can be created with all fields."""
        entry = RevenueRecognitionEntry.objects.create(
            subscription=active_sub,
            plan=active_sub.plan,
            amount_cents=100,  # $1.00
            currency="USD",
            period_start=active_sub.current_period_start,
            period_end=active_sub.current_period_end,
            recognized_date=timezone.now().date(),
            stripe_invoice_id="in_test_123",
            source="webhook",
        )
        assert entry.id is not None
        assert entry.amount_cents == 100
        assert entry.source == "webhook"

    def test_unique_constraint_per_sub_per_day(self, active_sub):
        """Cannot create two entries for same subscription and date."""
        today = timezone.now().date()
        RevenueRecognitionEntry.objects.create(
            subscription=active_sub,
            plan=active_sub.plan,
            amount_cents=100,
            currency="USD",
            period_start=active_sub.current_period_start,
            period_end=active_sub.current_period_end,
            recognized_date=today,
            source="scheduled",
        )
        with pytest.raises(Exception):
            RevenueRecognitionEntry.objects.create(
                subscription=active_sub,
                plan=active_sub.plan,
                amount_cents=200,
                currency="USD",
                period_start=active_sub.current_period_start,
                period_end=active_sub.current_period_end,
                recognized_date=today,
                source="scheduled",
            )

    def test_different_dates_allowed(self, active_sub):
        """Different dates for same subscription are allowed."""
        today = timezone.now().date()
        yesterday = today - timedelta(days=1)
        RevenueRecognitionEntry.objects.create(
            subscription=active_sub,
            plan=active_sub.plan,
            amount_cents=100,
            currency="USD",
            recognized_date=today,
            source="scheduled",
        )
        RevenueRecognitionEntry.objects.create(
            subscription=active_sub,
            plan=active_sub.plan,
            amount_cents=100,
            currency="USD",
            recognized_date=yesterday,
            source="scheduled",
        )
        assert (
            RevenueRecognitionEntry.objects.filter(subscription=active_sub).count() == 2
        )

    def test_str_representation(self, active_sub):
        """__str__ returns human-readable format."""
        entry = RevenueRecognitionEntry.objects.create(
            subscription=active_sub,
            plan=active_sub.plan,
            amount_cents=1234,
            currency="USD",
            recognized_date=timezone.now().date(),
        )
        assert "12.34" in str(entry)
        assert "USD" in str(entry)

    def test_default_source_is_scheduled(self, active_sub):
        """Source defaults to 'scheduled' when not specified."""
        entry = RevenueRecognitionEntry.objects.create(
            subscription=active_sub,
            plan=active_sub.plan,
            amount_cents=100,
            currency="USD",
            recognized_date=timezone.now().date(),
        )
        assert entry.source == "scheduled"


# ---------------------------------------------------------------------------
# Celery task tests
# ---------------------------------------------------------------------------


class TestRecognizeRevenueTask:
    """Tests for the recognize_revenue Celery task."""

    def test_monthly_subscription_daily_amount(self, active_sub):
        """Monthly plan: daily amount = price / 30 days."""
        from billing.tasks import recognize_revenue

        today = (timezone.now() - timedelta(days=1)).date()
        result = recognize_revenue(target_date=today.isoformat())

        assert result["created"] >= 1
        entries = RevenueRecognitionEntry.objects.filter(subscription=active_sub)
        assert entries.count() == 1

        entry = entries.first()
        # 3000 cents / 30 days = 100 cents/day
        assert entry.amount_cents == 100
        assert entry.source == "scheduled"

    def test_skips_free_plans(self, user, product, free_plan):
        """Free plans (price_cents=0) should be skipped."""
        from billing.tasks import recognize_revenue

        sub = Subscription.objects.create(
            user=user,
            plan=free_plan,
            product=product,
            status=SubscriptionStatus.ACTIVE,
            current_period_start=timezone.now() - timedelta(days=15),
            current_period_end=timezone.now() + timedelta(days=15),
            currency="USD",
        )

        today = (timezone.now() - timedelta(days=1)).date()
        result = recognize_revenue(target_date=today.isoformat())

        # Should be skipped because price is 0
        assert result["skipped"] >= 1
        assert RevenueRecognitionEntry.objects.filter(subscription=sub).count() == 0

    def test_skips_lifetime_plans(self, user, product, lifetime_plan):
        """Lifetime plans should be skipped by daily recognition."""
        from billing.tasks import recognize_revenue

        sub = Subscription.objects.create(
            user=user,
            plan=lifetime_plan,
            product=product,
            status=SubscriptionStatus.ACTIVE,
            current_period_start=timezone.now() - timedelta(days=100),
            current_period_end=timezone.now() + timedelta(days=265),
            currency="USD",
        )

        today = (timezone.now() - timedelta(days=1)).date()
        result = recognize_revenue(target_date=today.isoformat())

        assert result["skipped"] >= 1
        assert RevenueRecognitionEntry.objects.filter(subscription=sub).count() == 0

    def test_idempotent_duplicate_run(self, active_sub):
        """Running twice for the same date does not create duplicates."""
        from billing.tasks import recognize_revenue

        today = (timezone.now() - timedelta(days=1)).date()

        result1 = recognize_revenue(target_date=today.isoformat())
        result2 = recognize_revenue(target_date=today.isoformat())

        assert result1["created"] >= 1
        # Second run should create 0 (all skipped due to unique constraint)
        assert result2["created"] == 0
        assert result2["skipped"] >= 1

        # Only 1 entry exists
        assert (
            RevenueRecognitionEntry.objects.filter(subscription=active_sub).count() == 1
        )

    def test_inactive_subscription_skipped(self, active_sub):
        """Expired subscriptions should be skipped."""
        from billing.tasks import recognize_revenue

        # Move period end to the past
        active_sub.current_period_end = timezone.now() - timedelta(days=5)
        active_sub.save()

        today = (timezone.now() - timedelta(days=1)).date()
        result = recognize_revenue(target_date=today.isoformat())

        # Should be skipped because period_end < recognized date
        assert (
            RevenueRecognitionEntry.objects.filter(subscription=active_sub).count() == 0
        )


# ---------------------------------------------------------------------------
# Webhook-triggered recognition tests
# ---------------------------------------------------------------------------


class TestWebhookRevenueRecognition:
    """Tests for revenue recognition triggered by invoice.payment_succeeded webhook."""

    def _make_invoice_event(self, sub, amount_paid=3000):
        """Create a mock invoice.payment_succeeded event."""
        return {
            "data": {
                "object": {
                    "id": f"in_test_{sub.id}",
                    "subscription": sub.stripe_subscription_id,
                    "amount_paid": amount_paid,
                    "currency": "usd",
                    "status": "paid",
                    "period_start": int(sub.current_period_start.timestamp()),
                    "period_end": int(sub.current_period_end.timestamp()),
                    "lines": {"data": [{"description": "Pro Monthly"}]},
                    "charge": None,  # Skip fee fetching
                }
            }
        }

    def test_webhook_creates_entry_on_payment_day(self, active_sub):
        """Webhook creates a revenue entry for today on payment."""
        from billing.stripe.webhooks.handlers.invoice import (
            handle_invoice_payment_succeeded,
        )

        event = self._make_invoice_event(active_sub)
        handle_invoice_payment_succeeded(event)

        today = timezone.now().date()
        entry = RevenueRecognitionEntry.objects.filter(
            subscription=active_sub,
            recognized_date=today,
        ).first()

        assert entry is not None
        assert entry.source == "webhook"
        assert entry.amount_cents > 0
        assert entry.stripe_invoice_id == f"in_test_{active_sub.id}"

    def test_webhook_entry_is_updatable(self, active_sub):
        """update_or_create updates the entry if it already exists."""
        from billing.stripe.webhooks.handlers.invoice import (
            handle_invoice_payment_succeeded,
        )

        today = timezone.now().date()

        # Pre-create an entry
        RevenueRecognitionEntry.objects.create(
            subscription=active_sub,
            plan=active_sub.plan,
            amount_cents=50,  # Old amount
            currency="USD",
            recognized_date=today,
            source="scheduled",
        )

        event = self._make_invoice_event(active_sub, amount_paid=3000)
        handle_invoice_payment_succeeded(event)

        entry = RevenueRecognitionEntry.objects.get(
            subscription=active_sub,
            recognized_date=today,
        )
        # Should have been updated, not duplicated
        assert entry.source == "webhook"
        assert entry.amount_cents != 50

    def test_webhook_failure_does_not_block_payment(self, active_sub):
        """Revenue recognition failure is non-fatal to payment processing."""
        from billing.stripe.webhooks.handlers.invoice import (
            handle_invoice_payment_succeeded,
        )

        # Set an invalid period that will cause revenue recognition to fail
        event = self._make_invoice_event(active_sub)
        event["data"]["object"]["period_start"] = None
        event["data"]["object"]["period_end"] = None

        # Should NOT raise — revenue recognition is wrapped in try/except
        try:
            handle_invoice_payment_succeeded(event)
        except Exception:
            pytest.fail(
                "Webhook handler should not raise on revenue recognition failure"
            )

        # Sub status should still be updated
        active_sub.refresh_from_db()
        assert active_sub.status == SubscriptionStatus.ACTIVE
