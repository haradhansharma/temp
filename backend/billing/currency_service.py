"""Currency conversion service for the billing app.

Handles conversion between plan base currency and user's preferred
currency using exchange rates stored in the ExchangeRate model.

Also serves as the **single source of truth** for currency metadata
(symbol, name, decimal digits). Sister domains consume this data
via the ``/billing/currencies`` endpoint or the ``currencies`` field
on ``/billing/auth/me`` — they should NOT hardcode their own symbol
maps.

Flow:
  1. Plans are priced in BASE_CURRENCY (default USD).
  2. Exchange rates are fetched daily from a free API by Celery.
  3. When the frontend requests plans with ?currency=BDT, this service
     converts price_cents from the plan's currency to BDT.
  4. The frontend displays the converted price alongside the base price.
"""

import logging
import urllib.request
import json
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Dict, Any

from django.conf import settings

logger = logging.getLogger(__name__)


# =============================================================================
# Currency Metadata — Single Source of Truth
# =============================================================================
# Every currency supported by the system is defined here.
# Sister domains fetch this via /billing/currencies or the currencies
# field on auth/me — they must NOT duplicate this data.
#
# Fields per currency:
#   symbol        — display symbol (e.g. "$", "৳", "€")
#   name          — human-readable name (e.g. "US Dollar", "Bangladeshi Taka")
#   decimal_digits — number of decimal places for amounts (0 for JPY/KRW/VND)
# =============================================================================

CURRENCY_META: dict[str, dict[str, str | int]] = {
    "USD": {"symbol": "$", "name": "US Dollar", "decimal_digits": 2},
    "EUR": {"symbol": "€", "name": "Euro", "decimal_digits": 2},
    "GBP": {"symbol": "£", "name": "British Pound", "decimal_digits": 2},
    "JPY": {"symbol": "¥", "name": "Japanese Yen", "decimal_digits": 0},
    "CNY": {"symbol": "¥", "name": "Chinese Yuan", "decimal_digits": 2},
    "INR": {"symbol": "₹", "name": "Indian Rupee", "decimal_digits": 2},
    "BDT": {"symbol": "৳", "name": "Bangladeshi Taka", "decimal_digits": 2},
    "PKR": {"symbol": "₨", "name": "Pakistani Rupee", "decimal_digits": 2},
    "AUD": {"symbol": "A$", "name": "Australian Dollar", "decimal_digits": 2},
    "CAD": {"symbol": "C$", "name": "Canadian Dollar", "decimal_digits": 2},
    "CHF": {"symbol": "CHF", "name": "Swiss Franc", "decimal_digits": 2},
    "HKD": {"symbol": "HK$", "name": "Hong Kong Dollar", "decimal_digits": 2},
    "NZD": {"symbol": "NZ$", "name": "New Zealand Dollar", "decimal_digits": 2},
    "SGD": {"symbol": "S$", "name": "Singapore Dollar", "decimal_digits": 2},
    "KRW": {"symbol": "₩", "name": "South Korean Won", "decimal_digits": 0},
    "SEK": {"symbol": "kr", "name": "Swedish Krona", "decimal_digits": 2},
    "NOK": {"symbol": "kr", "name": "Norwegian Krone", "decimal_digits": 2},
    "DKK": {"symbol": "kr", "name": "Danish Krone", "decimal_digits": 2},
    "MXN": {"symbol": "MX$", "name": "Mexican Peso", "decimal_digits": 2},
    "BRL": {"symbol": "R$", "name": "Brazilian Real", "decimal_digits": 2},
    "ZAR": {"symbol": "R", "name": "South African Rand", "decimal_digits": 2},
    "RUB": {"symbol": "₽", "name": "Russian Ruble", "decimal_digits": 2},
    "TRY": {"symbol": "₺", "name": "Turkish Lira", "decimal_digits": 2},
    "AED": {"symbol": "د.إ", "name": "UAE Dirham", "decimal_digits": 2},
    "SAR": {"symbol": "﷼", "name": "Saudi Riyal", "decimal_digits": 2},
    "THB": {"symbol": "฿", "name": "Thai Baht", "decimal_digits": 2},
    "MYR": {"symbol": "RM", "name": "Malaysian Ringgit", "decimal_digits": 2},
    "IDR": {"symbol": "Rp", "name": "Indonesian Rupiah", "decimal_digits": 2},
    "VND": {"symbol": "₫", "name": "Vietnamese Dong", "decimal_digits": 0},
    "PHP": {"symbol": "₱", "name": "Philippine Peso", "decimal_digits": 2},
    "TWD": {"symbol": "NT$", "name": "Taiwan Dollar", "decimal_digits": 2},
    "PLN": {"symbol": "zł", "name": "Polish Zloty", "decimal_digits": 2},
    "NGN": {"symbol": "₦", "name": "Nigerian Naira", "decimal_digits": 2},
    "EGP": {"symbol": "E£", "name": "Egyptian Pound", "decimal_digits": 2},
    "KES": {"symbol": "KSh", "name": "Kenyan Shilling", "decimal_digits": 2},
    "COP": {"symbol": "COL$", "name": "Colombian Peso", "decimal_digits": 2},
    "CLP": {"symbol": "CLP$", "name": "Chilean Peso", "decimal_digits": 0},
    "PEN": {"symbol": "S/.", "name": "Peruvian Sol", "decimal_digits": 2},
    "ARS": {"symbol": "AR$", "name": "Argentine Peso", "decimal_digits": 2},
    "ILS": {"symbol": "₪", "name": "Israeli Shekel", "decimal_digits": 2},
}


def get_currency_symbol(currency_code: str) -> str:
    """Get the display symbol for a currency code.

    Falls back to the currency code itself if no meta is known.
    This is the canonical helper — use it everywhere instead of
    maintaining local symbol maps.
    """
    meta = CURRENCY_META.get(currency_code.upper())
    if meta:
        return str(meta["symbol"])
    return currency_code.upper()


def get_currency_name(currency_code: str) -> str:
    """Get the human-readable name for a currency code.

    Falls back to the currency code if no meta is known.
    """
    meta = CURRENCY_META.get(currency_code.upper())
    if meta:
        return str(meta["name"])
    return currency_code.upper()


def get_currency_decimal_digits(currency_code: str) -> int:
    """Get the number of decimal places for a currency.

    Returns 2 as a safe default for unknown currencies.
    """
    meta = CURRENCY_META.get(currency_code.upper())
    if meta:
        return int(meta["decimal_digits"])
    return 2


def get_all_currencies_meta() -> dict[str, dict[str, str | int]]:
    """Return the full CURRENCY_META dict.

    Used by the /billing/currencies endpoint and auth/me piggyback
    so sister domains can consume it without hardcoding.
    """
    return CURRENCY_META


# =============================================================================
# Conversion Helpers
# =============================================================================


def get_exchange_rate(
    from_currency: str,
    to_currency: str,
) -> Optional[Decimal]:
    """Look up the exchange rate for a currency pair.

    Handles three cases:
      1. Same currency → returns 1.0 immediately.
      2. Direct pair (e.g. USD→BDT) → looks up in ExchangeRate table.
      3. Cross pair via base (e.g. EUR→BDT via USD) → composes two rates.

    Returns None if no rate is available (e.g. on fresh install before
    the first Celery fetch completes).
    """
    from .models import ExchangeRate

    from_code = from_currency.upper()
    to_code = to_currency.upper()

    # Same currency — no conversion needed
    if from_code == to_code:
        return Decimal("1.0")

    base = getattr(settings, "BASE_CURRENCY", "USD").upper()

    # Direct pair stored in DB (base → target)
    try:
        direct = ExchangeRate.objects.get(
            base_currency=from_code,
            target_currency=to_code,
        )
        return direct.rate
    except ExchangeRate.DoesNotExist:
        pass

    # Reverse pair stored in DB (target → base) — invert the rate
    try:
        reverse = ExchangeRate.objects.get(
            base_currency=to_code,
            target_currency=from_code,
        )
        return Decimal("1") / reverse.rate if reverse.rate > 0 else None
    except ExchangeRate.DoesNotExist:
        pass

    # Cross pair: from → base → to
    if from_code != base and to_code != base:
        rate_from = get_exchange_rate(from_code, base)
        rate_to = get_exchange_rate(base, to_code)
        if rate_from is not None and rate_to is not None:
            return rate_from * rate_to

    return None


def convert_price(
    amount_cents: int,
    from_currency: str,
    to_currency: str,
) -> tuple[Optional[int], Optional[Decimal]]:
    """Convert a price in cents from one currency to another.

    Returns:
        (converted_amount_cents, exchange_rate_used)

    If no rate is available, returns (None, None) so the caller knows
    conversion failed and can fall back to the original price/currency.
    """
    rate = get_exchange_rate(from_currency, to_currency)
    if rate is None:
        return None, None

    # Convert cents → decimal → apply rate → round to cents
    original = Decimal(amount_cents) / Decimal(100)
    converted = (original * rate).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )
    converted_cents = int(converted * 100)
    return converted_cents, rate


def convert_plan_prices(
    plans: list,
    target_currency: str,
) -> list[dict]:
    """Batch-convert prices for a list of plan objects.

    Takes a list of Plan model instances (or dicts with plan fields)
    and adds converted price fields for the target currency.

    Returns a list of dicts with the following extra keys:
      - converted_price_cents: int or None
      - user_currency: str (the requested target currency)
      - exchange_rate: str or None (the rate used, e.g. "109.850000")

    If no rate is available for a plan's currency → target, the converted
    fields are None and the frontend should fall back to the base price.
    """
    base = getattr(settings, "BASE_CURRENCY", "USD").upper()
    target = target_currency.upper() if target_currency else base

    if target == base:
        # Same as base — no conversion needed
        return [
            {
                **_plan_to_dict(plan),
                "converted_price_cents": _get_price_cents(plan),
                "user_currency": target,
                "exchange_rate": "1.0",
            }
            for plan in plans
        ]

    result = []
    for plan in plans:
        plan_dict = _plan_to_dict(plan)
        price_cents = _get_price_cents(plan)
        plan_currency = _get_plan_currency(plan).upper()

        converted_cents, rate = convert_price(price_cents, plan_currency, target)

        plan_dict["converted_price_cents"] = converted_cents  # None when no rate
        # Only set user_currency when conversion actually succeeded —
        # frontend uses `user_currency ?? plan.currency` to pick the right
        # symbol.  If we blindly set user_currency=target even when the
        # conversion failed, the frontend formats the ORIGINAL price_cents
        # (which are in plan.currency) with the TARGET symbol, e.g. ৳9.00
        # for a $9 plan.
        plan_dict["user_currency"] = target if converted_cents is not None else None
        plan_dict["exchange_rate"] = str(rate) if rate is not None else None

        result.append(plan_dict)

    return result


# =============================================================================
# Rate Fetching (called by Celery)
# =============================================================================


def fetch_exchange_rates() -> Dict[str, Any]:
    """Fetch latest exchange rates from the configured API.

    Uses the free open.er-api.com endpoint (no API key required).
    Falls back to frankfurter.app if the primary API fails.
    Returns the full JSON response dict on success, or raises an
    exception on failure.

    The API returns rates relative to the base currency specified in
    the URL path, e.g. /v6/latest/USD returns all rates relative to USD.
    """
    base = getattr(settings, "BASE_CURRENCY", "USD").upper()

    # CC-03: Try primary API first, then fallback
    primary_err = None
    try:
        data = _fetch_from_primary_api(base)
        return data
    except Exception as _primary_err:
        primary_err = _primary_err
        logger.warning(f"Primary exchange rate API failed: {primary_err}")

    # Fallback to frankfurter.app
    try:
        data = _fetch_from_fallback_api(base)
        logger.info("Successfully fetched rates from fallback API (frankfurter.app)")
        return data
    except Exception as fallback_err:
        logger.error(f"Fallback exchange rate API also failed: {fallback_err}")
        # CC-03: Alert admins that rates are stale
        _alert_stale_rates(str(primary_err))
        raise ValueError(
            f"All exchange rate APIs failed. Primary: {primary_err}, "
            f"Fallback: {fallback_err}"
        )


def _fetch_from_primary_api(base: str) -> Dict[str, Any]:
    """Fetch rates from the primary open.er-api.com endpoint."""
    api_url = getattr(
        settings, "EXCHANGE_RATE_API_URL", "https://open.er-api.com/v6/latest"
    )
    url = f"{api_url}/{base}"

    req = urllib.request.Request(url)
    req.add_header("Accept", "application/json")
    req.add_header("User-Agent", "Sattabase/1.0")

    logger.info(f"Fetching exchange rates from primary API: {url}")

    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    if data.get("result") != "success":
        raise ValueError(
            f"Exchange rate API returned error: {data.get('error-type', 'unknown')}"
        )

    return data


def _fetch_from_fallback_api(base: str) -> Dict[str, Any]:
    """Fetch rates from fallback frankfurter.app endpoint (CC-03)."""
    url = f"https://api.frankfurter.app/latest?from={base}"

    req = urllib.request.Request(url)
    req.add_header("Accept", "application/json")
    req.add_header("User-Agent", "Sattabase/1.0")

    logger.info(f"Fetching exchange rates from fallback API: {url}")

    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    # Normalize frankfurter response to match primary API format
    return {
        "result": "success",
        "base": data.get("base", base),
        "rates": data.get("rates", {}),
    }


def _alert_stale_rates(error_detail: str):
    """Send admin alert when exchange rates cannot be updated (CC-03)."""
    try:
        from django.core.mail import mail_admins

        mail_admins(
            "Exchange Rate Update Failed — Rates May Be Stale",
            f"The exchange rate update task failed to fetch rates from both "
            f"the primary and fallback APIs. Currency conversions may show "
            f"outdated rates.\n\n"
            f"Error: {error_detail}\n\n"
            f"Please check the API endpoints manually and update rates "
            f"if needed.",
            fail_silently=True,
        )
    except Exception:
        logger.exception("Failed to send stale rates admin alert")


def update_exchange_rates() -> dict:
    """Fetch exchange rates from API and upsert into ExchangeRate table.

    Called by the ``update_exchange_rates`` Celery task (daily).

    Returns:
        {"updated": int, "skipped": int, "base": str}
    """
    from .models import ExchangeRate

    base = getattr(settings, "BASE_CURRENCY", "USD").upper()
    data = fetch_exchange_rates()
    rates = data.get("rates", {})

    if not rates:
        logger.warning("Exchange rate API returned no rates")
        return {"updated": 0, "skipped": 0, "base": base}

    updated = 0
    skipped = 0

    for target_currency, rate_value in rates.items():
        target = target_currency.upper()

        if target == base:
            skipped += 1
            continue

        try:
            rate = Decimal(str(rate_value))
        except (ValueError, TypeError):
            logger.warning(f"Invalid rate for {target}: {rate_value}")
            skipped += 1
            continue

        ExchangeRate.objects.update_or_create(
            base_currency=base,
            target_currency=target,
            defaults={"rate": rate},
        )
        updated += 1

    logger.info(
        f"Exchange rates updated: {updated} updated, {skipped} skipped, base={base}"
    )

    return {"updated": updated, "skipped": skipped, "base": base}


def get_all_rates_for_base(base_currency: str) -> dict[str, str]:
    """Get all exchange rates for a given base currency as a compact dict.

    Returns: {"USD": "1.000000", "EUR": "0.920000", "BDT": "109.850000", ...}

    Used by auth/me to piggyback exchange rates for sister domains.
    Also includes the base currency itself with rate "1.000000".
    """
    from .models import ExchangeRate

    base_code = base_currency.upper()

    rates = {}
    # Add base→base as 1.0
    rates[base_code] = "1.000000"

    # Direct rates: base → all targets
    for row in ExchangeRate.objects.filter(base_currency=base_code).values(
        "target_currency", "rate"
    ):
        rates[row["target_currency"]] = str(row["rate"])

    # If we got some rates, also try reverse for any missing pairs
    # This handles cases like BDT→USD when only USD→BDT is stored
    if not rates or len(rates) <= 1:
        # Try using the system base (usually USD) as pivot
        system_base = getattr(settings, "BASE_CURRENCY", "USD").upper()
        if system_base != base_code:
            for row in ExchangeRate.objects.filter(base_currency=system_base).values(
                "target_currency", "rate"
            ):
                target = row["target_currency"]
                if target == base_code and row["rate"] > 0:
                    # We have USD→BDT, need BDT→USD (invert)
                    # And BDT→EUR = BDT→USD * USD→EUR
                    base_to_system = Decimal("1") / row["rate"]
                    rates[system_base] = str(base_to_system.quantize(Decimal("0.000001")))

                    # Now compute cross rates: base → system → target
                    for cross_row in ExchangeRate.objects.filter(
                        base_currency=system_base
                    ).exclude(target_currency=base_code).values(
                        "target_currency", "rate"
                    ):
                        cross_rate = base_to_system * cross_row["rate"]
                        rates[cross_row["target_currency"]] = str(
                            cross_rate.quantize(Decimal("0.000001"))
                        )
                    break

    return rates


# =============================================================================
# Internal Helpers
# =============================================================================


def _plan_to_dict(plan) -> dict:
    """Convert a Plan model instance to a dict.

    Includes DB columns from ``__dict__`` and computed ``@property``
    fields (``display_price``, ``is_free``) that Pydantic expects
    in ``PlanOutputSchema``.
    """
    if hasattr(plan, "__dict__"):
        d = {k: v for k, v in plan.__dict__.items() if not k.startswith("_")}
        # Include model properties that Pydantic schema requires
        for prop in ("display_price", "is_free"):
            if hasattr(plan, prop):
                d[prop] = getattr(plan, prop)
        return d
    return plan


def _get_price_cents(plan) -> int:
    """Extract price_cents from a Plan model or dict."""
    if isinstance(plan, dict):
        return plan.get("price_cents", 0)
    return getattr(plan, "price_cents", 0)


def _get_plan_currency(plan) -> str:
    """Extract currency from a Plan model or dict."""
    if isinstance(plan, dict):
        return plan.get("currency", getattr(settings, "BASE_CURRENCY", "USD"))
    return getattr(plan, "currency", getattr(settings, "BASE_CURRENCY", "USD"))
