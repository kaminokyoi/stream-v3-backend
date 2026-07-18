# core/utils.py

from .models import Platform, PriceTier


def platform_choices() -> list[tuple[str, str]]:
    try:
        choices = [
            (platform.name, platform.name)
            for platform in Platform.objects.all()
        ]
        choices.append(('Autres', 'Autres'))
        return choices
    except Exception as e:
        print(f'Exception: {e}')
        return [("None", "None")]


def duration_choices() -> list[tuple[str, str]]:
    return [
        ('1 mois', '1 mois'),
        ('3 mois', '3 mois'),
        ('6 mois', '6 mois'),
        ('1 an', '1 an'),
    ]


def calculate_expiration(duration: str, purchase_date):
    from django.utils import timezone
    from datetime import timedelta

    if not purchase_date:
        purchase_date = timezone.now()

    if duration.lower() in ["1 mois", "3 mois", "6 mois"]:
        expiration = (
                purchase_date + timedelta(days=int(duration[0]) * 30)
        ).replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0
        )

        return expiration

    else:
        return (
                purchase_date + timedelta(days=365)
        ).replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0
        )


def calculate_price(platform: str, duration: str, account_type: str = 'mutual', sub_type: str = '') -> int:
    """
    Calculate the price of a subscription from the database.

    Args:
        platform: Platform name (e.g. 'Netflix')
        duration: Duration string (e.g. '1 mois', '3 mois', '6 mois', '1 an')
        account_type: 'mutual', 'personal'
        sub_type: Sub-category for platforms with tiers (e.g. 'Mobile', 'Essentiel', 'Premium')

    Returns:
        Price in FCFA, 0 if not found
    """

    # Normalize sub_type: ensure it's never 'None' or None
    if not sub_type or sub_type.lower() == 'none':
        sub_type = ''

    try:
        tier = PriceTier.objects.select_related('platform').get(
            platform__name=platform,
            account_type=account_type,
            category=sub_type,
        )
        return tier.computed_prices().get(duration, 0)
    except PriceTier.DoesNotExist:
        # Fallback: for personal subscriptions without a specified sub_type,
        # try to find the first matching personal tier (e.g. for renewals
        # where the original sub_type is not stored on the order).
        if account_type == 'personal' and not sub_type:
            tier = PriceTier.objects.select_related('platform').filter(
                platform__name=platform,
                account_type='personal',
            ).order_by('base_price').first()
            if tier:
                return tier.computed_prices().get(duration, 0)
        return 0


def get_all_prices() -> dict:
    """
    Build complete pricing data from DB for template/JS injection.

    Returns dict with:
        'shared': {platform_name: {duration: price, ...}, ...}
        'personal': {platform_name: {duration: price} or {category: {duration: price}}, ...}
        'no_personal': [platform_names_without_personal]
        'platforms_json': [{name, has_personal, shared, personal}, ...]
    """
    platforms = Platform.objects.filter(price_tiers__isnull=False).prefetch_related('price_tiers').distinct()

    shared = {}
    personal = {}
    no_personal = []
    platforms_json = []

    for platform in platforms:
        # Shared prices
        shared_prices = platform.get_shared_prices()
        if shared_prices:
            shared[platform.name] = shared_prices

        # Personal prices
        if platform.has_personal:
            personal_data = platform.get_personal_prices()
            if personal_data:
                personal[platform.name] = personal_data
        else:
            no_personal.append(platform.name)

        # Full JSON for JS injection
        platforms_json.append(platform.get_all_pricing_json())

    return {
        'shared': shared,
        'personal': personal,
        'no_personal': no_personal,
        'platforms_json': platforms_json,
    }
