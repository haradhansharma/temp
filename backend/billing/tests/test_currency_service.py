"""Tests for currency conversion service (CC-02)."""

from unittest.mock import patch, MagicMock
from decimal import Decimal
import pytest

from billing.currency_service import (
    get_exchange_rate,
    convert_price,
    convert_plan_prices,
    fetch_exchange_rates,
)


class MockExchangeRate:
    """In-memory mock for ExchangeRate model."""
    objects = None

    @staticmethod
    def get_or_create(defaults=None, **kwargs):
        return MagicMock()


class TestGetExchangeRate:
    """Tests for get_exchange_rate."""

    def test_same_currency_returns_1(self):
        result = get_exchange_rate("USD", "USD")
        assert result == Decimal("1.0")

    def test_same_currency_case_insensitive(self):
        result = get_exchange_rate("usd", "USD")
        assert result == Decimal("1.0")


class TestConvertPrice:
    """Tests for convert_price."""

    def test_basic_conversion(self):
        with patch("billing.currency_service.get_exchange_rate", return_value=Decimal("109.85")):
            cents, rate = convert_price(900, "USD", "BDT")
            assert cents == 9887  # 9.00 * 109.85
            assert rate == Decimal("109.85")

    def test_no_rate_returns_none(self):
        with patch("billing.currency_service.get_exchange_rate", return_value=None):
            cents, rate = convert_price(900, "USD", "EUR")
            assert cents is None
            assert rate is None

    def test_zero_amount(self):
        with patch("billing.currency_service.get_exchange_rate", return_value=Decimal("1.0")):
            cents, rate = convert_price(0, "USD", "EUR")
            assert cents == 0


class TestFetchExchangeRates:
    """Tests for fetch_exchange_rates with fallback (CC-03)."""

    @patch("billing.currency_service._fetch_from_fallback_api")
    @patch("billing.currency_service._alert_stale_rates")
    @patch("billing.currency_service._fetch_from_primary_api", side_effect=Exception("API down"))
    def test_fallback_on_primary_failure(self, mock_alert, mock_fallback, mock_primary):
        """If primary API fails, fallback should be tried."""
        mock_fallback.return_value = {
            "result": "success",
            "base": "USD",
            "rates": {"BDT": "109.85"},
        }
        with patch("billing.currency_service.settings.BASE_CURRENCY", "USD"):
            result = fetch_exchange_rates()
        assert result["base"] == "USD"
        assert result["rates"]["BDT"] == "109.85"
        mock_fallback.assert_called_once()

    @patch("billing.currency_service._alert_stale_rates")
    @patch("billing.currency_service._fetch_from_fallback_api", side_effect=Exception("Fallback down"))
    @patch("billing.currency_service._fetch_from_primary_api", side_effect=Exception("Primary down"))
    def test_both_failures_alerts_admin(self, mock_alert, mock_fallback, mock_primary):
        """If both APIs fail, admin should be alerted."""
        with patch("billing.currency_service.settings.BASE_CURRENCY", "USD"):
            with pytest.raises(ValueError, match="All exchange rate APIs failed"):
                fetch_exchange_rates()
        mock_alert.assert_called_once()
