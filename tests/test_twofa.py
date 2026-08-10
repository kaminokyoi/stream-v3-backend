"""Tests for 2FA (Two-Factor Authentication).

Covers:
  - Login flow: 2FA disabled → JWT pair
  - Login flow: 2FA enabled (TOTP/email/whatsapp) → 2fa_required + twofa_token
  - jwt/2fa-verify: correct code, wrong code, expired token, recovery code
  - Admin endpoints: status, setup, verify-setup, disable, regenerate
"""
from unittest.mock import patch

import pytest

from users.twofa_service import TwoFAService


# ---------------------------------------------------------------------------
# Login flow with 2FA gate
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_login_2fa_disabled_returns_jwt(api_client, user):
    """User without 2FA gets a normal JWT pair."""
    payload = {'phone_number': '600000000', 'password': 'pass1234'}
    resp = api_client.post('/api/v1/public/auth/jwt/create/', payload, format='json')
    assert resp.status_code == 200, resp.content
    assert 'access' in resp.data
    assert 'refresh' in resp.data
    assert resp.data.get('2fa_required') is not True


@pytest.mark.django_db
def test_login_2fa_totp_returns_twofa_token(api_client, user):
    """User with TOTP 2FA gets a twofa_token instead of JWT."""
    user.twofa_enabled = True
    user.twofa_method = 'totp'
    user.twofa_secret = TwoFAService.generate_totp_secret()
    user.save()

    payload = {'phone_number': '600000000', 'password': 'pass1234'}
    resp = api_client.post('/api/v1/public/auth/jwt/create/', payload, format='json')
    assert resp.status_code == 200, resp.content
    assert resp.data['2fa_required'] is True
    assert 'twofa_token' in resp.data
    assert resp.data['method'] == 'totp'
    assert 'access' not in resp.data


@pytest.mark.django_db
@patch('users.twofa_service.TwoFAService._send_email_otp')
def test_login_2fa_email_sends_otp(mock_send, api_client, user):
    """User with email 2FA gets twofa_token and OTP is sent."""
    user.twofa_enabled = True
    user.twofa_method = 'email'
    user.save()

    payload = {'phone_number': '600000000', 'password': 'pass1234'}
    resp = api_client.post('/api/v1/public/auth/jwt/create/', payload, format='json')
    assert resp.status_code == 200, resp.content
    assert resp.data['2fa_required'] is True
    assert resp.data['method'] == 'email'
    assert 'twofa_token' in resp.data
    assert mock_send.called


@pytest.mark.django_db
def test_login_2fa_wrong_credentials_still_401(api_client, user):
    """Bad credentials return 401 even with 2FA enabled."""
    user.twofa_enabled = True
    user.twofa_method = 'totp'
    user.save()

    payload = {'phone_number': '600000000', 'password': 'wrongpass'}
    resp = api_client.post('/api/v1/public/auth/jwt/create/', payload, format='json')
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# jwt/2fa-verify endpoint
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_2fa_verify_correct_totp_code(api_client, user):
    """Valid TOTP code → JWT pair."""
    secret = TwoFAService.generate_totp_secret()
    user.twofa_enabled = True
    user.twofa_method = 'totp'
    user.twofa_secret = secret
    user.save()

    twofa_token = TwoFAService.create_2fa_token(user.id)
    code = TwoFAService.get_totp(secret).now()

    resp = api_client.post(
        '/api/v1/public/auth/jwt/2fa-verify/',
        {'twofa_token': twofa_token, 'code': code},
        format='json',
    )
    assert resp.status_code == 200, resp.content
    assert 'access' in resp.data
    assert 'refresh' in resp.data


@pytest.mark.django_db
def test_2fa_verify_correct_email_otp(api_client, user):
    """Valid email OTP → JWT pair."""
    user.twofa_enabled = True
    user.twofa_method = 'email'
    user.save()

    twofa_code = TwoFAService.create_and_send_otp.__wrapped__ if hasattr(TwoFAService.create_and_send_otp, '__wrapped__') else None
    with patch.object(TwoFAService, '_send_email_otp'):
        twofa = TwoFAService.create_and_send_otp(user, 'email')

    twofa_token = TwoFAService.create_2fa_token(user.id)

    resp = api_client.post(
        '/api/v1/public/auth/jwt/2fa-verify/',
        {'twofa_token': twofa_token, 'code': twofa.code},
        format='json',
    )
    assert resp.status_code == 200, resp.content
    assert 'access' in resp.data


@pytest.mark.django_db
def test_2fa_verify_wrong_code(api_client, user):
    """Wrong code → 400."""
    user.twofa_enabled = True
    user.twofa_method = 'totp'
    user.twofa_secret = TwoFAService.generate_totp_secret()
    user.save()

    twofa_token = TwoFAService.create_2fa_token(user.id)

    resp = api_client.post(
        '/api/v1/public/auth/jwt/2fa-verify/',
        {'twofa_token': twofa_token, 'code': '000000'},
        format='json',
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_2fa_verify_expired_token(api_client, user):
    """Expired/invalid twofa_token → 400."""
    user.twofa_enabled = True
    user.twofa_method = 'totp'
    user.save()

    resp = api_client.post(
        '/api/v1/public/auth/jwt/2fa-verify/',
        {'twofa_token': 'invalid-token', 'code': '123456'},
        format='json',
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_2fa_verify_missing_fields(api_client):
    resp = api_client.post(
        '/api/v1/public/auth/jwt/2fa-verify/',
        {'twofa_token': ''},
        format='json',
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_2fa_verify_recovery_code(api_client, user):
    """Recovery code → JWT pair + single-use removal."""
    user.twofa_enabled = True
    user.twofa_method = 'totp'
    user.save()

    codes = TwoFAService.generate_recovery_codes()
    TwoFAService.store_recovery_codes(user, codes)
    twofa_token = TwoFAService.create_2fa_token(user.id)

    resp = api_client.post(
        '/api/v1/public/auth/jwt/2fa-verify/',
        {'twofa_token': twofa_token, 'code': codes[0]},
        format='json',
    )
    assert resp.status_code == 200, resp.content
    assert 'access' in resp.data

    user.refresh_from_db()
    hash_of_used = TwoFAService.hash_recovery_code(codes[0])
    assert hash_of_used not in user.twofa_recovery_codes


# ---------------------------------------------------------------------------
# Admin 2FA management endpoints
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_admin_2fa_status_disabled(admin_client):
    resp = admin_client.get('/api/v1/admin/2fa/status/')
    assert resp.status_code == 200
    assert resp.data['enabled'] is False


@pytest.mark.django_db
def test_admin_2fa_setup_totp(admin_client):
    resp = admin_client.post('/api/v1/admin/2fa/setup/', {'method': 'totp'}, format='json')
    assert resp.status_code == 200, resp.content
    assert 'qr_code' in resp.data
    assert 'otpauth_uri' in resp.data
    assert 'secret' in resp.data


@pytest.mark.django_db
@patch.object(TwoFAService, '_send_email_otp')
def test_admin_2fa_setup_email(mock_send, admin_client):
    resp = admin_client.post('/api/v1/admin/2fa/setup/', {'method': 'email'}, format='json')
    assert resp.status_code == 200, resp.content
    assert mock_send.called


@pytest.mark.django_db
def test_admin_2fa_setup_invalid_method(admin_client):
    resp = admin_client.post('/api/v1/admin/2fa/setup/', {'method': 'sms'}, format='json')
    assert resp.status_code == 400


@pytest.mark.django_db
def test_admin_2fa_verify_setup_totp(admin_client, admin_user):
    """Setup TOTP → verify with correct code → 2FA enabled."""
    setup_resp = admin_client.post('/api/v1/admin/2fa/setup/', {'method': 'totp'}, format='json')
    secret = setup_resp.data['secret']
    admin_user.refresh_from_db()
    assert admin_user.twofa_secret == secret

    code = TwoFAService.get_totp(secret).now()
    resp = admin_client.post(
        '/api/v1/admin/2fa/verify-setup/',
        {'method': 'totp', 'code': code},
        format='json',
    )
    assert resp.status_code == 200, resp.content
    assert 'recovery_codes' in resp.data
    assert len(resp.data['recovery_codes']) == 10

    admin_user.refresh_from_db()
    assert admin_user.twofa_enabled is True
    assert admin_user.twofa_method == 'totp'


@pytest.mark.django_db
def test_admin_2fa_verify_setup_wrong_code(admin_client, admin_user):
    admin_client.post('/api/v1/admin/2fa/setup/', {'method': 'totp'}, format='json')
    resp = admin_client.post(
        '/api/v1/admin/2fa/verify-setup/',
        {'method': 'totp', 'code': '000000'},
        format='json',
    )
    assert resp.status_code == 400
    admin_user.refresh_from_db()
    assert admin_user.twofa_enabled is False


@pytest.mark.django_db
def test_admin_2fa_disable(admin_client, admin_user):
    admin_user.twofa_enabled = True
    admin_user.twofa_method = 'totp'
    admin_user.twofa_secret = TwoFAService.generate_totp_secret()
    codes = TwoFAService.generate_recovery_codes()
    TwoFAService.store_recovery_codes(admin_user, codes)
    admin_user.save()

    resp = admin_client.post(
        '/api/v1/admin/2fa/disable/',
        {'password': 'admin1234'},
        format='json',
    )
    assert resp.status_code == 200, resp.content
    admin_user.refresh_from_db()
    assert admin_user.twofa_enabled is False
    assert admin_user.twofa_secret == ''
    assert admin_user.twofa_recovery_codes == []


@pytest.mark.django_db
def test_admin_2fa_disable_wrong_password(admin_client, admin_user):
    admin_user.twofa_enabled = True
    admin_user.save()

    resp = admin_client.post(
        '/api/v1/admin/2fa/disable/',
        {'password': 'wrongpass'},
        format='json',
    )
    assert resp.status_code == 400
    admin_user.refresh_from_db()
    assert admin_user.twofa_enabled is True


@pytest.mark.django_db
def test_admin_2fa_regenerate_recovery(admin_client, admin_user):
    admin_user.twofa_enabled = True
    admin_user.twofa_method = 'totp'
    codes = TwoFAService.generate_recovery_codes()
    TwoFAService.store_recovery_codes(admin_user, codes)
    admin_user.save()

    resp = admin_client.post('/api/v1/admin/2fa/regenerate-recovery/', format='json')
    assert resp.status_code == 200, resp.content
    assert len(resp.data['recovery_codes']) == 10
    assert resp.data['recovery_codes'] != codes


@pytest.mark.django_db
def test_admin_2fa_regenerate_recovery_not_enabled(admin_client, admin_user):
    resp = admin_client.post('/api/v1/admin/2fa/regenerate-recovery/', format='json')
    assert resp.status_code == 400


@pytest.mark.django_db
def test_admin_2fa_endpoints_require_auth(api_client):
    """All 2FA admin endpoints require authentication."""
    for method, url, payload in [
        ('get', '/api/v1/admin/2fa/status/', None),
        ('post', '/api/v1/admin/2fa/setup/', {'method': 'totp'}),
        ('post', '/api/v1/admin/2fa/disable/', {'password': 'x'}),
    ]:
        fn = getattr(api_client, method)
        resp = fn(url, payload, format='json') if payload else fn(url)
        assert resp.status_code in (401, 403), f'{url} returned {resp.status_code}'


@pytest.mark.django_db
def test_admin_2fa_endpoints_require_superuser(authed_client):
    """Regular authenticated user cannot access admin 2FA endpoints."""
    resp = authed_client.get('/api/v1/admin/2fa/status/')
    assert resp.status_code == 403
