"""
Pytest configuration + shared fixtures for StreamPartner backend tests.

Run with:  uv run pytest
"""
import pytest

from core.models import Platform, PriceTier, Review
from payments.models import Order, Subscription
from products.models import Account, Profile
from users.models import User


@pytest.fixture
def user(db):
    u = User(
        first_name='Test',
        last_name='User',
        country_code='237',
        phone_number='600000000',
        email='test@example.com',
    )
    u.set_password('pass1234')
    u.save()
    return u


@pytest.fixture
def make_platform(db):
    def _make(name='Netflix', has_personal=False, order=0):
        platform, _ = Platform.objects.get_or_create(
            name=name,
            defaults={'has_personal': has_personal, 'order': order},
        )
        return platform
    return _make


@pytest.fixture
def make_price_tier(db, make_platform):
    def _make(platform=None, account_type='mutual', category='', base_price=2500):
        platform = platform or make_platform()
        return PriceTier.objects.create(
            platform=platform,
            account_type=account_type,
            category=category,
            base_price=base_price,
        )
    return _make


@pytest.fixture
def make_account(db, make_platform):
    def _make(platform_name='Netflix', account_type='mutual', number='ACC1', max_profile=5, place=2):
        if not Platform.objects.filter(name=platform_name).exists():
            make_platform(name=platform_name)
        return Account.objects.create(
            number=number,
            platform=platform_name,
            email=f'{number}@test.com',
            password='pass',
            max_profile=max_profile,
            type=account_type,
            place=place,
            status='activate',
        )
    return _make


@pytest.fixture
def make_profile(db, make_account):
    def _make(account=None, number='P1', code='0000'):
        account = account or make_account()
        return Profile.objects.create(number=number, code=code, account=account, place=1)
    return _make


@pytest.fixture
def make_order(db, user):
    def _make(platform='Netflix', duration='1 mois', account_type='mutual', price=2500, status='completed'):
        return Order.objects.create(
            user=user,
            platform=platform,
            duration=duration,
            type=account_type,
            price=price,
            status=status,
        )
    return _make


@pytest.fixture
def make_subscription(db, user, make_order):
    def _make(platform='Netflix', duration='1 mois', account_type='mutual',
              expiration=None, profile=None, status='active'):
        from django.utils import timezone
        from core.utils import calculate_expiration
        order = make_order(platform=platform, duration=duration, account_type=account_type)
        if expiration is None:
            expiration = calculate_expiration(duration, timezone.now())
        return Subscription.objects.create(
            user=user,
            order=order,
            expiration_date=expiration,
            profile=profile,
            status=status,
        )
    return _make


import pytest
from rest_framework.test import APIClient


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def authed_client(api_client, user):
    """APIClient authenticated as `user` via JWT."""
    from rest_framework_simplejwt.tokens import RefreshToken
    refresh = RefreshToken.for_user(user)
    api_client.credentials(HTTP_AUTHORIZATION=f'JWT {refresh.access_token}')
    return api_client


# ---------------------------------------------------------------------------
# Test environment overrides (cache + throttling)
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def use_locmem_cache(settings):
    """Replace Redis cache with LocMem for tests (no Redis dependency)."""
    settings.CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        }
    }
    settings.REST_FRAMEWORK = {
        **settings.REST_FRAMEWORK,
        'DEFAULT_THROTTLE_CLASSES': [],  # disable throttling in tests
    }
    # Run Celery tasks synchronously (no broker connection in tests)
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True
    settings.CELERY_BROKER_URL = 'memory://'


@pytest.fixture
def admin_user(db):
    u = User(
        first_name='Admin',
        last_name='Root',
        country_code='237',
        phone_number='700000000',
        email='admin@example.com',
        is_staff=True,
        is_superuser=True,
    )
    u.set_password('admin1234')
    u.save()
    return u


@pytest.fixture
def admin_client(api_client, admin_user):
    """APIClient authenticated as a superuser via JWT."""
    from rest_framework_simplejwt.tokens import RefreshToken
    refresh = RefreshToken.for_user(admin_user)
    api_client.credentials(HTTP_AUTHORIZATION=f'JWT {refresh.access_token}')
    return api_client
