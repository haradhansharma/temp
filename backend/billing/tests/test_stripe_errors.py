"""Tests for Stripe error translation (CC-02)."""

from unittest.mock import patch, MagicMock
import pytest
from stripe.error import CardError, InvalidRequestError, AuthenticationError, RateLimitError

from billing.stripe_errors import handle_stripe_error
from common.exceptions import BadRequestException


class TestHandleStripeError:
    """Tests for the handle_stripe_error function (CC-01)."""

    def test_card_declined_returns_exception(self):
        """Card decline errors should return a user-friendly exception."""
        err = CardError("Your card was declined.", param="number", code="card_declined")
        exc = handle_stripe_error(err)
        assert isinstance(exc, BadRequestException)
        assert "declined" in str(exc).lower()

    def test_expired_card_returns_exception(self):
        err = CardError("Your card has expired.", param="exp_month", code="expired_card")
        exc = handle_stripe_error(err)
        assert isinstance(exc, BadRequestException)
        assert "expired" in str(exc).lower()

    def test_insufficient_funds(self):
        err = CardError("Your card has insufficient funds.", param="amount", code="insufficient_funds")
        exc = handle_stripe_error(err)
        assert isinstance(exc, BadRequestException)
        assert "insufficient" in str(exc).lower()

    def test_currency_mismatch(self):
        err = InvalidRequestError("Cannot combine currencies", param="currency")
        exc = handle_stripe_error(err)
        assert isinstance(exc, BadRequestException)
        assert "currency" in str(exc).lower()

    def test_subscription_already_canceled(self):
        err = InvalidRequestError("Subscription is already canceled.", param="sub")
        exc = handle_stripe_error(err)
        assert isinstance(exc, BadRequestException)
        assert "already canceled" in str(exc).lower()

    def test_server_error_transient(self):
        err = CardError("Internal server error", http_status=502)
        err.http_status = 502
        exc = handle_stripe_error(err)
        assert isinstance(exc, BadRequestException)
        assert "temporarily unavailable" in str(exc).lower()

    def test_unknown_error_fallback(self):
        err = CardError("Some unknown stripe error", http_status=400)
        err.http_status = 400
        exc = handle_stripe_error(err)
        assert isinstance(exc, BadRequestException)

    def test_rate_limit(self):
        err = RateLimitError("Rate limit exceeded")
        exc = handle_stripe_error(err)
        assert isinstance(exc, BadRequestException)
        assert "too many requests" in str(exc).lower()

    def test_context_in_logs(self):
        """The context parameter should be included in log output."""
        err = CardError("Card declined", code="card_declined")
        with patch("billing.stripe_errors.logger") as mock_logger:
            handle_stripe_error(err, context="test_context")
            mock_logger.error.assert_called_once()
            log_msg = mock_logger.error.call_args[0][0]
            assert "test_context" in log_msg
