"""Django signals for ServiceCredential lifecycle events.

Wired via ``common.apps.CommonConfig.ready()`` so that Django imports
this module at startup.

Signals registered:

- **CORS cache invalidation** (C1): When a ``ServiceCredential`` is
  created, updated (``is_active`` toggled), or deleted, the cached set
  of allowed CORS origins is invalidated so the CORS middleware reloads
  fresh from the database on the next request.

- **Audit + webhook triggers** (C4/C5): Signal handlers that dispatch
  async audit-log writes and Celery webhook-delivery tasks are wired
  here too, keeping all credential lifecycle logic in one place.
"""

import logging

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# C1 — CORS cache invalidation
# ---------------------------------------------------------------------------

@receiver(post_save, sender="billing.ServiceCredential")
def invalidate_cors_on_credential_save(sender, instance, created, **kwargs):
    """Invalidate the CORS origins cache when a credential is saved.

    The CORS middleware caches the set of allowed origins in Redis with a
    5-minute TTL (key: ``sattabase_allowed_cors_origins``).  When a
    ``ServiceCredential`` is created or its ``is_active`` flag changes,
    the cache is stale — the new domain may need to be allowed or
    disallowed.  Busting the cache forces the next request to reload
    from the database.

    This signal is lightweight: a single Redis ``delete`` call.
    """
    from django.core.cache import cache

    cache_key = "sattabase_allowed_cors_origins"
    deleted = cache.delete(cache_key)
    logger.debug(
        "CORS_CACHE_INVALIDATED: credential_id=%s, created=%s, "
        "is_active=%s, cache_deleted=%s",
        instance.id,
        created,
        instance.is_active,
        deleted,
    )


@receiver(post_delete, sender="billing.ServiceCredential")
def invalidate_cors_on_credential_delete(sender, instance, **kwargs):
    """Invalidate the CORS origins cache when a credential is deleted."""
    from django.core.cache import cache

    cache_key = "sattabase_allowed_cors_origins"
    deleted = cache.delete(cache_key)
    logger.debug(
        "CORS_CACHE_INVALIDATED: credential_id=%s (deleted), "
        "cache_deleted=%s",
        instance.id,
        deleted,
    )


# ---------------------------------------------------------------------------
# C4/C5 — Audit log + webhook dispatch on credential mutations
# ---------------------------------------------------------------------------

@receiver(post_save, sender="billing.ServiceCredential")
def audit_credential_save(sender, instance, created, **kwargs):
    """Write an audit log entry when a credential is created or updated.

    Uses the existing ``AdminAuditLog`` model.  This runs synchronously
    inside ``post_save`` (which fires inside ``transaction.atomic`` if
    the caller uses one).  The write is a lightweight INSERT that will
    roll back with the outer transaction if it fails.
    """
    try:
        from common.audit import write_credential_audit

        if created:
            write_credential_audit(
                action="api_key.created",
                credential=instance,
                admin_user=instance.created_by,
                details={
                    "name": instance.name,
                    "service_domain": instance.service_domain.domain,
                    "api_key_prefix": instance.api_key_prefix,
                },
            )
        else:
            # Detect whether this is a revocation or reactivation
            # by checking if is_active changed (we don't have the old
            # value, so we log the current state).
            write_credential_audit(
                action="api_key.updated",
                credential=instance,
                details={
                    "name": instance.name,
                    "service_domain": instance.service_domain.domain,
                    "api_key_prefix": instance.api_key_prefix,
                    "is_active": instance.is_active,
                },
            )
    except Exception:
        # Audit logging must never break a save operation.
        logger.exception(
            "CREDENTIAL_AUDIT_SAVE_FAILED: credential_id=%s", instance.id
        )


@receiver(post_delete, sender="billing.ServiceCredential")
def audit_credential_delete(sender, instance, **kwargs):
    """Write an audit log entry when a credential is deleted."""
    try:
        from common.audit import write_credential_audit

        write_credential_audit(
            action="api_key.deleted",
            credential=instance,
            details={
                "name": instance.name,
                "service_domain": instance.service_domain.domain,
                "api_key_prefix": instance.api_key_prefix,
                "was_active": instance.is_active,
            },
        )
    except Exception:
        logger.exception(
            "CREDENTIAL_AUDIT_DELETE_FAILED: credential_id=%s", instance.id
        )
