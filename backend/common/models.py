from django.db import models


class TimeStampedModel(models.Model):
    """Abstract base model that provides created_at and updated_at timestamps."""

    created_at = models.DateTimeField(
        auto_now_add=True,
        editable=False,
        db_index=True,
        verbose_name="Created At",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        editable=False,
        db_index=True,
        verbose_name="Updated At",
    )

    class Meta:
        abstract = True


class SoftDeleteModel(models.Model):
    """Abstract base model that provides soft delete functionality.

    Instead of permanently deleting records, marks them as deleted
    with a timestamp. Use `soft_delete()` and `restore()` methods.
    """

    is_deleted = models.BooleanField(
        default=False, db_index=True, verbose_name="Is Deleted"
    )
    deleted_at = models.DateTimeField(
        null=True, blank=True, editable=False, verbose_name="Deleted At"
    )

    class Meta:
        abstract = True

    def soft_delete(self):
        from django.utils import timezone

        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(update_fields=["is_deleted", "deleted_at"])

    def restore(self):
        self.is_deleted = False
        self.deleted_at = None
        self.save(update_fields=["is_deleted", "deleted_at"])


class ActivatorModel(models.Model):
    """Abstract base model that provides is_active status tracking."""

    is_active = models.BooleanField(
        default=True, db_index=True, verbose_name="Is Active"
    )
    activated_at = models.DateTimeField(
        null=True, blank=True, editable=False, verbose_name="Activated At"
    )

    class Meta:
        abstract = True

    def activate(self):
        from django.utils import timezone

        self.is_active = True
        self.activated_at = timezone.now()
        self.save(update_fields=["is_active", "activated_at"])

    def deactivate(self):
        self.is_active = False
        self.save(update_fields=["is_active"])
