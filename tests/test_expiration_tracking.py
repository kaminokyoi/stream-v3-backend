"""Tests for the idempotent subscription notification tracking system."""
from datetime import timedelta
from django.utils import timezone
from unittest.mock import patch

import pytest


@pytest.mark.django_db
def test_expiration_j3_notification_sets_flag(user, make_subscription):
    """J-3 notification sets notified_j3=True — should not re-send."""
    expiration = timezone.now() + timedelta(days=2)
    sub = make_subscription(expiration=expiration, status='active')
    user.email = 'test@example.com'
    user.save()
    sub.refresh_from_db()

    from payments.tasks import check_expiring_subscriptions_task
    with patch('notifications.services._send_email') as mock_email, \
         patch('notifications.services._push_user'):
        check_expiring_subscriptions_task()
        assert mock_email.call_count == 1

    sub.refresh_from_db()
    assert sub.notified_j3 is True

    # Second run should NOT re-send
    with patch('notifications.services._send_email') as mock_email2, \
         patch('notifications.services._push_user'):
        check_expiring_subscriptions_task()
        assert mock_email2.call_count == 0


@pytest.mark.django_db
def test_expiration_j_notification_sets_flag(user, make_subscription):
    """J notification sets notified_j=True — should not re-send."""
    expiration = timezone.now()
    sub = make_subscription(expiration=expiration, status='active')
    user.email = 'test@example.com'
    user.save()
    sub.refresh_from_db()

    from payments.tasks import check_expiring_subscriptions_task
    with patch('notifications.services._send_email') as mock_email, \
         patch('notifications.services._push_user'):
        check_expiring_subscriptions_task()
        assert mock_email.call_count >= 1

    sub.refresh_from_db()
    assert sub.notified_j is True

    # Second run should NOT re-send J notification
    with patch('notifications.services._send_email') as mock_email2, \
         patch('notifications.services._push_user'):
        check_expiring_subscriptions_task()
        assert mock_email2.call_count == 0


@pytest.mark.django_db
def test_expiration_j1_marks_expired(user, make_subscription):
    """J+1 notification marks subscription as expired."""
    expiration = timezone.now() - timedelta(days=2)
    sub = make_subscription(expiration=expiration, status='active')
    user.email = 'test@example.com'
    user.save()
    sub.refresh_from_db()

    from payments.tasks import check_expiring_subscriptions_task
    with patch('notifications.services._send_email'), \
         patch('notifications.services._push_user'):
        check_expiring_subscriptions_task()

    sub.refresh_from_db()
    assert sub.notified_j1 is True
    assert sub.status == 'expired'


@pytest.mark.django_db
def test_renewal_resets_notification_flags(user, make_subscription, make_order):
    """Renewing a subscription resets all notified_* flags to False."""
    expiration = timezone.now() - timedelta(days=1)
    sub = make_subscription(expiration=expiration, status='expired')
    sub.notified_j3 = True
    sub.notified_j = True
    sub.notified_j1 = True
    sub.save()

    from payments.services import PaymentCompletionService
    from payments.models import Order

    order = Order.objects.create(
        user=user,
        platform=sub.order.platform,
        duration='1 mois',
        type='mutual',
        price=2500,
        status='completed',
        motif='renewal',
        renewal_from=sub,
        purchase_date=sub.expiration_date,
    )

    service = PaymentCompletionService()
    with patch('notifications.services.notify_subscription_renewed'):
        result = service.process_validate_payment(order)

    sub.refresh_from_db()
    assert sub.notified_j3 is False
    assert sub.notified_j is False
    assert sub.notified_j1 is False
    assert sub.status == 'active'


@pytest.mark.django_db
def test_skip_subs_without_email(user, make_subscription):
    """Subs without email should be skipped (no crash)."""
    expiration = timezone.now() + timedelta(days=2)
    sub = make_subscription(expiration=expiration, status='active')
    user.email = ''
    user.save()

    from payments.tasks import check_expiring_subscriptions_task
    with patch('notifications.services._send_email') as mock_email:
        check_expiring_subscriptions_task()
        assert mock_email.call_count == 0
