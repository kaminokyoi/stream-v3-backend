"""Tests for the first-review +7-day bonus (audit §5.9).

Rule: the FIRST review by a user who has an active subscription grants
+7 days on a random active subscription. Subsequent reviews grant no
bonus. No active subscription => no bonus.
"""
from datetime import timedelta
from django.utils import timezone

import pytest

from core.services import ReviewService
from core.models import Review


@pytest.mark.django_db
def test_first_review_awards_bonus(user, make_subscription):
    sub = make_subscription(
        platform='Netflix',
        duration='1 mois',
        expiration=timezone.now() + timedelta(days=10),
    )
    original_expiration = sub.expiration_date

    result = ReviewService.submit_review(user, stars=5, comment='great')

    assert result['bonus_awarded'] is True
    assert Review.objects.filter(user=user).count() == 1
    sub.refresh_from_db()
    assert sub.expiration_date == original_expiration + timedelta(days=7)


@pytest.mark.django_db
def test_second_review_no_bonus(user, make_subscription):
    make_subscription(
        platform='Netflix',
        duration='1 mois',
        expiration=timezone.now() + timedelta(days=10),
    )
    ReviewService.submit_review(user, stars=5, comment='first')
    # Second submission: update same review
    result = ReviewService.submit_review(user, stars=4, comment='updated')

    assert result['bonus_awarded'] is False
    assert Review.objects.filter(user=user).count() == 1


@pytest.mark.django_db
def test_review_without_active_subscription_no_bonus(user, make_subscription):
    make_subscription(
        platform='Netflix',
        duration='1 mois',
        expiration=timezone.now() - timedelta(days=1),  # expired
        status='expired',
    )
    result = ReviewService.submit_review(user, stars=5, comment='ok')

    assert result['bonus_awarded'] is False
    assert Review.objects.filter(user=user).count() == 1


@pytest.mark.django_db
def test_review_stars_capped_at_five(user, make_subscription):
    make_subscription(
        platform='Netflix',
        duration='1 mois',
        expiration=timezone.now() + timedelta(days=10),
    )
    ReviewService.submit_review(user, stars=99, comment='')
    review = Review.objects.get(user=user)
    assert review.stars == 5
