"""Shared utilities for webhook processing.

This module exists to break the circular import between ``router.py`` and
``handlers/*.py``.  Both the router (for event logging) and individual
handlers (for persisting Stripe responses to JSONFields) need the Decimal
sanitization helper.  Placing it here means neither side imports the other.
"""

from decimal import Decimal


def sanitize_for_json(obj):
    """Recursively convert Decimal values to float for JSON serialization.

    Stripe's Python SDK uses ``Decimal`` internally for monetary amounts
    (e.g. ``unit_amount_decimal``).  When ``to_dict()`` is called on a
    Stripe event or resource object, these Decimal values leak into the
    resulting dict.  Django's JSONField (which uses ``json.dumps`` under
    the hood) cannot serialize Decimal, so we must convert them to float
    before persisting.

    This is the single sanitization point — all webhook payloads and
    Stripe response dicts pass through here before being saved to any
    JSONField.
    """
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitize_for_json(item) for item in obj]
    return obj
