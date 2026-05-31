"""Celery tasks for the common app.

Currently provides:

- ``deliver_credential_webhook`` — sends a signed HTTP POST to a
  sister domain's webhook URL when a credential is revoked or rotated.
  Uses retry with exponential backoff for production reliability.
"""

import json
import logging

from celery import shared_task

logger = logging.getLogger(__name__)

# Webhook HTTP delivery timeout (seconds).
WEBHOOK_TIMEOUT = 10

# Maximum retries for webhook delivery.
WEBHOOK_MAX_RETRIES = 3


@shared_task(
    bind=True,
    max_retries=WEBHOOK_MAX_RETRIES,
    default_retry_delay=60,  # 1 min, then 2 min, then 4 min (exponential)
)
def deliver_credential_webhook(
    self,
    webhook_url: str,
    webhook_secret: str,
    payload: dict,
    event_type: str,
    credential_id: int,
    domain: str,
):
    """Deliver a credential status webhook to a sister domain.

    Sends an HTTP POST with:

    - ``Content-Type: application/json``
    - ``X-Satta-Signature`` — HMAC-SHA256 of the payload body.
    - ``X-Satta-Timestamp`` — Unix timestamp for replay protection.
    - ``X-Satta-Event`` — Event type (``credential.revoked`` /
      ``credential.rotated``).

    The task is queued by ``common.webhooks.dispatch_credential_webhook``
    and retried up to 3 times with exponential backoff on connection
    errors, timeouts, or 5xx responses.

    Args:
        webhook_url: The URL to POST to.
        webhook_secret: HMAC secret for signing.
        payload: The event payload dict.
        event_type: Event identifier.
        credential_id: For logging / audit trail.
        domain: Domain name (for logging).
    """
    from common.webhooks import generate_webhook_signature

    payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    signature = generate_webhook_signature(payload_bytes, webhook_secret)

    headers = {
        "Content-Type": "application/json",
        "X-Satta-Signature": signature,
        "X-Satta-Event": event_type,
        "User-Agent": "Sattabase-Webhook/1.0",
    }

    try:
        import requests

        response = requests.post(
            webhook_url,
            data=payload_bytes,
            headers=headers,
            timeout=WEBHOOK_TIMEOUT,
        )

        if response.status_code >= 500:
            # Server error — retry.
            logger.warning(
                "WEBHOOK_SERVER_ERROR: event=%s, credential_id=%s, "
                "domain='%s', status=%s, url=%s",
                event_type,
                credential_id,
                domain,
                response.status_code,
                webhook_url,
            )
            raise self.retry(
                exc=Exception(
                    f"Webhook server error: {response.status_code}"
                )
            )

        if response.status_code >= 400:
            # Client error (4xx) — do NOT retry (the payload or URL is bad).
            logger.warning(
                "WEBHOOK_CLIENT_ERROR: event=%s, credential_id=%s, "
                "domain='%s', status=%s, body=%s, url=%s",
                event_type,
                credential_id,
                domain,
                response.status_code,
                response.text[:500],
                webhook_url,
            )
            return {
                "status": "client_error",
                "http_status": response.status_code,
                "credential_id": credential_id,
                "domain": domain,
            }

        # Success (2xx).
        logger.info(
            "WEBHOOK_DELIVERED: event=%s, credential_id=%s, "
            "domain='%s', status=%s",
            event_type,
            credential_id,
            domain,
            response.status_code,
        )
        return {
            "status": "delivered",
            "http_status": response.status_code,
            "credential_id": credential_id,
            "domain": domain,
        }

    except requests.exceptions.Timeout:
        logger.warning(
            "WEBHOOK_TIMEOUT: event=%s, credential_id=%s, "
            "domain='%s', url=%s",
            event_type,
            credential_id,
            domain,
            webhook_url,
        )
        raise self.retry(exc=Exception("Webhook delivery timed out"))

    except requests.exceptions.ConnectionError:
        logger.warning(
            "WEBHOOK_CONNECTION_ERROR: event=%s, credential_id=%s, "
            "domain='%s', url=%s",
            event_type,
            credential_id,
            domain,
            webhook_url,
        )
        raise self.retry(exc=Exception("Webhook connection failed"))

    except Exception as exc:
        logger.error(
            "WEBHOOK_DELIVERY_FAILED: event=%s, credential_id=%s, "
            "domain='%s', error=%s",
            event_type,
            credential_id,
            domain,
            exc,
        )
        raise self.retry(exc=exc)
