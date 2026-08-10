"""Tests for the admin API endpoints (/api/v1/admin/*).

Covers:
  - Permissions: requires JWT + is_superuser
  - Dashboard: stats + chart data
  - Users: list, create, CRUD, CSV export/import
  - Orders: list
  - Proofs: validate (activate), validate-only, reject
  - Subscriptions: list, change profile, unlink, renew, mark/unmark, history, toggle, mark-expired
  - Accounts: list, create, renew
  - Profiles: list, create
  - Platforms + Price tiers
  - FAQ, Reviews, Gift codes, Payment numbers
  - Messaging: notifications + messages CRUD + send
  - Download-image utility
"""
import io
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import Platform, PriceTier, Faq, Review
from payments.models import Order, Subscription, PaymentProof, GiftCode, PaymentNumber, SubscriptionMarker
from products.models import Account, Profile, Card, AccountMarker
from users.models import User


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_admin_endpoints_require_admin(api_client, user):
    """A non-superuser authenticated user must be forbidden from admin endpoints."""
    from rest_framework_simplejwt.tokens import RefreshToken
    refresh = RefreshToken.for_user(user)
    api_client.credentials(HTTP_AUTHORIZATION=f'JWT {refresh.access_token}')
    resp = api_client.get('/api/v1/admin/users/')
    assert resp.status_code in (403, 403)


@pytest.mark.django_db
def test_admin_endpoints_require_auth(api_client):
    resp = api_client.get('/api/v1/admin/users/')
    assert resp.status_code in (401, 403)


@pytest.mark.django_db
def test_admin_endpoints_work_for_superuser(admin_client):
    resp = admin_client.get('/api/v1/admin/users/')
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_admin_dashboard_stats(admin_client, make_order):
    make_order(status='completed', price=5000, platform='Netflix')
    make_order(status='pending_payment', platform='Netflix')
    make_order(status='failed', platform='Spotify')
    resp = admin_client.get('/api/v1/admin/dashboard/')
    assert resp.status_code == 200
    assert 'total_revenue' in resp.data
    assert 'total_users' in resp.data
    assert 'active_subs' in resp.data
    assert 'expired_subs' in resp.data
    assert 'last_orders' in resp.data
    assert 'platform_labels' in resp.data
    assert 'platform_data' in resp.data
    assert isinstance(resp.data['platform_labels'], list)
    assert isinstance(resp.data['platform_data'], list)
    # Platform popularity must count ALL orders regardless of status
    assert 'Netflix' in resp.data['platform_labels']
    assert 'Spotify' in resp.data['platform_labels']
    netflix_idx = resp.data['platform_labels'].index('Netflix')
    spotify_idx = resp.data['platform_labels'].index('Spotify')
    assert resp.data['platform_data'][netflix_idx] == 2  # completed + pending
    assert resp.data['platform_data'][spotify_idx] == 1  # failed


@pytest.mark.django_db
def test_admin_dashboard_chart_data_revenue(admin_client, make_order):
    make_order(status='completed', price=5000)
    resp = admin_client.get('/api/v1/admin/dashboard/?action=chart_data&type=revenue&period=7_days')
    assert resp.status_code == 200
    assert 'labels' in resp.data
    assert 'data' in resp.data
    assert 'total' in resp.data


@pytest.mark.django_db
def test_admin_dashboard_chart_data_invalid_type_falls_back(admin_client):
    resp = admin_client.get('/api/v1/admin/dashboard/?action=chart_data&type=invalid&period=7_days')
    assert resp.status_code == 200
    # falls back to revenue
    assert 'labels' in resp.data


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_admin_user_list(admin_client, user):
    resp = admin_client.get('/api/v1/admin/users/')
    assert resp.status_code == 200
    assert resp.data['count'] >= 1


@pytest.mark.django_db
def test_admin_user_create(admin_client):
    resp = admin_client.post('/api/v1/admin/users/', {
        'phone_number': '688888888',
        'country_code': '237',
        'first_name': 'Jane',
        'last_name': 'Doe',
        'password': 'pass1234',
    }, format='json')
    assert resp.status_code == 201, resp.content
    assert User.objects.filter(phone_number='688888888').exists()


@pytest.mark.django_db
def test_admin_user_search(admin_client, user):
    resp = admin_client.get('/api/v1/admin/users/?q=Test')
    assert resp.status_code == 200
    assert resp.data['count'] >= 1


@pytest.mark.django_db
def test_admin_user_export_csv(admin_client, user):
    resp = admin_client.get('/api/v1/admin/users/export_csv/')
    assert resp.status_code == 200
    assert resp['Content-Type'] == 'text/csv'
    content = resp.content.decode('utf-8')
    assert 'first_name' in content
    assert 'Test' in content


@pytest.mark.django_db
def test_admin_user_import_csv(admin_client):
    csv_content = "first_name,last_name,country_code,phone_number,password\nJohn,Smith,237,677777777,hashedpass\n"
    from django.core.files.uploadedfile import SimpleUploadedFile
    f = SimpleUploadedFile('users.csv', csv_content.encode('utf-8'), content_type='text/csv')
    resp = admin_client.post('/api/v1/admin/users/import_csv/', {'file': f}, format='multipart')
    assert resp.status_code == 200
    assert resp.data['imported'] == 1
    assert User.objects.filter(phone_number='677777777').exists()


# ---------------------------------------------------------------------------
# Proofs: validate / validate-only / reject
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_admin_proof_validate_activates_subscription(admin_client, user, make_order, db):
    order = make_order(status='pending_validation', platform='Netflix', duration='1 mois', account_type='mutual')
    from PIL import Image
    from django.core.files.uploadedfile import SimpleUploadedFile
    img = Image.new('RGB', (5, 5))
    buf = io.BytesIO(); img.save(buf, format='PNG'); buf.seek(0)
    proof = PaymentProof.objects.create(
        order=order,
        image=SimpleUploadedFile('p.png', buf.read(), content_type='image/png'),
    )
    resp = admin_client.post(f'/api/v1/admin/proofs/{proof.pk}/validate/')
    assert resp.status_code == 200
    order.refresh_from_db()
    assert order.status == 'completed'
    assert Subscription.objects.filter(order=order).exists()


@pytest.mark.django_db
def test_admin_proof_validate_only_no_subscription(admin_client, user, make_order):
    order = make_order(status='pending_validation')
    from PIL import Image
    from django.core.files.uploadedfile import SimpleUploadedFile
    img = Image.new('RGB', (5, 5))
    buf = io.BytesIO(); img.save(buf, format='PNG'); buf.seek(0)
    proof = PaymentProof.objects.create(
        order=order,
        image=SimpleUploadedFile('p.png', buf.read(), content_type='image/png'),
    )
    resp = admin_client.post(f'/api/v1/admin/proofs/{proof.pk}/validate_only/')
    assert resp.status_code == 200
    order.refresh_from_db()
    assert order.status == 'completed'


@pytest.mark.django_db
def test_admin_proof_reject(admin_client, user, make_order):
    order = make_order(status='pending_validation')
    from PIL import Image
    from django.core.files.uploadedfile import SimpleUploadedFile
    img = Image.new('RGB', (5, 5))
    buf = io.BytesIO(); img.save(buf, format='PNG'); buf.seek(0)
    proof = PaymentProof.objects.create(
        order=order,
        image=SimpleUploadedFile('p.png', buf.read(), content_type='image/png'),
    )
    resp = admin_client.post(f'/api/v1/admin/proofs/{proof.pk}/reject/', {'reason': 'Fake'}, format='json')
    assert resp.status_code == 200
    proof.refresh_from_db()
    assert proof.rejected is True
    assert proof.rejection_reason == 'Fake'
    order.refresh_from_db()
    assert order.status == 'failed'


# ---------------------------------------------------------------------------
# Subscriptions: change profile, unlink, renew, mark, toggle, mark-expired
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_admin_subscription_change_profile(admin_client, user, make_account, make_profile, make_subscription):
    account = make_account(platform_name='Netflix', max_profile=5, place=2)
    p1 = make_profile(account=account, number='P1', code='1111')
    p2 = make_profile(account=account, number='P2', code='2222')
    sub = make_subscription(platform='Netflix', profile=p1)
    resp = admin_client.post(f'/api/v1/admin/subscriptions/{sub.id}/change_profile/', {'profile_id': p2.id}, format='json')
    assert resp.status_code == 200
    sub.refresh_from_db()
    assert sub.profile_id == p2.id


@pytest.mark.django_db
def test_admin_subscription_unlink(admin_client, user, make_account, make_profile, make_subscription):
    account = make_account(platform_name='Netflix')
    profile = make_profile(account=account, number='P1', code='1111')
    sub = make_subscription(platform='Netflix', profile=profile)
    resp = admin_client.post(f'/api/v1/admin/subscriptions/{sub.id}/unlink_profile/')
    assert resp.status_code == 200
    sub.refresh_from_db()
    assert sub.profile is None


@pytest.mark.django_db
def test_admin_subscription_renew(admin_client, user, make_subscription, make_price_tier):
    make_price_tier(base_price=2500)
    sub = make_subscription(platform='Netflix', expiration=timezone.now() + timedelta(days=10))
    resp = admin_client.post(f'/api/v1/admin/subscriptions/{sub.id}/renew/', {'duration': '1 mois'}, format='json')
    assert resp.status_code == 200
    sub.refresh_from_db()
    assert sub.expiration_date > timezone.now() + timedelta(days=20)


@pytest.mark.django_db
def test_admin_subscription_mark_expired(admin_client, user, make_subscription):
    sub = make_subscription(platform='Netflix', expiration=timezone.now() + timedelta(days=10))
    resp = admin_client.post(f'/api/v1/admin/subscriptions/{sub.id}/mark_expired/')
    assert resp.status_code == 200
    sub.refresh_from_db()
    assert sub.status == 'expired'


@pytest.mark.django_db
def test_admin_subscription_toggle_expiry(admin_client, user, make_subscription):
    sub = make_subscription(platform='Netflix', expiration=timezone.now() + timedelta(days=10))
    resp = admin_client.post(f'/api/v1/admin/subscriptions/{sub.id}/toggle_expiry/')
    assert resp.status_code == 200
    sub.refresh_from_db()
    assert sub.status == 'expired'


@pytest.mark.django_db
def test_admin_subscription_actions_on_expired(admin_client, user, make_subscription):
    """Regression: action endpoints must find expired subscriptions (the status
    filter defaulted to 'active' on detail routes, causing 404s on the expired tab)."""
    sub = make_subscription(
        platform='Netflix',
        status='expired',
        expiration=timezone.now() - timedelta(days=1),
    )
    resp = admin_client.post(
        f'/api/v1/admin/subscriptions/{sub.id}/mark/',
        {'marker_name': 'regression', 'marker_color': '#ffffff'},
        format='json',
    )
    assert resp.status_code == 200
    resp = admin_client.patch(f'/api/v1/admin/subscriptions/{sub.id}/', {'status': 'expired'}, format='json')
    assert resp.status_code == 200
    resp = admin_client.post(f'/api/v1/admin/subscriptions/{sub.id}/mark_expired/')
    assert resp.status_code == 200
    resp = admin_client.delete(f'/api/v1/admin/subscriptions/{sub.id}/')
    assert resp.status_code == 204
    assert sub.profile is None


@pytest.mark.django_db
def test_admin_subscription_mark_and_unmark(admin_client, user, make_subscription):
    sub = make_subscription(platform='Netflix', expiration=timezone.now() + timedelta(days=10))
    resp = admin_client.post(f'/api/v1/admin/subscriptions/{sub.id}/mark/', {'marker_name': 'VIP', 'marker_color': '#ff0000'}, format='json')
    assert resp.status_code == 200
    assert sub.markers.filter(name='VIP').exists()
    marker = SubscriptionMarker.objects.get(name='VIP')
    resp = admin_client.post(f'/api/v1/admin/subscriptions/{sub.id}/unmark/', {'marker_id': marker.id}, format='json')
    assert resp.status_code == 200
    assert not sub.markers.filter(name='VIP').exists()


@pytest.mark.django_db
def test_admin_subscription_profile_history(admin_client, user, make_account, make_profile, make_subscription):
    from payments.models import SubscriptionProfileHistory
    account = make_account(platform_name='Netflix')
    profile = make_profile(account=account, number='P1', code='1111')
    sub = make_subscription(platform='Netflix', profile=profile)
    SubscriptionProfileHistory.objects.create(
        subscription=sub, profile_number='P0', profile_code='0000',
        account_number='ACC0', platform='Netflix',
    )
    resp = admin_client.get(f'/api/v1/admin/subscriptions/{sub.id}/profile_history/')
    assert resp.status_code == 200
    assert len(resp.data['history']) == 1


@pytest.mark.django_db
def test_admin_subscription_ordering_by_purchase_date(admin_client, user, make_order):
    """Active subscriptions must be ordered by purchase date descending (newest first)."""
    from core.utils import calculate_expiration
    # Create orders with explicit purchase_dates
    old_date = timezone.now() - timedelta(days=10)
    new_date = timezone.now() - timedelta(days=1)
    order_old = Order.objects.create(
        user=user, platform='Netflix', duration='1 mois', type='mutual',
        price=2500, status='completed', purchase_date=old_date,
    )
    order_new = Order.objects.create(
        user=user, platform='Prime Video', duration='1 mois', type='mutual',
        price=3000, status='completed', purchase_date=new_date,
    )
    sub_old = Subscription.objects.create(
        user=user, order=order_old,
        expiration_date=calculate_expiration('1 mois', old_date),
        status='active',
    )
    sub_new = Subscription.objects.create(
        user=user, order=order_new,
        expiration_date=calculate_expiration('1 mois', new_date),
        status='active',
    )
    resp = admin_client.get('/api/v1/admin/subscriptions/?status=active')
    assert resp.status_code == 200
    ids = [s['id'] for s in resp.data['results']]
    # newest purchase_date should come first
    assert ids[0] == sub_new.id
    assert ids[1] == sub_old.id


# ---------------------------------------------------------------------------
# Accounts + Profiles
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_admin_account_list(admin_client, make_account):
    make_account(platform_name='Netflix')
    resp = admin_client.get('/api/v1/admin/accounts/')
    assert resp.status_code == 200
    assert resp.data['count'] >= 1


@pytest.mark.django_db
def test_admin_account_create(admin_client, make_platform):
    make_platform(name='Netflix')
    resp = admin_client.post('/api/v1/admin/accounts/', {
        'number': 'ACC_NEW',
        'platform': 'Netflix',
        'email': 'acc@test.com',
        'password': 'pass',
        'type': 'mutual',
        'place': 2,
    }, format='json')
    assert resp.status_code == 201, resp.content


@pytest.mark.django_db
def test_admin_account_renew(admin_client, make_account):
    from datetime import timedelta as td
    account = make_account(platform_name='Netflix')
    original_end = account.end_date
    resp = admin_client.post(f'/api/v1/admin/accounts/{account.pk}/renew/')
    assert resp.status_code == 200
    account.refresh_from_db()
    assert account.month_count == 1
    if original_end:
        assert account.end_date > original_end


@pytest.mark.django_db
def test_admin_account_update_card(admin_client, make_account):
    from datetime import date
    card1 = Card.objects.create(numero='1111', nom='Carte A', cvv='123', telephone='655000000', expiration_date=date(2030, 1, 1))
    card2 = Card.objects.create(numero='2222', nom='Carte B', cvv='456', telephone='655000001', expiration_date=date(2030, 1, 1))
    account = make_account(platform_name='Netflix', number='ACC_CARD')
    account.card = card1
    account.save()
    resp = admin_client.patch(
        f'/api/v1/admin/accounts/{account.pk}/',
        {'card_id': card2.pk},
        format='json',
    )
    assert resp.status_code == 200, resp.content
    account.refresh_from_db()
    assert account.card_id == card2.pk
    assert resp.data['card']['id'] == card2.pk
    resp = admin_client.patch(
        f'/api/v1/admin/accounts/{account.pk}/',
        {'card_id': None},
        format='json',
    )
    assert resp.status_code == 200, resp.content
    account.refresh_from_db()
    assert account.card_id is None


@pytest.mark.django_db
def test_admin_user_reset_password_link_format(admin_client, user):
    resp = admin_client.post(f'/api/v1/admin/users/{user.pk}/reset_password/')
    assert resp.status_code == 200, resp.content
    url = resp.data['reset_url']
    assert '/password-reset/complete?uid=' in url
    assert 'token=' in url
    from django.utils.http import urlsafe_base64_decode
    uid = urlsafe_base64_decode(url.split('uid=')[1].split('&')[0]).decode()
    assert int(uid) == user.pk


@pytest.mark.django_db
def test_admin_profile_list(admin_client, make_account, make_profile):
    account = make_account(platform_name='Netflix')
    make_profile(account=account, number='P1', code='1111')
    resp = admin_client.get('/api/v1/admin/profiles/')
    assert resp.status_code == 200
    assert resp.data['count'] >= 1


@pytest.mark.django_db
def test_admin_profile_active_subscriptions_count_excludes_expired(admin_client, make_account, make_profile, make_subscription):
    account = make_account(platform_name='Netflix', number='ACC_PLACES')
    profile = make_profile(account=account, number='P7', code='0000')
    make_subscription(profile=profile, status='active')
    make_subscription(profile=profile, status='expired')
    resp = admin_client.get(f'/api/v1/admin/profiles/{profile.pk}/')
    assert resp.status_code == 200, resp.content
    assert resp.data['active_subscriptions_count'] == 1
    statuses = [s['status'] for s in resp.data['active_subscriptions']]
    assert statuses == ['active']
    all_statuses = sorted(s['status'] for s in resp.data['all_subscriptions'])
    assert all_statuses == ['active', 'expired']


# ---------------------------------------------------------------------------
# Platforms + Price tiers
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_admin_platform_list(admin_client, make_platform):
    make_platform(name='Netflix')
    resp = admin_client.get('/api/v1/admin/platforms/')
    assert resp.status_code == 200


@pytest.mark.django_db
def test_admin_price_tier_create(admin_client, make_platform):
    platform = make_platform(name='Netflix')
    resp = admin_client.post('/api/v1/admin/price-tiers/', {
        'platform': platform.id,
        'account_type': 'mutual',
        'base_price': 2500,
    }, format='json')
    assert resp.status_code == 201, resp.content


# ---------------------------------------------------------------------------
# FAQ, Reviews, Gift codes, Payment numbers
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_admin_faq_crud(admin_client):
    resp = admin_client.post('/api/v1/admin/faqs/', {'question': 'Q?', 'answer': 'A.'}, format='json')
    assert resp.status_code == 201
    faq_id = resp.data['id']
    resp = admin_client.get('/api/v1/admin/faqs/')
    assert resp.data['count'] == 1
    resp = admin_client.patch(f'/api/v1/admin/faqs/{faq_id}/', {'answer': 'Updated.'}, format='json')
    assert resp.status_code == 200
    resp = admin_client.delete(f'/api/v1/admin/faqs/{faq_id}/')
    assert resp.status_code in (200, 204)


@pytest.mark.django_db
def test_admin_review_list(admin_client, user, make_subscription):
    Review.objects.create(user=user, stars=5, comment='Great')
    resp = admin_client.get('/api/v1/admin/reviews/')
    assert resp.status_code == 200
    assert resp.data['count'] == 1


@pytest.mark.django_db
def test_admin_giftcode_crud(admin_client):
    resp = admin_client.post('/api/v1/admin/giftcodes/', {
        'code': 'PROMO',
        'days': 5,
        'start_date': timezone.now().isoformat(),
        'end_date': (timezone.now() + timedelta(days=30)).isoformat(),
    }, format='json')
    assert resp.status_code == 201, resp.content
    gid = resp.data['id']
    resp = admin_client.post(f'/api/v1/admin/giftcodes/{gid}/toggle/')
    assert resp.status_code == 200


@pytest.mark.django_db
def test_admin_payment_number_toggle_rule(admin_client):
    PaymentNumber.objects.create(provider='orange', number='690000001', name='A', is_active=True)
    PaymentNumber.objects.create(provider='orange', number='690000002', name='B', is_active=True)
    p3 = PaymentNumber.objects.create(provider='orange', number='690000003', name='C', is_active=False)
    resp = admin_client.post(f'/api/v1/admin/payment-numbers/{p3.pk}/toggle/')
    assert resp.status_code == 400  # 2 active already


# ---------------------------------------------------------------------------
# Messaging
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_admin_notification_crud(admin_client):
    resp = admin_client.post('/api/v1/admin/messaging/notifications/', {
        'title': 'Hello', 'message': 'World', 'notification_type': 'info',
    }, format='json')
    assert resp.status_code == 201
    nid = resp.data['id']
    resp = admin_client.post(f'/api/v1/admin/messaging/notifications/{nid}/send/', {
        'send_to_all': True,
    }, format='json')
    assert resp.status_code == 200


@pytest.mark.django_db
def test_admin_message_crud(admin_client):
    resp = admin_client.post('/api/v1/admin/messaging/messages/', {
        'subject': 'Subject', 'message': 'Body', 'message_type': 'info',
    }, format='json')
    assert resp.status_code == 201
    mid = resp.data['id']
    resp = admin_client.post(f'/api/v1/admin/messaging/messages/{mid}/send/', {
        'recipients': [],
    }, format='json')
    assert resp.status_code == 400  # no recipients


# ---------------------------------------------------------------------------
# Cards
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_admin_card_crud(admin_client):
    # Create
    resp = admin_client.post('/api/v1/admin/cards/', {
        'numero': '1234567890123456', 'nom': 'Visa Premier',
        'cvv': '123', 'telephone': '+237690000000',
        'expiration_date': '2027-06-01', 'status': 'actif',
    }, format='json')
    assert resp.status_code == 201
    card_id = resp.data['id']
    # numero should be returned decrypted
    assert resp.data['numero'] == '1234567890123456'
    assert resp.data['masked_numero'] is not None
    assert '3456' in resp.data['masked_numero']  # last 4 visible

    # List
    resp = admin_client.get('/api/v1/admin/cards/')
    assert resp.status_code == 200
    assert resp.data['count'] >= 1

    # Update
    resp = admin_client.patch(f'/api/v1/admin/cards/{card_id}/', {
        'nom': 'Mastercard',
    }, format='json')
    assert resp.status_code == 200
    assert resp.data['nom'] == 'Mastercard'

    # Delete
    resp = admin_client.delete(f'/api/v1/admin/cards/{card_id}/')
    assert resp.status_code == 204


@pytest.mark.django_db
def test_admin_card_encryption(admin_client):
    """Card numero must be encrypted in DB but decrypted in API response."""
    resp = admin_client.post('/api/v1/admin/cards/', {
        'numero': '9999888877776666', 'nom': 'Test Card',
        'cvv': '999', 'telephone': '+237690000001',
        'expiration_date': '2027-12-01', 'status': 'actif',
    }, format='json')
    assert resp.status_code == 201
    card_id = resp.data['id']
    # DB value should NOT be the plaintext
    card = Card.objects.get(id=card_id)
    raw_numero = card.numero
    # numero attribute is decrypted by from_db_value, so re-fetch from DB cursor
    from django.db import connection
    with connection.cursor() as cursor:
        cursor.execute("SELECT numero FROM products_card WHERE id = %s", [card_id])
        row = cursor.fetchone()
    db_value = row[0]
    assert db_value != '9999888877776666'  # encrypted in DB
    assert len(db_value) > 50  # Fernet tokens are long
    # API returns decrypted
    resp = admin_client.get(f'/api/v1/admin/cards/{card_id}/')
    assert resp.data['numero'] == '9999888877776666'


# ---------------------------------------------------------------------------
# Account Markers
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_admin_account_mark(admin_client, make_account):
    account = make_account(platform_name='Netflix')
    resp = admin_client.post(f'/api/v1/admin/accounts/{account.id}/mark/', {
        'marker_name': 'Risque', 'marker_color': '#ff0000',
    }, format='json')
    assert resp.status_code == 200
    assert resp.data['marker']['name'] == 'Risque'
    account.refresh_from_db()
    assert account.markers.filter(name='Risque').exists()


@pytest.mark.django_db
def test_admin_account_unmark(admin_client, make_account):
    account = make_account(platform_name='Netflix')
    marker = AccountMarker.objects.create(name='VIP', color='#00ff00')
    account.markers.add(marker)
    resp = admin_client.post(f'/api/v1/admin/accounts/{account.id}/unmark/', {
        'marker_id': marker.id,
    }, format='json')
    assert resp.status_code == 200
    account.refresh_from_db()
    assert not account.markers.filter(name='VIP').exists()


@pytest.mark.django_db
def test_admin_account_markers_in_list(admin_client, make_account):
    account = make_account(platform_name='Netflix')
    marker = AccountMarker.objects.create(name='Premium', color='#0000ff')
    account.markers.add(marker)
    resp = admin_client.get('/api/v1/admin/accounts/')
    assert resp.status_code == 200
    acc_data = next(a for a in resp.data['results'] if a['id'] == account.id)
    assert len(acc_data['markers']) == 1
    assert acc_data['markers'][0]['name'] == 'Premium'
