"""
Celery tasks for the payments app.

Subscription lifecycle automation: account remaining-days update,
expiration checks (with notifications), and stale-order cleanup.
"""
from celery import shared_task
from logging import getLogger

logger = getLogger(__name__)


@shared_task
def update_remaining_days():
    """Recalculate remaining_day for all active accounts (bulk)."""
    from products.models import Account
    from django.db.models import F
    from django.db.models.functions import Now
    from django.db.models import ExpressionWrapper, IntegerField
    from django.db.models import Case, When, Value

    accounts = Account.objects.filter(status='activate', end_date__isnull=False)
    count = accounts.count()
    if count == 0:
        return 0

    # Bulk update: calculate days remaining in SQL
    # remaining_day = max(0, (end_date - now).days)
    accounts.update(
        remaining_day=Case(
            When(end_date__gt=Now(), then=ExpressionWrapper(
                F('end_date__date') - Now(),
                output_field=IntegerField(),
            )),
            default=Value(0),
        )
    )
    logger.info(f"Bulk updated remaining days for {count} accounts")
    return count


@shared_task
def check_expiring_subscriptions_task():
    """Daily check of expiring/expired subscriptions + notifications.

    - 3 days before expiration -> warn
    - on expiration day      -> notify
    - already expired         -> notify + mark status='expired'
    """
    from datetime import timedelta
    from django.utils import timezone
    from payments.models import Subscription
    from notifications.services import (
        notify_expiring_soon,
        notify_expiration_today,
        notify_subscription_expired,
    )

    today = timezone.now().date()
    three_days_later = today + timedelta(days=3)
    counts = {'3_days': 0, 'today': 0, 'expired': 0}

    subs_3days = Subscription.objects.filter(
        status='active',
        expiration_date__date=three_days_later,
    ).select_related('user', 'order', 'profile')
    for sub in subs_3days:
        notify_expiring_soon(sub)
        counts['3_days'] += 1

    subs_today = Subscription.objects.filter(
        status__in=['active', 'expired'],
        expiration_date__date=today,
    ).select_related('user', 'order', 'profile')
    for sub in subs_today:
        notify_expiration_today(sub)
        counts['today'] += 1

    subs_expired = Subscription.objects.filter(
        status__in=['active', 'expired'],
        expiration_date__date__lt=today,
    ).select_related('user', 'order', 'profile')
    expired_ids = []
    for sub in subs_expired:
        notify_subscription_expired(sub)
        expired_ids.append(sub.id)
        counts['expired'] += 1

    # Bulk update instead of per-row save
    if expired_ids:
        Subscription.objects.filter(id__in=expired_ids).update(status='expired')

    logger.info(
        f"Expiration check: {counts['3_days']} 3-day warnings, "
        f"{counts['today']} expiring today, {counts['expired']} expired"
    )
    return counts


@shared_task
def delete_stale_pending_orders_task():
    """Delete orders stuck in 'pending_payment' for more than 24 hours."""
    from datetime import timedelta
    from django.utils import timezone
    from payments.models import Order

    cutoff_time = timezone.now() - timedelta(hours=24)
    logger.info(f"Cleaning up stale pending_payment orders created before {cutoff_time}")
    try:
        stale_orders = Order.objects.filter(status='pending_payment', purchase_date__lte=cutoff_time)
        count = stale_orders.count()
        if count > 0:
            deleted_count, _ = stale_orders.delete()
            logger.info(f"Deleted {deleted_count} stale pending_payment orders.")
            return deleted_count
        logger.info("No stale pending_payment orders found.")
        return 0
    except Exception as e:
        logger.error(f"Error cleaning up stale pending_payment orders: {e}")
        return False
