# backend/base/celery.py

from __future__ import absolute_import, unicode_literals
import os
from celery import Celery

# from celery.schedules import crontab, solar
# from datetime import timedelta
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "base.settings")
app = Celery("base")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
app.conf.task_track_started = True
app.conf.worker_send_task_events = True


app.conf.beat_schedule = {
    # F5/I2: Retry failed webhook events every 6 hours
    "reconcile-webhooks-every-6-hours": {
        "task": "billing.tasks.reconcile_webhooks",
        "schedule": crontab(minute=0, hour="*/6"),  # Every 6 hours
        "args": (24,),  # max_age_hours
    },
    # F8/F10: Sync Stripe customer data to local profiles daily
    "sync-customer-data-daily": {
        "task": "billing.tasks.sync_customer_data",
        "schedule": crontab(minute=30, hour=3),  # 3:30 AM UTC daily
    },
    # Dunning: Process past_due subscriptions daily
    "dunning-retry-daily": {
        "task": "billing.tasks.dunning_retry",
        "schedule": crontab(minute=0, hour=4),  # 4:00 AM UTC daily
    },
    # Currency: Fetch exchange rates daily (before customer sync)
    "update-exchange-rates-daily": {
        "task": "billing.tasks.update_exchange_rates",
        "schedule": crontab(minute=0, hour=3),  # 3:00 AM UTC daily
    },
    # CRIT-02: Revenue recognition — daily at 2:30 AM UTC
    "recognize-revenue-daily": {
        "task": "billing.tasks.recognize_revenue",
        "schedule": crontab(minute=30, hour=2),  # 2:30 AM UTC daily
    },
    # CRIT-02: Cleanup stale webhook events — weekly Sunday at 5 AM UTC
    "cleanup-stale-webhook-events-weekly": {
        "task": "billing.tasks.cleanup_stale_webhook_events",
        "schedule": crontab(minute=0, hour=5, day_of_week="sunday"),  # Weekly Sunday
        "args": (90,),  # retention_days
    },
    # Cleanup expired auth tokens every day at 3 AM UTC
    # "cleanup-expired-tokens": {
    #     "task": "common.tasks.cleanup_expired_tokens",
    #     "schedule": crontab(hour=3, minute=0),
    # },
    # 'task-every-30-minutes': {
    #     'task': 'myapp.tasks.some_task',w
    #     'schedule': 1800.0,  # 30 minutes
    # },
    # 'task-every-5-seconds': {
    #     'task': 'myapp.tasks.some_task',
    #     'schedule': 5.0,  # 5 seconds
    # },
    # 'task-at-sunrise': {
    #     'task': 'myapp.tasks.some_task',
    #     'schedule': solar('sunrise', latitude=40.7128, longitude=-74.0060),
    # },
    # 'task-at-sunset': {
    #     'task': 'myapp.tasks.some_task',
    #     'schedule': solar('sunset', latitude=40.7128, longitude=-74.0060),
    # },
    # 'custom-schedule-task': {
    #     'task': 'myapp.tasks.some_task',
    #     'schedule': timedelta(days=1, hours=2, minutes=30),  # Every 1 day, 2 hours, and 30 minutes
    # },
}
