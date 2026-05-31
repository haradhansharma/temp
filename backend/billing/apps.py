from django.apps import AppConfig


class BillingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'billing'
    def ready(self):
        """HIGH-01: Validate Stripe keys are configured at startup.

        Raises ImproperlyConfigured if any critical Stripe key is missing
        in a non-debug environment. In DEBUG mode, missing keys are logged
        as warnings to allow local development without Stripe credentials.
        """
        import logging
        from django.conf import settings
        from django.core.exceptions import ImproperlyConfigured

        logger = logging.getLogger(__name__)

        # In tests or management commands, settings may not be fully loaded
        if not hasattr(settings, 'STRIPE_SECRET_KEY'):
            return

        critical_keys = {
            'STRIPE_SECRET_KEY': settings.STRIPE_SECRET_KEY,
            'STRIPE_PUBLISHABLE_KEY': settings.STRIPE_PUBLISHABLE_KEY,
        }

        for key_name, value in critical_keys.items():
            if not value:
                if getattr(settings, 'DEBUG', False):
                    logger.warning(
                        f"HIGH-01: {key_name} is not set. "
                        f"Stripe features will not work."
                    )
                else:
                    raise ImproperlyConfigured(
                        f"HIGH-01: {key_name} must be set in production. "
                        f"Set the corresponding environment variable and restart."
                    )

        # Webhook secret is critical for security — always warn
        if not getattr(settings, 'STRIPE_WEBHOOK_SECRET', None):
            if getattr(settings, 'DEBUG', False):
                logger.warning(
                    "HIGH-01: STRIPE_WEBHOOK_SECRET is not set. "
                    "Webhook signature verification will fail."
                )
            else:
                raise ImproperlyConfigured(
                    "HIGH-01: STRIPE_WEBHOOK_SECRET must be set in production. "
                    "Without it, webhook signatures cannot be verified, "
                    "allowing forged events."
                )
