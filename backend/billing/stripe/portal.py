"""Stripe Customer Portal session creation."""

import logging

from django.conf import settings

from .customer import find_customer_id
from .client import create_portal_session as _create_portal
from .checkout import validate_return_url

logger = logging.getLogger(__name__)


def create_portal(user, return_url: str = None) -> str:
    """Create a Stripe Customer Portal session.  Returns the portal URL.

    Raises:
        ValueError: If user has no Stripe customer.
    """
    customer_id = find_customer_id(user)
    if not customer_id:
        raise ValueError("No Stripe customer found.  Complete a checkout first.")

    _return_url = return_url or getattr(settings, "STRIPE_PORTAL_RETURN_URL", "")

    # PT-01: Validate return_url to prevent open redirect attacks.
    # Both the default STRIPE_PORTAL_RETURN_URL and any caller-provided
    # return_url must pass validation against registered ServiceDomain
    # entries or the app's own domain.
    if not validate_return_url(_return_url):
        logger.warning(
            f"Portal return_url failed validation: {_return_url}. "
            f"Falling back to STRIPE_PORTAL_RETURN_URL."
        )
        _return_url = getattr(settings, "STRIPE_PORTAL_RETURN_URL", "")
        if not validate_return_url(_return_url):
            raise ValueError(
                "No valid return URL configured for Stripe Portal. "
                "Set STRIPE_PORTAL_RETURN_URL in settings."
            )

    # UX-04: Append portal=success query param so the frontend can show
    # feedback toast when the user returns from Stripe Portal.
    portal_base = _return_url.rstrip("/")
    separator = "&" if "?" in portal_base else "?"
    _return_url = f"{portal_base}{separator}portal=success"

    # If a sister-domain return_url was provided and validated, pass it
    # through so the frontend can redirect back after portal interaction.
    if return_url and validate_return_url(return_url) and return_url != _return_url:
        sep2 = "&" if "?" in _return_url else "?"
        _return_url = f"{_return_url}{sep2}return_url={return_url}"

    # CMP-08: Use pre-configured portal configuration if available
    portal_kwargs = {
        "customer_id": customer_id,
        "return_url": _return_url,
    }
    portal_config = getattr(settings, "STRIPE_PORTAL_CONFIGURATION", None)
    if portal_config:
        portal_kwargs["configuration"] = portal_config

    session = _create_portal(**portal_kwargs)

    logger.info(f"Portal session {session['id']} for {user.email}")
    return session["url"]
