"""Django admin configuration for the users app."""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User, UserLoginHistory
from .models import RoleChoices, TimezoneChoices, CurrencyChoices, LanguageChoices


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    fieldsets = BaseUserAdmin.fieldsets + (
        (
            "Profile",
            {
                "fields": (
                    "phone",
                    "avatar",
                    "timezone",
                    "currency",
                    "language",
                )
            },
        ),
        ("Authentication Status", {"fields": ("is_email_verified", "last_login_ip")}),
        ("SaaS", {"fields": ("role",)}),
        ("Soft Delete", {"fields": ("is_deleted", "deleted_at")}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "first_name",
                    "last_name",
                    "password1",
                    "password2",
                ),
            },
        ),
    )

    list_display = (
        "email",
        "slug",
        "first_name",
        "last_name",
        "is_email_verified",
        "is_active",
        "is_staff",
        "role",
        "timezone",
        "currency",
        "created_at",
    )
    list_filter = (
        "is_email_verified",
        "is_active",
        "is_staff",
        "is_deleted",
        "role",
        "timezone",
        "currency",
        "language",
        "created_at",
    )
    search_fields = ("email", "first_name", "last_name", "slug")
    ordering = ("-created_at",)
    readonly_fields = (
        "slug",
        "created_at",
        "updated_at",
        "last_login",
        "last_login_ip",
        "deleted_at",
    )

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return self.readonly_fields + ("email",)
        return self.readonly_fields


@admin.register(UserLoginHistory)
class UserLoginHistoryAdmin(admin.ModelAdmin):
    """Admin configuration for user login history records."""

    list_display = (
        "user",
        "ip_address",
        "created_at",
    )
    list_filter = ("created_at",)
    search_fields = ("user__email", "ip_address", "user_agent")
    readonly_fields = ("user", "ip_address", "user_agent", "created_at")
    ordering = ("-created_at",)

    def has_add_permission(self, request):
        """Disable manual creation — login records are auto-created on login."""
        return False

    def has_change_permission(self, request, obj=None):
        """Login history is immutable — no editing allowed."""
        return False
