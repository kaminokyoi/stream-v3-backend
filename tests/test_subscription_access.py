"""Tests for platform access-masking rules (audit §5.7).

Security-critical: the backend must never leak credentials for masked
platforms.
  - Spotify / Apple Music: only the principal profile (first created on
    the account) sees email/password; secondary profiles see blanks.
  - Surfshark: all access fields hidden.
  - Normal platform: all fields visible.
"""
import pytest

from core.services import SubscriptionAccessService


@pytest.mark.django_db
def test_spotify_principal_profile_sees_access(user, make_account, make_profile, make_subscription):
    account = make_account(platform_name='Spotify', max_profile=2, place=2)
    principal = make_profile(account=account, number='P1', code='1111')   # first created => principal
    make_subscription( platform='Spotify', profile=principal)

    subs_data, _ = SubscriptionAccessService.build_dashboard_subscriptions(user)
    sub = next(s for s in subs_data if s['platform_name'] == 'Spotify')
    assert sub['email'] == account.email
    assert sub['password'] == account.password
    assert sub['profileNum'] == 'P1'


@pytest.mark.django_db
def test_spotify_secondary_profile_access_masked(user, make_account, make_profile, make_subscription):
    account = make_account(platform_name='Spotify', max_profile=2, place=2)
    principal = make_profile(account=account, number='P1', code='1111')
    secondary = make_profile(account=account, number='P2', code='2222')
    make_subscription( platform='Spotify', profile=secondary)

    subs_data, _ = SubscriptionAccessService.build_dashboard_subscriptions(user)
    sub = next(s for s in subs_data if s['platform_name'] == 'Spotify')
    assert sub['email'] == ''
    assert sub['password'] == ''
    assert sub['profileNum'] == 'P2'   # profile number still shown


@pytest.mark.django_db
def test_surfshark_all_access_masked(user, make_account, make_profile, make_subscription):
    account = make_account(platform_name='Surfshark', max_profile=2, place=2)
    profile = make_profile(account=account, number='S1', code='3333')
    make_subscription( platform='Surfshark', profile=profile)

    subs_data, _ = SubscriptionAccessService.build_dashboard_subscriptions(user)
    sub = next(s for s in subs_data if s['platform_name'] == 'Surfshark')
    assert sub['email'] == ''
    assert sub['password'] == ''
    assert sub['profileNum'] == ''
    assert sub['profilePin'] == ''


@pytest.mark.django_db
def test_normal_platform_all_access_visible(user, make_account, make_profile, make_subscription):
    account = make_account(platform_name='Netflix', max_profile=5, place=2)
    profile = make_profile(account=account, number='N1', code='4444')
    make_subscription( platform='Netflix', profile=profile)

    subs_data, _ = SubscriptionAccessService.build_dashboard_subscriptions(user)
    sub = next(s for s in subs_data if s['platform_name'] == 'Netflix')
    assert sub['email'] == account.email
    assert sub['password'] == account.password
    assert sub['profileNum'] == 'N1'
    assert sub['profilePin'] == '4444'
