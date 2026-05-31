"""Utility functions for the common app.

Provides both synchronous and asynchronous pagination helpers for use
with Django's ORM. Use async versions in async controller/service methods
to avoid blocking the event loop.
"""

import math
from typing import Any, List, Tuple, TypeVar

from django.db import models

T = TypeVar("T")


def get_paginated_data(
    queryset: models.QuerySet, page: int, page_size: int
) -> Tuple[List[Any], dict]:
    """Paginate a Django queryset and return results with metadata.

    Args:
        queryset: The Django queryset to paginate.
        page: Current page number (1-indexed).
        page_size: Number of items per page.

    Returns:
        A tuple of (results_list, metadata_dict).
    """
    total_items = queryset.count()
    total_pages = math.ceil(total_items / page_size) if total_items > 0 else 1

    # Clamp page to valid range
    page = max(1, min(page, total_pages))

    offset = (page - 1) * page_size
    results = list(queryset[offset : offset + page_size])

    meta = {
        "total_items": total_items,
        "total_pages": total_pages,
        "current_page": page,
        "page_size": page_size,
        "has_next": page < total_pages,
        "has_previous": page > 1,
    }

    return results, meta


async def get_paginated_data_async(
    queryset: models.QuerySet, page: int, page_size: int
) -> Tuple[List[Any], dict]:
    """Async version of get_paginated_data().

    Uses Django's async ORM methods (acount, async iteration) so the event
    loop is not blocked while waiting for database I/O.

    Args:
        queryset: The Django queryset to paginate.
        page: Current page number (1-indexed).
        page_size: Number of items per page.

    Returns:
        A tuple of (results_list, metadata_dict).

    Example::

        @http_get("/list")
        async def list_items(self, request, pagination: PaginationInput = Query(...)):
            qs = Item.objects.all().order_by("-created_at")
            results, meta = await get_paginated_data_async(qs, pagination.page, pagination.page_size)
            return {"meta": meta, "results": results}
    """
    total_items = await queryset.acount()
    total_pages = math.ceil(total_items / page_size) if total_items > 0 else 1

    # Clamp page to valid range
    page = max(1, min(page, total_pages))

    offset = (page - 1) * page_size
    paginated_qs = queryset[offset : offset + page_size]

    # Evaluate the queryset asynchronously
    results = [item async for item in paginated_qs.aiterator()]

    meta = {
        "total_items": total_items,
        "total_pages": total_pages,
        "current_page": page,
        "page_size": page_size,
        "has_next": page < total_pages,
        "has_previous": page > 1,
    }

    return results, meta


def generate_api_key() -> tuple:
    """Generate a new service API key.

    Returns a tuple of (raw_key, prefix, sha256_hash).

    - ``raw_key`` is shown ONCE to the admin at creation time. It cannot
      be recovered after that.
    - ``prefix`` (first 12 chars) is stored for identification in logs
      and admin displays.
    - ``hash`` is the SHA-256 digest stored in the database for lookup.

    Format: ``sb_live_<43 chars from token_urlsafe(32)>``
    Total length: 50 characters.

    Example::
        sb_live_a1BcD2eF3gH4iJ5kL6mN7oP8qR9sT0uV1wX2yZ3A4bC5dE6fG7hI
    """
    import hashlib
    import secrets

    raw = f"sb_live_{secrets.token_urlsafe(32)}"
    prefix = raw[:12]
    key_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return raw, prefix, key_hash
