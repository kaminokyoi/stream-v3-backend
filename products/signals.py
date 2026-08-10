# products/signals.py

import logging

from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone
from dateutil.relativedelta import relativedelta

from .models import Profile, Account

logger = logging.getLogger(__name__)


@receiver(post_delete, sender=Profile)
def decrement_profile_count(sender, instance, **kwargs):
    instance.account.profiles -= 1
    instance.account.save()


# ---------------------------------------------------------------------------
# Access-change notifications (decoupled from model.save())
# When an Account email/password or a Profile code/number changes, notify
# the users linked via active subscriptions. Implemented via pre_save +
# post_save so the model stays free of notification concerns.
# ---------------------------------------------------------------------------

@receiver(pre_save, sender=Account)
def capture_account_access(sender, instance, **kwargs):
    """Remember previous email/password to detect access changes."""
    if instance.pk:
        try:
            old = Account.objects.get(pk=instance.pk)
            instance._old_access = (old.email, old.password)
        except Account.DoesNotExist:
            instance._old_access = None
    else:
        instance._old_access = None


@receiver(pre_save, sender=Account)
def normalize_account_fields(sender, instance, **kwargs):
    """Derive start_date, end_date, remaining_day on save (L2.21).

    Extracted from Account.save() so that the model's save() only persists
    the row and the business logic is isolated here for testability.
    """
    if instance.type == 'personal':
        instance.max_profile = 1
    if not instance.start_date and instance.end_date and instance.month_count:
        instance.start_date = instance.end_date - relativedelta(months=instance.month_count)
    if instance.start_date and instance.month_count:
        instance.end_date = instance.start_date + relativedelta(months=instance.month_count)
    if instance.end_date:
        delta = instance.end_date - timezone.now()
        instance.remaining_day = max(0, delta.days)


@receiver(post_save, sender=Account)
def notify_account_access_change(sender, instance, created, **kwargs):
    """Notify users linked to an account whose email/password changed."""
    old_access = getattr(instance, '_old_access', None)
    if not old_access:
        return
    if (old_access[0], old_access[1]) != (instance.email, instance.password):
        from notifications.tasks import send_access_update_notification
        from payments.models import Subscription
        user_ids = list(Subscription.objects.filter(
            profile__account=instance, status='active'
        ).values_list('user__id', flat=True).distinct())
        for uid in user_ids:
            send_access_update_notification.delay(uid)
        logger.info(f"Account {instance.pk} access changed, notified {len(user_ids)} users")


@receiver(pre_save, sender=Profile)
def capture_profile_access(sender, instance, **kwargs):
    """Remember previous code/number to detect access changes."""
    if instance.pk:
        try:
            old = Profile.objects.get(pk=instance.pk)
            instance._old_access = (old.code, old.number)
        except Profile.DoesNotExist:
            instance._old_access = None
    else:
        instance._old_access = None


@receiver(post_save, sender=Profile)
def notify_profile_access_change(sender, instance, created, **kwargs):
    """Notify users linked to a profile whose code/number changed."""
    old_access = getattr(instance, '_old_access', None)
    if not old_access:
        return
    if (old_access[0], old_access[1]) != (instance.code, instance.number):
        from notifications.tasks import send_access_update_notification
        from payments.models import Subscription
        user_ids = list(Subscription.objects.filter(
            profile=instance, status='active'
        ).values_list('user__id', flat=True).distinct())
        for uid in user_ids:
            send_access_update_notification.delay(uid, instance.account.platform)
        logger.info(f"Profile {instance.pk} access changed, notified {len(user_ids)} users")
