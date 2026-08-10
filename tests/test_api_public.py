"""Tests for the public API endpoints (/api/v1/public/*).

Covers:
  - Auth: registration, JWT create/refresh/verify
  - Catalogue: platforms list, platform pricing
  - Reviews: public list
  - FAQ: public list
  - Permissions: anonymous access works
"""
import pytest

from core.models import Platform, PriceTier, Faq


# ---------------------------------------------------------------------------
# Auth (Djoser + SimpleJWT)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_register_user(api_client, make_platform):
    payload = {
        'phone_number': '699999999',
        'country_code': '237',
        'first_name': 'Jean',
        'last_name': 'Dupont',
        'password': 'Str0ng!Pass',
        're_password': 'Str0ng!Pass',
    }
    resp = api_client.post('/api/v1/public/auth/users/', payload, format='json')
    assert resp.status_code == 201, resp.content
    assert resp.data['phone_number'] == '699999999'
    assert 'password' not in resp.data


@pytest.mark.django_db
def test_register_user_password_mismatch(api_client):
    payload = {
        'phone_number': '699999999',
        'country_code': '237',
        'first_name': 'Jean',
        'last_name': 'Dupont',
        'password': 'Str0ng!Pass',
        're_password': 'Different!Pass',
    }
    resp = api_client.post('/api/v1/public/auth/users/', payload, format='json')
    assert resp.status_code == 400


@pytest.mark.django_db
def test_jwt_create_with_phone(api_client, user):
    payload = {'phone_number': '600000000', 'password': 'pass1234'}
    resp = api_client.post('/api/v1/public/auth/jwt/create/', payload, format='json')
    assert resp.status_code == 200, resp.content
    assert 'access' in resp.data
    assert 'refresh' in resp.data


@pytest.mark.django_db
def test_jwt_create_wrong_password(api_client, user):
    payload = {'phone_number': '600000000', 'password': 'wrongpass'}
    resp = api_client.post('/api/v1/public/auth/jwt/create/', payload, format='json')
    assert resp.status_code == 401


@pytest.mark.django_db
def test_jwt_refresh_and_verify(api_client, user):
    from rest_framework_simplejwt.tokens import RefreshToken
    refresh = RefreshToken.for_user(user)

    resp = api_client.post(
        '/api/v1/public/auth/jwt/verify/',
        {'token': str(refresh.access_token)},
        format='json',
    )
    assert resp.status_code == 200

    resp = api_client.post(
        '/api/v1/public/auth/jwt/refresh/',
        {'refresh': str(refresh)},
        format='json',
    )
    assert resp.status_code == 200
    assert 'access' in resp.data


@pytest.mark.django_db
def test_jwt_auth_header_format(api_client, user):
    """The API uses 'JWT <token>' (not 'Bearer <token>')."""
    from rest_framework_simplejwt.tokens import RefreshToken
    access = str(RefreshToken.for_user(user).access_token)
    api_client.credentials(HTTP_AUTHORIZATION=f'JWT {access}')
    resp = api_client.get('/api/v1/public/auth/users/me/')
    assert resp.status_code == 200
    assert resp.data['phone_number'] == '600000000'


# ---------------------------------------------------------------------------
# Catalogue: platforms + pricing
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_platforms_list_public(api_client, make_price_tier):
    make_price_tier(base_price=2500)
    resp = api_client.get('/api/v1/public/platforms/')
    assert resp.status_code == 200
    assert resp.data['count'] >= 1
    assert 'name' in resp.data['results'][0]


@pytest.mark.django_db
def test_platform_pricing_endpoint(api_client, make_platform, make_price_tier):
    platform = make_platform(name='Netflix', has_personal=True)
    make_price_tier(platform=platform, account_type='mutual', base_price=2500)
    make_price_tier(platform=platform, account_type='personal', category='Premium', base_price=3000)

    resp = api_client.get(f'/api/v1/public/platforms/{platform.pk}/pricing/')
    assert resp.status_code == 200
    assert resp.data['name'] == 'Netflix'
    assert resp.data['shared_prices']['1 mois'] == 2500
    assert resp.data['shared_prices']['1 an'] == 24000
    assert 'Premium' in resp.data['personal_prices']


@pytest.mark.django_db
def test_platforms_list_excludes_platforms_without_pricing(api_client, make_platform):
    """Platforms without PriceTier should not appear in the catalogue."""
    make_platform(name='NoPricing')
    resp = api_client.get('/api/v1/public/platforms/')
    names = [p['name'] for p in resp.data['results']]
    assert 'NoPricing' not in names


# ---------------------------------------------------------------------------
# Reviews + FAQ (public read-only)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_reviews_public_list(api_client, user, make_subscription):
    from core.models import Review
    Review.objects.create(user=user, stars=5, comment='Excellent')
    resp = api_client.get('/api/v1/public/reviews/')
    assert resp.status_code == 200
    assert resp.data['count'] == 1
    assert resp.data['results'][0]['stars'] == 5
    assert resp.data['results'][0]['user_name'] == 'Test User'


@pytest.mark.django_db
def test_faqs_public_list(api_client):
    Faq.objects.create(question='Comment ça marche ?', answer='Inscrivez-vous.')
    resp = api_client.get('/api/v1/public/faqs/')
    assert resp.status_code == 200
    assert resp.data['count'] == 1
    assert resp.data['results'][0]['question'] == 'Comment ça marche ?'


# ---------------------------------------------------------------------------
# Permissions: anonymous access to catalogue, auth required for me
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_catalogue_accessible_anonymously(api_client, make_price_tier):
    make_price_tier()
    for url in ['/api/v1/public/platforms/', '/api/v1/public/reviews/', '/api/v1/public/faqs/']:
        resp = api_client.get(url)
        assert resp.status_code == 200, f'{url} returned {resp.status_code}'


@pytest.mark.django_db
def test_auth_users_me_requires_auth(api_client):
    resp = api_client.get('/api/v1/public/auth/users/me/')
    assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Password reset (phone-based, Djoser override)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_password_reset_by_phone_dispatches_link(api_client, user, settings):
    from unittest.mock import patch
    with patch('notifications.tasks.send_password_reset_link_task') as task:
        resp = api_client.post(
            '/api/v1/public/auth/users/reset_password/',
            {'phone_number': '600000000'},
            format='json',
        )
    assert resp.status_code == 204, resp.content
    task.apply.assert_called_once()
    args = task.apply.call_args.kwargs['args']
    assert args[0] == user.id
    assert '/password-reset/complete?uid=' in args[1]
    assert 'token=' in args[1]
    from django.utils.http import urlsafe_base64_decode
    uid = urlsafe_base64_decode(args[1].split('uid=')[1].split('&')[0]).decode()
    assert int(uid) == user.id


@pytest.mark.django_db
def test_password_reset_unknown_phone_returns_204(api_client):
    from unittest.mock import patch
    with patch('notifications.tasks.send_password_reset_link_task') as task:
        resp = api_client.post(
            '/api/v1/public/auth/users/reset_password/',
            {'phone_number': '999999999'},
            format='json',
        )
    assert resp.status_code == 204
    task.apply.assert_not_called()


@pytest.mark.django_db
def test_password_reset_confirm_changes_password(api_client, user):
    from django.contrib.auth.tokens import default_token_generator
    from django.utils.encoding import force_bytes
    from django.utils.http import urlsafe_base64_encode
    token = default_token_generator.make_token(user)
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    resp = api_client.post(
        '/api/v1/public/auth/users/reset_password_confirm/',
        {'uid': uid, 'token': token, 'new_password': 'NouveauPass!42'},
        format='json',
    )
    assert resp.status_code == 204, resp.content
    user.refresh_from_db()
    assert user.check_password('NouveauPass!42')
    login = api_client.post(
        '/api/v1/public/auth/jwt/create/',
        {'phone_number': '600000000', 'password': 'NouveauPass!42'},
        format='json',
    )
    assert login.status_code == 200


@pytest.mark.django_db
def test_password_reset_confirm_invalid_token(api_client, user):
    from django.utils.encoding import force_bytes
    from django.utils.http import urlsafe_base64_encode
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    resp = api_client.post(
        '/api/v1/public/auth/users/reset_password_confirm/',
        {'uid': uid, 'token': 'invalid-token', 'new_password': 'NouveauPass!42'},
        format='json',
    )
    assert resp.status_code == 400
