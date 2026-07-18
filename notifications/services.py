"""
Notification services for StreamPartner.

Centralized, synchronous helpers that render email templates and dispatch
them asynchronously via `notifications.tasks.send_email_task`.

All subscription lifecycle emails, admin alerts, password-reset and bulk
messaging flow through here. No app should import notification logic from
elsewhere.
"""
import logging

from django.template.loader import render_to_string

from .tasks import send_email_task, send_push_notification_task, send_push_to_admins_task

logger = logging.getLogger(__name__)

WHATSAPP_URL = "https://wa.me/237680610819"
DASHBOARD_URL = "https://streampartner.in/dashboard/"


def _send_email(user, subject, template_name, context):
    """Render an email template and queue it for sending via Celery."""
    email = getattr(user, 'email', None)
    if not email:
        logger.warning(f"No email for user {getattr(user, 'id', '?')}, skipping notification")
        return
    html_message = render_to_string(template_name, context)
    send_email_task.delay(email, subject, subject, html_message)


def _push_user(user, title, body, data, notification_type="system"):
    """Queue a push notification to a user (async, non-blocking)."""
    if not user or not getattr(user, 'id', None):
        return
    send_push_notification_task.delay(user.id, title, body, data, notification_type)


def _push_admins(title, body, data, notification_type="system"):
    """Queue a push notification to all admins (async, non-blocking)."""
    send_push_to_admins_task.delay(title, body, data, notification_type)


# ---------------------------------------------------------------------------
# Subscription lifecycle notifications
# ---------------------------------------------------------------------------

def notify_purchase_received(order):
    """Sent after a user submits a payment proof."""
    user = order.user
    if not user:
        return
    is_renewal = getattr(order, 'renewal_from', None) is not None
    notify_admin_subscription_purchase(
        user_name=user.get_full_name(),
        user_phone=user.get_phone_number(),
        platform=order.platform,
        duration=order.duration,
        subscription_type=order.type,
        action='renouvellement' if is_renewal else 'achat',
    )
    context = {
        'user': user,
        'order': {
            'id': order.id,
            'platform_name': order.platform,
            'duration': order.duration,
            'price': order.price,
        },
    }
    _send_email(user, "Confirmation de commande", "notifications/emails/order_received.html", context)
    _push_user(user, "Commande reçue", f"{order.platform} — {order.duration} — {order.price} FCFA",
               {"screen": "orders", "type": "order", "resource_id": order.id}, "order")


def notify_payment_validated(order):
    """Sent after a payment proof is validated."""
    user = order.user
    if not user:
        return
    context = {
        'user': user,
        'order': {
            'id': order.id,
            'platform_name': order.platform,
            'duration': order.duration,
            'price': order.price,
        },
    }
    _send_email(
        user,
        f"Votre commande {order.platform} pour {order.duration} a été validée",
        "notifications/emails/payment_validated.html",
        context,
    )
    _push_user(user, "Paiement confirmé", f"{order.platform} — {order.duration} — {order.price} FCFA",
               {"screen": "orders", "type": "order", "resource_id": order.id}, "order")


def notify_subscription_activated(subscription):
    """Sent when a subscription is activated (proof validated + profile assigned)."""
    user = subscription.user
    profile = subscription.profile
    order = subscription.order
    context = {
        'user': user,
        'order': {'platform_name': order.platform},
        'email': profile.account.email if profile and profile.account else 'N/A',
        'password': profile.account.password if profile and profile.account else 'N/A',
        'profile_name': profile.number if profile else None,
        'profile_pin': profile.code if profile else None,
        'expiration_date': subscription.expiration_date,
        'dashboard_url': DASHBOARD_URL,
    }
    _send_email(user, f"Vos accès {order.platform}", "notifications/emails/subscription_active.html", context)
    _push_user(user, "Abonnement activé", f"{order.platform} — Profil #{profile.number if profile else '?'}",
               {"screen": "subscriptions", "type": "subscription", "resource_id": subscription.id}, "subscription")


def notify_subscription_info_updated(subscription):
    """Sent when subscription info is updated (profile change, etc.)."""
    user = subscription.user
    platform = subscription.order.platform
    context = {
        'user': user,
        'platform_name': platform,
        'dashboard_url': DASHBOARD_URL,
    }
    _send_email(user, f"Mise à jour de vos identifiants {platform}", "notifications/emails/update_notification.html", context)
    _push_user(user, "Identifiants modifiés", f"{platform} — Vos accès ont été mis à jour",
               {"screen": "subscriptions", "type": "subscription", "resource_id": subscription.id}, "subscription")


def notify_subscription_renewed(subscription):
    """Sent after a subscription renewal or extension is completed."""
    user = subscription.user
    order = subscription.order
    context = {
        'user': user,
        'platform_name': order.platform,
        'duration': order.duration,
        'dashboard_url': DASHBOARD_URL,
    }
    if order.motif == 'extension':
        subject = f"Prolongement de votre abonnement {order.platform}"
        template = "notifications/emails/subscription_extended.html"
    else:
        subject = f"Renouvellement de votre abonnement {order.platform}"
        template = "notifications/emails/subscription_renewed.html"
    _send_email(user, subject, template, context)
    push_title = "Prolongement" if order.motif == 'extension' else "Renouvellement"
    _push_user(user, push_title, f"{order.platform} — {order.duration}",
               {"screen": "subscriptions", "type": "subscription", "resource_id": subscription.id}, "subscription")


def notify_expiring_soon(subscription):
    """Sent 3 days before a subscription expires."""
    user = subscription.user
    order = subscription.order
    context = {
        'user': user,
        'platform_name': order.platform,
        'expiration_date': subscription.expiration_date,
        'dashboard_url': DASHBOARD_URL,
        'whatsapp_url': WHATSAPP_URL,
    }
    _send_email(user, f"Fin d'abonnement {order.platform} dans 3 jours", "notifications/emails/sub_expiring_3days.html", context)
    _push_user(user, "Expiration J-3", f"{order.platform} — Expire dans 3 jours",
               {"screen": "subscriptions", "type": "subscription", "resource_id": subscription.id}, "subscription")


def notify_expiration_today(subscription):
    """Sent on the day a subscription expires."""
    user = subscription.user
    order = subscription.order
    context = {
        'user': user,
        'platform_name': order.platform,
        'expiration_date': subscription.expiration_date,
        'dashboard_url': DASHBOARD_URL,
        'whatsapp_url': WHATSAPP_URL,
    }
    _send_email(user, f"Fin de votre abonnement {order.platform} aujourd'hui", "notifications/emails/sub_expiring_today.html", context)
    _push_user(user, "Expiration aujourd'hui", f"{order.platform} — Expire aujourd'hui",
               {"screen": "subscriptions", "type": "subscription", "resource_id": subscription.id}, "subscription")


def notify_subscription_expired(subscription):
    """Sent the day after a subscription has expired."""
    user = subscription.user
    order = subscription.order
    context = {
        'user': user,
        'platform_name': order.platform,
        'expiration_date': subscription.expiration_date,
        'dashboard_url': DASHBOARD_URL,
        'whatsapp_url': WHATSAPP_URL,
    }
    _send_email(user, f"Votre abonnement {order.platform} a expiré hier", "notifications/emails/sub_expired_yesterday.html", context)
    _push_user(user, "Abonnement expiré", f"{order.platform} — Expiré",
               {"screen": "subscriptions", "type": "subscription", "resource_id": subscription.id}, "subscription")


def notify_profile_unlinked(subscription):
    """Sent when a profile is unlinked from an expired subscription."""
    user = subscription.user
    context = {
        'user': user,
        'platform_name': subscription.order.platform,
        'dashboard_url': DASHBOARD_URL,
        'whatsapp_url': WHATSAPP_URL,
    }
    _send_email(user, f"Déconnexion de votre abonnement {subscription.order.platform}", "notifications/emails/sub_profile_unlinked.html", context)
    _push_user(user, "Profil délié", f"{subscription.order.platform} — Profil délié de votre abonnement",
               {"screen": "subscriptions", "type": "subscription", "resource_id": subscription.id}, "subscription")


# ---------------------------------------------------------------------------
# Access update + password reset + admin alerts
# ---------------------------------------------------------------------------

def notify_access_update(user, platform_name=""):
    """Notify a user that the access credentials of one of their subscriptions changed."""
    if not user.email:
        return False
    context = {
        'user': user,
        'platform_name': platform_name,
        'dashboard_url': DASHBOARD_URL,
    }
    html_message = render_to_string('notifications/emails/update_notification.html', context)
    text_message = (
        f"Bonjour {user.first_name},\n\n"
        f"Nous vous informons qu'une mise à jour a été effectuée sur les informations "
        f"d'accès liées à votre abonnement {platform_name}.\n"
        f"Veuillez consulter votre espace client : {DASHBOARD_URL}"
    )
    send_email_task.delay(user.email, "Mise à jour de vos identifiants StreamPartner", text_message, html_message)
    _push_user(user, "Accès modifiés", f"{platform_name or 'Plateforme'} — Identifiants mis à jour",
               {"screen": "subscriptions", "type": "subscription"}, "subscription")
    return True


def notify_password_reset_link(user, reset_url):
    """Send a password-reset link to the user (or to admin if user has no email)."""
    from django.conf import settings
    if user.email:
        context = {'user': user, 'reset_url': reset_url}
        html_message = render_to_string('notifications/emails/password_reset.html', context)
        text_message = f"Cliquez sur ce lien pour réinitialiser votre mot de passe : {reset_url}"
        send_email_task.delay(user.email, "Réinitialisation de votre mot de passe", text_message, html_message)
        _push_user(user, "Réinitialisation mot de passe", "Un lien de réinitialisation a été envoyé par email",
                   {"screen": "settings", "type": "system"}, "system")
        return True
    admin_email = getattr(settings, 'REPORT_RECIPIENT_EMAIL', 'streampartnernotif@gmail.com')
    context = {
        'user_name': user.get_full_name(),
        'user_phone': user.get_phone_number(),
        'reset_url': reset_url,
    }
    html_message = render_to_string('notifications/emails/password_reset_admin.html', context)
    text_message = (
        f"L'utilisateur {user.get_full_name()} ({user.get_phone_number()}) "
        f"a demandé une réinitialisation de mot de passe mais n'a pas d'email.\n"
        f"Lien de réinitialisation : {reset_url}"
    )
    send_email_task.delay(
        admin_email,
        f"Réinitialisation mot de passe - {user.get_full_name()} (sans email)",
        text_message,
        html_message,
    )
    logger.info(f"Password reset link for user {user.id} (no email) sent to admin {admin_email}")
    return True


def notify_admin_subscription_purchase(user_name, user_phone, platform, duration, subscription_type, action):
    """Notify the admin inbox that a user just bought/renewed a subscription."""
    from django.conf import settings
    type_display = 'Personnel' if subscription_type == 'personal' else 'Mutualisé'
    action_display = 'acheté' if action == 'achat' else 'renouvelé'
    subject = f"{'Nouvel achat' if action == 'achat' else 'Renouvellement'} d'abonnement"
    message = (
        f"Bonjour,\n\n"
        f"Un utilisateur vient de {action_display} un abonnement :\n\n"
        f"👤 Nom : {user_name}\n"
        f"📞 Numéro : {user_phone}\n"
        f"📺 Plateforme : {platform}\n"
        f"⏱️ Durée : {duration}\n"
        f"📋 Type : {type_display}\n\n"
        f"— Stream Partner"
    )
    context = {
        'user_name': user_name,
        'user_phone': user_phone,
        'platform': platform,
        'duration': duration,
        'type_display': type_display,
        'action_display': action_display,
        'action': action,
    }
    html_message = render_to_string('notifications/emails/admin_notification.html', context)
    to_email = getattr(settings, 'SUBSCRIPTION_NOTIFICATION_EMAIL', 'streampartnernotif@gmail.com')
    send_email_task.delay(to_email, subject, message, html_message)
    logger.info(f"Admin subscription notification queued for {action} by {user_name}")
    _push_admins(
        f"{'Nouvel achat' if action == 'achat' else 'Renouvellement'}",
        f"{user_name} — {platform} — {duration} — {type_display}",
        {"screen": "orders", "type": "order"},
        "order",
    )


def notify_admin_login(user, ip, location, timestamp):
    """Alert the admin inbox about an admin/staff login (IP + geolocation)."""
    from django.conf import settings
    from django.utils import timezone as _tz
    subject = f"[Stream Partner] Connexion à l'interface d'administration"
    text_body = (
        f"Une connexion à l'interface d'administration a été détectée :\n\n"
        f"👤 Utilisateur : {user.get_full_name()}\n"
        f"📞 Téléphone : {user.phone_number}\n"
        f"📧 Email : {user.email or 'Non renseigné'}\n"
        f"🌐 Adresse IP : {ip}\n"
        f"📍 Localisation : {location}\n"
        f"⏰ Date/Heure : {timestamp.strftime('%d/%m/%Y %H:%M:%S')}\n"
    )
    html_body = f"""
    <html><body style="font-family: Arial, sans-serif; background-color: #050505; color: #ffffff; padding: 20px;">
      <div style="max-width: 600px; margin: 0 auto; background-color: #121212; border: 1px solid #333; border-radius: 12px; padding: 30px; box-shadow: 0 4px 12px rgba(0,0,0,0.5);">
        <h2 style="color: #2a9d8f; border-bottom: 1px solid #333; padding-bottom: 10px; margin-top: 0;">Connexion Admin Détectée</h2>
        <p style="color: #cccccc; font-size: 14px;">Une connexion à l'interface d'administration a été détectée avec les détails suivants :</p>
        <table style="width: 100%; border-collapse: collapse; margin-top: 20px; font-size: 14px;">
          <tr><td style="padding: 8px 0; color: #888888; width: 140px;">👤 Utilisateur :</td><td style="padding: 8px 0; color: #ffffff; font-weight: bold;">{user.get_full_name()}</td></tr>
          <tr><td style="padding: 8px 0; color: #888888;">📞 Téléphone :</td><td style="padding: 8px 0; color: #ffffff;">{user.phone_number}</td></tr>
          <tr><td style="padding: 8px 0; color: #888888;">📧 Email :</td><td style="padding: 8px 0; color: #ffffff;">{user.email or 'Non renseigné'}</td></tr>
          <tr><td style="padding: 8px 0; color: #888888;">🌐 Adresse IP :</td><td style="padding: 8px 0; color: #ffffff; font-family: monospace;">{ip}</td></tr>
          <tr><td style="padding: 8px 0; color: #888888;">📍 Localisation :</td><td style="padding: 8px 0; color: #2a9d8f; font-weight: bold;">{location}</td></tr>
          <tr><td style="padding: 8px 0; color: #888888;">⏰ Date/Heure :</td><td style="padding: 8px 0; color: #ffffff;">{timestamp.strftime('%d/%m/%Y %H:%M:%S')}</td></tr>
        </table>
        <div style="margin-top: 30px; padding-top: 15px; border-top: 1px solid #333; text-align: center; color: #555555; font-size: 12px;">Cet email a été envoyé automatiquement par Stream Partner.</div>
      </div>
    </body></html>
    """
    recipient = getattr(settings, 'REPORT_RECIPIENT_EMAIL', 'streampartnernotif@gmail.com')
    send_email_task.delay(recipient, subject, text_body, html_body)
    _push_admins(
        "Connexion admin",
        f"{user.get_full_name()} — {ip} — {location}",
        {"screen": "settings", "type": "system"},
        "system",
    )


# ---------------------------------------------------------------------------
# Bulk messaging helper (used by dashboard.tasks)
# ---------------------------------------------------------------------------

def send_bulk_email(users, subject, text_body, template_name, context_builder):
    """Generic bulk email sender.

    Iterates over `users`, renders `template_name` with `context_builder(user)`
    for each, and queues individual emails via `send_email_task`.
    """
    sent = 0
    for user in users:
        if not user.email:
            continue
        context = context_builder(user)
        html_message = render_to_string(template_name, context)
        send_email_task.delay(user.email, subject, text_body, html_message)
        sent += 1
    return sent
