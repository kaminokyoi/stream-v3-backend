# Generated data migration: seed PriceTier rows from previous hardcoded pricing.
from django.db import migrations


# Previous hardcoded prices — base_price is the 1-month price.
SEED_DATA = [
    # ── Shared (mutual) prices ──
    # Platform,       type,       category, base_price, description
    ('Netflix',       'mutual',   '',       2500,       ''),
    ('Disney Plus',   'mutual',   '',       2500,       ''),
    ('HBO Max',       'mutual',   '',       2500,       ''),
    ('Paramount+',    'mutual',   '',       2500,       ''),
    ('Prime Video',   'mutual',   '',       2000,       ''),
    ('Spotify',       'mutual',   '',       2000,       ''),
    ('Apple Music',   'mutual',   '',       2000,       ''),
    ('Crunchyroll',   'mutual',   '',       1500,       ''),
    ('Surfshark',     'mutual',   '',       1500,       ''),

    # ── Personal prices ──
    # Netflix personal tiers
    ('Netflix',       'personal', 'Mobile',    4500,  '1 écran, qualité 480p'),
    ('Netflix',       'personal', 'Essentiel', 5500,  '1 écran, qualité 1080p'),
    ('Netflix',       'personal', 'Premium',   10500, '4 écrans, qualité 4K'),

    # Other personal
    ('Prime Video',   'personal', '',       8000,  ''),
    ('Crunchyroll',   'personal', '',       5000,  ''),
    ('Apple Music',   'personal', '',       5000,  ''),
    ('Spotify',       'personal', '',       5000,  ''),
    ('Surfshark',     'personal', '',       5000,  ''),
    ('HBO Max',       'personal', '',       7500,  ''),
]

# Platforms that have personal plans
HAS_PERSONAL = ['Netflix', 'Prime Video', 'Crunchyroll', 'Apple Music', 'Spotify', 'Surfshark', 'HBO Max']


def seed_price_tiers(apps, schema_editor):
    Platform = apps.get_model('core', 'Platform')
    PriceTier = apps.get_model('core', 'PriceTier')

    # Update has_personal flag on existing platforms
    for name in HAS_PERSONAL:
        Platform.objects.filter(name=name).update(has_personal=True)

    # Create PriceTier rows
    for (platform_name, account_type, category, base_price, description) in SEED_DATA:
        try:
            platform = Platform.objects.get(name=platform_name)
        except Platform.DoesNotExist:
            # Platform doesn't exist in DB yet, skip
            continue

        PriceTier.objects.get_or_create(
            platform=platform,
            account_type=account_type,
            category=category,
            defaults={
                'base_price': base_price,
                'category_description': description,
            }
        )


def reverse_seed(apps, schema_editor):
    PriceTier = apps.get_model('core', 'PriceTier')
    PriceTier.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_alter_platform_options_remove_platform_plan_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_price_tiers, reverse_seed),
    ]
