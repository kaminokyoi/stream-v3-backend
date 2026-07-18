"""
Core domain services.

SubscriptionAccessService
    Centralizes the access-masking rules per platform (Spotify, Apple Music,
    Surfshark, Onoff). This logic MUST stay server-side: it protects
    credentials. Both the HTML dashboard and the future REST API consume it.

ReviewService
    Encapsulates review submission + the "+7 days" first-review bonus logic.
"""
import random
from typing import Optional

from dateutil.relativedelta import relativedelta
from django.db.models import Min
from django.utils import timezone

from payments.models import Order, Subscription, SubscriptionProfileHistory
from products.models import Profile
from .models import Review


class SubscriptionAccessService:
    """Builds the user dashboard data with platform-specific access masking."""

    PLATFORM_STYLES = {
        'Netflix': ('ph-monitor-play', '#E50914', 'images/netflix.svg'),
        'Disney Plus': ('ph-star', '#3B82F6', 'images/disney_plus.svg'),
        'Prime Video': ('ph-video', '#38BDF8', 'images/prime_video.svg'),
        'Spotify': ('ph-music-notes', '#22C55E', 'images/spotify.svg'),
        'HBO Max': ('ph-film-strip', '#A855F7', 'images/hbo_max.svg'),
        'Crunchyroll': ('ph-lightning', '#F97316', 'images/crunchyroll.svg'),
        'Apple Music': ('ph-music-note', '#EC4899', 'images/apple_music.svg'),
        'Apple TV': ('ph-tv', '#A3A3A3', 'images/apple_tv.svg'),
        'Paramount Plus': ('ph-film-slate', '#0064FF', 'images/paramount_plus.svg'),
        'Surfshark': ('ph-shield-check', '#22D3EE', 'images/surfshark.svg'),
        'Onoff': ('ph-phone', '#60A5FA', 'images/onoff.svg'),
    }

    @classmethod
    def get_platform_style(cls, name: str) -> tuple[str, str, str]:
        """Return (icon, color, logo_path) for a platform name."""
        return cls.PLATFORM_STYLES.get(name, ('ph-play-circle', '#ffffff', ''))

    @classmethod
    def build_dashboard_subscriptions(cls, user) -> tuple[list[dict], list[dict]]:
        """Return (subscriptions_data, notifications_data) for a user.

        Applies the platform-specific masking rules:
        - Spotify / Apple Music: only the principal profile (first created
          on the account) sees email/password; secondary profiles see blanks.
        - Surfshark: all access fields are hidden.
        - Onoff: handled via the account type.
        Subscriptions expired AND unlinked are excluded from display.
        """
        now = timezone.now()

        subs = Subscription.objects.filter(
            user=user
        ).select_related(
            'order', 'profile', 'profile__account'
        ).exclude(
            status='expired', profile__isnull=True
        ).order_by('-status', 'expiration_date')

        # First profile (Min id) per account — used for Spotify/Apple Music masking
        account_ids = {sub.profile.account_id for sub in subs if sub.profile and sub.profile.account_id}
        first_profile_by_account = {}
        if account_ids:
            profiles_min = Profile.objects.filter(
                account_id__in=account_ids
            ).values('account_id').annotate(first_id=Min('id'))
            for p_data in profiles_min:
                first_profile_by_account[p_data['account_id']] = p_data['first_id']

        subs_data = []
        notifs_data = []

        for sub in subs:
            platform_name = sub.order.platform
            icon, color, logo = cls.get_platform_style(platform_name)

            email = sub.profile.account.email if sub.profile and sub.profile.account else 'En attente...'
            password = sub.profile.account.password if sub.profile and sub.profile.account else '...'
            profile_num = sub.profile.number if sub.profile else ''
            profile_pin = sub.profile.code if sub.profile else ''

            p_name_lower = platform_name.strip().lower()

            if p_name_lower in ['spotify', 'apple music']:
                if sub.profile and sub.profile.account_id:
                    if first_profile_by_account.get(sub.profile.account_id) != sub.profile.id:
                        email = ''
                        password = ''
            elif p_name_lower == 'surfshark':
                email = ''
                password = ''
                profile_num = ''
                profile_pin = ''

            is_expired = sub.status == 'expired' or sub.expiration_date < now
            display_status = 'expired' if is_expired else sub.status

            subs_data.append({
                'id': sub.id,
                'name': f"{platform_name} {sub.order.get_type_display()}",
                'platform_name': platform_name,
                'type': sub.order.type,
                'purchase_date': sub.order.purchase_date,
                'expiration_date': sub.expiration_date,
                'email': email,
                'password': password,
                'profileNum': profile_num,
                'profilePin': profile_pin,
                'icon': icon,
                'color': color,
                'logo': logo,
                'status': display_status,
                'order_status': sub.order.status,
                'price': sub.order.price,
                'duration': sub.order.duration,
            })

            if is_expired:
                notifs_data.append({
                    'id': sub.id,
                    'name': f"{platform_name} {sub.order.get_type_display()}",
                    'platform': platform_name,
                    'platform_name': platform_name,
                    'type': sub.order.type,
                    'date': sub.expiration_date.strftime('%d/%m/%Y'),
                    'expiration_date': sub.expiration_date,
                    'price': sub.order.price,
                    'duration': sub.order.duration,
                    'icon': icon,
                    'color': color,
                    'logo': logo,
                    'status': 'expired',
                })
            else:
                days_left = (sub.expiration_date - now).days
                if 0 <= days_left <= 5:
                    notifs_data.append({
                        'id': sub.id,
                        'name': f"{platform_name} {sub.order.get_type_display()}",
                        'platform': platform_name,
                        'date': sub.expiration_date.strftime('%d/%m/%Y'),
                        'expiration_date': sub.expiration_date,
                        'icon': icon,
                        'status': 'active',
                    })

        return subs_data, notifs_data

    @classmethod
    def build_dashboard_orders(cls, user) -> tuple[list[dict], list[dict]]:
        """Return (orders_data, pending_orders_data) for a user."""
        orders = Order.objects.filter(user=user).order_by('-purchase_date')
        orders_data = []
        pending_orders_data = []

        for o in orders:
            if o.status in ['pending_payment', 'pending_validation']:
                icon, color, logo = cls.get_platform_style(o.platform)
                pending_orders_data.append({
                    'id': str(o.order_id),
                    'platform': o.platform,
                    'price': str(o.price),
                    'duration': o.duration,
                    'status': o.status,
                    'status_label': str(o.get_status_display()),
                    'icon': icon,
                    'color': color,
                    'logo': logo,
                    'purchase_date': o.purchase_date.strftime('%d/%m/%Y'),
                })
            orders_data.append({
                'id': str(o.order_id),
                'platform': o.platform,
                'price': o.price,
                'duration': o.duration,
                'purchase_date': o.purchase_date,
                'status': o.status,
                'status_label': o.get_status_display(),
            })

        return orders_data, pending_orders_data

    @classmethod
    def should_show_review_modal(cls, user) -> bool:
        """True if the user has an active subscription and has not reviewed yet."""
        has_active_subs = Subscription.objects.filter(user=user, status='active').exists()
        has_review = Review.objects.filter(user=user).exists()
        return has_active_subs and not has_review


class ReviewService:
    """Handles review submission and the first-review +7 days bonus."""

    @classmethod
    def submit_review(cls, user, stars, comment='') -> dict:
        """Create or update a user's review, awarding the +7-day bonus on first review.

        Returns a dict with: message, bonus_awarded (bool), bonus_sub_name (str).
        """
        already_reviewed = Review.objects.filter(user=user).exists()

        Review.objects.update_or_create(
            user=user,
            defaults={'stars': stars, 'comment': comment},
        )

        response_data = {
            'message': 'Avis enregistré ! Merci pour votre retour.',
            'bonus_awarded': False,
        }

        if not already_reviewed:
            user_subs = list(Subscription.objects.filter(user=user, status='active'))
            if user_subs:
                random_sub = random.choice(user_subs)
                now = timezone.now()
                random_sub.expiration_date += relativedelta(days=7)
                if random_sub.expiration_date > now:
                    random_sub.status = 'active'

                if not random_sub.profile:
                    random_sub.profile = cls._relink_last_profile(random_sub)

                random_sub.save(update_fields=['expiration_date', 'status', 'profile'])

                platform_name = "votre abonnement"
                if random_sub.order and random_sub.order.platform:
                    platform_name = f"{random_sub.order.platform} {random_sub.order.get_type_display()}"

                response_data['message'] = (
                    f"Avis enregistré ! Cadeau de bienvenue : +7 jours ont été "
                    f"ajoutés à {platform_name} ! 🎁"
                )
                response_data['bonus_awarded'] = True
                response_data['bonus_sub_name'] = platform_name

        return response_data

    @staticmethod
    def _relink_last_profile(subscription: Subscription) -> Optional[Profile]:
        """Try to re-attribute the last unlinked profile to a subscription (bonus case)."""
        last_history = SubscriptionProfileHistory.objects.filter(
            subscription=subscription
        ).order_by('-unlinked_at').first()
        if not last_history:
            return None
        return Profile.objects.filter(
            number=last_history.profile_number,
            account__number=last_history.account_number,
            account__platform=last_history.platform,
        ).first()
