"""Business logic services for the users app.

Services encapsulate all business logic, keeping controllers thin and
testable. Controllers should only handle HTTP concerns (request parsing,
response formatting) and delegate to services.

Each service class provides both synchronous and asynchronous methods.
Use async methods in async controller endpoints to avoid blocking the
event loop.
"""

import logging
from typing import Optional

from asgiref.sync import sync_to_async
from django.contrib.auth import authenticate, get_user_model, hashers
from django.utils import timezone
from django.core.mail import send_mail

from .models import User, UserLoginHistory

logger = logging.getLogger(__name__)
UserModel = get_user_model()


# =============================================================================
# Auth Service
# =============================================================================


class AuthService:
    """Handles user authentication operations (registration, login, password management)."""

    @staticmethod
    def register_user(
        email: str,
        password: str,
        first_name: str,
        last_name: str = "",
        timezone: str = "UTC",
        currency: str = "USD",
        language: str = "en",
    ) -> User:
        """Register a new user account."""
        if UserModel.objects.email_exists(email):
            raise ValueError("A user with this email address already exists.")

        user = UserModel.objects.create_user(
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            timezone=timezone,
            currency=currency,
            language=language,
            is_active=True,
            is_email_verified=False,
        )
        logger.info(f"User registered: {user.email}")
        return user

    @staticmethod
    async def aregister_user(
        email: str,
        password: str,
        first_name: str,
        last_name: str = "",
        timezone: str = "UTC",
        currency: str = "USD",
        language: str = "en",
    ) -> User:
        """Async version of register_user()."""
        if await UserModel.objects.aemail_exists(email):
            raise ValueError("A user with this email address already exists.")

        user = await UserModel.objects.acreate_user(
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            timezone=timezone,
            currency=currency,
            language=language,
            is_active=True,
            is_email_verified=False,
        )
        logger.info(f"User registered (async): {user.email}")
        return user

    # =========================================================================
    # Login History
    # =========================================================================

    @staticmethod
    def record_login(
        user: User, ip_address: str = None, user_agent: str = ""
    ) -> UserLoginHistory:
        """Record a login event and update the user's last_login field."""
        from django.contrib.auth import update_session_auth_hash

        # Update Django's built-in last_login field
        user.last_login = timezone.now()
        user.last_login_ip = ip_address
        user.save(update_fields=["last_login", "last_login_ip"])

        # Create login history record
        history = UserLoginHistory.objects.create(
            user=user,
            ip_address=ip_address,
            user_agent=user_agent[:500],  # Truncate very long UAs
        )
        logger.info(
            f"Login recorded: user={user.email}, ip={ip_address}, history_id={history.id}"
        )
        return history

    @staticmethod
    async def arecord_login(
        user: User, ip_address: str = None, user_agent: str = ""
    ) -> UserLoginHistory:
        """Async version of record_login()."""
        # Update Django's built-in last_login field
        user.last_login = timezone.now()
        user.last_login_ip = ip_address
        await user.asave(update_fields=["last_login", "last_login_ip"])

        # Create login history record
        history = await UserLoginHistory.objects.acreate(
            user=user,
            ip_address=ip_address,
            user_agent=user_agent[:500],
        )
        logger.info(
            f"Login recorded (async): user={user.email}, ip={ip_address}, history_id={history.id}"
        )
        return history

    @staticmethod
    def authenticate_user(email: str, password: str) -> User:
        """Authenticate a user with email and password."""
        user = authenticate(request=None, username=email, password=password)

        if not user:
            raise ValueError("Invalid email or password.")

        if not user.is_active:
            raise ValueError("Your account is not active. Please contact support.")

        if user.is_deleted:
            raise ValueError("This account has been deactivated.")

        return user

    @staticmethod
    async def aauthenticate_user(email: str, password: str) -> User:
        """Async version of authenticate_user()."""
        user = await UserModel.objects.aget_by_email(email)

        if not user:
            raise ValueError("Invalid email or password.")

        if not hashers.check_password(password, user.password):
            raise ValueError("Invalid email or password.")

        if not user.is_active:
            raise ValueError("Your account is not active. Please contact support.")

        if user.is_deleted:
            raise ValueError("This account has been deactivated.")

        return user

    # =========================================================================
    # Password Change
    # =========================================================================

    @staticmethod
    def change_password(user: User, current_password: str, new_password: str) -> None:
        """Change a user's password. Requires current password."""
        if not user.check_password(current_password):
            raise ValueError("Current password is incorrect.")

        user.set_password(new_password)
        user.save(update_fields=["password"])
        logger.info(f"Password changed: user={user.email}")

    @staticmethod
    async def achange_password(
        user: User, current_password: str, new_password: str
    ) -> None:
        """Async version of change_password()."""
        if not user.check_password(current_password):
            raise ValueError("Current password is incorrect.")

        user.set_password(new_password)
        await user.asave(update_fields=["password"])
        logger.info(f"Password changed (async): user={user.email}")

    # =========================================================================
    # Password Reset (OTP-Based)
    # =========================================================================

    PASSWORD_RESET_OTP_PREFIX = "pwreset_otp"
    PASSWORD_RESET_ATTEMPTS_PREFIX = "pwreset_attempts"
    PASSWORD_RESET_OTP_EXPIRY = 600  # 10 minutes
    MAX_PASSWORD_RESET_ATTEMPTS = 5

    @staticmethod
    def _generate_otp() -> str:
        """Generate a cryptographically random 6-digit OTP (zero-padded string)."""
        import secrets

        return str(secrets.randbelow(1_000_000)).zfill(6)

    @classmethod
    def _get_pwreset_otp_cache_key(cls, email: str) -> str:
        return f"{cls.PASSWORD_RESET_OTP_PREFIX}:{email.lower().strip()}"

    @classmethod
    def _get_pwreset_attempts_cache_key(cls, email: str) -> str:
        return f"{cls.PASSWORD_RESET_ATTEMPTS_PREFIX}:{email.lower().strip()}"

    @classmethod
    async def arequest_password_reset(cls, email: str) -> None:
        """Request a password reset. Generates 6-digit OTP, sends via email."""
        email = email.lower().strip()
        try:
            user = await UserModel.objects.aget(
                email=email, is_active=True, is_deleted=False
            )
        except User.DoesNotExist:
            logger.warning(f"Password reset requested for non-existent email: {email}")
            # Still raise to trigger the 200 "sent" response in controller
            raise ValueError(
                "If an account with this email exists, a reset code has been sent."
            )

        otp = cls._generate_otp()
        cache_key = cls._get_pwreset_otp_cache_key(email)

        from django.core.cache import cache

        await sync_to_async(cache.set)(cache_key, otp, cls.PASSWORD_RESET_OTP_EXPIRY)

        # Reset attempt counter
        attempts_key = cls._get_pwreset_attempts_cache_key(email)
        await sync_to_async(cache.delete)(attempts_key)

        try:
            from django.conf import settings

            await sync_to_async(send_mail)(
                subject="Password Reset - Satta Ledger",
                message=(
                    f"You requested a password reset.\n\n"
                    f"Your verification code is: {otp}\n\n"
                    f"This code expires in 10 minutes.\n\n"
                    f"If you didn't request this, ignore this email."
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=True,
            )
        except Exception as e:
            logger.error(f"Failed to send password reset OTP: {e}")

        logger.info(f"Password reset OTP sent (async): user={user.email}")

    @classmethod
    async def aconfirm_password_reset(
        cls, email: str, otp: str, new_password: str
    ) -> None:
        """Confirm a password reset using OTP and set new password."""
        from django.core.cache import cache

        email = email.lower().strip()
        cache_key = cls._get_pwreset_otp_cache_key(email)
        attempts_key = cls._get_pwreset_attempts_cache_key(email)

        # Check attempt limit
        attempts = await sync_to_async(cache.get)(attempts_key, 0)
        if attempts >= cls.MAX_PASSWORD_RESET_ATTEMPTS:
            await sync_to_async(cache.delete)(cache_key)
            raise ValueError(
                "Too many failed attempts. Please request a new reset code."
            )

        # Get cached OTP
        cached_otp = await sync_to_async(cache.get)(cache_key)
        if not cached_otp:
            raise ValueError("Reset code has expired. Please request a new one.")

        # Validate OTP
        if otp.strip() != str(cached_otp):
            await sync_to_async(cache.set)(
                attempts_key, attempts + 1, cls.PASSWORD_RESET_OTP_EXPIRY
            )
            remaining = cls.MAX_PASSWORD_RESET_ATTEMPTS - (attempts + 1)
            raise ValueError(
                f"Invalid reset code. {remaining} attempt{'s' if remaining != 1 else ''} remaining."
            )

        # OTP correct — find user and reset password
        try:
            user = await UserModel.objects.aget(
                email=email, is_active=True, is_deleted=False
            )
        except User.DoesNotExist:
            raise ValueError("No account found with this email address.")

        user.set_password(new_password)

        # OTP verified → email ownership proven → mark verified if not already
        if not user.is_email_verified:
            user.is_email_verified = True
            update_fields = ["password", "is_email_verified"]
        else:
            update_fields = ["password"]

        await user.asave(update_fields=update_fields)

        # Clean up cache
        await sync_to_async(cache.delete)(cache_key)
        await sync_to_async(cache.delete)(attempts_key)

        logger.info(f"Password reset confirmed (async): user={user.email}, email_verified={user.is_email_verified}")

    # =========================================================================
    # Sensitive Actions — Identity Confirmation
    # =========================================================================

    @staticmethod
    def confirm_identity(user: User, current_password: str) -> None:
        """Verify the user's identity by checking their current password.

        This is a reusable gate for sensitive operations (email change,
        account deletion, etc.). Returns None on success, raises ValueError
        on failure.
        """
        if not user.check_password(current_password):
            raise ValueError("Current password is incorrect.")

    @staticmethod
    async def aconfirm_identity(user: User, current_password: str) -> None:
        """Async version of confirm_identity()."""
        if not user.check_password(current_password):
            raise ValueError("Current password is incorrect.")

    # =========================================================================
    # Email Change (OTP-Based)
    # =========================================================================

    EMAIL_CHANGE_CACHE_PREFIX = "email_change_data"
    EMAIL_CHANGE_ATTEMPTS_PREFIX = "email_change_attempts"
    EMAIL_CHANGE_OTP_EXPIRY = 600  # 10 minutes
    MAX_EMAIL_CHANGE_ATTEMPTS = 5

    @staticmethod
    async def aactivate_user(user: User) -> None:
        """Async version of activate_user()."""
        user.is_active = True
        user.is_email_verified = True
        await user.asave(update_fields=["is_active", "is_email_verified"])
        logger.info(f"User activated (async): {user.email}")

    @classmethod
    def request_email_change(
        cls, user: User, current_password: str, new_email: str
    ) -> None:
        """Request an email change after verifying current password.

        Generates a 6-digit OTP, stores OTP + new_email in cache,
        and sends OTP to the CURRENT email address.
        """
        if not user.check_password(current_password):
            raise ValueError("Current password is incorrect.")

        new_email = new_email.lower().strip()

        if user.email == new_email:
            raise ValueError("New email must be different from current email.")

        if UserModel.objects.email_exists(new_email):
            raise ValueError("An account with this email address already exists.")

        # Generate OTP
        otp = cls._generate_otp()

        # Store OTP + new_email in cache
        from django.core.cache import cache

        cache_key = f"{cls.EMAIL_CHANGE_CACHE_PREFIX}:{user.id}"
        cache.set(
            cache_key,
            {"otp": otp, "new_email": new_email},
            cls.EMAIL_CHANGE_OTP_EXPIRY,
        )

        # Reset attempt counter
        attempts_key = f"{cls.EMAIL_CHANGE_ATTEMPTS_PREFIX}:{user.id}"
        cache.delete(attempts_key)

        # Send OTP to CURRENT email
        try:
            from django.conf import settings

            send_mail(
                subject="Confirm Email Change - Satta Ledger",
                message=(
                    f"You requested to change your email to: {new_email}\n\n"
                    f"Your verification code is: {otp}\n\n"
                    f"This code expires in 10 minutes.\n\n"
                    f"If you didn't request this, ignore this email — your email will NOT be changed."
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=True,
            )
        except Exception as e:
            logger.error(f"Failed to send email change OTP: {e}")

        logger.info(f"Email change OTP sent: user={user.email} -> {new_email}")

    @classmethod
    async def arequest_email_change(
        cls, user: User, current_password: str, new_email: str
    ) -> None:
        """Async version of request_email_change()."""
        if not user.check_password(current_password):
            raise ValueError("Current password is incorrect.")

        new_email = new_email.lower().strip()

        if user.email == new_email:
            raise ValueError("New email must be different from current email.")

        if await UserModel.objects.aemail_exists(new_email):
            raise ValueError("An account with this email address already exists.")

        otp = cls._generate_otp()

        from django.core.cache import cache

        cache_key = f"{cls.EMAIL_CHANGE_CACHE_PREFIX}:{user.id}"
        await sync_to_async(cache.set)(
            cache_key,
            {"otp": otp, "new_email": new_email},
            cls.EMAIL_CHANGE_OTP_EXPIRY,
        )

        attempts_key = f"{cls.EMAIL_CHANGE_ATTEMPTS_PREFIX}:{user.id}"
        await sync_to_async(cache.delete)(attempts_key)

        try:
            from django.conf import settings

            await sync_to_async(send_mail)(
                subject="Confirm Email Change - Satta Ledger",
                message=(
                    f"You requested to change your email to: {new_email}\n\n"
                    f"Your verification code is: {otp}\n\n"
                    f"This code expires in 10 minutes.\n\n"
                    f"If you didn't request this, ignore this email — your email will NOT be changed."
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=True,
            )
        except Exception as e:
            logger.error(f"Failed to send email change OTP: {e}")

        logger.info(f"Email change OTP sent (async): user={user.email} -> {new_email}")

    @classmethod
    def confirm_email_change_otp(cls, user: User, otp: str) -> str:
        """Confirm an email change using OTP.

        Validates the OTP, checks attempts, applies the email change.
        Returns the new email address.
        """
        from django.core.cache import cache

        cache_key = f"{cls.EMAIL_CHANGE_CACHE_PREFIX}:{user.id}"
        attempts_key = f"{cls.EMAIL_CHANGE_ATTEMPTS_PREFIX}:{user.id}"

        # Check attempt limit
        attempts = cache.get(attempts_key, 0)
        if attempts >= cls.MAX_EMAIL_CHANGE_ATTEMPTS:
            cache.delete(cache_key)
            raise ValueError(
                "Too many failed attempts. Please request a new verification code."
            )

        # Get cached data
        cached = cache.get(cache_key)
        if not cached:
            raise ValueError("Verification code has expired. Please request a new one.")

        # Validate OTP
        if str(otp).strip() != str(cached["otp"]):
            cache.set(attempts_key, attempts + 1, cls.EMAIL_CHANGE_OTP_EXPIRY)
            remaining = cls.MAX_EMAIL_CHANGE_ATTEMPTS - (attempts + 1)
            raise ValueError(
                f"Invalid verification code. {remaining} attempt{'s' if remaining != 1 else ''} remaining."
            )

        new_email = cached["new_email"]

        # Double-check new email isn't taken
        if UserModel.objects.email_exists(new_email):
            cache.delete(cache_key)
            raise ValueError(
                "An account with this email address already exists. "
                "Please request a new email change."
            )

        # Apply the change
        old_email = user.email
        user.email = new_email
        user.is_email_verified = True
        user.save(update_fields=["email", "is_email_verified"])

        # Clean up cache
        cache.delete(cache_key)
        cache.delete(attempts_key)

        logger.info(f"Email changed via OTP: user={old_email} -> {new_email}")
        return new_email

    @classmethod
    async def aconfirm_email_change_otp(cls, user: User, otp: str) -> str:
        """Async version of confirm_email_change_otp()."""
        from django.core.cache import cache

        cache_key = f"{cls.EMAIL_CHANGE_CACHE_PREFIX}:{user.id}"
        attempts_key = f"{cls.EMAIL_CHANGE_ATTEMPTS_PREFIX}:{user.id}"

        attempts = await sync_to_async(cache.get)(attempts_key, 0)
        if attempts >= cls.MAX_EMAIL_CHANGE_ATTEMPTS:
            await sync_to_async(cache.delete)(cache_key)
            raise ValueError(
                "Too many failed attempts. Please request a new verification code."
            )

        cached = await sync_to_async(cache.get)(cache_key)
        if not cached:
            raise ValueError("Verification code has expired. Please request a new one.")

        if str(otp).strip() != str(cached["otp"]):
            await sync_to_async(cache.set)(
                attempts_key, attempts + 1, cls.EMAIL_CHANGE_OTP_EXPIRY
            )
            remaining = cls.MAX_EMAIL_CHANGE_ATTEMPTS - (attempts + 1)
            raise ValueError(
                f"Invalid verification code. {remaining} attempt{'s' if remaining != 1 else ''} remaining."
            )

        new_email = cached["new_email"]

        if await UserModel.objects.aemail_exists(new_email):
            await sync_to_async(cache.delete)(cache_key)
            raise ValueError(
                "An account with this email address already exists. "
                "Please request a new email change."
            )

        old_email = user.email
        user.email = new_email
        user.is_email_verified = True
        await user.asave(update_fields=["email", "is_email_verified"])

        await sync_to_async(cache.delete)(cache_key)
        await sync_to_async(cache.delete)(attempts_key)

        logger.info(f"Email changed via OTP (async): user={old_email} -> {new_email}")
        return new_email

    # =========================================================================
    # Email Verification (OTP-Based)
    # =========================================================================

    # Cache settings for OTP storage
    OTP_CACHE_PREFIX = "email_verify_otp"
    OTP_CACHE_ATTEMPTS_PREFIX = "email_verify_attempts"
    OTP_EXPIRY_SECONDS = 600  # 10 minutes
    MAX_OTP_ATTEMPTS = 5

    @staticmethod
    def _get_otp_cache_key(email: str) -> str:
        return f"{AuthService.OTP_CACHE_PREFIX}:{email.lower().strip()}"

    @staticmethod
    def _get_attempts_cache_key(email: str) -> str:
        return f"{AuthService.OTP_CACHE_ATTEMPTS_PREFIX}:{email.lower().strip()}"

    @classmethod
    def request_email_verification(cls, email: str) -> None:
        """Request an email verification OTP.

        Generates a 6-digit OTP, stores it in cache with expiry,
        and sends it via email.

        Args:
            email: The email address to verify.

        Raises:
            ValueError: If no account exists with this email.
        """
        try:
            user = UserModel.objects.get(email=email, is_active=True, is_deleted=False)
        except User.DoesNotExist:
            logger.warning(f"Email verify requested for non-existent email: {email}")
            raise ValueError("No account found with this email address.")

        if user.is_email_verified:
            raise ValueError("This email is already verified.")

        # Generate and store OTP in cache
        otp = cls._generate_otp()
        cache_key = cls._get_otp_cache_key(email)

        from django.core.cache import cache

        cache.set(cache_key, otp, cls.OTP_EXPIRY_SECONDS)

        # Reset attempt counter
        attempts_key = cls._get_attempts_cache_key(email)
        cache.delete(attempts_key)

        # Send OTP via email
        try:
            from django.conf import settings

            send_mail(
                subject="Verify Your Email - Satta Ledger",
                message=(
                    f"Your email verification code is: {otp}\n\n"
                    f"This code expires in 10 minutes.\n\n"
                    f"If you didn't request this, ignore this email."
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=True,
            )
        except Exception as e:
            logger.error(f"Failed to send email verification OTP: {e}")

        logger.info(f"Email verification OTP sent: user={user.email}")

    @classmethod
    async def arequest_email_verification(cls, email: str) -> None:
        """Async version of request_email_verification()."""
        try:
            user = await UserModel.objects.aget(
                email=email, is_active=True, is_deleted=False
            )
        except User.DoesNotExist:
            logger.warning(f"Email verify requested for non-existent email: {email}")
            raise ValueError("No account found with this email address.")

        if user.is_email_verified:
            raise ValueError("This email is already verified.")

        otp = cls._generate_otp()
        cache_key = cls._get_otp_cache_key(email)

        from django.core.cache import cache

        await sync_to_async(cache.set)(cache_key, otp, cls.OTP_EXPIRY_SECONDS)

        attempts_key = cls._get_attempts_cache_key(email)
        await sync_to_async(cache.delete)(attempts_key)

        try:
            from django.conf import settings

            await sync_to_async(send_mail)(
                subject="Verify Your Email - Satta Ledger",
                message=(
                    f"Your email verification code is: {otp}\n\n"
                    f"This code expires in 10 minutes.\n\n"
                    f"If you didn't request this, ignore this email."
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=True,
            )
        except Exception as e:
            logger.error(f"Failed to send email verification OTP: {e}")

        logger.info(f"Email verification OTP sent (async): user={user.email}")

    @classmethod
    def confirm_email_verification(cls, email: str, otp: str) -> None:
        """Confirm email verification using OTP.

        Validates the OTP against cached value, checks attempts limit,
        and marks the user as verified.

        Args:
            email: The email address being verified.
            otp: The 6-digit OTP code.

        Raises:
            ValueError: If OTP is invalid, expired, too many attempts, or user not found.
        """
        from django.core.cache import cache

        cache_key = cls._get_otp_cache_key(email)
        attempts_key = cls._get_attempts_cache_key(email)

        # Check attempt limit
        attempts = cache.get(attempts_key, 0)
        if attempts >= cls.MAX_OTP_ATTEMPTS:
            cache.delete(cache_key)  # Invalidate OTP after too many attempts
            raise ValueError(
                "Too many failed attempts. Please request a new verification code."
            )

        # Get cached OTP
        cached_otp = cache.get(cache_key)
        if not cached_otp:
            raise ValueError("Verification code has expired. Please request a new one.")

        # Validate OTP
        if str(otp).strip() != str(cached_otp):
            cache.set(attempts_key, attempts + 1, cls.OTP_EXPIRY_SECONDS)
            remaining = cls.MAX_OTP_ATTEMPTS - (attempts + 1)
            raise ValueError(
                f"Invalid verification code. {remaining} attempt{'s' if remaining != 1 else ''} remaining."
            )

        # OTP is correct — verify the user
        try:
            user = UserModel.objects.get(email=email, is_active=True, is_deleted=False)
        except User.DoesNotExist:
            raise ValueError("No account found with this email address.")

        if user.is_email_verified:
            # Already verified, just clean up cache
            cache.delete(cache_key)
            cache.delete(attempts_key)
            return

        user.is_email_verified = True
        user.save(update_fields=["is_email_verified"])

        # Clean up cache
        cache.delete(cache_key)
        cache.delete(attempts_key)

        logger.info(f"Email verified: user={user.email}")

    @classmethod
    async def aconfirm_email_verification(cls, email: str, otp: str) -> None:
        """Async version of confirm_email_verification()."""
        from django.core.cache import cache

        cache_key = cls._get_otp_cache_key(email)
        attempts_key = cls._get_attempts_cache_key(email)

        attempts = await sync_to_async(cache.get)(attempts_key, 0)
        if attempts >= cls.MAX_OTP_ATTEMPTS:
            await sync_to_async(cache.delete)(cache_key)
            raise ValueError(
                "Too many failed attempts. Please request a new verification code."
            )

        cached_otp = await sync_to_async(cache.get)(cache_key)
        if not cached_otp:
            raise ValueError("Verification code has expired. Please request a new one.")

        if str(otp).strip() != str(cached_otp):
            await sync_to_async(cache.set)(
                attempts_key, attempts + 1, cls.OTP_EXPIRY_SECONDS
            )
            remaining = cls.MAX_OTP_ATTEMPTS - (attempts + 1)
            raise ValueError(
                f"Invalid verification code. {remaining} attempt{'s' if remaining != 1 else ''} remaining."
            )

        try:
            user = await UserModel.objects.aget(
                email=email, is_active=True, is_deleted=False
            )
        except User.DoesNotExist:
            raise ValueError("No account found with this email address.")

        if user.is_email_verified:
            await sync_to_async(cache.delete)(cache_key)
            await sync_to_async(cache.delete)(attempts_key)
            return

        user.is_email_verified = True
        await user.asave(update_fields=["is_email_verified"])

        await sync_to_async(cache.delete)(cache_key)
        await sync_to_async(cache.delete)(attempts_key)

        logger.info(f"Email verified (async): user={user.email}")

    # =========================================================================
    # Cross-Domain SSO (Authorization Code Flow)
    # =========================================================================

    AUTH_CODE_CACHE_PREFIX = "sso_auth_code"
    AUTH_CODE_TTL = 30  # seconds
    AUTH_CODE_LENGTH = 48  # bytes of randomness

    @staticmethod
    async def agenerate_auth_code(user: "User") -> str:
        """Generate a one-time authorization code for cross-domain SSO.
        
        The code is stored in Redis with a 30-second TTL, mapped to the user's ID.
        The code can only be used once — it is deleted upon exchange.
        """
        import secrets
        from django.core.cache import cache
        
        code = secrets.token_urlsafe(AuthService.AUTH_CODE_LENGTH)
        cache_key = f"{AuthService.AUTH_CODE_CACHE_PREFIX}:{code}"
        # Store user_id and a hash of the user's current state for validation
        cache.set(cache_key, {"user_id": user.id, "is_active": user.is_active}, AuthService.AUTH_CODE_TTL)
        return code

    @staticmethod
    async def aexchange_auth_code(code: str) -> "User":
        """Exchange a one-time authorization code for the associated user.
        
        Validates the code exists in Redis, retrieves the user, and deletes the code
        (one-time use). Raises ValueError if code is invalid, expired, or user is inactive.
        """
        from django.core.cache import cache
        from .models import User
        
        cache_key = f"{AuthService.AUTH_CODE_CACHE_PREFIX}:{code}"
        code_data = cache.get(cache_key)
        
        if code_data is None:
            raise ValueError("Invalid or expired authorization code.")
        
        # Delete the code immediately (one-time use)
        cache.delete(cache_key)
        
        user_id = code_data.get("user_id")
        if not user_id:
            raise ValueError("Malformed authorization code.")
        
        user = await User.objects.filter(
            id=user_id, is_active=True, is_deleted=False
        ).afirst()
        
        if not user:
            raise ValueError("User not found or inactive.")
        
        if not user.is_email_verified:
            raise ValueError("Email not verified. Please verify your email first.")
        
        return user

    # =========================================================================
    # Account Deletion (Soft Delete)
    # =========================================================================

    @staticmethod
    def delete_account(user: User, current_password: str) -> None:
        """Soft-delete a user account after confirming current password.

        Uses the SoftDeleteModel.soft_delete() method which sets:
        - is_deleted = True
        - deleted_at = current timestamp

        Also sets is_active = False to prevent login.

        Args:
            user: The authenticated user.
            current_password: User's current password (identity confirmation).

        Raises:
            ValueError: If password is incorrect.
        """
        if not user.check_password(current_password):
            raise ValueError("Current password is incorrect.")

        # Use the SoftDeleteModel's soft_delete() method to properly set
        # is_deleted=True and deleted_at=now
        user.soft_delete()

        # Also deactivate the account to prevent authentication
        user.is_active = False
        user.save(update_fields=["is_active"])

        logger.info(f"Account soft-deleted: user={user.email}")

    @staticmethod
    async def adelete_account(user: User, current_password: str) -> None:
        """Async version of delete_account()."""
        if not user.check_password(current_password):
            raise ValueError("Current password is incorrect.")

        # Use the SoftDeleteModel's soft_delete() method
        user.soft_delete()

        # Also deactivate the account to prevent authentication
        user.is_active = False
        await user.asave(update_fields=["is_active"])

        logger.info(f"Account soft-deleted (async): user={user.email}")


# =============================================================================
# User Service
# =============================================================================


class UserService:
    """Handles user profile operations."""

    @staticmethod
    def get_user_by_id(user_id: int) -> User:
        """Get a user by ID. Filters out soft-deleted users."""
        try:
            return UserModel.objects.get(id=user_id, is_deleted=False)
        except User.DoesNotExist:
            raise ValueError("User not found.")

    @staticmethod
    async def aget_user_by_id(user_id: int) -> User:
        """Async version of get_user_by_id()."""
        try:
            return await UserModel.objects.aget(id=user_id, is_deleted=False)
        except User.DoesNotExist:
            raise ValueError("User not found.")

    @staticmethod
    def get_user_by_email(email: str) -> Optional[User]:
        """Get a user by email. Returns None if not found."""
        try:
            return UserModel.objects.get(email=email)
        except User.DoesNotExist:
            return None

    @staticmethod
    async def aget_user_by_email(email: str) -> Optional[User]:
        """Async version of get_user_by_email()."""
        try:
            return await UserModel.objects.aget(email=email)
        except User.DoesNotExist:
            return None

    @staticmethod
    def get_active_user_by_email(email: str) -> Optional[User]:
        """Get an active, non-deleted user by email."""
        try:
            return UserModel.objects.get(email=email, is_active=True, is_deleted=False)
        except User.DoesNotExist:
            return None

    @staticmethod
    async def aget_active_user_by_email(email: str) -> Optional[User]:
        """Async version of get_active_user_by_email()."""
        try:
            return await UserModel.objects.aget(
                email=email, is_active=True, is_deleted=False
            )
        except User.DoesNotExist:
            return None

    @staticmethod
    def get_user_by_slug(slug: str) -> Optional[User]:
        """Get a user by their public slug. Returns None if not found."""
        return UserModel.objects.filter(slug=slug, is_deleted=False).first()

    @staticmethod
    async def aget_user_by_slug(slug: str) -> Optional[User]:
        """Async version of get_user_by_slug()."""
        return await UserModel.objects.filter(slug=slug, is_deleted=False).afirst()

    @staticmethod
    def update_profile(user: User, **kwargs) -> User:
        """Update a user's profile fields. Only whitelisted fields allowed."""
        allowed_fields = [
            "first_name",
            "last_name",
            "phone",
            "timezone",
            "currency",
            "language",
        ]
        updated_fields = []
        for field, value in kwargs.items():
            if field in allowed_fields and value is not None:
                setattr(user, field, value)
                updated_fields.append(field)

        if updated_fields:
            user.save(update_fields=updated_fields)
            logger.info(f"Profile updated: user={user.email}, fields={updated_fields}")

        return user

    @staticmethod
    async def aupdate_profile(user: User, **kwargs) -> User:
        """Async version of update_profile()."""
        allowed_fields = [
            "first_name",
            "last_name",
            "phone",
            "timezone",
            "currency",
            "language",
        ]
        updated_fields = []
        for field, value in kwargs.items():
            if field in allowed_fields and value is not None:
                setattr(user, field, value)
                updated_fields.append(field)

        if updated_fields:
            await user.asave(update_fields=updated_fields)
            logger.info(
                f"Profile updated (async): user={user.email}, fields={updated_fields}"
            )

        return user
