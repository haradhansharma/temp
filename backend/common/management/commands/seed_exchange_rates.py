"""Django management command to fetch and seed exchange rates.

Usage:
    python manage.py seed_exchange_rates

Fetches live rates from the configured API (default: open.er-api.com)
and upserts them into the ExchangeRate table.  Safe to run multiple
times — it uses update_or_create so existing rows are updated.

Typical workflow:
    1. Run this command after initial deploy / migration
    2. Set up the Celery beat schedule for daily auto-refresh
    3. Rates are cached in the DB so the conversion API never hits
       the external service at request time.
"""

from django.core.management.base import BaseCommand

from billing.currency_service import update_exchange_rates


class Command(BaseCommand):
    help = (
        "Fetch exchange rates from the configured API and seed the "
        "ExchangeRate table.  Run this once after migration and then "
        "let the Celery task keep them updated daily."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--base",
            type=str,
            default=None,
            help=(
                "Override BASE_CURRENCY for this run "
                "(e.g. --base=EUR).  Default: settings.BASE_CURRENCY or USD."
            ),
        )

    def handle(self, *args, **options):
        base_override = options.get("base")
        if base_override:
            from django.conf import settings

            settings.BASE_CURRENCY = base_override.upper()

        self.stdout.write("Fetching exchange rates from API...")
        try:
            result = update_exchange_rates()
            self.stdout.write(
                self.style.SUCCESS(
                    f"Done. {result['updated']} rates upserted, "
                    f"{result['skipped']} skipped.  Base: {result['base']}"
                )
            )
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f"Failed to fetch rates: {exc}"))
            raise
