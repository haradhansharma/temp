"""Centralized Stripe error translation for user-friendly messages.

Stripe API errors are cryptic and contain internal request IDs, resource
identifiers, and technical jargon that should never be shown to end users.

This module provides a single function ``handle_stripe_error()`` that:

1. Inspects the Stripe exception (error code, HTTP status, message)
2. Matches it against known error patterns
3. Returns a clear, actionable message for the user
4. Logs the full original error for debugging

Usage in controllers::

    from .stripe_errors import handle_stripe_error

    try:
        await sync_to_async(cancel_subscription_on_stripe)(subscription)
    except stripe.error.StripeError as e:
        raise BadRequestException(handle_stripe_error(e))

This replaces scattered try/except blocks that give generic messages.
"""

import logging
import re
from typing import Optional

from common.exceptions import BadRequestException

import stripe

logger = logging.getLogger(__name__)


# =============================================================================
# Error Message Map
# =============================================================================

# Each entry: (match_key, user_message)
# match_key is checked against the LOWER-CASED Stripe error message.
# First match wins — order matters (more specific patterns first).
_ERROR_PATTERNS: list[tuple[str, str]] = [
    # ── Currency errors ─────────────────────────────────────────────────
    (
        "cannot combine currencies",
        "Your billing account already uses a different currency. "
        "Stripe does not allow mixing currencies under one account. "
        "Please change your currency preference to match your existing "
        "subscription, or cancel it first before subscribing in a new currency.",
    ),
    # ── Subscription state errors ───────────────────────────────────────
    (
        "subscription is already canceled",
        "This subscription is already canceled. No action is needed.",
    ),
    (
        "subscription has been canceled",
        "This subscription has already been canceled.",
    ),
    (
        "subscription is already active",
        "This subscription is already active.",
    ),
    (
        "subscription is in a canceled state",
        "This subscription is canceled and cannot be modified. "
        "Please reactivate it first.",
    ),
    (
        "no such subscription",
        "Subscription not found on the payment provider. "
        "It may have been deleted. Please contact support.",
    ),
    (
        "this subscription has no active subscription schedule",
        "This subscription does not have an active schedule to modify.",
    ),
    # ── Customer errors ─────────────────────────────────────────────────
    (
        "no such customer",
        "Your billing account was not found on the payment provider. "
        "Please complete a checkout first, or contact support.",
    ),
    (
        "customer was deleted",
        "Your billing account has been removed. "
        "Please contact support to set up billing again.",
    ),
    # ── Payment method errors ───────────────────────────────────────────
    (
        "card_declined",
        "Your card was declined. Please try a different payment method.",
    ),
    (
        "your card was declined",
        "Your card was declined. Please try a different payment method.",
    ),
    (
        "your card does not support this type of purchase",
        "Your card does not support this type of purchase. "
        "Please try a different card or contact your bank.",
    ),
    (
        "insufficient funds",
        "Insufficient funds on your payment method. "
        "Please use a different card or add funds.",
    ),
    (
        "expired_card",
        "Your card has expired. Please update your payment method.",
    ),
    (
        "incorrect_cvc",
        "The CVC code is incorrect. Please try again.",
    ),
    (
        "incorrect_number",
        "The card number is incorrect. Please check and try again.",
    ),
    (
        "incorrect_zip",
        "The ZIP/postal code does not match your card. Please verify.",
    ),
    (
        "payment_intent_authentication_failure",
        "Payment authentication failed. Please try again or use a different card.",
    ),
    (
        "payment_method_unactivated",
        "Your payment method is not yet activated. "
        "Please try a different payment method.",
    ),
    (
        "payment_method_unexpected_state",
        "Something went wrong with your payment method. "
        "Please try again or use a different one.",
    ),
    # ── Price / Product errors ──────────────────────────────────────────
    (
        "no such price",
        "The selected plan is no longer available. "
        "Please choose a different plan or contact support.",
    ),
    (
        "price is inactive",
        "The selected plan is no longer available for purchase. "
        "Please choose a different plan.",
    ),
    (
        "no such product",
        "This product is no longer available on the payment provider. "
        "Please contact support.",
    ),
    # ── Coupon / Promotion code errors ──────────────────────────────────
    (
        "coupon expired",
        "This promo code has expired.",
    ),
    (
        "coupon not found",
        "This promo code is not valid.",
    ),
    (
        "customer has already applied this coupon",
        "You have already used this promo code.",
    ),
    (
        "promotion code is not valid",
        "This promo code is not valid. Please check and try again.",
    ),
    # ── Refund errors ───────────────────────────────────────────────────
    (
        "charge has already been refunded",
        "This payment has already been refunded.",
    ),
    (
        "refund amount exceeds charge amount",
        "Refund amount exceeds the original payment. " "Please enter a smaller amount.",
    ),
    (
        "charge is already refunded",
        "This charge has already been fully refunded.",
    ),
    (
        "cannot refund a charge that has no successful payment",
        "No successful payment found to refund for this charge.",
    ),
    # ── Rate limiting ───────────────────────────────────────────────────
    (
        "rate_limit",
        "Too many requests to the payment provider. "
        "Please wait a moment and try again.",
    ),
    # ── Portal / Checkout session errors ────────────────────────────────
    (
        "customer does not have any active subscriptions",
        "No active subscription found for billing management. "
        "Complete a checkout first.",
    ),
    # ── Configuration errors (shouldn't happen in production) ───────────
    (
        "invalid_api_key",
        "Payment system is temporarily misconfigured. " "Please contact support.",
    ),
]


# =============================================================================
# Error code to message fallback (for Stripe error codes without message match)
# =============================================================================

_ERROR_CODE_MAP: dict[str, str] = {
    "card_declined": "Your card was declined. Please try a different payment method.",
    "expired_card": "Your card has expired. Please update your payment method.",
    "incorrect_cvc": "The CVC code is incorrect. Please try again.",
    "incorrect_number": "The card number is incorrect. Please check and try again.",
    "incorrect_zip": "The ZIP/postal code does not match your card. Please verify.",
    "insufficient_funds": "Insufficient funds. Please use a different payment method.",
    "invalid_expiry_year": "The card's expiry year is invalid. Please check and try again.",
    "invalid_expiry_month": "The card's expiry month is invalid. Please check and try again.",
    "processing_error": "An error occurred while processing your card. Please try again.",
    "authentication_required": "Additional authentication is required for this payment. "
    "Please complete verification with your bank.",
    "setup_intent_authentication_failure": "Payment verification failed. "
    "Please try again or contact your bank.",
}


# =============================================================================
# Public API
# =============================================================================


def handle_stripe_error(
    error: stripe.error.StripeError,
    context: Optional[str] = None,
) -> BadRequestException:
    """Translate a Stripe API error into a user-friendly BadRequestException.

    CC-01: Returns a BadRequestException directly so controllers can
    simply ``raise handle_stripe_error(e)`` instead of wrapping it.

    Args:
        error: The caught Stripe exception.
        context: Optional human-readable context for logging
                 (e.g. ``"cancel_subscription"``).

    Returns:
        A BadRequestException with a clear, actionable message.

    Side effects:
        Logs the full original error at ERROR level for debugging.
    """
    error_msg = str(error).lower()
    error_code = getattr(error, "code", None) or ""
    http_status = getattr(error, "http_status", None) or 0
    stripe_request_id = getattr(error, "request_id", "") or ""

    # Build a context string for logging
    log_ctx = f"[{context}] " if context else ""
    logger.error(
        f"{log_ctx}Stripe error (status={http_status}, "
        f"code={error_code}, request_id={stripe_request_id}): {error}",
        exc_info=False,
    )

    def _make_exception(msg: str) -> BadRequestException:
        """Helper to create the exception with consistent detail."
        """
        exc = BadRequestException(msg)
        return exc

    # 1. Try matching against known message patterns
    for pattern, user_message in _ERROR_PATTERNS:
        if pattern in error_msg:
            return _make_exception(user_message)

    # 2. Try matching against known error codes
    if error_code in _ERROR_CODE_MAP:
        return _make_exception(_ERROR_CODE_MAP[error_code])

    # 3. Handle by HTTP status class
    if http_status >= 500:
        # Stripe server error — transient
        return _make_exception(
            "The payment provider is temporarily unavailable. "
            "Please try again in a few moments."
        )

    if http_status == 429:
        return _make_exception("Too many requests. Please wait a moment and try again.")

    if http_status == 401:
        # Auth error — configuration issue, not user's fault.
        # CRITICAL: Active alert because ALL payment processing is broken.
        logger.critical(
            f"{log_ctx}Stripe API key is invalid or missing! "
            f"Check SF_STRIPE_SECRET_KEY in settings."
        )
        # Send immediate admin alert — payment system is down
        try:
            from django.core.mail import mail_admins

            mail_admins(
                "CRITICAL: Stripe API Key Invalid",
                f"The Stripe API key is invalid or missing. "
                f"All payment processing is currently broken. "
                f"Context: {context or 'unknown'}",
                fail_silently=True,
            )
        except Exception:
            logger.exception("Failed to send admin alert for invalid Stripe key")
        return _make_exception("Payment system is temporarily unavailable. Please contact support.")

    if http_status == 404:
        return _make_exception(
            "The requested resource was not found on the payment provider. "
            "Please contact support."
        )

    if http_status in (400, 402):
        # Generic client error — likely a parameter issue
        return _make_exception(
            "Payment processing failed. Please verify your details "
            "and try again, or contact support for assistance."
        )

    # 4. Final fallback — generic but not alarming
    return _make_exception(
        "Something went wrong with the payment provider. "
        "Please try again or contact support if the issue persists."
    )
