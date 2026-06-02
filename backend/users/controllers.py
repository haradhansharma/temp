"""Ninja Extra controllers for the users app.

Controllers handle HTTP routing and delegate business logic to services.
They are auto-discovered by ninja_extra's ``auto_discover_controllers()``.

Each controller is decorated with ``@api_controller()`` which registers it
with the API router, sets the URL prefix, applies default auth and
permissions, and generates OpenAPI documentation.

Controllers use ``async def`` where ORM operations are needed (via service
async methods) for non-blocking I/O under Daphne/uvicorn.

Security features utilised from ``common``:

- **Exceptions**: ``NotFoundException``, ``BadRequestException``,
  ``UnauthorizedException``, ``ForbiddenException``, ``ConflictException``,
  ``TooManyRequestsException``, ``AccountNotActiveException`` — raised
  instead of returning tuple responses, caught by registered exception
  handlers in ``api/views.py``.
- **Rate limiting**: ``check_rate_limit_or_raise()`` from
  ``common.rate_limit`` — raises ``TooManyRequestsException`` when
  exceeded.
- **Schemas**: ``MessageResponse`` from ``common.schemas`` for
  standardised success responses.
"""

import logging

from asgiref.sync import sync_to_async

from ninja_extra import api_controller, http_post, http_get, http_put, http_delete
from ninja.security import HttpBearer
from ninja_jwt.tokens import AccessToken, RefreshToken
from ninja_jwt.exceptions import TokenError
from ninja import UploadedFile, File
from django.http import HttpRequest
from django.conf import settings

from common.permissions import IsAuthenticated
from common.rate_limit import check_rate_limit_or_raise
from common.schemas import MessageResponse
from common.exceptions import (
    BadRequestException,
    UnauthorizedException,
    ForbiddenException,
    NotFoundException,
    ConflictException,
)

from .schemas import (
    RegisterInputSchema,
    LoginInputSchema,
    TokenOutputSchema,
    TokenRefreshInputSchema,
    TokenVerifyInputSchema,
    TokenBlacklistInputSchema,
    AuthorizeOutputSchema,
    TokenExchangeInputSchema,
    PasswordResetRequestSchema,
    PasswordResetConfirmSchema,
    PasswordConfirmSchema,
    ChangeEmailRequestSchema,
    DeleteAccountRequestSchema,
    UserOutputSchema,
    UserProfileUpdateInputSchema,
    ChangePasswordInputSchema,
    EmailVerifyRequestSchema,
    EmailVerifyConfirmSchema,
    ChangeEmailConfirmOTPSchema,
    ChoicesSchema,
    AccessTokenOnlySchema,
    CookieRefreshInputSchema,
)
from .services import AuthService, UserService
from .models import (
    User,
    RoleChoices,
    TimezoneChoices,
    CurrencyChoices,
    LanguageChoices,
)

logger = logging.getLogger(__name__)

# ninja_jwt's for_user() and blacklist() perform sync DB writes.
# Wrap them so they can be safely called from async endpoints.
async_token_for_user = sync_to_async(AccessToken.for_user)
async_refresh_for_user = sync_to_async(RefreshToken.for_user)
async_decode_refresh = sync_to_async(lambda t: RefreshToken(t))
async_blacklist = sync_to_async(lambda r: r.blacklist())


# =============================================================================
# HIGH-03 FIX: Cookie-based Authentication (XSS Protection)
# =============================================================================

# Cookie names for refresh token storage
REFRESH_TOKEN_COOKIE_NAME = "sb_refresh_token"
REMEMBER_ME_COOKIE_NAME = "sb_remember_me"

# Cookie expiration times
REFRESH_COOKIE_EXPIRY_DAYS = 30  # When "remember me" is true


def _get_cookie_settings() -> tuple:
    """Return (secure, samesite) for auth cookies based on environment.

    Development (DEBUG=True, HTTP localhost):
        - SameSite=Lax, Secure=False
        - Works because localhost:4321 → localhost:8086 is SAME-SITE
          (same registrable domain), so Lax allows cookies on fetch POST.
        - Secure=False is required because the browser will REJECT
          Set-Cookie with Secure=True over plain HTTP (no HTTPS),
          meaning the cookie is never stored at all.

    Production (DEBUG=False, HTTPS):
        - SameSite=None, Secure=True
        - Required for cross-domain setups (e.g., app.example.com →
          api.example.com) where origins are truly cross-site.
        - SameSite=None REQUIRES Secure=True per browser spec.

    Why SameSite=Lax works in dev:
        The SameSite algorithm checks the "site" (scheme + registrable
        domain).  http://localhost:4321 and http://localhost:8086 share
        the same site (http + localhost), so Lax cookies are sent on
        fetch() POST requests between them.
    """
    if settings.DEBUG:
        return False, "Lax"
    return True, "None"


def _set_auth_cookie(response, refresh_token: str, remember: bool = False) -> None:
    """Set refresh token in httpOnly cookie for XSS protection.
    
    HIGH-03 FIX: Stores refresh token in httpOnly cookie instead of
    localStorage/sessionStorage. This prevents XSS attacks from stealing
    the refresh token.
    
    Cookie settings are determined by _get_cookie_settings() which
    adapts to the environment (dev vs prod).
    
    Args:
        response: Django HttpResponse object
        refresh_token: The refresh token to store
        remember: If True, cookie persists for 30 days; otherwise session cookie
    """
    secure, samesite = _get_cookie_settings()
    
    # Set refresh token cookie
    if remember:
        from django.utils import timezone
        from datetime import timedelta
        expires = timezone.now() + timedelta(days=REFRESH_COOKIE_EXPIRY_DAYS)
        response.set_cookie(
            REFRESH_TOKEN_COOKIE_NAME,
            refresh_token,
            expires=expires,
            httponly=True,
            secure=secure,
            samesite=samesite,
            path="/",
        )
        # Set a flag cookie to indicate remember me is enabled
        # This is NOT httpOnly so frontend can read it
        response.set_cookie(
            REMEMBER_ME_COOKIE_NAME,
            "true",
            expires=expires,
            httponly=False,  # Readable by frontend
            secure=secure,
            samesite=samesite,
            path="/",
        )
    else:
        # Session cookie - expires when browser closes
        response.set_cookie(
            REFRESH_TOKEN_COOKIE_NAME,
            refresh_token,
            httponly=True,
            secure=secure,
            samesite=samesite,
            path="/",
        )
        # Clear remember me flag (use set_cookie with max_age=0 for
        # compatibility with Django versions where delete_cookie() lacks
        # the 'secure' keyword argument)
        response.set_cookie(
            REMEMBER_ME_COOKIE_NAME,
            "",
            max_age=0,
            path="/",
            secure=secure,
            samesite=samesite,
        )


def _clear_auth_cookie(response) -> None:
    """Clear the refresh token cookie on logout.
    
    HIGH-03 FIX: Removes the httpOnly cookie containing refresh token.
    Must match the SameSite/Secure settings used when the cookie was set,
    otherwise the browser won't delete it.
    
    Uses set_cookie with max_age=0 instead of delete_cookie() because
    delete_cookie() in older Django versions does not support the
    ``secure`` keyword argument.
    """
    secure, samesite = _get_cookie_settings()
    response.set_cookie(
        REFRESH_TOKEN_COOKIE_NAME,
        "",
        max_age=0,
        path="/",
        httponly=True,
        secure=secure,
        samesite=samesite,
    )
    response.set_cookie(
        REMEMBER_ME_COOKIE_NAME,
        "",
        max_age=0,
        path="/",
        secure=secure,
        samesite=samesite,
    )


# =============================================================================
# JWT Authentication (for protecting endpoints)
# =============================================================================


class JWTAuth(HttpBearer):
    """HTTP Bearer authentication using JWT access tokens.

    Validates the Bearer token from the Authorization header,
    decodes it, and returns the authenticated user.  Shared across
    all apps — billing controllers import this class.
    """

    async def authenticate(self, request, token):
        try:
            access_token = AccessToken(token)
            user_id = access_token.get("user_id")
            if not user_id:
                return None

            user = await User.objects.filter(
                id=user_id, is_active=True, is_deleted=False
            ).afirst()
            if user:
                request.user = user
                return user
            return None
        except Exception as e:
            # LOW-01 FIX: Log auth failures at WARNING level for security monitoring
            logger.warning(f"JWT auth failed: {e}")
            return None


# =============================================================================
# Auth Controller — Registration, Login, Token Management, Password Reset
# =============================================================================


@api_controller("/auth", tags=["Authentication"], auth=None)
class AuthController:
    """Public authentication endpoints.

    All endpoints in this controller are public (no auth required).
    They handle user registration, login, token management, and
    password reset / email verification via OTP.
    """

    @http_get(
        "/choices",
        response=ChoicesSchema,
        summary="Get field choices",
        description="Return available timezone, currency, and language choices. Used by registration and profile forms.",
    )
    def get_choices(self):
        """Return available timezone, currency, and language choices.

        Labels are explicitly cast to ``str`` because Django's
        ``TextChoices`` stores labels as lazy translation proxies
        (``gettext_lazy``).  Pydantic requires plain ``str`` values,
        so ``str(l)`` resolves the proxy eagerly.
        """
        return {
            "timezones": [
                {"value": v, "label": str(l)} for v, l in TimezoneChoices.choices
            ],
            "currencies": [
                {"value": v, "label": str(l)} for v, l in CurrencyChoices.choices
            ],
            "languages": [
                {"value": v, "label": str(l)} for v, l in LanguageChoices.choices
            ],
        }

    @http_post(
        "/register",
        response={201: MessageResponse, 409: dict, 400: dict, 429: dict},
        summary="Register a new account",
        description="Create a new user account. A verification code will be sent to the provided email.",
    )
    async def register(self, request: HttpRequest, payload: RegisterInputSchema):
        """Register a new user and send email verification OTP."""
        check_rate_limit_or_raise(
            request,
            "register",
            max_attempts=getattr(settings, "RATE_LIMIT_REGISTER_ATTEMPTS", 5),
            window_seconds=getattr(settings, "RATE_LIMIT_REGISTER_WINDOW", 3600),
        )

        try:
            user = await AuthService.aregister_user(
                email=payload.email,
                password=payload.password,
                first_name=payload.first_name,
                last_name=payload.last_name or "",
                timezone=payload.timezone,
                currency=payload.currency,
                language=payload.language,
            )

            # Automatically send verification OTP after registration
            try:
                await AuthService.arequest_email_verification(payload.email)
            except Exception as e:
                logger.warning(
                    f"Failed to send verification OTP after registration: {e}"
                )

            return 201, MessageResponse(
                message="Registration successful. Please check your email for a verification code."
            )

        except ValueError as e:
            msg = str(e)
            if "already exists" in msg:
                raise ConflictException(msg)
            raise BadRequestException(msg)

        except Exception as e:
            logger.error(f"Registration error: {e}")
            raise BadRequestException("Registration failed. Please try again.")

    @http_post(
        "/login",
        response={200: TokenOutputSchema, 401: dict, 403: dict, 429: dict},
        summary="Login with email and password",
        description="Authenticate with email/password and receive JWT tokens.",
    )
    async def login(self, request: HttpRequest, payload: LoginInputSchema):
        """Authenticate and return JWT access + refresh tokens.
        
        HIGH-03 FIX: Also sets refresh token in httpOnly cookie for XSS protection.
        The response body still contains both tokens for backwards compatibility
        with API clients and SSO flows.
        """
        check_rate_limit_or_raise(
            request,
            "login",
            max_attempts=getattr(settings, "RATE_LIMIT_LOGIN_ATTEMPTS", 10),
            window_seconds=getattr(settings, "RATE_LIMIT_LOGIN_WINDOW", 900),
        )

        try:
            user = await AuthService.aauthenticate_user(payload.email, payload.password)
            access = await async_token_for_user(user)
            refresh = await async_refresh_for_user(user)

            # Record login in history table and update last_login/last_login_ip
            from common.rate_limit import get_client_ip

            client_ip = get_client_ip(request)
            user_agent = request.META.get("HTTP_USER_AGENT", "")
            try:
                await AuthService.arecord_login(
                    user, ip_address=client_ip, user_agent=user_agent
                )
            except Exception as e:
                logger.warning(f"Failed to record login history: {e}")

            # HIGH-03 FIX: Set refresh token in httpOnly cookie
            # The remember flag controls whether the cookie persists (30 days) or is session-only
            from django.http import JsonResponse
            
            response_data = TokenOutputSchema(access=str(access), refresh=str(refresh))
            response = JsonResponse(response_data.dict())
            _set_auth_cookie(response, str(refresh), remember=payload.remember)
            
            return response

        except ValueError as e:
            msg = str(e)
            if "Invalid" in msg:
                raise UnauthorizedException(msg)
            raise ForbiddenException(msg)

    @http_post(
        "/token/refresh",
        response={200: TokenOutputSchema, 401: dict},
        summary="Refresh access token",
        description="Exchange a valid refresh token for a new access token pair.",
    )
    async def refresh_token(self, payload: TokenRefreshInputSchema):
        """Exchange a refresh token for a new token pair.
        
        CRIT-01 FIX: Blacklist the old refresh token before issuing new ones.
        This prevents token reuse attacks where stolen refresh tokens could be
        used multiple times.
        """
        try:
            refresh = await async_decode_refresh(payload.refresh)

            user_id = refresh.get("user_id")
            if not user_id:
                raise ValueError("Invalid token payload")

            user = await User.objects.filter(
                id=user_id, is_active=True, is_deleted=False
            ).afirst()
            if not user:
                raise ValueError("User not found or inactive")

            # CRIT-01 FIX: Blacklist the OLD refresh token before issuing new ones
            # This prevents the old token from being used again (token rotation security)
            await async_blacklist(refresh)

            new_access = await async_token_for_user(user)
            new_refresh = await async_refresh_for_user(user)

            return TokenOutputSchema(access=str(new_access), refresh=str(new_refresh))

        except (ValueError, TokenError) as e:
            error_msg = str(e)
            
            # MED-02 FIX: Detect refresh token reuse (potential security breach)
            if "blacklisted" in error_msg.lower():
                logger.warning(
                    f"SECURITY_ALERT: Refresh token reuse detected in body-based refresh! "
                    f"Possible token theft attempt. Error: {error_msg}"
                )
            
            logger.debug(f"Token refresh failed: {e}")
            raise UnauthorizedException("Invalid or expired refresh token.")

    @http_post(
        "/token/refresh-cookie",
        response={200: AccessTokenOnlySchema, 401: dict},
        summary="Refresh access token using cookie",
        description=(
            "Refresh access token using the refresh token from httpOnly cookie. "
            "HIGH-03 FIX: This endpoint is the preferred way to refresh tokens "
            "for browser clients as it uses cookie-based auth for XSS protection."
        ),
    )
    async def refresh_token_cookie(self, request: HttpRequest, payload: CookieRefreshInputSchema):
        """Refresh access token using cookie-based refresh token.
        
        HIGH-03 FIX: Reads refresh token from httpOnly cookie instead of request body.
        This is more secure because the cookie cannot be accessed by JavaScript,
        protecting against XSS attacks.
        
        TOKEN ROTATION STRATEGY (UPDATED):
        The cookie-based refresh endpoint now ROTATES the refresh token — it
        issues a new refresh token with a fresh expiry on every refresh. This
        ensures that active users stay logged in for the full cookie duration
        (30 days with "Remember Me").

        The OLD refresh token is NOT blacklisted on rotation. This is intentional
        — it prevents race conditions where multiple concurrent refresh requests
        (caused by Astro View Transitions, HMR, or multiple browser tabs) would
        each blacklist the previous token, causing cascading 401 failures.

        The old token naturally expires (TTL configured via SIMPLE_JWT settings),
        providing a grace period during which concurrent tabs can still use the
        old cookie. The browser replaces the old cookie with the new one as soon
        as any tab receives the refresh response.

        Tokens ARE blacklisted on explicit logout, which is the correct place
        for immediate revocation.
        
        Security trade-off: A stolen refresh token remains valid until it expires
        naturally (up to 7 days), rather than being invalidated immediately on
        rotation. This is acceptable because:
        1. The cookie is httpOnly — XSS cannot steal it
        2. SameSite=Lax (dev) / SameSite=None+Secure (prod) — CSRF-resistant
        3. Natural expiration (7 days) limits the window
        4. Explicit logout DOES blacklist the token immediately
        5. The alternative (rotation + blacklist) causes constant auth failures
           in SPAs with Astro View Transitions, making the app unusable
        
        CSRF FIX: This endpoint is explicitly CSRF-exempt because:
        1. It uses JWT tokens (not Django sessions) for authentication
        2. The refresh token is in an httpOnly cookie
        3. Django's CsrfViewMiddleware would block cross-origin POST requests
           that carry credential cookies, but JWT provides equivalent protection
           without requiring a CSRF token in the request body.
        """
        from django.http import JsonResponse
        
        # Get refresh token from cookie
        refresh_token = request.COOKIES.get(REFRESH_TOKEN_COOKIE_NAME)
        if not refresh_token:
            raise UnauthorizedException("No refresh token cookie found.")

        try:
            refresh = await async_decode_refresh(refresh_token)

            user_id = refresh.get("user_id")
            if not user_id:
                raise ValueError("Invalid token payload")

            user = await User.objects.filter(
                id=user_id, is_active=True, is_deleted=False
            ).afirst()
            if not user:
                raise ValueError("User not found or inactive")

            # NOTE: We intentionally do NOT blacklist the old refresh token here.
            # See the docstring above for the rationale. Blacklisting only
            # happens on explicit logout (see logout_cookie endpoint).

            new_access = await async_token_for_user(user)

            # ROTATE the refresh token — issue a NEW one with a fresh expiry.
            # This ensures active users stay logged in for the full cookie
            # duration (30 days with "Remember Me"). Without rotation, the
            # refresh token JWT expires after 7 days even though the cookie
            # persists for 30 days, breaking "Remember Me".
            new_refresh = await async_refresh_for_user(user)

            # Check if "remember me" was enabled (cookie persists)
            remember_me = request.COOKIES.get(REMEMBER_ME_COOKIE_NAME) == "true"

            # Return access token and set the NEW refresh token in the cookie.
            response_data = AccessTokenOnlySchema(access=str(new_access))
            response = JsonResponse(response_data.dict())
            # Set the NEW refresh token in the cookie — this extends the session
            _set_auth_cookie(response, str(new_refresh), remember=remember_me)

            return response

        except Exception as e:
            # BROAD EXCEPTION FIX: Previously only (ValueError, TokenError) were
            # caught, but simplejwt/ninja_jwt can raise other exception types
            # (e.g., TokenBackendError, InvalidToken) that would cause a 500
            # Internal Server Error. Catching all exceptions ensures we always
            # return a proper 401 and clear the invalid cookie.
            error_msg = str(e)
            
            # MED-02 FIX: Detect refresh token reuse (potential security breach)
            # If the token is blacklisted, it means it was already used in logout
            if "blacklisted" in error_msg.lower():
                logger.warning(
                    f"SECURITY_ALERT: Refresh token reuse detected! "
                    f"Possible token theft attempt. Error: {error_msg}"
                )
            else:
                logger.debug(f"Cookie token refresh failed: {e}")
            
            # Clear the invalid/blacklisted cookie so subsequent requests don't fail
            response = JsonResponse({"detail": "Invalid or expired refresh token."}, status=401)
            _clear_auth_cookie(response)
            return response

    @http_post(
        "/token/verify",
        response={200: MessageResponse, 401: dict},
        summary="Verify access token",
        description="Verify an access token is still valid.",
    )
    async def verify_token(self, payload: TokenVerifyInputSchema):
        """Check if an access token is valid."""
        try:
            AccessToken(payload.token)
            return MessageResponse(message="Token is valid.")
        except Exception:
            raise UnauthorizedException("Token is invalid or expired.")

    @http_post(
        "/token/blacklist",
        response={200: MessageResponse, 401: dict},
        summary="Blacklist a refresh token",
        description="Blacklist a refresh token so it cannot be used again. MED-04 FIX: Requires authentication.",
        auth=JWTAuth(),
    )
    async def blacklist_token(self, request: HttpRequest, payload: TokenBlacklistInputSchema):
        """Add a refresh token to the blacklist.
        
        MED-04 FIX: Now requires authentication. Previously anyone could blacklist
        any token, enabling DoS attacks.
        """
        try:
            refresh = await async_decode_refresh(payload.refresh)
            await async_blacklist(refresh)
            return MessageResponse(message="Token blacklisted successfully.")
        except Exception as e:
            # LOW-01 FIX: Log blacklist failures at WARNING level for security monitoring
            logger.warning(f"Token blacklist failed: {e}")
            raise UnauthorizedException("Failed to blacklist token.")

    @http_post(
        "/logout",
        response={200: MessageResponse, 401: dict},
        summary="Logout and clear auth cookie",
        description=(
            "HIGH-03 FIX: Blacklist the refresh token from cookie and clear auth cookies. "
            "This is the preferred logout endpoint for browser clients."
        ),
    )
    async def logout_cookie(self, request: HttpRequest):
        """Logout by blacklisting refresh token from cookie and clearing cookies.
        
        HIGH-03 FIX: Reads refresh token from httpOnly cookie, blacklists it,
        and clears the cookie. This provides secure logout for browser clients.
        
        CSRF FIX: Explicitly CSRF-exempt — uses JWT cookies, not Django sessions.
        """
        from django.http import JsonResponse
        
        refresh_token = request.COOKIES.get(REFRESH_TOKEN_COOKIE_NAME)
        
        if refresh_token:
            try:
                refresh = await async_decode_refresh(refresh_token)
                await async_blacklist(refresh)
            except Exception as e:
                # Even if blacklisting fails, clear the cookie
                logger.debug(f"Failed to blacklist token on logout: {e}")

        response = JsonResponse({"message": "Logged out successfully."})
        _clear_auth_cookie(response)
        
        return response

    # =========================================================================
    # Password Reset Endpoints
    # =========================================================================

    @http_post(
        "/password-reset/request",
        response={200: MessageResponse, 429: dict},
        summary="Request password reset",
        description=(
            "Request a password reset email. "
            "If an account with the given email exists, a reset code will be sent. "
            "Always returns 200 to prevent email enumeration."
        ),
    )
    async def request_password_reset(
        self, request: HttpRequest, payload: PasswordResetRequestSchema
    ):
        """Request a password reset OTP via email."""
        check_rate_limit_or_raise(
            request,
            "pwreset_req",
            max_attempts=getattr(settings, "RATE_LIMIT_PASSWORD_RESET_ATTEMPTS", 5),
            window_seconds=getattr(settings, "RATE_LIMIT_PASSWORD_RESET_WINDOW", 3600),
        )

        try:
            await AuthService.arequest_password_reset(payload.email)
        except ValueError:
            # Always return 200 to prevent email enumeration
            pass

        return MessageResponse(
            message="If an account with this email exists, a reset code has been sent."
        )

    @http_post(
        "/password-reset/confirm",
        response={200: MessageResponse, 400: dict, 429: dict},
        summary="Confirm password reset with OTP",
        description="Reset password using the 6-digit code received via email.",
    )
    async def confirm_password_reset(
        self, request: HttpRequest, payload: PasswordResetConfirmSchema
    ):
        """Confirm password reset with OTP and set new password.
        
        MED-03 FIX: Rate limit key now includes email to prevent global exhaustion.
        Each email has its own rate limit bucket.
        """
        # MED-03 FIX: Include email in rate limit key to prevent global exhaustion attacks
        check_rate_limit_or_raise(
            request,
            f"pwreset_confirm:{payload.email}",
            max_attempts=getattr(settings, "RATE_LIMIT_PASSWORD_RESET_ATTEMPTS", 5),
            window_seconds=getattr(settings, "RATE_LIMIT_PASSWORD_RESET_WINDOW", 3600),
        )

        try:
            await AuthService.aconfirm_password_reset(
                email=payload.email,
                otp=payload.otp,
                new_password=payload.new_password,
            )
            return MessageResponse(
                message="Password reset successfully. You can now log in with your new password."
            )
        except ValueError as e:
            raise BadRequestException(str(e))

    # =========================================================================
    # Email Verification (OTP)
    # =========================================================================

    @http_post(
        "/verify-email/request",
        response={200: MessageResponse, 400: dict, 429: dict},
        summary="Request email verification OTP",
        description=(
            "Request a 6-digit verification code to be sent to the provided email. "
            "The code expires in 10 minutes. Maximum 3 verification attempts per email per hour."
        ),
    )
    async def request_email_verification(
        self, request: HttpRequest, payload: EmailVerifyRequestSchema
    ):
        """Request an email verification OTP.
        
        MED-16 FIX: Rate limit now includes email to prevent email bombing attacks.
        Reduced from 5/5min to 3/hour per email.
        """
        # MED-16 FIX: Include email in rate limit key to prevent email bombing
        # Reduced from 5/5min to 3/hour per email
        check_rate_limit_or_raise(
            request,
            f"email_verify_req:{payload.email}",
            max_attempts=getattr(settings, "RATE_LIMIT_EMAIL_VERIFY_ATTEMPTS", 3),
            window_seconds=getattr(settings, "RATE_LIMIT_EMAIL_VERIFY_WINDOW", 3600),  # 1 hour
        )

        try:
            await AuthService.arequest_email_verification(payload.email)
            return MessageResponse(message="Verification code sent to your email.")
        except ValueError as e:
            raise BadRequestException(str(e))

    @http_post(
        "/verify-email/confirm",
        response={200: MessageResponse, 400: dict, 429: dict},
        summary="Confirm email verification with OTP",
        description=(
            "Verify an email address using the 6-digit code sent via email. "
            "Maximum 5 attempts per code. After 5 failed attempts, a new code must be requested."
        ),
    )
    async def confirm_email_verification(
        self, request: HttpRequest, payload: EmailVerifyConfirmSchema
    ):
        """Confirm email verification with OTP."""
        check_rate_limit_or_raise(
            request,
            "email_verify_confirm",
            max_attempts=getattr(settings, "RATE_LIMIT_EMAIL_VERIFY_ATTEMPTS", 10),
            window_seconds=getattr(settings, "RATE_LIMIT_EMAIL_VERIFY_WINDOW", 300),
        )

        try:
            await AuthService.aconfirm_email_verification(payload.email, payload.otp)
            return MessageResponse(
                message="Email verified successfully. You can now log in."
            )
        except ValueError as e:
            raise BadRequestException(str(e))

    # =========================================================================
    # Cross-Domain SSO (Authorization Code Flow)
    # =========================================================================

    @http_post(
        "/authorize",
        response={200: AuthorizeOutputSchema, 401: dict},
        auth=JWTAuth(),
        permissions=[IsAuthenticated],
        summary="Generate SSO authorization code",
        description=(
            "Generate a one-time authorization code for cross-domain single sign-on. "
            "Requires a valid JWT access token. The code expires in 30 seconds and "
            "can only be used once. Sister domains use this to redirect authenticated "
            "users to the Sattabase base domain without requiring a second login."
        ),
    )
    async def authorize(self, request: HttpRequest):
        """Generate a one-time authorization code for cross-domain SSO.
        
        Called by a sister domain's frontend when the user needs to access
        the base Sattabase domain (e.g., for billing management). The code
        is passed as a URL parameter in the redirect.
        """
        code = await AuthService.agenerate_auth_code(request.user)
        return AuthorizeOutputSchema(code=code, expires_in=30)

    @http_post(
        "/token/exchange",
        response={200: TokenOutputSchema, 400: dict, 401: dict},
        summary="Exchange authorization code for tokens",
        description=(
            "Exchange a one-time authorization code for JWT access and refresh tokens. "
            "The code is consumed upon use and cannot be reused. Called by the "
            "Sattabase base domain's callback page after a sister domain redirects "
            "the user with an authorization code."
        ),
    )
    async def exchange_token(self, request: HttpRequest, payload: TokenExchangeInputSchema):
        """Exchange an authorization code for a JWT token pair.
        
        Called by the base Sattabase domain's /auth/callback page to
        complete the cross-domain SSO flow. Returns the same response
        format as /auth/login.
        
        CRIT-06 FIX: Added rate limiting to prevent brute force attacks on auth codes.
        HIGH-03 FIX: Also sets refresh token in httpOnly cookie for XSS protection.
        """
        from django.http import JsonResponse
        
        # CRIT-06 FIX: Rate limit auth code exchange to prevent brute force attacks
        check_rate_limit_or_raise(request, "token_exchange", max_attempts=10, window_seconds=60)
        
        try:
            user = await AuthService.aexchange_auth_code(payload.code)
            access = await async_token_for_user(user)
            refresh = await async_refresh_for_user(user)
            
            # HIGH-03 FIX: Set refresh token in httpOnly cookie
            # SSO callback uses session cookie (not persistent) for security
            response_data = TokenOutputSchema(access=str(access), refresh=str(refresh))
            response = JsonResponse(response_data.dict())
            _set_auth_cookie(response, str(refresh), remember=False)
            
            return response
        except ValueError as e:
            msg = str(e)
            if "not verified" in msg:
                raise ForbiddenException(msg)
            if "Invalid" in msg or "expired" in msg:
                raise BadRequestException(msg)
            raise UnauthorizedException(msg)


# =============================================================================
# User Controller — Profile Management (authenticated)
# =============================================================================


@api_controller(
    "/users",
    tags=["Users"],
    auth=JWTAuth(),
    permissions=[IsAuthenticated],
)
class UserController:
    """Authenticated user profile endpoints.

    All endpoints require a valid JWT access token.
    """

    # =========================================================================
    # Profile (No extra confirmation needed)
    # =========================================================================

    @http_get(
        "/me",
        response=UserOutputSchema,
        summary="Get current user profile",
        description="Return the authenticated user's profile information.",
    )
    async def get_profile(self, request: HttpRequest):
        """Return the authenticated user's profile.

        Made async to ensure compatibility with async JWTAuth.authenticate()
        under ASGI (Daphne). Sync methods in an async controller can fail to
        access request.user set by async authentication because the ASGI
        handler may not properly bridge the sync/async boundary for attribute
        access on the request object.
        """
        return request.user

    @http_get(
        "/{slug}",
        response={200: UserOutputSchema, 404: dict},
        summary="Get user by slug",
        description="Look up a user's public profile by their UUID slug.",
    )
    async def get_user_by_slug(self, slug: str):
        user = await UserService.aget_user_by_slug(slug)
        if not user:
            raise NotFoundException("User not found.")
        return user

    @http_put(
        "/me",
        response=UserOutputSchema,
        summary="Update user profile",
        description="Update the authenticated user's profile fields.",
    )
    async def update_profile(
        self, request: HttpRequest, payload: UserProfileUpdateInputSchema
    ):
        user = await UserService.aupdate_profile(
            request.user, **payload.model_dump(exclude_none=True)
        )
        return user

    # =========================================================================
    # Avatar Upload
    # =========================================================================

    @http_put(
        "/me/avatar",
        response={200: UserOutputSchema, 400: dict},
        summary="Upload avatar",
        description="Upload or replace the authenticated user's avatar image. Accepts JPEG, PNG, GIF, WebP. Max 2 MB.",
    )
    async def update_avatar(
        self,
        request: HttpRequest,
        file: UploadedFile = File(..., alias="avatar"),
    ):
        """Handle avatar upload via multipart/form-data."""
        if "avatar" not in request.FILES:
            raise BadRequestException("No file provided. Use the 'avatar' field.")

        file = request.FILES["avatar"]

        # Validate file type
        ALLOWED_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
        if file.content_type not in ALLOWED_TYPES:
            raise BadRequestException(
                "Invalid file type. Allowed: JPEG, PNG, GIF, WebP."
            )

        # Validate file size (2 MB)
        MAX_SIZE = 2 * 1024 * 1024
        if file.size > MAX_SIZE:
            raise BadRequestException("File too large. Maximum size is 2 MB.")

        # Delete old avatar file if it exists
        user = request.user
        if user.avatar:
            try:
                user.avatar.delete(save=False)
            except Exception as e:
                logger.warning(f"Failed to delete old avatar: {e}")

        # Save new avatar
        user.avatar = file
        await user.asave(update_fields=["avatar"])
        logger.info(f"Avatar updated: user={user.email}")

        return user

    @http_delete(
        "/me/avatar",
        response={200: UserOutputSchema, 404: dict},
        summary="Delete avatar",
        description="Remove the authenticated user's avatar image.",
    )
    async def delete_avatar(self, request: HttpRequest):
        """Remove the user's avatar file and clear the field."""
        user = request.user

        if not user.avatar:
            raise NotFoundException("No avatar to delete.")

        try:
            user.avatar.delete(save=False)
        except Exception as e:
            logger.warning(f"Failed to delete avatar file: {e}")

        user.avatar = None
        await user.asave(update_fields=["avatar"])
        logger.info(f"Avatar deleted: user={user.email}")

        return user

    # =========================================================================
    # Password Change
    # =========================================================================

    @http_post(
        "/me/change-password",
        response={200: MessageResponse, 400: dict},
        summary="Change password",
        description="Change the authenticated user's password. Requires current password.",
    )
    async def change_password(
        self, request: HttpRequest, payload: ChangePasswordInputSchema
    ):
        """Change password after verifying current password."""
        # HIGH-19: Rate limit password changes to prevent abuse
        check_rate_limit_or_raise(request, "change_password", max_attempts=5, window_seconds=3600)
        try:
            await AuthService.achange_password(
                request.user,
                current_password=payload.current_password,
                new_password=payload.new_password,
            )
            return MessageResponse(message="Password changed successfully.")
        except ValueError as e:
            raise BadRequestException(str(e))

    # =========================================================================
    # Sensitive Actions — Require Current Password Re-Confirmation
    # =========================================================================

    @http_post(
        "/me/confirm-identity",
        response={200: MessageResponse, 401: dict, 429: dict},
        summary="Confirm identity",
        description=(
            "Verify identity by providing current password. "
            "Use this before sensitive operations (email change, account deletion). "
            "Returns success if password is correct — acts as a reusable identity gate."
        ),
    )
    async def confirm_identity(
        self, request: HttpRequest, payload: PasswordConfirmSchema
    ):
        """Verify the user's current password as an identity gate."""
        check_rate_limit_or_raise(
            request,
            "confirm_identity",
            max_attempts=getattr(settings, "RATE_LIMIT_SENSITIVE_ATTEMPTS", 10),
            window_seconds=getattr(settings, "RATE_LIMIT_SENSITIVE_WINDOW", 3600),
        )

        try:
            await AuthService.aconfirm_identity(
                request.user,
                current_password=payload.current_password,
            )
            return MessageResponse(message="Identity confirmed.")
        except ValueError as e:
            raise UnauthorizedException(str(e))

    @http_post(
        "/me/change-email",
        response={200: MessageResponse, 400: dict, 401: dict, 429: dict},
        summary="Request email change (OTP)",
        description=(
            "Request to change email address. Requires current password. "
            "A 6-digit OTP will be sent to your CURRENT email. "
            "Use POST /users/me/change-email/confirm with the OTP to complete the change."
        ),
    )
    async def request_email_change(
        self, request: HttpRequest, payload: ChangeEmailRequestSchema
    ):
        """Request email change — sends OTP to current email."""
        check_rate_limit_or_raise(
            request,
            "email_change",
            max_attempts=getattr(settings, "RATE_LIMIT_SENSITIVE_ATTEMPTS", 5),
            window_seconds=getattr(settings, "RATE_LIMIT_SENSITIVE_WINDOW", 3600),
        )

        try:
            await AuthService.arequest_email_change(
                request.user,
                current_password=payload.current_password,
                new_email=payload.new_email,
            )
            return MessageResponse(
                message="A verification code has been sent to your current email."
            )
        except ValueError as e:
            msg = str(e)
            if "password" in msg.lower():
                raise UnauthorizedException(msg)
            raise BadRequestException(msg)

    @http_post(
        "/me/change-email/confirm",
        response={200: MessageResponse, 400: dict, 429: dict},
        summary="Confirm email change with OTP",
        description=(
            "Confirm an email change using the 6-digit OTP sent to your current email. "
            "After confirmation, your session will be invalidated. Please log in with your new email."
        ),
    )
    async def confirm_email_change_otp(
        self, request: HttpRequest, payload: ChangeEmailConfirmOTPSchema
    ):
        """Confirm email change with OTP from current email."""
        check_rate_limit_or_raise(
            request,
            "email_change_confirm",
            max_attempts=getattr(settings, "RATE_LIMIT_SENSITIVE_ATTEMPTS", 10),
            window_seconds=getattr(settings, "RATE_LIMIT_SENSITIVE_WINDOW", 3600),
        )

        try:
            new_email = await AuthService.aconfirm_email_change_otp(
                request.user, payload.otp
            )
            return MessageResponse(
                message=f"Email changed to {new_email}. Please log in with your new email."
            )
        except ValueError as e:
            raise BadRequestException(str(e))

    @http_post(
        "/me/delete-account",
        response={200: MessageResponse, 401: dict, 429: dict},
        summary="Delete account",
        description=(
            "Soft-delete your account. Requires current password confirmation. "
            "Your data will be retained but the account will be deactivated. "
            "You will be logged out immediately — discard your JWT tokens."
        ),
    )
    async def delete_account(
        self, request: HttpRequest, payload: DeleteAccountRequestSchema
    ):
        """Soft-delete the account after password confirmation."""
        check_rate_limit_or_raise(
            request,
            "delete_account",
            max_attempts=getattr(settings, "RATE_LIMIT_SENSITIVE_ATTEMPTS", 3),
            window_seconds=getattr(settings, "RATE_LIMIT_SENSITIVE_WINDOW", 3600),
        )

        try:
            await AuthService.adelete_account(
                request.user,
                current_password=payload.current_password,
            )
            return MessageResponse(
                message="Account deleted successfully. Please discard your tokens and close this session."
            )
        except ValueError as e:
            raise UnauthorizedException(str(e))

    # =========================================================================
    # Session
    # =========================================================================

    @http_post(
        "/me/logout",
        response=MessageResponse,
        summary="Logout (client-side)",
        description="Notify the server of logout. Client should discard JWT tokens.",
    )
    def logout(self, request: HttpRequest):
        logger.info(f"User logout: {request.user.email}")
        return MessageResponse(
            message="Logged out successfully. Please discard your tokens."
        )
