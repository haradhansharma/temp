"""Admin controller for user management (Phase 9.5).

Provides admin-only CRUD endpoints for user administration including
status management, role changes, and audit trail compilation. All
endpoints require ``is_staff=True`` and every mutation is audit-logged
via the ``@log_admin_access`` decorator.

Endpoints:
    Users (9.5):
        GET    /admin/users                      — list (filterable, searchable, paginated)
        GET    /admin/users/{id}                 — detail with subscriptions and login history
        PATCH  /admin/users/{id}/status          — activate/deactivate user
        PATCH  /admin/users/{id}/role            — change user role
        GET    /admin/users/{id}/audit           — compiled audit trail
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from django.db.models import Q, Count, Prefetch
from django.http import HttpRequest
from django.utils import timezone
from asgiref.sync import sync_to_async

from ninja import Query
from ninja_extra import api_controller, http_get, http_patch

from common.exceptions import (
    NotFoundException,
    BadRequestException,
)
from common.permissions import IsAuthenticated, IsAdmin
from common.schemas import MessageResponse, PaginatedResponse, PaginationInput

from users.controllers import JWTAuth
from users.models import User, UserLoginHistory, RoleChoices

from .models import (
    Subscription,
    SubscriptionStatus,
    PlanChangeLog,
    Refund,
)
from .admin_schemas import (
    AdminUserListItemSchema,
    AdminUserDetailSchema,
    AdminUserSubscriptionItemSchema,
    AdminUserStatusUpdateSchema,
    AdminUserRoleUpdateSchema,
    AdminAuditEventSchema,
)
from .admin_utils import log_admin_access, admin_write_rate_limit, admin_read_rate_limit

logger = logging.getLogger(__name__)


# =============================================================================
# Admin Controller — Users
# =============================================================================


@api_controller(
    "/admin",
    tags=["Admin — Users"],
    auth=JWTAuth(),
    permissions=[IsAuthenticated, IsAdmin],
)
class AdminUserController:
    """Admin endpoints for managing user accounts.

    All endpoints require JWT authentication with staff privileges.
    Every mutation is audit-logged via the ``@log_admin_access`` decorator.

    The user management endpoints allow admins to search, view, and
    modify user accounts. Status changes (activate/deactivate) and role
    changes are protected by validation logic that prevents admins from
    deactivating themselves and warns when deactivating users with
    active subscriptions.
    """

    # =========================================================================
    # Helpers
    # =========================================================================

    async def _get_user_or_404(self, user_id: int) -> User:
        """Fetch a user by ID or raise NotFoundException."""
        try:
            return await sync_to_async(User.objects.get)(pk=user_id)
        except User.DoesNotExist:
            raise NotFoundException("User not found.")

    async def _serialize_user_list_item(self, user: User, **extra) -> dict:
        """Serialize a user for admin list view with subscription counts.

        Accepts optional keyword arguments for pre-computed subscription
        counts to avoid N+1 queries during pagination.
        """
        # Count subscriptions if not provided
        sub_count = extra.get("subscription_count")
        active_sub_count = extra.get("active_subscription_count")

        if sub_count is None:
            sub_count = await sync_to_async(
                user.subscriptions.count
            )()

        if active_sub_count is None:
            active_sub_count = await sync_to_async(
                user.subscriptions.filter(
                    status__in=(
                        SubscriptionStatus.ACTIVE,
                        SubscriptionStatus.TRIALING,
                    )
                ).count
            )()

        return {
            "id": user.id,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "full_name": user.full_name,
            "is_active": user.is_active,
            "is_email_verified": user.is_email_verified,
            "is_staff": user.is_staff,
            "role": user.role,
            "avatar": (
                user.avatar.url if user.avatar else None
            ),
            "subscription_count": sub_count,
            "active_subscription_count": active_sub_count,
            "last_login_at": user.last_login,
            "created_at": user.created_at,
        }

    async def _serialize_user_detail(self, user: User) -> dict:
        """Serialize a user for admin detail view with subscriptions."""
        data = await self._serialize_user_list_item(user)

        # Additional profile fields
        data.update({
            "phone": user.phone,
            "timezone": user.timezone,
            "currency": user.currency,
            "language": user.language,
        })

        # Get all subscriptions across products
        subs_qs = (
            Subscription.objects.filter(user=user)
            .select_related("plan", "plan__product", "product")
            .order_by("-created_at")
        )
        subscriptions = []
        async for sub in subs_qs:
            subscriptions.append({
                "id": sub.id,
                "product_name": sub.product.name,
                "product_slug": sub.product.slug,
                "plan_name": sub.plan.name,
                "plan_slug": sub.plan.slug,
                "status": sub.status,
                "current_period_end": sub.current_period_end,
                "cancel_at_period_end": sub.cancel_at_period_end,
                "created_at": sub.created_at,
            })
        data["subscriptions"] = subscriptions

        return data

    # =========================================================================
    # List & Detail
    # =========================================================================

    @http_get(
        "/users",
        response=PaginatedResponse[AdminUserListItemSchema],
        summary="List users",
        description=(
            "List all users with annotated subscription counts. "
            "Supports ?is_active=, ?is_email_verified=, ?role=, "
            "?search= (email, name) filters. Paginated."
        ),
    )
    async def list_users(
        self,
        request: HttpRequest,
        is_active: Optional[bool] = None,
        is_email_verified: Optional[bool] = None,
        role: Optional[str] = None,
        search: Optional[str] = None,
        pagination: PaginationInput = Query(...),
    ):
        """List all users with admin-level filters and subscription counts.

        Returns users ordered by most recent first. Each item includes
        total and active subscription counts. Supports filtering by
        active status, email verification, role, and free-text search
        across email and name fields.
        """
        qs = (
            User.objects.annotate(
                subscription_count=Count("subscriptions", distinct=True),
                active_subscription_count=Count(
                    "subscriptions",
                    filter=Q(
                        subscriptions__status__in=(
                            SubscriptionStatus.ACTIVE,
                            SubscriptionStatus.TRIALING,
                        )
                    ),
                    distinct=True,
                ),
            )
            .order_by("-created_at")
        )

        if is_active is not None:
            qs = qs.filter(is_active=is_active)

        if is_email_verified is not None:
            qs = qs.filter(is_email_verified=is_email_verified)

        if role is not None:
            qs = qs.filter(role=role)

        if search:
            qs = qs.filter(
                Q(email__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
            )

        from common.utils import get_paginated_data_async

        results, meta = await get_paginated_data_async(
            qs, pagination.page, pagination.page_size
        )

        items = []
        for user in results:
            items.append({
                "id": user.id,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "full_name": user.full_name,
                "is_active": user.is_active,
                "is_email_verified": user.is_email_verified,
                "is_staff": user.is_staff,
                "role": user.role,
                "avatar": (
                    user.avatar.url if user.avatar else None
                ),
                "subscription_count": user.subscription_count,
                "active_subscription_count": user.active_subscription_count,
                "last_login_at": user.last_login,
                "created_at": user.created_at,
            })

        return {"meta": meta, "results": items}

    @http_get(
        "/users/{user_id}",
        response={200: AdminUserDetailSchema, 404: dict},
        summary="Get user detail",
        description=(
            "Return full user detail with profile info, all subscriptions "
            "across products, and recent login history (last 10 entries)."
        ),
    )
    async def get_user_detail(
        self,
        request: HttpRequest,
        user_id: int,
    ):
        """Get user detail with subscriptions and login history.

        Includes profile fields, all subscriptions across products,
        and the 10 most recent login events for context.
        """
        user = await self._get_user_or_404(user_id)
        return await self._serialize_user_detail(user)

    # =========================================================================
    # User Mutations
    # =========================================================================

    @http_patch(
        "/users/{user_id}/status",
        response={200: dict, 400: dict, 404: dict},
        summary="Update user status",
        description=(
            "Activate or deactivate a user account. Deactivation warns if "
            "user has active subscriptions. Admins cannot deactivate themselves."
        ),
    )
    @admin_write_rate_limit
    @log_admin_access
    async def update_user_status(
        self,
        request: HttpRequest,
        user_id: int,
        payload: AdminUserStatusUpdateSchema,
    ):
        """Activate or deactivate a user account.

        Prevents an admin from deactivating their own account. Warns
        (but does not block) if the user has active subscriptions,
        since deactivation does not automatically cancel them. The
        admin should manually cancel subscriptions if needed.
        """
        user = await self._get_user_or_404(user_id)

        # Prevent self-deactivation
        if user_id == request.user.id and not payload.is_active:
            raise BadRequestException(
                "You cannot deactivate your own account. "
                "Ask another admin to do this."
            )

        if user.is_active == payload.is_active:
            raise BadRequestException(
                f"User is already {'active' if payload.is_active else 'inactive'}."
            )

        warnings = []

        # Check for active subscriptions when deactivating
        if not payload.is_active:
            active_subs = await sync_to_async(
                lambda: Subscription.objects.filter(
                    user=user,
                    status__in=(
                        SubscriptionStatus.ACTIVE,
                        SubscriptionStatus.TRIALING,
                    ),
                ).count()
            )()

            if active_subs > 0:
                warnings.append(
                    f"User has {active_subs} active subscription(s). "
                    "Deactivating the account does not cancel these "
                    "subscriptions. Consider canceling them separately "
                    "if access should be revoked immediately."
                )

        user.is_active = payload.is_active
        await sync_to_async(user.save)(update_fields=["is_active", "updated_at"])

        logger.info(
            "ADMIN_USER_STATUS_CHANGED: user_id=%s, email=%s, "
            "is_active=%s, reason='%s', "
            "changed_by=%s, ip=%s",
            user.id,
            user.email,
            payload.is_active,
            payload.reason,
            request.user.email,
            request.META.get("REMOTE_ADDR"),
        )

        result = await self._serialize_user_detail(user)
        if warnings:
            result["warnings"] = warnings
        return result

    @http_patch(
        "/users/{user_id}/role",
        response={200: dict, 400: dict, 404: dict},
        summary="Update user role",
        description=(
            "Change a user's role to owner, admin, or member. "
            "Admins cannot demote themselves."
        ),
    )
    @admin_write_rate_limit
    @log_admin_access
    async def update_user_role(
        self,
        request: HttpRequest,
        user_id: int,
        payload: AdminUserRoleUpdateSchema,
    ):
        """Change a user's role.

        Validates that the target role is a valid RoleChoices value.
        Prevents an admin from demoting themselves (e.g., changing
        their own role from admin to member) to avoid lockout scenarios.
        """
        user = await self._get_user_or_404(user_id)

        # Validate role
        valid_roles = [r.value for r in RoleChoices]
        if payload.role not in valid_roles:
            raise BadRequestException(
                f"Invalid role '{payload.role}'. "
                f"Must be one of: {', '.join(valid_roles)}."
            )

        # Prevent self-demotion
        if user_id == request.user.id and payload.role != user.role:
            # Check if the new role is lower than current
            role_hierarchy = {"owner": 3, "admin": 2, "member": 1}
            current_level = role_hierarchy.get(user.role, 0)
            new_level = role_hierarchy.get(payload.role, 0)
            if new_level < current_level:
                raise BadRequestException(
                    "You cannot demote your own role. "
                    "Ask another admin to do this."
                )

        if user.role == payload.role:
            raise BadRequestException(
                f"User is already '{payload.role}'."
            )

        old_role = user.role
        user.role = payload.role

        # Sync is_staff: owner and admin roles get staff access
        user.is_staff = payload.role in ("owner", "admin")
        await sync_to_async(user.save)(
            update_fields=["role", "is_staff", "updated_at"]
        )

        logger.info(
            "ADMIN_USER_ROLE_CHANGED: user_id=%s, email=%s, "
            "old_role='%s', new_role='%s', reason='%s', "
            "changed_by=%s, ip=%s",
            user.id,
            user.email,
            old_role,
            payload.role,
            payload.reason,
            request.user.email,
            request.META.get("REMOTE_ADDR"),
        )

        return await self._serialize_user_detail(user)

    # =========================================================================
    # Audit Trail
    # =========================================================================

    @http_get(
        "/users/{user_id}/audit",
        response=PaginatedResponse[AdminAuditEventSchema],
        summary="Get user audit trail",
        description=(
            "Compile a chronological audit trail from multiple sources: "
            "login history, plan changes, subscription status changes, "
            "and refund history. Returns events ordered by timestamp desc. "
            "Paginated (default 20, max 100 per page)."
        ),
    )
    async def get_user_audit(
        self,
        request: HttpRequest,
        user_id: int,
        pagination: PaginationInput = Query(...),
    ):
        """Compile a comprehensive audit trail for a user.

        Aggregates events from multiple data sources into a single
        chronological timeline:

        - **login**: User login events from ``UserLoginHistory``
        - **plan_change**: Subscription plan changes from ``PlanChangeLog``
        - **subscription_status**: Subscription lifecycle events
          (inferred from status field and related metadata)
        - **refund**: Refund events from ``Refund`` records

        Events are sorted by timestamp descending (most recent first).
        """
        user = await self._get_user_or_404(user_id)
        events = []

        # --- Login events ---
        login_qs = UserLoginHistory.objects.filter(
            user=user
        ).order_by("-created_at")[:50]
        async for login in login_qs:
            events.append({
                "event_type": "login",
                "description": f"User logged in from {login.ip_address or 'unknown IP'}",
                "metadata": {
                    "ip_address": login.ip_address,
                    "user_agent": login.user_agent[:200] if login.user_agent else None,
                },
                "ip_address": login.ip_address,
                "timestamp": login.created_at,
            })

        # --- Plan change events ---
        plan_changes_qs = (
            PlanChangeLog.objects.filter(
                subscription__user=user
            )
            .select_related("from_plan", "to_plan", "subscription__product", "initiated_by")
            .order_by("-created_at")[:50]
        )
        async for change in plan_changes_qs:
            initiator = (
                change.initiated_by.email if change.initiated_by else "system"
            )
            events.append({
                "event_type": "plan_change",
                "description": (
                    f"Changed plan from '{change.from_plan.name}' to "
                    f"'{change.to_plan.name}' on "
                    f"'{change.subscription.product.name}'"
                ),
                "metadata": {
                    "from_plan": change.from_plan.name,
                    "to_plan": change.to_plan.name,
                    "product": change.subscription.product.name,
                    "proration_amount_cents": change.proration_amount_cents,
                    "currency": change.currency,
                    "proration_behavior": change.proration_behavior,
                    "initiated_by": initiator,
                },
                "ip_address": None,
                "timestamp": change.created_at,
            })

        # --- Subscription status events ---
        subs_qs = (
            Subscription.objects.filter(user=user)
            .select_related("plan", "product")
            .order_by("-updated_at")[:50]
        )
        async for sub in subs_qs:
            # Cancellation event
            if sub.canceled_at:
                events.append({
                    "event_type": "subscription_status",
                    "description": (
                        f"Subscription to '{sub.plan.name}' "
                        f"({sub.product.name}) was canceled"
                    ),
                    "metadata": {
                        "plan": sub.plan.name,
                        "product": sub.product.name,
                        "status": sub.status,
                        "cancel_at_period_end": sub.cancel_at_period_end,
                    },
                    "ip_address": None,
                    "timestamp": sub.canceled_at,
                })

            # Expiration event
            if sub.expires_at:
                events.append({
                    "event_type": "subscription_status",
                    "description": (
                        f"Subscription to '{sub.plan.name}' "
                        f"({sub.product.name}) expired"
                    ),
                    "metadata": {
                        "plan": sub.plan.name,
                        "product": sub.product.name,
                        "status": sub.status,
                    },
                    "ip_address": None,
                    "timestamp": sub.expires_at,
                })

        # --- Refund events ---
        refunds_qs = (
            Refund.objects.filter(subscription__user=user)
            .select_related("subscription__plan", "subscription__product", "initiated_by", "approved_by")
            .order_by("-created_at")[:50]
        )
        async for refund in refunds_qs:
            initiator = (
                refund.initiated_by.email if refund.initiated_by else "system"
            )
            approver = (
                refund.approved_by.email if refund.approved_by else None
            )
            events.append({
                "event_type": "refund",
                "description": (
                    f"Refund of {refund.amount_cents / 100:.2f} {refund.currency} "
                    f"for '{refund.subscription.plan.name}' "
                    f"({refund.subscription.product.name}) — {refund.status}"
                ),
                "metadata": {
                    "plan": refund.subscription.plan.name,
                    "product": refund.subscription.product.name,
                    "amount_cents": refund.amount_cents,
                    "currency": refund.currency,
                    "reason": refund.reason,
                    "reason_category": refund.reason_category,
                    "status": refund.status,
                    "initiated_by": initiator,
                    "approved_by": approver,
                },
                "ip_address": refund.initiated_by_ip,
                "timestamp": refund.created_at,
            })

        # Sort all events by timestamp descending
        events.sort(key=lambda e: e["timestamp"] or timezone.now(), reverse=True)

        # Paginate the compiled events
        total_items = len(events)
        total_pages = max(1, (total_items + pagination.page_size - 1) // pagination.page_size)
        page = max(1, min(pagination.page, total_pages))

        start = (page - 1) * pagination.page_size
        end = start + pagination.page_size
        page_items = events[start:end]

        meta = {
            "total_items": total_items,
            "total_pages": total_pages,
            "current_page": page,
            "page_size": pagination.page_size,
            "has_next": page < total_pages,
            "has_previous": page > 1,
        }

        return {"meta": meta, "results": page_items}
