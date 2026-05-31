"""Stripe Customer management.

All functions return plain dicts or strings.
"""

import logging
from typing import Optional

from ..models import Subscription
from .client import (
    get_api_key,
    retrieve_customer,
    create_customer,
    modify_customer,
    to_dict,
)

logger = logging.getLogger(__name__)


def get_or_create_customer_id(user) -> str:
    """Return the Stripe Customer ID for *user*, creating if needed.

    Looks for an existing customer ID on any of the user's subscriptions.
    If found, verifies it still exists in Stripe.  Otherwise creates a
    new Stripe Customer.
    """
    api_key = get_api_key()

    existing = (
        Subscription.objects.filter(user=user)
        .exclude(stripe_customer_id="")
        .exclude(stripe_customer_id__isnull=True)
        .first()
    )

    if existing and existing.stripe_customer_id:
        try:
            retrieve_customer(existing.stripe_customer_id)
            return existing.stripe_customer_id
        except Exception:
            # Customer deleted in Stripe — fall through
            pass

    cust = create_customer(
        email=user.email,
        name=user.get_full_name() or user.email,
        metadata={"user_id": user.id, "user_email": user.email},
    )
    logger.info(f"Created Stripe customer {cust['id']} for {user.email}")
    return cust["id"]


def find_customer_id(user) -> Optional[str]:
    """Return the user's Stripe Customer ID, or None."""
    sub = (
        Subscription.objects.filter(user=user)
        .exclude(stripe_customer_id="")
        .exclude(stripe_customer_id__isnull=True)
        .first()
    )
    return sub.stripe_customer_id if sub else None


def sync_customer_to_local(user) -> dict:
    """Pull latest data from Stripe and update the local user record.

    Returns dict with synced status and changed fields.
    """
    customer_id = find_customer_id(user)
    if not customer_id:
        return {"synced": False, "error": "No Stripe customer found"}

    try:
        cust = retrieve_customer(customer_id)
    except Exception as e:
        logger.error(f"Failed to retrieve Stripe customer {customer_id}: {e}")
        return {"synced": False, "error": str(e)}

    updated = False

    # Email
    stripe_email = cust.get("email")
    if stripe_email and stripe_email != user.email:
        user.email = stripe_email
        updated = True

    # Name
    stripe_name = cust.get("name")
    if stripe_name:
        parts = stripe_name.strip().split(" ", 1)
        if parts[0] and parts[0] != user.first_name:
            user.first_name = parts[0]
            updated = True
        if len(parts) > 1 and parts[1] != user.last_name:
            user.last_name = parts[1]
            updated = True

    # Currency from metadata
    metadata = cust.get("metadata") or {}
    stripe_currency = (
        metadata.get("preferred_currency") if isinstance(metadata, dict) else None
    )
    if stripe_currency and hasattr(user, "currency"):
        choices = [
            c[0]
            for c in getattr(
                user.__class__, "CurrencyChoices", type("C", (), {"choices": ()})
            )
        ]
        if stripe_currency in choices and stripe_currency != user.currency:
            user.currency = stripe_currency
            updated = True

    if updated:
        user.save()
        logger.info(f"Synced customer data from Stripe for user {user.id}")
    else:
        logger.info(f"No customer data changes for user {user.id}")

    return {
        "synced": True,
        "email": stripe_email,
        "name": stripe_name,
        "currency": stripe_currency,
    }
