"""Webhook dispatch for ServiceCredential status changes.

When a service credential is revoked or rotated, the sister domain that
owns that credential needs to be notified immediately so it can stop
using the old key and switch to the new one.  This module provides:

- ``generate_webhook_signature`` — HMAC-SHA256 payload signing.
- ``build_webhook_payload`` — structured payload construction.
- ``dispatch_credential_webhook`` — async-safe entry point that queues
  a Celery task for reliable delivery with retries.

Webhooks are **opt-in per domain**.  A ``ServiceDomain`` must have
``webhook_url`` and ``webhook_secret`` configured to receive events.

Security:
- Every payload is signed with HMAC-SHA256 using the domain's
  ``webhook_secret``.
- The signature is sent in the ``X-Satta-Signature`` header.
- Receivers should verify the signature before processing.
- The ``X-Satta-Timestamp`` header prevents replay attacks.

Celery task:
- ``deliver_credential_webhook`` (``common/tasks.py``) — sends the HTTP
  POST with retry logic (max 3 attempts, exponential backoff).
"""

import json
import hashlib
import hmac
import logging
import time

from django.conf import settings

logger = logging.getLogger(__name__)

# Maximum age (seconds) for webhook timestamp to prevent replay attacks.
MAX_TIMESTAMP_AGE = 300  # 5 minutes


def generate_webhook_signature(payload: bytes, secret: str) -> str:
    """Generate HMAC-SHA256 signature for a webhook payload.

    Args:
        payload: Raw JSON-encoded bytes.
        secret: The webhook secret shared with the receiving domain.

    Returns:
        Hex-encoded HMAC-SHA256 digest.
    """
    return hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()


def verify_webhook_signature(
    payload: bytes, signature: str, secret: str
) -> bool:
    """Verify a webhook signature (for receiving endpoints).

    Uses ``hmac.compare_digest`` for constant-time comparison.

    Args:
        payload: Raw JSON-encoded bytes received in the request body.
        signature: Value from the ``X-Satta-Signature`` header.
        secret: The webhook secret configured for the receiving domain.

    Returns:
        True if the signature is valid.
    """
    expected = generate_webhook_signature(payload, secret)
    return hmac.compare_digest(expected, signature)


def build_webhook_payload(
    event_type: str,
    credential,
    *,
    old_prefix: str | None = None,
    new_prefix: str | None = None,
) -> dict:
    """Build the structured webhook payload.

    Args:
        event_type: One of ``credential.revoked``, ``credential.rotated``.
        credential: The ``ServiceCredential`` instance.
        old_prefix: For rotation events, the prefix of the old key.
        new_prefix: For rotation events, the prefix of the new key.

    Returns:
        Dict ready for JSON serialization.
    """
    payload = {
        "event": event_type,
        "timestamp": int(time.time()),
        "data": {
            "credential_id": credential.id,
            "api_key_prefix": credential.api_key_prefix,
            "name": credential.name,
            "is_active": credential.is_active,
            "service_domain": credential.service_domain.domain,
        },
    }

    if old_prefix:
        payload["data"]["old_prefix"] = old_prefix
    if new_prefix:
        payload["data"]["new_prefix"] = new_prefix

    return payload


def dispatch_credential_webhook(
    event_type: str,
    credential,
    *,
    old_prefix: str | None = None,
    new_prefix: str | None = None,
) -> None:
    """Queue a Celery task to deliver a credential webhook.

    This is the main entry point for controllers and signals.  It does
    NOT block — it queues the delivery for the Celery worker.

    If the domain has no ``webhook_url`` or ``webhook_secret`` configured,
    the call is a no-op (logged at debug level).

    Args:
        event_type: One of ``credential.revoked``, ``credential.rotated``.
        credential: The ``ServiceCredential`` instance.
        old_prefix: For rotation events.
        new_prefix: For rotation events.
    """
    domain = credential.service_domain
    webhook_url = getattr(domain, "webhook_url", "")
    webhook_secret = getattr(domain, "webhook_secret", "")

    if not webhook_url or not webhook_secret:
        logger.debug(
            "WEBHOOK_SKIP: domain='%s' has no webhook_url or "
            "webhook_secret configured",
            domain.domain,
        )
        return

    payload = build_webhook_payload(
        event_type,
        credential,
        old_prefix=old_prefix,
        new_prefix=new_prefix,
    )

    # Queue Celery task for reliable async delivery.
    from common.tasks import deliver_credential_webhook

    deliver_credential_webhook.delay(
        webhook_url=webhook_url,
        webhook_secret=webhook_secret,
        payload=payload,
        event_type=event_type,
        credential_id=credential.id,
        domain=domain.domain,
    )

    logger.info(
        "WEBHOOK_QUEUED: event=%s, credential_id=%s, domain='%s', url=%s",
        event_type,
        credential.id,
        domain.domain,
        webhook_url,
    )
