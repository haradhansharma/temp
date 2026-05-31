"""API key audit logging for service credential lifecycle events.

Provides a synchronous helper (``write_credential_audit``) that writes to
the existing ``AdminAuditLog`` model.  Designed to be called from:

- **Django signals** (``common/signals.py``) — runs in the ORM thread,
  inside the same transaction as the credential save.
- **Controllers** (``common/controllers.py``) — for admin-initiated
  mutations (create, revoke, rotate) where we have the request context.
- **Middleware** (``common/middleware.py``) — for validation failures
  where we have the request but no admin user.

The ``AdminAuditLog`` model (``billing/models.py``) stores:

- ``admin_user`` — FK to the admin who triggered the action (nullable).
- ``action`` — dot-separated identifier, e.g. ``api_key.revoked``.
- ``method`` — HTTP method (for controller-sourced entries).
- ``path`` — request path (for controller/middleware-sourced entries).
- ``ip_address`` — client IP.
- ``status_code`` — HTTP response status (for controller-sourced entries).
- ``details`` — JSON blob with structured context.
"""

import logging

logger = logging.getLogger(__name__)


def write_credential_audit(
    action: str,
    credential=None,
    admin_user=None,
    method: str = "",
    path: str = "",
    ip_address: str = "",
    status_code: int | None = None,
    details: dict | None = None,
) -> None:
    """Persist a credential audit event to ``AdminAuditLog``.

    This is a **synchronous** function.  Call it from:

    - Signal handlers (run in the ORM thread / transaction).
    - Sync controller code or via ``sync_to_async`` wrapper.
    - Middleware sync path.

    For async middleware/controller code, wrap with ``sync_to_async``::

        await sync_to_async(write_credential_audit)(...)

    Args:
        action: Dot-separated action identifier.
            Examples: ``api_key.created``, ``api_key.revoked``,
            ``api_key.validation_failed``, ``api_key.domain_mismatch``.
        credential: The ``ServiceCredential`` instance (or None for
            validation failures where the credential was not found).
        admin_user: The admin ``User`` who triggered the action.
        method: HTTP method (e.g. ``POST``, ``PATCH``).
        path: Request path.
        ip_address: Client IP address.
        status_code: HTTP response status code.
        details: Additional structured context (merged with auto-detected
            fields from *credential*).
    """
    from billing.models import AdminAuditLog

    # Build details dict with auto-detected fields from credential.
    merged_details = details or {}
    if credential is not None:
        merged_details.setdefault("credential_id", credential.id)
        merged_details.setdefault("api_key_prefix", credential.api_key_prefix)
        merged_details.setdefault("name", credential.name)
        if hasattr(credential, "service_domain"):
            merged_details.setdefault(
                "service_domain", credential.service_domain.domain
            )

    AdminAuditLog.objects.create(
        admin_user=admin_user,
        action=action,
        method=method.upper() if method else "",
        path=path,
        ip_address=ip_address or None,
        status_code=status_code,
        details=merged_details,
    )
