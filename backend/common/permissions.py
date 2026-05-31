from ninja_extra.permissions import BasePermission


class IsAuthenticated(BasePermission):
    """Allows access only to authenticated users."""

    def has_permission(self, request, view=None, controller=None, **kwargs):
        return bool(request.user and request.user.is_authenticated)


class IsAdmin(BasePermission):
    """Allows access only to admin/staff users."""

    def has_permission(self, request, view=None, controller=None, **kwargs):
        return bool(
            request.user and request.user.is_authenticated and request.user.is_staff
        )


class IsVerified(BasePermission):
    """Allows access only to users with verified email."""

    def has_permission(self, request, view=None, controller=None, **kwargs):
        return bool(
            request.user
            and request.user.is_authenticated
            and getattr(request.user, "is_email_verified", False)
        )


class IsSelfOrAdmin(BasePermission):
    """Allows access if the user is the object owner or an admin.

    Checks object-level permission using `user` attribute on the object.
    Must be used with has_object_permission.
    """

    def has_permission(self, request, view=None, controller=None, **kwargs):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj, controller=None, **kwargs):
        if request.user.is_staff:
            return True
        if hasattr(obj, "user"):
            return obj.user == request.user
        if hasattr(obj, "owner"):
            return obj.owner == request.user
        return obj == request.user


class IsServiceAuthenticated(BasePermission):
    """Allows access only if a valid service API key was provided.

    Used for endpoints that require service-to-service authentication
    (e.g., the SDK auth/me endpoint). The ``validate_api_key`` function
    must have been called before this permission is checked, typically
    via middleware or a decorator.

    Checks ``request.service_credential`` which is set by
    ``common.api_key_auth.validate_api_key``.
    """

    def has_permission(self, request, view=None, controller=None, **kwargs):
        return bool(
            getattr(request, "service_credential", None) is not None
            and request.service_credential.is_active
        )


class IsAuthenticatedOrService(BasePermission):
    """Allows access if the request is either JWT-authenticated OR carries a
    valid service API key.

    This is the primary permission for endpoints that serve both the
    SattaBase frontend (regular user JWT) and sister-domain SDKs
    (``X-API-Key`` header).  The ``service_credential_middleware`` sets
    ``request.service_credential`` before this permission is checked, so
    SDK requests with a valid key pass through even if no JWT is present
    (or the JWT is absent because the SDK calls auth/me after login).

    When the middleware runs with ``API_KEY_ENFORCED=True``, invalid API
    keys are rejected with 403 *before* this permission is evaluated.
    """

    def has_permission(self, request, view=None, controller=None, **kwargs):
        is_user = bool(request.user and request.user.is_authenticated)
        is_service = bool(
            getattr(request, "service_credential", None) is not None
            and request.service_credential.is_active
        )
        return is_user or is_service
