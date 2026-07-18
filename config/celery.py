"""
Celery configuration for StreamPartner.
"""
import os
from celery import Celery
from celery.schedules import crontab
from logging import getLogger


logging = getLogger(__name__)

# Set the default Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('config')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django apps.
app.autodiscover_tasks()


app.conf.beat_schedule = {
    'update-account-remaining-days-daily': {
        'task': 'payments.tasks.update_remaining_days',
        'schedule': crontab(hour=0, minute=0),
    },
    'check-expiring-subscriptions-daily': {
        'task': 'payments.tasks.check_expiring_subscriptions_task',
        'schedule': crontab(hour=8, minute=0),
    },
    'send-weekly-analytics-report': {
        'task': 'dashboard.tasks.send_report_email_task',
        'schedule': crontab(hour=8, minute=0, day_of_week='monday'),
    },
    'send-monthly-analytics-report': {
        'task': 'dashboard.tasks.send_report_email_end_of_month_task',
        'schedule': crontab(hour=23, minute=30, day_of_month='28-31'),
    },
    'delete-stale-pending-payment-orders-daily': {
        'task': 'payments.tasks.delete_stale_pending_orders_task',
        'schedule': crontab(hour=0, minute=15),
    },
    'check-expiring-cards-daily': {
        'task': 'notifications.tasks.check_expiring_cards_task',
        'schedule': crontab(hour=0, minute=30),
    },
}

@app.task(bind=True, ignore_result=True)
def debug_task(self):
    logging.info(f"Request: {self.request!r}")
    print(f'Request: {self.request!r}')
