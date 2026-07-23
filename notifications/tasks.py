"""
Celery tasks for the notifications app.

- send_email_task: generic email sender (used by all notify_* services)
- send_access_update_notification: async entrypoint for access-change alerts
- send_rejection_proof_email: async entrypoint for payment-proof rejection
- send_password_reset_link_task: async entrypoint for password reset
"""
from celery import shared_task
from logging import getLogger

logger = getLogger(__name__)


@shared_task
def send_email_task(to_email, subject, text_body, html_body=None):
    """Envoie un email via l'intégration configurée (Resend via Anymail)."""
    from django.conf import settings
    from django.core.mail import send_mail
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'system@notification.streampartner.in')
    try:
        if not to_email:
            return False
        send_mail(
            subject=subject,
            message=text_body,
            from_email=from_email,
            recipient_list=[to_email],
            fail_silently=False,
            html_message=html_body,
        )
        logger.info(f"Email sent to {to_email}: {subject}")
        return True
    except Exception as e:
        logger.error(f"Email Error: {e}")
        return False


@shared_task
def send_access_update_notification(user_id, platform_name=""):
    """Envoie une notification lorsqu'un compte ou profil lié a été modifié."""
    from users.models import User
    from .services import notify_access_update
    try:
        user = User.objects.get(id=user_id)
        notify_access_update(user, platform_name)
        logger.info(f"Access update notification queued for user {user_id}")
        return True
    except User.DoesNotExist:
        logger.error(f"User {user_id} not found for access update notification")
        return False


@shared_task
def send_rejection_proof_email(to_email, user_first_name, reason, order_id, platform_name):
    """Envoie un message de rejet de preuve de paiement."""
    from django.template.loader import render_to_string
    if not to_email:
        return False
    dashboard_url = "https://streampartner.in/dashboard/"
    retry_url = f"https://streampartner.in/payments/failure/{order_id}"
    context = {
        'user': {'first_name': user_first_name},
        'reason': reason,
        'order': {'id': order_id, 'platform_name': platform_name},
        'dashboard_url': dashboard_url,
        'retry_url': retry_url,
    }
    html_message = render_to_string('notifications/emails/proof_rejected.html', context)
    text_message = (
        f"Paiement non validé pour la commande #{order_id} ({platform_name}). "
        f"Raison : {reason}\nLien pour réessayer : {retry_url}"
    )
    send_email_task.delay(to_email, f"Paiement non validé (#{order_id})", text_message, html_message)
    # Also notify admins via push
    from .tasks import send_push_to_admins_task
    send_push_to_admins_task.delay(
        "Preuve rejetée",
        f"#{order_id} — {platform_name} — {reason}",
        {"screen": "proofs", "type": "payment", "resource_id": order_id},
        "payment",
    )
    return True


@shared_task
def send_password_reset_link_task(user_id, reset_url):
    """Envoie un lien de réinitialisation de mot de passe par email."""
    from users.models import User
    from .services import notify_password_reset_link
    try:
        user = User.objects.get(pk=user_id)
        return notify_password_reset_link(user, reset_url)
    except User.DoesNotExist:
        logger.error(f"User with id {user_id} not found")
        return False


@shared_task
def notify_admin_login_task(user_id, ip, timestamp_iso):
    """Resolve IP geolocation (blocking) and send the admin-login alert email.

    Deported to a task so the synchronous HTTP call to ip-api does not
    delay the login request.
    """
    import datetime as _dt
    from users.models import User
    from users.utils import get_location_info
    from .services import notify_admin_login
    try:
        user = User.objects.get(id=user_id)
        location = get_location_info(ip)
        timestamp = _dt.datetime.fromisoformat(timestamp_iso)
        notify_admin_login(user, ip, location, timestamp)
    except User.DoesNotExist:
        logger.error(f"User {user_id} not found for admin login notification")
        return False


@shared_task
def check_expiring_cards_task():
    """Daily task to check for expiring cards and set their status to 'inactif'.

    Cards expire at the end of their expiration month.
    """
    from django.utils import timezone
    from products.models import Card
    from dateutil.relativedelta import relativedelta

    today = timezone.now().date()
    active_cards = Card.objects.filter(status='actif')
    expired_ids = []
    for card in active_cards.values('id', 'expiration_date'):
        expiry_limit = card['expiration_date'] + relativedelta(months=1)
        if today >= expiry_limit:
            expired_ids.append(card['id'])

    if expired_ids:
        Card.objects.filter(id__in=expired_ids).update(status='inactif')

    expired_count = len(expired_ids)
    if expired_count > 0:
        logger.info(f"Card expiration check: {expired_count} cards marked as inactif (bulk).")
    return expired_count


# ---------------------------------------------------------------------------
# Push notification tasks
# ---------------------------------------------------------------------------

@shared_task
def send_push_notification_task(user_id, title, body, data=None, notification_type="system"):
    """Async wrapper for sending a push notification to a single user."""
    from .push_service import send_push_to_user
    send_push_to_user(user_id, title, body, data or {}, notification_type)


@shared_task
def send_push_to_admins_task(title, body, data=None, notification_type="system"):
    """Async wrapper for sending a push notification to all admins."""
    from .push_service import send_push_to_admins
    send_push_to_admins(title, body, data or {}, notification_type)
