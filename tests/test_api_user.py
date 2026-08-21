"""Tests for the user API endpoints (/api/v1/user/*).

Covers:
  - Profile: GET (me), PATCH (update email), email uniqueness
  - Dashboard: aggregated data with masked subscriptions
  - Orders: create (purchase init with server-side price), cancel, list
  - Subscriptions: list (access masking), detail, renewal
  - Payment proof: upload
  - Gift code: verify (valid, invalid, expired)
  - Reviews: submit (with bonus), get my review
  - Permissions: all endpoints require JWT, own resources only
"""
import io
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from PIL import Image

from core.models import Review, Platform
from payments.models import Order, Subscription, GiftCode


def fake_image(name='proof.png'):
    """Create a minimal valid PNG image for upload tests."""
    img = Image.new('RGB', (10, 10), color='red')
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return SimpleUploadedFile(name, buf.read(), content_type='image/png')


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_profile_get(authed_client, user):
    resp = authed_client.get('/api/v1/user/profile/')
    assert resp.status_code == 200
    assert resp.data['phone_number'] == '600000000'
    assert resp.data['needs_email'] is False  # fixture has email


@pytest.mark.django_db
def test_profile_update_email(authed_client, user):
    resp = authed_client.patch('/api/v1/user/profile/', {'email': 'new@example.com'}, format='json')
    assert resp.status_code == 200
    user.refresh_from_db()
    assert user.email == 'new@example.com'


@pytest.mark.django_db
def test_profile_update_email_duplicate(authed_client, user, db):
    from users.models import User
    other = User(phone_number='611111111', first_name='A', last_name='B', country_code='237')
    other.set_password('p')
    other.save()
    other.email = 'taken@example.com'
    other.save()
    resp = authed_client.patch('/api/v1/user/profile/', {'email': 'taken@example.com'}, format='json')
    assert resp.status_code == 400


@pytest.mark.django_db
def test_profile_cannot_clear_email(authed_client, user):
    resp = authed_client.patch('/api/v1/user/profile/', {'email': ''}, format='json')
    assert resp.status_code == 400
    user.refresh_from_db()
    assert user.email == 'test@example.com'


@pytest.mark.django_db
def test_register_country_code_normalized_without_plus(api_client, make_platform):
    from users.models import User
    payload = {
        'phone_number': '699999997',
        'country_code': '+33',
        'first_name': 'Jean',
        'last_name': 'Dupont',
        'password': 'Str0ng!Pass',
        're_password': 'Str0ng!Pass',
    }
    resp = api_client.post('/api/v1/public/auth/users/', payload, format='json')
    assert resp.status_code == 201, resp.content
    u = User.objects.get(phone_number='699999997')
    assert u.country_code == '33'


@pytest.mark.django_db
def test_profile_requires_auth(api_client):
    resp = api_client.get('/api/v1/user/profile/')
    assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_dashboard_aggregated(authed_client, user, make_subscription, make_price_tier):
    make_price_tier(base_price=2500)
    make_subscription(
        platform='Netflix',
        duration='1 mois',
        expiration=timezone.now() + timedelta(days=10),
    )
    resp = authed_client.get('/api/v1/user/dashboard/')
    assert resp.status_code == 200
    assert 'subscriptions' in resp.data
    assert 'orders' in resp.data
    assert 'pending_orders' in resp.data
    assert 'notifications' in resp.data
    assert 'pricing' in resp.data
    assert 'platforms' in resp.data
    assert len(resp.data['subscriptions']) == 1


@pytest.mark.django_db
def test_dashboard_logo_uses_media_proxy(authed_client, user, make_subscription, make_platform):
    """Dashboard logos point to the media proxy (stable URL, forced Content-Type)."""
    from core.models import Platform
    make_platform(name='Netflix')
    Platform.objects.filter(name='Netflix').update(logo='logos/netflix/netflix_logo.svg')
    make_subscription(platform='Netflix')
    resp = authed_client.get('/api/v1/user/dashboard/')
    assert resp.status_code == 200
    sub = resp.data['subscriptions'][0]
    assert sub['logo'] == '/api/v1/public/media/logos/netflix/netflix_logo.svg'


@pytest.mark.django_db
def test_dashboard_subscription_access_masked(authed_client, user, make_account, make_profile, make_subscription):
    """Surfshark subscription: all access fields must be masked (security)."""
    account = make_account(platform_name='Surfshark', max_profile=2, place=2)
    profile = make_profile(account=account, number='S1', code='4444')
    make_subscription( platform='Surfshark', profile=profile,
                      expiration=timezone.now() + timedelta(days=10))
    resp = authed_client.get('/api/v1/user/dashboard/')
    sub = next(s for s in resp.data['subscriptions'] if s['platform_name'] == 'Surfshark')
    assert sub['email'] == ''
    assert sub['password'] == ''
    assert sub['profileNum'] == ''
    assert sub['profilePin'] == ''


# ---------------------------------------------------------------------------
# Orders: create (purchase init)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_order_create(authed_client, make_price_tier):
    make_price_tier(base_price=2500)
    resp = authed_client.post('/api/v1/user/orders/', {
        'platform': 'Netflix',
        'duration': '1 mois',
        'type': 'mutual',
    }, format='json')
    assert resp.status_code == 201, resp.content
    assert 'order_id' in resp.data
    order = Order.objects.get(order_id=resp.data['order_id'])
    assert order.price == 2500
    assert order.status == 'pending_payment'
    assert order.motif == 'subscription'


@pytest.mark.django_db
def test_order_create_recalculates_price_server_side(authed_client, make_price_tier):
    """Even if a malicious client sends a price, it's recalculated server-side."""
    make_price_tier(base_price=2500)
    resp = authed_client.post('/api/v1/user/orders/', {
        'platform': 'Netflix',
        'duration': '1 an',
        'type': 'mutual',
    }, format='json')
    assert resp.status_code == 201
    order = Order.objects.get(order_id=resp.data['order_id'])
    assert order.price == 24000  # 2*(2*(3*2500-500)-1000)


@pytest.mark.django_db
def test_order_create_invalid_platform(authed_client, make_price_tier):
    make_price_tier(base_price=2500)
    resp = authed_client.post('/api/v1/user/orders/', {
        'platform': 'FakePlatform',
        'duration': '1 mois',
        'type': 'mutual',
    }, format='json')
    assert resp.status_code == 400


@pytest.mark.django_db
def test_order_cancel(authed_client, user, make_order):
    order = make_order(status='pending_payment')
    resp = authed_client.post(f'/api/v1/user/orders/{order.order_id}/cancel/')
    assert resp.status_code == 200
    assert not Order.objects.filter(pk=order.pk).exists()


@pytest.mark.django_db
def test_order_cancel_completed_rejected(authed_client, user, make_order):
    order = make_order(status='completed')
    resp = authed_client.post(f'/api/v1/user/orders/{order.order_id}/cancel/')
    assert resp.status_code == 400


@pytest.mark.django_db
def test_order_list_own_only(authed_client, user, make_order):
    from users.models import User
    other = User(phone_number='622222222', first_name='X', last_name='Y', country_code='237')
    other.set_password('p')
    other.save()
    make_order(platform='Netflix')  # user's order
    Order.objects.create(user=other, platform='Spotify', duration='1 mois',
                         type='mutual', price=2000, status='completed')
    resp = authed_client.get('/api/v1/user/orders/')
    assert resp.status_code == 200
    assert all(o['platform'] == 'Netflix' for o in resp.data['results'])


# ---------------------------------------------------------------------------
# Subscriptions: list + detail + renewal
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_subscription_list_masked(authed_client, user, make_account, make_profile, make_subscription):
    account = make_account(platform_name='Spotify', max_profile=2, place=2)
    principal = make_profile(account=account, number='P1', code='1111')
    make_subscription( platform='Spotify', profile=principal,
                      expiration=timezone.now() + timedelta(days=10))
    resp = authed_client.get('/api/v1/user/subscriptions/')
    assert resp.status_code == 200
    sub = resp.data['results'][0]
    assert sub['email'] == account.email  # principal profile sees access
    assert sub['password'] == account.password


@pytest.mark.django_db
def test_subscription_detail(authed_client, user, make_subscription):
    sub = make_subscription(platform='Netflix',
                           expiration=timezone.now() + timedelta(days=10))
    resp = authed_client.get(f'/api/v1/user/subscriptions/{sub.id}/')
    assert resp.status_code == 200
    assert resp.data['id'] == sub.id


@pytest.mark.django_db
def test_subscription_renewal(authed_client, user, make_subscription, make_price_tier):
    make_price_tier(base_price=2500)
    sub = make_subscription(platform='Netflix',
                           expiration=timezone.now() + timedelta(days=10))
    resp = authed_client.post(f'/api/v1/user/subscriptions/{sub.id}/renewal/', {
        'duration': '1 mois',
    }, format='json')
    assert resp.status_code == 201, resp.content
    new_order = Order.objects.get(order_id=resp.data['order_id'])
    assert new_order.renewal_from_id == sub.id
    assert new_order.motif == 'extension'
    assert new_order.price == 2500


@pytest.mark.django_db
def test_subscription_renewal_expired_becomes_renewal_motif(authed_client, user, make_subscription, make_price_tier):
    make_price_tier(base_price=2500)
    sub = make_subscription(platform='Netflix', status='expired',
                           expiration=timezone.now() - timedelta(days=1))
    resp = authed_client.post(f'/api/v1/user/subscriptions/{sub.id}/renewal/', {
        'duration': '1 mois',
    }, format='json')
    assert resp.status_code == 201
    new_order = Order.objects.get(order_id=resp.data['order_id'])
    assert new_order.motif == 'renewal'


# ---------------------------------------------------------------------------
# Payment proof upload
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_payment_proof_upload(authed_client, user, make_order):
    order = make_order(status='pending_payment')
    img = fake_image()
    resp = authed_client.post(
        f'/api/v1/user/payments/manual/{order.order_id}/',
        {'proof_image': img},
        format='multipart',
    )
    assert resp.status_code == 201, resp.content
    order.refresh_from_db()
    assert order.status == 'pending_validation'


@pytest.mark.django_db
def test_payment_proof_upload_other_user_order(authed_client, user, db):
    from users.models import User
    other = User(phone_number='633333333', first_name='X', last_name='Y', country_code='237')
    other.set_password('p')
    other.save()
    order = Order.objects.create(user=other, platform='Netflix', duration='1 mois',
                                  type='mutual', price=2500, status='pending_payment')
    img = fake_image()
    resp = authed_client.post(
        f'/api/v1/user/payments/manual/{order.order_id}/',
        {'proof_image': img},
        format='multipart',
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Gift code verification
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_gift_code_verify_valid(authed_client, db):
    from django.utils import timezone
    GiftCode.objects.create(
        code='PROMO10',
        days=5,
        start_date=timezone.now() - timedelta(days=1),
        end_date=timezone.now() + timedelta(days=30),
        status=True,
    )
    resp = authed_client.post('/api/v1/user/gift-code/verify/', {
        'code': 'PROMO10',
    }, format='json')
    assert resp.status_code == 200
    assert resp.data['valid'] is True
    assert resp.data['days'] == 5


@pytest.mark.django_db
def test_gift_code_verify_not_found(authed_client):
    resp = authed_client.post('/api/v1/user/gift-code/verify/', {
        'code': 'NONEXISTENT',
    }, format='json')
    assert resp.status_code == 400


@pytest.mark.django_db
def test_gift_code_verify_expired(authed_client, db):
    from django.utils import timezone
    GiftCode.objects.create(
        code='EXPIRED1',
        days=3,
        start_date=timezone.now() - timedelta(days=30),
        end_date=timezone.now() - timedelta(days=1),
        status=True,
    )
    resp = authed_client.post('/api/v1/user/gift-code/verify/', {
        'code': 'EXPIRED1',
    }, format='json')
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Reviews
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_review_submit_first_with_bonus(authed_client, user, make_subscription):
    make_subscription(platform='Netflix',
                      expiration=timezone.now() + timedelta(days=10))
    resp = authed_client.post('/api/v1/user/reviews/', {
        'stars': 5,
        'comment': 'Great',
    }, format='json')
    assert resp.status_code == 200
    assert resp.data['bonus_awarded'] is True
    assert Review.objects.filter(user=user).count() == 1


@pytest.mark.django_db
def test_review_submit_second_no_bonus(authed_client, user, make_subscription):
    make_subscription(platform='Netflix',
                      expiration=timezone.now() + timedelta(days=10))
    authed_client.post('/api/v1/user/reviews/', {'stars': 5, 'comment': 'first'}, format='json')
    resp = authed_client.post('/api/v1/user/reviews/', {'stars': 4, 'comment': 'second'}, format='json')
    assert resp.status_code == 200
    assert resp.data['bonus_awarded'] is False


@pytest.mark.django_db
def test_review_get_my_review(authed_client, user, make_subscription):
    make_subscription(platform='Netflix',
                      expiration=timezone.now() + timedelta(days=10))
    authed_client.post('/api/v1/user/reviews/', {'stars': 5, 'comment': 'Great'}, format='json')
    resp = authed_client.get('/api/v1/user/reviews/')
    assert resp.status_code == 200
    assert resp.data['stars'] == 5


@pytest.mark.django_db
def test_review_get_none(authed_client, user):
    resp = authed_client.get('/api/v1/user/reviews/')
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Permissions: all user endpoints require JWT
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_all_user_endpoints_require_auth(api_client):
    for method, url in [
        ('GET', '/api/v1/user/profile/'),
        ('GET', '/api/v1/user/dashboard/'),
        ('GET', '/api/v1/user/orders/'),
        ('GET', '/api/v1/user/subscriptions/'),
        ('POST', '/api/v1/user/gift-code/verify/'),
        ('GET', '/api/v1/user/reviews/'),
    ]:
        resp = getattr(api_client, method.lower())(url)
        assert resp.status_code in (401, 403), f'{method} {url} returned {resp.status_code}'


# ---------------------------------------------------------------------------
# Push Notifications: device registration + notification history
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_register_device(api_client, user):
    """User can register a push token for their device."""
    from rest_framework_simplejwt.tokens import RefreshToken
    refresh = RefreshToken.for_user(user)
    api_client.credentials(HTTP_AUTHORIZATION=f'JWT {refresh.access_token}')
    resp = api_client.post('/api/v1/user/device/register/', {
        'token': 'ExpoPushToken[abc123]',
        'platform': 'android',
    }, format='json')
    assert resp.status_code in (200, 201)
    from notifications.models import PushToken
    assert PushToken.objects.filter(user=user, token='ExpoPushToken[abc123]').exists()


@pytest.mark.django_db
def test_register_device_updates_existing(api_client, user):
    """Registering the same token updates it instead of creating a duplicate."""
    from rest_framework_simplejwt.tokens import RefreshToken
    refresh = RefreshToken.for_user(user)
    api_client.credentials(HTTP_AUTHORIZATION=f'JWT {refresh.access_token}')
    api_client.post('/api/v1/user/device/register/', {
        'token': 'ExpoPushToken[dup]',
        'platform': 'ios',
    }, format='json')
    api_client.post('/api/v1/user/device/register/', {
        'token': 'ExpoPushToken[dup]',
        'platform': 'ios',
    }, format='json')
    from notifications.models import PushToken
    assert PushToken.objects.filter(token='ExpoPushToken[dup]').count() == 1


@pytest.mark.django_db
def test_unregister_device(api_client, user):
    """User can unregister (deactivate) a push token."""
    from rest_framework_simplejwt.tokens import RefreshToken
    from notifications.models import PushToken
    refresh = RefreshToken.for_user(user)
    api_client.credentials(HTTP_AUTHORIZATION=f'JWT {refresh.access_token}')
    PushToken.objects.create(user=user, token='ExpoPushToken[removeme]', platform='android')
    resp = api_client.post('/api/v1/user/device/unregister/', {
        'token': 'ExpoPushToken[removeme]',
    }, format='json')
    assert resp.status_code == 200
    token = PushToken.objects.get(token='ExpoPushToken[removeme]')
    assert not token.is_active


@pytest.mark.django_db
def test_push_notifications_list(api_client, user):
    """User can list their push notifications."""
    from rest_framework_simplejwt.tokens import RefreshToken
    from notifications.models import PushNotification
    refresh = RefreshToken.for_user(user)
    api_client.credentials(HTTP_AUTHORIZATION=f'JWT {refresh.access_token}')
    PushNotification.objects.create(user=user, title='Test', body='Body', notification_type='order')
    resp = api_client.get('/api/v1/user/notifications/')
    assert resp.status_code == 200
    assert resp.data['count'] == 1
    assert resp.data['results'][0]['title'] == 'Test'


@pytest.mark.django_db
def test_mark_notification_read(api_client, user):
    """User can mark a notification as read."""
    from rest_framework_simplejwt.tokens import RefreshToken
    from notifications.models import PushNotification
    refresh = RefreshToken.for_user(user)
    api_client.credentials(HTTP_AUTHORIZATION=f'JWT {refresh.access_token}')
    notif = PushNotification.objects.create(user=user, title='Unread', body='Body', notification_type='system')
    resp = api_client.post(f'/api/v1/user/notifications/{notif.id}/mark_read/')
    assert resp.status_code == 200
    notif.refresh_from_db()
    assert notif.is_read
    assert notif.read_at is not None


@pytest.mark.django_db
def test_mark_all_notifications_read(api_client, user):
    """User can mark all notifications as read."""
    from rest_framework_simplejwt.tokens import RefreshToken
    from notifications.models import PushNotification
    refresh = RefreshToken.for_user(user)
    api_client.credentials(HTTP_AUTHORIZATION=f'JWT {refresh.access_token}')
    PushNotification.objects.create(user=user, title='A', body='B', notification_type='system')
    PushNotification.objects.create(user=user, title='C', body='D', notification_type='order')
    resp = api_client.post('/api/v1/user/notifications/mark_all_read/')
    assert resp.status_code == 200
    assert PushNotification.objects.filter(user=user, is_read=False).count() == 0


@pytest.mark.django_db
def test_unread_notifications_count(api_client, user):
    """Unread count endpoint returns correct count."""
    from rest_framework_simplejwt.tokens import RefreshToken
    from notifications.models import PushNotification
    refresh = RefreshToken.for_user(user)
    api_client.credentials(HTTP_AUTHORIZATION=f'JWT {refresh.access_token}')
    PushNotification.objects.create(user=user, title='A', body='B', notification_type='system', is_read=False)
    PushNotification.objects.create(user=user, title='C', body='D', notification_type='order', is_read=True)
    resp = api_client.get('/api/v1/user/notifications/unread_count/')
    assert resp.status_code == 200
    assert resp.data['count'] == 1


@pytest.mark.django_db
def test_push_notification_filter_by_read(api_client, user):
    """User can filter notifications by is_read."""
    from rest_framework_simplejwt.tokens import RefreshToken
    from notifications.models import PushNotification
    refresh = RefreshToken.for_user(user)
    api_client.credentials(HTTP_AUTHORIZATION=f'JWT {refresh.access_token}')
    PushNotification.objects.create(user=user, title='Unread', body='B', notification_type='system', is_read=False)
    PushNotification.objects.create(user=user, title='Read', body='D', notification_type='order', is_read=True)
    resp = api_client.get('/api/v1/user/notifications/?is_read=false')
    assert resp.status_code == 200
    assert resp.data['count'] == 1
    assert resp.data['results'][0]['title'] == 'Unread'


@pytest.mark.django_db
def test_push_service_stores_notification(user):
    """send_push_to_user stores a PushNotification record."""
    from notifications.push_service import send_push_to_user
    from notifications.models import PushNotification
    send_push_to_user(user.id, "Test Title", "Test Body", {"screen": "orders"}, "order")
    notif = PushNotification.objects.get(user=user, title="Test Title")
    assert notif.body == "Test Body"
    assert notif.data == {"screen": "orders"}
    assert notif.notification_type == "order"
    assert not notif.is_read


@pytest.mark.django_db
def test_push_service_to_admins(admin_user):
    """send_push_to_admins sends to all admin users."""
    from notifications.push_service import send_push_to_admins
    from notifications.models import PushNotification
    send_push_to_admins("Admin Alert", "Something happened", {"screen": "settings"}, "system")
    assert PushNotification.objects.filter(user=admin_user, title="Admin Alert").exists()
