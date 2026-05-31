"""Custom API exceptions for the Sattabase project.

All exceptions extend ``ninja_extra.exceptions.APIException`` which itself
extends ``ninja.errors.HttpError``.  Django Ninja catches ``HttpError``
automatically and returns a response using the exception's ``status_code``
and ``detail``.

IMPORTANT — attribute naming conventions from ``APIException``:

- ``status_code``  — HTTP status integer (e.g. 404).
- ``default_detail`` — Default message string.  Must use this name
  (not ``default_message``); ``APIException.__init__`` reads
  ``self.default_detail`` when no ``detail`` argument is supplied.
- ``default_code``  — Machine-readable error code string consumed by
  ``_get_error_details()`` and stored inside ``ErrorDetail.code``.

Each exception is registered with its own handler in ``api/views.py``
so the response body always uses our standard envelope
``{"detail": ..., "code": ...}``.
"""

from ninja_extra.exceptions import APIException


class UnauthorizedException(APIException):
    """Raised when authentication is required but not provided."""

    status_code = 401
    default_detail = "Authentication credentials were not provided."
    default_code = "unauthorized"


class ForbiddenException(APIException):
    """Raised when the user does not have permission to perform the action."""

    status_code = 403
    default_detail = "You do not have permission to perform this action."
    default_code = "forbidden"


class NotFoundException(APIException):
    """Raised when a requested resource is not found."""

    status_code = 404
    default_detail = "The requested resource was not found."
    default_code = "not_found"


class BadRequestException(APIException):
    """Raised when the request data is invalid or malformed."""

    status_code = 400
    default_detail = "The request could not be understood."
    default_code = "bad_request"


class ConflictException(APIException):
    """Raised when the request conflicts with the current state."""

    status_code = 409
    default_detail = "The request conflicts with the current state of the resource."
    default_code = "conflict"


class TooManyRequestsException(APIException):
    """Raised when rate limit is exceeded."""

    status_code = 429
    default_detail = "Too many requests. Please try again later."
    default_code = "too_many_requests"


class AccountNotActiveException(APIException):
    """Raised when user account is not active."""

    status_code = 403
    default_detail = "Your account is not active. Please contact support."
    default_code = "account_not_active"


class AccountInactiveException(APIException):
    """Raised when user account has been deactivated.

    Distinct from ``AccountNotActiveException`` (email verification).
    This signals that an admin deactivated the account.  SDK consumers
    should treat this as a force-logout signal.
    """

    status_code = 401
    default_detail = "This account has been deactivated."
    default_code = "account_inactive"


class AccountDeletedException(APIException):
    """Raised when user account has been soft-deleted.

    Signals that the user requested account deletion.  SDK consumers
    should treat this as a permanent force-logout signal.
    """

    status_code = 401
    default_detail = "This account has been deleted."
    default_code = "account_deleted"
