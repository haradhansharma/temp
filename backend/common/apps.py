from django.apps import AppConfig


class CommonConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'common'

    def ready(self):
        """Import signals so Django registers the receivers.

        Signals for ``ServiceCredential`` lifecycle events (CORS cache
        invalidation, audit logging) are defined in ``common/signals.py``.
        Importing the module at app ready-time ensures Django wires them.
        """
        # pylint: disable=import-outside-toplevel, unused-import
        import common.signals  # noqa: F401