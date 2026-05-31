from typing import TypeVar, Generic, Optional, List, Any
from datetime import datetime
from ninja import Schema, ModelSchema
from pydantic import Field, ConfigDict


T = TypeVar("T")


# --- Pagination ---


class PaginationInput(Schema):
    """Schema for pagination input parameters."""

    page: int = Field(1, ge=1, description="Page number (1-indexed)")
    page_size: int = Field(20, ge=1, le=100, description="Items per page (max 100)")


class PaginationMeta(Schema):
    """Metadata for paginated responses."""

    total_items: int = Field(..., description="Total number of items")
    total_pages: int = Field(..., description="Total number of pages")
    current_page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Items per page")
    has_next: bool = Field(..., description="Whether next page exists")
    has_previous: bool = Field(..., description="Whether previous page exists")


class PaginatedResponse(Schema, Generic[T]):
    """Generic paginated response wrapper."""

    meta: PaginationMeta
    results: List[T]


# --- Message Responses ---


class MessageResponse(Schema):
    """Standard success message response."""

    message: str
    success: bool = True


class ErrorResponse(Schema):
    """Standard error response."""

    detail: str
    code: Optional[str] = None


# --- Service Domain Option (for admin dropdown) ---


class ServiceDomainOptionSchema(Schema):
    """Lightweight schema for populating the admin create-key dropdown.

    Returns a flat list of active service domains with their parent
    product name, so the admin can pick which domain to create a key for.
    """

    id: int
    domain: str = Field(..., description="Service domain, e.g. 'finance.sattabase.tld'")
    product_name: str = Field(..., description="Parent product display name")
    is_active: bool


# --- Service Credential / API Key Schemas ---


class ApiKeyCreateInputSchema(Schema):
    """Input schema for creating a new service API key."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Human-readable name for the credential",
    )
    service_domain_id: int = Field(
        ...,
        description="ID of the ServiceDomain this credential is for",
    )


class ApiKeyOutputSchema(Schema):
    """Output schema for API key listing (never includes the raw key)."""

    id: int
    name: str
    api_key_prefix: str
    service_domain_id: int
    service_domain: str
    permissions: dict = {}
    is_active: bool
    last_used_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    created_by: Optional[str] = None


class ApiKeyCreateOutputSchema(Schema):
    """Output schema for API key creation (includes the raw key ONCE)."""

    id: int
    name: str
    api_key_prefix: str
    raw_api_key: str = Field(
        ...,
        description="The raw API key. Store it securely — this is the only time it is shown.",
    )
    service_domain_id: int
    service_domain: str
    is_active: bool
    created_at: Optional[datetime] = None
    warning: str = Field(
        "Save this API key now. It cannot be recovered after this response.",
        description="Security warning",
    )


class ApiKeyRotateOutputSchema(Schema):
    """Output schema for API key rotation (includes the new raw key ONCE)."""

    id: int
    name: str
    old_prefix: str = Field(
        ...,
        description="Prefix of the old (now revoked) API key",
    )
    new_api_key: str = Field(
        ...,
        description="The new raw API key. Store it securely — this is the only time it is shown.",
    )
    new_prefix: str
    service_domain_id: int
    service_domain: str
    is_active: bool
    warning: str = Field(
        "Save this new API key now. The old key is immediately revoked and cannot be recovered.",
        description="Security warning",
    )


# --- Analytics Schemas (C6) ---


class ApiKeyUsageDaySchema(Schema):
    """Single day of API key usage."""

    date: str = Field(..., description="Date in YYYY-MM-DD format")
    requests: int = Field(..., description="Number of API requests on this day")


class ApiKeyAnalyticsResponse(Schema):
    """Response schema for API key usage analytics."""

    credential_id: int
    api_key_prefix: str
    service_domain: str
    period_days: int
    total_requests: int
    daily_usage: List[ApiKeyUsageDaySchema] = []


class ApiKeyAnalyticsOverviewSchema(Schema):
    """Response schema for aggregated analytics across all credentials."""

    total_requests: int = Field(
        ..., description="Total requests across all credentials in the period"
    )
    period_days: int = Field(
        ..., description="Number of days in the analysis period"
    )
    credentials: dict = Field(
        default={},
        description="Map of credential_id → total requests",
    )
