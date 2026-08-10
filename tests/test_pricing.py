"""Tests for the pricing rules (audit §5.2).

Formula (from PriceTier.base_price, monthly):
  1 mois  = base
  3 mois  = 3 * base - 500
  6 mois  = 2 * (3 mois) - 1000
  1 an    = 2 * (6 mois) - 2000

These MUST never change.
"""
import pytest

from core.models import PriceTier
from core.utils import calculate_price, calculate_expiration


@pytest.mark.django_db
def test_computed_prices_formula(make_price_tier):
    tier = make_price_tier(base_price=2500)
    p = tier.computed_prices()
    assert p['1 mois'] == 2500
    assert p['3 mois'] == 7000     # 3*2500 - 500
    assert p['6 mois'] == 13000    # 2*7000 - 1000
    assert p['1 an'] == 24000      # 2*13000 - 2000


@pytest.mark.django_db
def test_computed_prices_formula_with_small_base(make_price_tier):
    tier = make_price_tier(base_price=1500)
    p = tier.computed_prices()
    assert p['1 mois'] == 1500
    assert p['3 mois'] == 4000     # 3*1500 - 500
    assert p['6 mois'] == 7000     # 2*4000 - 1000
    assert p['1 an'] == 12000      # 2*7000 - 2000


@pytest.mark.django_db
def test_calculate_price_mutual(make_price_tier, make_platform):
    platform = make_platform(name='Prime Video')
    make_price_tier(platform=platform, account_type='mutual', base_price=2000)
    assert calculate_price('Prime Video', '1 mois', 'mutual') == 2000
    assert calculate_price('Prime Video', '3 mois', 'mutual') == 5500
    assert calculate_price('Prime Video', '1 an', 'mutual') == 18000


@pytest.mark.django_db
def test_calculate_price_personal_with_category(make_platform, make_price_tier):
    platform = make_platform(name='Netflix', has_personal=True)
    make_price_tier(platform=platform, account_type='personal', category='Mobile', base_price=1000)
    make_price_tier(platform=platform, account_type='personal', category='Premium', base_price=3000)
    assert calculate_price('Netflix', '1 mois', 'personal', 'Mobile') == 1000
    assert calculate_price('Netflix', '1 an', 'personal', 'Premium') == 30000


@pytest.mark.django_db
def test_calculate_price_unknown_platform_returns_zero(make_price_tier):
    make_price_tier(base_price=2500)
    assert calculate_price('UnknownPlatform', '1 mois', 'mutual') == 0


def test_calculate_expiration_1_month():
    from django.utils import timezone
    purchase = timezone.now()
    exp = calculate_expiration('1 mois', purchase)
    assert (exp.date() - purchase.date()).days >= 29
    assert (exp.date() - purchase.date()).days <= 30


def test_calculate_expiration_1_year():
    from django.utils import timezone
    purchase = timezone.now()
    exp = calculate_expiration('1 an', purchase)
    assert (exp.date() - purchase.date()).days >= 364
    assert (exp.date() - purchase.date()).days <= 366


def test_calculate_expiration_midnight():
    """Expiration should be at 00:00 (no time component)."""
    from django.utils import timezone
    purchase = timezone.now()
    exp = calculate_expiration('1 mois', purchase)
    assert exp.hour == 0
    assert exp.minute == 0
    assert exp.second == 0
