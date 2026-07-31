"""
Import legacy data from CSV files into the database.

Usage:
  # Dry-run (validate without writing):
  python manage.py import_csv_data --dry-run

  # Import specific tables only:
  python manage.py import_csv_data --only=users,accounts,profiles,orders,subscriptions,proofs

  # Full import:
  python manage.py import_csv_data

  # Custom CSV directory:
  python manage.py import_csv_data --csv-dir=/path/to/csv_data

The command uses update_or_create by PK, so it merges with existing data
without deleting anything. After import, PostgreSQL sequences are reset.
"""
import csv
import os
from datetime import datetime
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import connection, transaction
from django.utils import timezone

from users.models import User
from core.models import Platform, PriceTier, Review, Faq
from products.models import Account, Profile, Card, AccountMarker
from payments.models import (
    Order, Subscription, PaymentProof, GiftCode, PaymentNumber,
    SubscriptionMarker, SubscriptionProfileHistory,
)


PLATFORM_MAP = {
    'Disney Plus': 'Disney+',
    'Paramount Plus': 'Paramount+',
    'Hbo Max': 'HBO Max',
}

EXTRA_PLATFORMS = {'TINDER', 'METAVERIFIED', 'GOOGLEONE', 'CHAT GPT', 'CAPCUT'}


def map_platform(name):
    return PLATFORM_MAP.get(name, name)


def parse_bool(val):
    if not val or val.strip() == '':
        return False
    return val.strip().lower() in ('t', 'true', '1', 'yes')


def parse_int(val):
    val = val.strip() if val else ''
    if val == '':
        return None
    try:
        return int(val)
    except ValueError:
        return None


def parse_decimal(val):
    val = val.strip() if val else ''
    if val == '':
        return None
    try:
        return Decimal(val)
    except Exception:
        return None


def parse_datetime(val):
    val = val.strip() if val else ''
    if val == '' or val.lower() == 'none' or val.lower() == 'null':
        return None
    from django.utils.timezone import make_aware, is_aware
    from django.conf import settings

    # Normalize short timezone offsets: +00 → +0000, +01 → +0100
    import re
    val = re.sub(r'([+-])(\d{2})$', r'\g<1>\g<2>00', val)

    for fmt in ('%Y-%m-%d %H:%M:%S.%f%z', '%Y-%m-%d %H:%M:%S%z',
                '%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S',
                '%Y-%m-%d', '%Y-%m'):
        try:
            dt = datetime.strptime(val, fmt)
            if not is_aware(dt) and settings.USE_TZ:
                dt = make_aware(dt, timezone.get_default_timezone())
            return dt
        except ValueError:
            continue

    # Last resort: dateutil.parser handles any ISO format
    try:
        from dateutil import parser as dateutil_parser
        dt = dateutil_parser.parse(val)
        if not is_aware(dt) and settings.USE_TZ:
            dt = make_aware(dt, timezone.get_default_timezone())
        return dt
    except Exception:
        return None


def parse_date(val):
    val = val.strip() if val else ''
    if val == '':
        return None
    for fmt in ('%Y-%m-%d', '%Y/%m/%d'):
        try:
            return datetime.strptime(val, fmt).date()
        except ValueError:
            continue
    return None


class Command(BaseCommand):
    help = 'Import legacy data from CSV files.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Validate without writing.')
        parser.add_argument('--csv-dir', default=None, help='Path to CSV directory.')
        parser.add_argument('--only', default='', help='Comma-separated table names to import.')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        csv_dir = options['csv_dir'] or os.path.join(os.getcwd(), '..', 'csv_data')
        only = set(options['only'].split(',')) if options['only'] else None

        if not os.path.isdir(csv_dir):
            self.stderr.write(self.style.ERROR(f'CSV directory not found: {csv_dir}'))
            return

        self.stdout.write(self.style.WARNING(f'Mode: {"DRY-RUN" if dry_run else "LIVE IMPORT"}'))
        self.stdout.write(f'CSV dir: {csv_dir}')
        self.stdout.write(f'Tables: {", ".join(sorted(only)) if only else "ALL"}')
        self.stdout.write('')

        stats = {}

        def read_csv(filename):
            path = os.path.join(csv_dir, filename)
            if not os.path.exists(path):
                self.stdout.write(f'  SKIP {filename} (not found)')
                return []
            with open(path, newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                return list(reader)

        def should_run(table):
            return only is None or table in only

        with transaction.atomic():
            # Use savepoint for dry-run rollback
            sid = transaction.savepoint()

            # 1. Users
            if should_run('users'):
                rows = read_csv('users_user.csv')
                created = updated = skipped = 0
                for r in rows:
                    pk = parse_int(r['id'])
                    if not pk:
                        skipped += 1; continue
                    phone = r.get('phone_number', '').strip()
                    if not phone:
                        skipped += 1; continue
                    obj, was_created = User.objects.update_or_create(
                        pk=pk,
                        defaults={
                            'password': r.get('password', ''),
                            'last_login': parse_datetime(r.get('last_login', '')),
                            'is_superuser': parse_bool(r.get('is_superuser')),
                            'first_name': r.get('first_name', ''),
                            'last_name': r.get('last_name', ''),
                            'country_code': r.get('country_code', '237'),
                            'phone_number': phone,
                            'total_orders': parse_int(r.get('total_orders')) or 0,
                            'total_subscriptions': parse_int(r.get('total_subscriptions')) or 0,
                            'is_active': parse_bool(r.get('is_active', 't')),
                            'is_staff': parse_bool(r.get('is_staff')),
                            'is_admin': parse_bool(r.get('is_admin')),
                            'date_joined': parse_datetime(r.get('date_joined')) or timezone.now(),
                            'email': r.get('email', '') or None,
                        },
                    )
                    if was_created: created += 1
                    else: updated += 1
                stats['users'] = {'created': created, 'updated': updated, 'skipped': skipped, 'total': len(rows)}
                self._print_stats('users', stats['users'])

            # 2. Cards
            if should_run('cards'):
                rows = read_csv('products_card.csv')
                created = updated = 0
                for r in rows:
                    pk = parse_int(r['id'])
                    if not pk: continue
                    obj, was_created = Card.objects.update_or_create(
                        pk=pk,
                        defaults={
                            'numero': r.get('numero', ''),
                            'nom': r.get('nom', ''),
                            'cvv': r.get('cvv', ''),
                            'telephone': r.get('telephone', ''),
                            'expiration_date': parse_date(r.get('expiration_date')) or timezone.now().date(),
                            'status': r.get('status', 'actif'),
                        },
                    )
                    if was_created: created += 1
                    else: updated += 1
                stats['cards'] = {'created': created, 'updated': updated, 'total': len(rows)}
                self._print_stats('cards', stats['cards'])

            # 3. Accounts
            if should_run('accounts'):
                rows = read_csv('products_account.csv')
                created = updated = skipped = 0
                for r in rows:
                    pk = parse_int(r['id'])
                    if not pk: skipped += 1; continue
                    platform = map_platform(r.get('platform', ''))
                    card_id = parse_int(r.get('card_id'))
                    start_date = parse_datetime(r.get('start_date'))
                    end_date = parse_datetime(r.get('end_date'))
                    month_count = parse_int(r.get('month_count')) or 0
                    # Derive start_date from end_date if missing
                    if not start_date and end_date and month_count:
                        from dateutil.relativedelta import relativedelta
                        start_date = end_date - relativedelta(months=month_count)
                    obj, was_created = Account.objects.update_or_create(
                        pk=pk,
                        defaults={
                            'number': r.get('number', ''),
                            'platform': platform,
                            'email': r.get('email', ''),
                            'password': r.get('password', ''),
                            'profiles': parse_int(r.get('profiles')) or 0,
                            'max_profile': parse_int(r.get('max_profile')) or 5,
                            'type': r.get('type', 'mutual'),
                            'place': parse_int(r.get('place')) or 2,
                            'start_date': start_date,
                            'end_date': end_date,
                            'month_count': month_count,
                            'remaining_day': parse_int(r.get('remaining_day')) or 0,
                            'status': r.get('status', 'activate'),
                        },
                    )
                    if card_id:
                        card = Card.objects.filter(pk=card_id).first()
                        if card:
                            obj.card = card
                            obj.save(update_fields=['card'])
                    if was_created: created += 1
                    else: updated += 1
                stats['accounts'] = {'created': created, 'updated': updated, 'skipped': skipped, 'total': len(rows)}
                self._print_stats('accounts', stats['accounts'])

            # 4. Profiles
            if should_run('profiles'):
                rows = read_csv('products_profile.csv')
                created = updated = skipped = 0
                for r in rows:
                    pk = parse_int(r['id'])
                    if not pk: skipped += 1; continue
                    account_id = parse_int(r.get('account_id'))
                    if not account_id: skipped += 1; continue
                    account = Account.objects.filter(pk=account_id).first()
                    if not account: skipped += 1; continue
                    obj, was_created = Profile.objects.update_or_create(
                        pk=pk,
                        defaults={
                            'number': r.get('number', ''),
                            'code': r.get('code', ''),
                            'place': parse_int(r.get('place')) or 1,
                            'account': account,
                        },
                    )
                    if was_created: created += 1
                    else: updated += 1
                stats['profiles'] = {'created': created, 'updated': updated, 'skipped': skipped, 'total': len(rows)}
                self._print_stats('profiles', stats['profiles'])

            # 5. GiftCodes (needed before orders)
            if should_run('giftcodes'):
                rows = read_csv('payments_giftcode.csv')
                created = updated = 0
                for r in rows:
                    pk = parse_int(r['id'])
                    if not pk: continue
                    platform_id = parse_int(r.get('platform_id'))
                    platform = Platform.objects.filter(pk=platform_id).first() if platform_id else None
                    obj, was_created = GiftCode.objects.update_or_create(
                        pk=pk,
                        defaults={
                            'code': r.get('code', ''),
                            'days': parse_int(r.get('days')) or 0,
                            'start_date': parse_datetime(r.get('start_date')) or timezone.now(),
                            'end_date': parse_datetime(r.get('end_date')) or timezone.now(),
                            'status': parse_bool(r.get('status')),
                            'platform': platform,
                            'usage_limit': parse_int(r.get('usage_limit')) or 1,
                            'used_count': parse_int(r.get('used_count')) or 0,
                        },
                    )
                    if was_created: created += 1
                    else: updated += 1
                stats['giftcodes'] = {'created': created, 'updated': updated, 'total': len(rows)}
                self._print_stats('giftcodes', stats['giftcodes'])

            # 6. Orders (defer subscription_id + renewal_from_id)
            if should_run('orders'):
                rows = read_csv('payments_order.csv')
                created = updated = skipped = 0
                deferred = []
                for r in rows:
                    pk = parse_int(r['id'])
                    if not pk: skipped += 1; continue
                    user_id = parse_int(r.get('user_id'))
                    user = User.objects.filter(pk=user_id).first() if user_id else None
                    gift_code_id = parse_int(r.get('gift_code_id'))
                    gift_code = GiftCode.objects.filter(pk=gift_code_id).first() if gift_code_id else None
                    platform = map_platform(r.get('platform', ''))
                    obj, was_created = Order.objects.update_or_create(
                        pk=pk,
                        defaults={
                            'user': user,
                            'platform': platform,
                            'price': parse_int(r.get('price')) or 0,
                            'duration': r.get('duration', '1 mois'),
                            'purchase_date': parse_datetime(r.get('purchase_date')) or timezone.now(),
                            'status': r.get('status', 'pending_payment'),
                            'type': r.get('type', 'mutual'),
                            'motif': r.get('motif', 'subscription'),
                            'gift_code': gift_code,
                            'subscription': None,
                            'renewal_from': None,
                        },
                    )
                    deferred.append({
                        'pk': pk,
                        'subscription_id': parse_int(r.get('subscription_id')),
                        'renewal_from_id': parse_int(r.get('renewal_from_id')),
                    })
                    if was_created: created += 1
                    else: updated += 1
                stats['orders'] = {'created': created, 'updated': updated, 'skipped': skipped, 'total': len(rows), 'deferred': len(deferred)}
                self._print_stats('orders', stats['orders'])

            # 7. Subscriptions
            if should_run('subscriptions'):
                rows = read_csv('payments_subscription.csv')
                created = updated = skipped = 0
                for r in rows:
                    pk = parse_int(r['id'])
                    if not pk: skipped += 1; continue
                    order_id = parse_int(r.get('order_id'))
                    order = Order.objects.filter(pk=order_id).first() if order_id else None
                    if not order: skipped += 1; continue
                    user_id = parse_int(r.get('user_id'))
                    user = User.objects.filter(pk=user_id).first() if user_id else None
                    profile_id = parse_int(r.get('profile_id'))
                    profile = Profile.objects.filter(pk=profile_id).first() if profile_id else None
                    obj, was_created = Subscription.objects.update_or_create(
                        pk=pk,
                        defaults={
                            'order': order,
                            'user': user or order.user,
                            'profile': profile,
                            'expiration_date': parse_datetime(r.get('expiration_date')) or timezone.now(),
                            'status': r.get('status', 'active'),
                        },
                    )
                    if was_created: created += 1
                    else: updated += 1
                stats['subscriptions'] = {'created': created, 'updated': updated, 'skipped': skipped, 'total': len(rows)}
                self._print_stats('subscriptions', stats['subscriptions'])

            # 8. Update deferred order FKs (subscription + renewal_from)
            if should_run('orders') and not dry_run:
                updated_fks = 0
                for d in deferred:
                    updates = {}
                    if d['subscription_id']:
                        sub = Subscription.objects.filter(pk=d['subscription_id']).first()
                        if sub:
                            updates['subscription'] = sub
                    if d['renewal_from_id']:
                        renewal_sub = Subscription.objects.filter(pk=d['renewal_from_id']).first()
                        if renewal_sub:
                            updates['renewal_from'] = renewal_sub
                    if updates:
                        Order.objects.filter(pk=d['pk']).update(**updates)
                        updated_fks += 1
                self.stdout.write(f'  Orders FK backfill: {updated_fks} updated')

            # 9. Payment proofs
            if should_run('proofs'):
                rows = read_csv('payments_paymentproof.csv')
                created = updated = skipped = 0
                for r in rows:
                    pk = parse_int(r['id'])
                    if not pk: skipped += 1; continue
                    order_id = parse_int(r.get('order_id'))
                    order = Order.objects.filter(pk=order_id).first() if order_id else None
                    if not order: skipped += 1; continue
                    validated_by_id = parse_int(r.get('validated_by_id'))
                    validated_by = User.objects.filter(pk=validated_by_id).first() if validated_by_id else None
                    image = r.get('image', '').strip()
                    image2 = r.get('image2', '').strip()
                    obj, was_created = PaymentProof.objects.update_or_create(
                        pk=pk,
                        defaults={
                            'order': order,
                            'image': image,
                            'image2': image2 if image2 else None,
                            'submitted_at': parse_datetime(r.get('submitted_at')) or timezone.now(),
                            'validated': parse_bool(r.get('validated')),
                            'validated_at': parse_datetime(r.get('validated_at')),
                            'rejected': parse_bool(r.get('rejected')),
                            'rejection_reason': r.get('rejection_reason', ''),
                            'validated_by': validated_by,
                        },
                    )
                    if was_created: created += 1
                    else: updated += 1
                stats['proofs'] = {'created': created, 'updated': updated, 'skipped': skipped, 'total': len(rows)}
                self._print_stats('proofs', stats['proofs'])

            # 10. Subscription profile history
            if should_run('history'):
                rows = read_csv('payments_subscriptionprofilehistory.csv')
                created = skipped = 0
                for r in rows:
                    pk = parse_int(r['id'])
                    if not pk: skipped += 1; continue
                    sub_id = parse_int(r.get('subscription_id'))
                    sub = Subscription.objects.filter(pk=sub_id).first() if sub_id else None
                    if not sub: skipped += 1; continue
                    _, was_created = SubscriptionProfileHistory.objects.update_or_create(
                        pk=pk,
                        defaults={
                            'subscription': sub,
                            'profile_number': r.get('profile_number', ''),
                            'profile_code': r.get('profile_code', ''),
                            'account_number': r.get('account_number', ''),
                            'platform': map_platform(r.get('platform', '')),
                            'linked_at': parse_datetime(r.get('linked_at')) or timezone.now(),
                            'unlinked_at': parse_datetime(r.get('unlinked_at')),
                        },
                    )
                    if was_created: created += 1
                stats['history'] = {'created': created, 'skipped': skipped, 'total': len(rows)}
                self._print_stats('history', stats['history'])

            # 11. Reviews
            if should_run('reviews'):
                rows = read_csv('core_review.csv')
                created = updated = skipped = 0
                for r in rows:
                    pk = parse_int(r['id'])
                    if not pk: skipped += 1; continue
                    user_id = parse_int(r.get('user_id'))
                    user = User.objects.filter(pk=user_id).first() if user_id else None
                    obj, was_created = Review.objects.update_or_create(
                        pk=pk,
                        defaults={
                            'user': user,
                            'stars': parse_int(r.get('stars')) or 0,
                            'comment': r.get('comment', ''),
                            'create_at': parse_datetime(r.get('create_at')) or timezone.now(),
                        },
                    )
                    if was_created: created += 1
                    else: updated += 1
                stats['reviews'] = {'created': created, 'updated': updated, 'skipped': skipped, 'total': len(rows)}
                self._print_stats('reviews', stats['reviews'])

            # 12. FAQs
            if should_run('faqs'):
                rows = read_csv('core_faq.csv')
                created = updated = 0
                for r in rows:
                    pk = parse_int(r['id'])
                    if not pk: continue
                    _, was_created = Faq.objects.update_or_create(
                        pk=pk,
                        defaults={
                            'question': r.get('question', ''),
                            'answer': r.get('answer', ''),
                        },
                    )
                    if was_created: created += 1
                    else: updated += 1
                stats['faqs'] = {'created': created, 'updated': updated, 'total': len(rows)}
                self._print_stats('faqs', stats['faqs'])

            # 13. Payment numbers
            if should_run('paymentnumbers'):
                rows = read_csv('payments_paymentnumber.csv')
                created = updated = 0
                for r in rows:
                    pk = parse_int(r['id'])
                    if not pk: continue
                    _, was_created = PaymentNumber.objects.update_or_create(
                        pk=pk,
                        defaults={
                            'provider': r.get('provider', 'mtn'),
                            'number': r.get('number', ''),
                            'name': r.get('name', ''),
                            'is_active': parse_bool(r.get('is_active', 't')),
                            'created_at': parse_datetime(r.get('created_at')) or timezone.now(),
                        },
                    )
                    if was_created: created += 1
                    else: updated += 1
                stats['paymentnumbers'] = {'created': created, 'updated': updated, 'total': len(rows)}
                self._print_stats('paymentnumbers', stats['paymentnumbers'])

            # 14. Subscription markers + M2M
            if should_run('submarkers'):
                rows = read_csv('payments_subscriptionmarker.csv')
                for r in rows:
                    pk = parse_int(r['id'])
                    if not pk: continue
                    SubscriptionMarker.objects.update_or_create(
                        pk=pk,
                        defaults={'name': r.get('name', ''), 'color': r.get('color', '#ffffff')},
                    )
                m2m_rows = read_csv('payments_subscription_markers.csv')
                linked = 0
                for r in m2m_rows:
                    sub_id = parse_int(r.get('subscription_id'))
                    marker_id = parse_int(r.get('subscriptionmarker_id'))
                    if not sub_id or not marker_id: continue
                    sub = Subscription.objects.filter(pk=sub_id).first()
                    if sub:
                        sub.markers.add(marker_id)
                        linked += 1
                self.stdout.write(f'  Sub markers M2M: {linked} links')

            # 15. Account markers + M2M
            if should_run('accountmarkers'):
                rows = read_csv('products_accountmarker.csv')
                for r in rows:
                    pk = parse_int(r['id'])
                    if not pk: continue
                    AccountMarker.objects.update_or_create(
                        pk=pk,
                        defaults={'name': r.get('name', ''), 'color': r.get('color', '#ffffff')},
                    )
                m2m_rows = read_csv('products_account_markers.csv')
                linked = 0
                for r in m2m_rows:
                    acc_id = parse_int(r.get('account_id'))
                    marker_id = parse_int(r.get('accountmarker_id'))
                    if not acc_id or not marker_id: continue
                    acc = Account.objects.filter(pk=acc_id).first()
                    if acc:
                        acc.markers.add(marker_id)
                        linked += 1
                self.stdout.write(f'  Account markers M2M: {linked} links')

            # Reset sequences (PostgreSQL only)
            if not dry_run and connection.vendor == 'postgresql':
                self._reset_sequences()

            if dry_run:
                transaction.savepoint_rollback(sid)
                self.stdout.write('')
                self.stdout.write(self.style.SUCCESS('DRY-RUN complete — all data rolled back.'))
            else:
                transaction.savepoint_commit(sid)
                self.stdout.write('')
                self.stdout.write(self.style.SUCCESS('Import complete.'))

    def _print_stats(self, name, s):
        total = s.get('total', 0)
        created = s.get('created', 0)
        updated = s.get('updated', 0)
        skipped = s.get('skipped', 0)
        self.stdout.write(f'  {name:20s} {total:>5} rows → {created} created, {updated} updated, {skipped} skipped')

    def _reset_sequences(self):
        """Reset PostgreSQL sequences to max(id)+1 after explicit PK inserts."""
        models_map = {
            'users_user': User,
            'products_card': Card,
            'products_account': Account,
            'products_profile': Profile,
            'payments_order': Order,
            'payments_subscription': Subscription,
            'payments_paymentproof': PaymentProof,
            'payments_giftcode': GiftCode,
            'payments_paymentnumber': PaymentNumber,
            'payments_subscriptionmarker': SubscriptionMarker,
            'payments_subscriptionprofilehistory': SubscriptionProfileHistory,
            'products_accountmarker': AccountMarker,
            'core_review': Review,
            'core_faq': Faq,
        }
        reset_count = 0
        for table_name, model in models_map.items():
            db_table = model._meta.db_table
            try:
                max_id = model.objects.order_by('-id').first()
                max_pk = max_id.id if max_id else 0
                with connection.cursor() as cursor:
                    cursor.execute(
                        f"SELECT setval(pg_get_serial_sequence('{db_table}', 'id'), %s, true)",
                        [max_pk],
                    )
                reset_count += 1
            except Exception as e:
                self.stderr.write(f'  Sequence reset failed for {db_table}: {e}')
        self.stdout.write(f'  PostgreSQL sequences reset: {reset_count}/{len(models_map)}')
