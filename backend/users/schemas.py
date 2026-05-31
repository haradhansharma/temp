"""Pydantic schemas for the users app.

These schemas define the request/response contracts for all user-related API
endpoints. They enforce validation and provide automatic OpenAPI documentation.
"""

import re
from typing import Optional, Literal
from ninja import Schema, ModelSchema
from pydantic import Field, field_validator, model_validator

from .models import User, RoleChoices, TimezoneChoices, CurrencyChoices, LanguageChoices


# =============================================================================
# Shared Validators
# =============================================================================


def _validate_password_strength(v: str) -> str:
    """Validate password meets minimum strength requirements.

    Requirements:
    - At least 8 characters (enforced by min_length)
    - At least 1 uppercase letter
    - At least 1 lowercase letter
    - At least 1 digit
    - At least 1 special character
    """
    if not any(c.isupper() for c in v):
        raise ValueError("Password must contain at least one uppercase letter.")
    if not any(c.islower() for c in v):
        raise ValueError("Password must contain at least one lowercase letter.")
    if not any(c.isdigit() for c in v):
        raise ValueError("Password must contain at least one digit.")
    if not re.search(r'[!@#$%^&*(),.?":{}|<>_\-+=\[\]\\\/~`;\']', v):
        raise ValueError("Password must contain at least one special character.")
    return v


# =============================================================================
# Type Aliases for Choice Fields
# =============================================================================

RoleType = Literal[RoleChoices.OWNER, RoleChoices.ADMIN, RoleChoices.MEMBER]
TimezoneType = Literal[tuple(TimezoneChoices.values)]  # type: ignore
CurrencyType = Literal[tuple(CurrencyChoices.values)]  # type: ignore
LanguageType = Literal[tuple(LanguageChoices.values)]  # type: ignore


# =============================================================================
# Auth Schemas
# =============================================================================


class RegisterInputSchema(Schema):
    """Schema for user registration request."""

    email: str = Field(
        ...,
        max_length=255,
        description="User's email address (used as login)",
        examples=["user@example.com"],
    )
    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Password (min 8 chars, 1 uppercase, 1 lowercase, 1 digit, 1 special)",
        examples=["SecurePass123!"],
    )
    first_name: str = Field(
        ...,
        min_length=1,
        max_length=150,
        description="User's first name",
    )
    last_name: Optional[str] = Field(
        default="",
        max_length=150,
        description="User's last name",
    )
    timezone: TimezoneType = Field(
        default=TimezoneChoices.UTC,
        description="User's preferred timezone (IANA format)",
        examples=["UTC"],
    )
    currency: CurrencyType = Field(
        default=CurrencyChoices.USD,
        description="User's preferred currency (ISO 4217)",
        examples=["USD"],
    )
    language: LanguageType = Field(
        default=LanguageChoices.EN,
        description="User's preferred language (ISO 639-1)",
        examples=["en"],
    )

    @field_validator("email")
    @classmethod
    def email_must_be_lowercase(cls, v: str) -> str:
        return v.lower().strip()

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        return _validate_password_strength(v)


class LoginInputSchema(Schema):
    """Schema for email/password login request."""

    email: str = Field(
        ...,
        description="User's email address",
        examples=["user@example.com"],
    )
    password: str = Field(
        ...,
        description="User's password",
    )


class TokenOutputSchema(Schema):
    """Schema for JWT token pair response."""

    access: str = Field(..., description="Access token (short-lived)")
    refresh: str = Field(..., description="Refresh token (long-lived)")


class TokenRefreshInputSchema(Schema):
    """Schema for token refresh request."""

    refresh: str = Field(..., description="Refresh token")


class TokenVerifyInputSchema(Schema):
    """Schema for token verify request."""

    token: str = Field(..., description="Access token to verify")


class TokenBlacklistInputSchema(Schema):
    """Schema for token blacklist request."""

    refresh: str = Field(..., description="Refresh token to blacklist")


class AuthorizeOutputSchema(Schema):
    """Schema for authorization code response (cross-domain SSO)."""

    code: str = Field(..., description="One-time authorization code (expires in 30 seconds)")
    expires_in: int = Field(..., description="Code validity in seconds")


class TokenExchangeInputSchema(Schema):
    """Schema for exchanging an authorization code for JWT tokens."""

    code: str = Field(..., description="One-time authorization code received from /auth/authorize")


# =============================================================================
# Password Reset Schemas
# =============================================================================


class PasswordResetRequestSchema(Schema):
    """Schema for requesting a password reset."""

    email: str = Field(
        ...,
        max_length=255,
        description="Email address associated with the account",
        examples=["user@example.com"],
    )

    @field_validator("email")
    @classmethod
    def email_must_be_lowercase(cls, v: str) -> str:
        return v.lower().strip()


class PasswordResetConfirmSchema(Schema):
    """Schema for confirming a password reset with OTP."""

    email: str = Field(
        ...,
        max_length=255,
        description="Email address associated with the account",
        examples=["user@example.com"],
    )
    otp: str = Field(
        ...,
        min_length=6,
        max_length=6,
        description="6-digit OTP code received via email",
        examples=["123456"],
    )
    new_password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="New password (min 8 chars, 1 uppercase, 1 lowercase, 1 digit, 1 special)",
        examples=["NewSecurePass456!"],
    )
    confirm_password: str = Field(
        ...,
        description="Confirm new password",
    )

    @field_validator("email")
    @classmethod
    def email_must_be_lowercase(cls, v: str) -> str:
        return v.lower().strip()

    @field_validator("otp")
    @classmethod
    def otp_must_be_digits(cls, v: str) -> str:
        if not v.strip().isdigit():
            raise ValueError("OTP must be a 6-digit number.")
        return v.strip()

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        return _validate_password_strength(v)

    @model_validator(mode="after")
    def passwords_match(self):
        if self.new_password != self.confirm_password:
            raise ValueError("New password and confirm password do not match.")
        return self


# =============================================================================
# Sensitive Action — Re-Authentication Schemas
# =============================================================================


class PasswordConfirmSchema(Schema):
    """Schema for confirming user identity via current password.

    Used as a gate before sensitive operations like email change,
    account deletion, or security setting changes.
    """

    current_password: str = Field(
        ...,
        description="Current password to confirm identity",
    )


# =============================================================================
# Email Change Schemas (OTP-Based)
# =============================================================================


class ChangeEmailRequestSchema(Schema):
    """Schema for requesting an email change.

    Requires current password verification. A 6-digit OTP will be
    sent to the user's CURRENT email address.
    """

    current_password: str = Field(
        ...,
        description="Current password to confirm identity",
    )
    new_email: str = Field(
        ...,
        max_length=255,
        description="The new email address to change to",
        examples=["newemail@example.com"],
    )

    @field_validator("new_email")
    @classmethod
    def email_must_be_lowercase(cls, v: str) -> str:
        return v.lower().strip()


class ChangeEmailConfirmOTPSchema(Schema):
    """Schema for confirming an email change with OTP."""

    otp: str = Field(
        ...,
        min_length=6,
        max_length=6,
        description="6-digit verification code sent to your current email",
        examples=["123456"],
    )

    @field_validator("otp")
    @classmethod
    def otp_must_be_digits(cls, v: str) -> str:
        if not v.isdigit():
            raise ValueError("OTP must be a 6-digit number.")
        return v


class DeleteAccountRequestSchema(Schema):
    """Schema for requesting account deletion.

    Requires current password verification. The account will be soft-deleted.
    """

    current_password: str = Field(
        ...,
        description="Current password to confirm identity",
    )


# =============================================================================
# User Profile Schemas
# =============================================================================


class UserOutputSchema(ModelSchema):
    """Schema for user data in API responses."""

    full_name: str
    display_name: str

    class Meta:
        model = User
        fields = [
            "id",
            "slug",
            "email",
            "first_name",
            "last_name",
            "phone",
            "avatar",
            "timezone",
            "currency",
            "language",
            "is_email_verified",
            "is_active",
            "is_staff",
            "role",
            "created_at",
        ]


class UserProfileUpdateInputSchema(Schema):
    """Schema for updating user profile fields."""

    first_name: Optional[str] = Field(None, max_length=150)
    last_name: Optional[str] = Field(None, max_length=150)
    phone: Optional[str] = Field(None, max_length=30)
    timezone: Optional[TimezoneType] = Field(None, description="IANA timezone")
    currency: Optional[CurrencyType] = Field(None, description="ISO 4217 currency code")
    language: Optional[LanguageType] = Field(
        None, description="ISO 639-1 language code"
    )


class ChangePasswordInputSchema(Schema):
    """Schema for changing password (authenticated user)."""

    current_password: str = Field(..., description="Current password")
    new_password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="New password (min 8 chars, 1 uppercase, 1 lowercase, 1 digit, 1 special)",
    )
    confirm_password: str = Field(..., description="Confirm new password")

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        return _validate_password_strength(v)

    @model_validator(mode="after")
    def passwords_match(self):
        if self.new_password != self.confirm_password:
            raise ValueError("New password and confirm password do not match.")
        return self


# =============================================================================
# Email Verification (OTP) Schemas
# =============================================================================


class EmailVerifyRequestSchema(Schema):
    """Schema for requesting an email verification OTP."""

    email: str = Field(
        ...,
        max_length=255,
        description="Email address to send the verification code to",
        examples=["user@example.com"],
    )

    @field_validator("email")
    @classmethod
    def email_must_be_lowercase(cls, v: str) -> str:
        return v.lower().strip()


class EmailVerifyConfirmSchema(Schema):
    """Schema for confirming email verification with OTP."""

    email: str = Field(
        ...,
        max_length=255,
        description="The email address being verified",
        examples=["user@example.com"],
    )
    otp: str = Field(
        ...,
        min_length=6,
        max_length=6,
        description="6-digit verification code sent to email",
        examples=["123456"],
    )

    @field_validator("email")
    @classmethod
    def email_must_be_lowercase(cls, v: str) -> str:
        return v.lower().strip()

    @field_validator("otp")
    @classmethod
    def otp_must_be_digits(cls, v: str) -> str:
        if not v.isdigit():
            raise ValueError("OTP must be a 6-digit number.")
        return v


# =============================================================================
# Choices Schemas
# =============================================================================


class ChoiceItemSchema(Schema):
    """Single choice item (value + label)."""

    value: str
    label: str


class ChoicesSchema(Schema):
    """All field choices served to the frontend."""

    timezones: list[ChoiceItemSchema]
    currencies: list[ChoiceItemSchema]
    languages: list[ChoiceItemSchema]


# =============================================================================
# Message Schemas
# =============================================================================


class MessageSchema(Schema):
    """Standard message response."""

    message: str
    success: bool = True
