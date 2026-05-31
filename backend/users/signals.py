"""Django signals for the users app."""

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import User


@receiver(post_save, sender=User)
def user_post_save(sender, instance: User, created: bool, **kwargs):
    if created:
        import logging

        logger = logging.getLogger(__name__)
        logger.info(f"New user created: id={instance.id}, email={instance.email}")
