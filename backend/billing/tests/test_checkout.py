"""Tests for Stripe checkout flow (CC-02)."""

from unittest.mock import patch, MagicMock


class TestCheckoutDeduplication:
    """Tests for checkout session deduplication (CMP-07)."""

    @patch("billing.stripe.checkout.cache")
    @patch("billing.stripe.checkout._create_checkout")
    def test_returns_cached_url_on_double_click(self, mock_create, mock_cache):
        """If a cached URL exists within 5 min, return it without calling Stripe."""
        mock_cache.get.return_value = "https://checkout.stripe.com/cached-session"
        mock_create.return_value = {
            "id": "cs_new_session",
            "url": "https://checkout.stripe.com/new-session",
        }

        from billing.stripe.checkout import create_checkout

        # Setup mocks
        user = MagicMock(id=42, email="test@example.com")
        plan = MagicMock(
            is_free=False, currency="USD", price_cents=900, slug="pro",
            trial_days=0,
        )
        product = MagicMock(id=1, slug="finance")

        with patch("billing.stripe.checkout.resolve_price_id", return_value="price_123"):
            with patch("billing.stripe.checkout.get_or_create_customer_id", return_value="cus_123"):
                with patch("billing.stripe.checkout.settings") as mock_settings:
                    mock_settings.STRIPE_TAX_ENABLED = True
                    mock_settings.STRIPE_SUCCESS_URL = "http://localhost/success"
                    mock_settings.STRIPE_CANCEL_URL = "http://localhost/cancel"
                    mock_settings.TOS_VERSION = "1.0"

                    result = create_checkout(user, plan, product, "USD")

        assert result == "https://checkout.stripe.com/cached-session"
        mock_create.assert_not_called()

    @patch("billing.stripe.checkout.cache")
    @patch("billing.stripe.checkout._create_checkout")
    def test_creates_and_caches_new_checkout(self, mock_create, mock_cache):
        """First checkout should create session and cache the URL."""
        mock_cache.get.return_value = None
        mock_create.return_value = {
            "id": "cs_new_session",
            "url": "https://checkout.stripe.com/new-session",
        }

        from billing.stripe.checkout import create_checkout

        user = MagicMock(id=42, email="test@example.com")
        plan = MagicMock(
            is_free=False, currency="USD", price_cents=900, slug="pro",
            trial_days=0,
        )
        product = MagicMock(id=1, slug="finance")

        with patch("billing.stripe.checkout.resolve_price_id", return_value="price_123"):
            with patch("billing.stripe.checkout.get_or_create_customer_id", return_value="cus_123"):
                with patch("billing.stripe.checkout.settings") as mock_settings:
                    mock_settings.STRIPE_TAX_ENABLED = True
                    mock_settings.STRIPE_SUCCESS_URL = "http://localhost/success"
                    mock_settings.STRIPE_CANCEL_URL = "http://localhost/cancel"
                    mock_settings.TOS_VERSION = "1.0"

                    result = create_checkout(user, plan, product, "USD")

        assert result == "https://checkout.stripe.com/new-session"
        mock_create.assert_called_once()
        mock_cache.set.assert_called_once_with(
            "checkout_recent_42_1_pro",
            "https://checkout.stripe.com/new-session",
            timeout=300,
        )
