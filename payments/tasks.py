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

    Idempotent tracking via notified_j3 / notified_j / notified_j1 booleans.
    Each notification is sent at most once per subscription lifetime. Flags
    are reset to False on renewal/extension (see _reset_notification_flags).

    Windows:
      J-3 : expiration_date in [today, today+3] → warn
      J   : expiration_date ≤ today              → notify
      J+1 : expiration_date < yesterday           → notify + mark expired
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
    counts = {'j3': 0, 'j': 0, 'j1': 0}

    # ── J-3 : warn 3 days before expiration ──────────────────────────
    subs_j3 = (
        Subscription.objects
        .filter(status='active', notified_j3=False, expiration_date__date__lte=today + timedelta(days=3),
                expiration_date__date__gt=today, user__email__isnull=False)
        .exclude(user__email='')
        .select_related('user', 'order', 'profile')
    )
    j3_ids = []
    for sub in subs_j3:
        notify_expiring_soon(sub)
        j3_ids.append(sub.id)
    if j3_ids:
        Subscription.objects.filter(id__in=j3_ids).update(notified_j3=True)
    counts['j3'] = len(j3_ids)

    # ── J : notify on expiration day ─────────────────────────────────
    subs_j = (
        Subscription.objects
        .filter(notified_j=False, expiration_date__date__lte=today, user__email__isnull=False)
        .exclude(user__email='')
        .select_related('user', 'order', 'profile')
    )
    j_ids = []
    for sub in subs_j:
        notify_expiration_today(sub)
        j_ids.append(sub.id)
    if j_ids:
        Subscription.objects.filter(id__in=j_ids).update(notified_j=True)
    counts['j'] = len(j_ids)

    # ── J+1 : notify + mark expired ──────────────────────────────────
    subs_j1 = (
        Subscription.objects
        .filter(notified_j1=False, expiration_date__date__lt=today, user__email__isnull=False)
        .exclude(user__email='')
        .select_related('user', 'order', 'profile')
    )
    j1_ids = []
    for sub in subs_j1:
        notify_subscription_expired(sub)
        j1_ids.append(sub.id)
    if j1_ids:
        Subscription.objects.filter(id__in=j1_ids).update(notified_j1=True, status='expired')
    counts['j1'] = len(j1_ids)

    logger.info(
        f"Expiration check: {counts['j3']} J-3 warnings, "
        f"{counts['j']} expiring today, {counts['j1']} expired"
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
