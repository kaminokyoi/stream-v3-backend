"""
Celery tasks for the dashboard app.

Responsibilities (after refactor):
- Weekly/monthly PDF analytics reports (WeasyPrint)
- Bulk messaging to selected users (Notification / Message models)

Generic email sending lives in `notifications.tasks`.
Subscription lifecycle automation lives in `payments.tasks`.
"""
import os
from io import BytesIO

from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from weasyprint import HTML
from logging import getLogger

logger = getLogger(__name__)

DASHBOARD_URL = "https://streampartner.in/dashboard/"


# ---------------------------------------------------------------------------
# Analytics report tasks
# ---------------------------------------------------------------------------

def _generate_and_send_report(period_days):
    """Generate the PDF analytics report and email it."""
    import base64
    from dashboard.report import collect_report_data

    data = collect_report_data(period_days)

    # Load the logo for WeasyPrint (base64-inlined SVG)
    logo_uri = None
    logo_path = os.path.join(settings.BASE_DIR, 'dashboard', 'static', 'images', 'st.svg')
    if os.path.exists(logo_path):
        try:
            with open(logo_path, 'r', encoding='utf-8') as f:
                svg_content = f.read()
                b64_svg = base64.b64encode(svg_content.encode('utf-8')).decode('utf-8')
                logo_uri = f"data:image/svg+xml;base64,{b64_svg}"
        except Exception as e:
            logger.error(f"Failed to read logo: {e}")

    html_string = render_to_string('dashboard/report_pdf.html', {'data': data, 'logo_uri': logo_uri})

    pdf_file = BytesIO()
    HTML(string=html_string, base_url="").write_pdf(pdf_file)
    pdf_file.seek(0)

    to_email = getattr(settings, 'REPORT_RECIPIENT_EMAIL', 'streampartnernotif@gmail.com')
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'Stream Partner <hello@contact.streampartner.in>')

    subject = f"Stream Partner - Rapport Analytique ({period_days} derniers jours)"
    body = (
        f"Bonjour,\n\n"
        f"Veuillez trouver ci-joint votre rapport analytique Stream Partner pour "
        f"les {period_days} derniers jours.\n\n"
        f"Cordialement,\nLe système automatisé Stream Partner."
    )
    email = EmailMessage(subject=subject, body=body, from_email=from_email, to=[to_email])
    email.attach(f"Stream_Partner_Report_{period_days}d.pdf", pdf_file.read(), 'application/pdf')
    logger.info(f"Sending email report to {to_email}")
    email.send(fail_silently=False)


@shared_task
def send_report_email_task():
    """Send the weekly PDF analytics report by email."""
    try:
        period_days = getattr(settings, 'REPORT_PERIOD_DAYS', 7)
        _generate_and_send_report(period_days)
        return True
    except Exception as e:
        logger.error(f"Erreur génération/envoi rapport PDF hebdomadaire: {e}")
        return False


@shared_task
def send_report_email_end_of_month_task():
    """Send the monthly PDF analytics report (last day of month only)."""
    from django.utils import timezone
    import calendar

    today = timezone.now().date()
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    if today.day != days_in_month:
        logger.info(f"Not the last day of the month ({today.day}/{days_in_month}), skipping monthly report.")
        return False
    try:
        _generate_and_send_report(days_in_month)
        return True
    except Exception as e:
        logger.error(f"Erreur génération/envoi rapport PDF mensuel: {e}")
        return False


# ---------------------------------------------------------------------------
# Bulk messaging tasks
# ---------------------------------------------------------------------------

@shared_task
def send_bulk_notification_task(notification_id, user_ids):
    """Send a Notification to selected users via email."""
    from dashboard.models import Notification
    from users.models import User
    from notifications.services import send_bulk_email

    try:
        notif = Notification.objects.get(id=notification_id)
        users = User.objects.filter(id__in=user_ids)
        sent = send_bulk_email(
            users=users,
            subject=notif.title,
            text_body=notif.message,
            template_name='notifications/emails/bulk_message.html',
            context_builder=lambda u: {'user': u, 'content': notif.message, 'dashboard_url': DASHBOARD_URL},
        )
        notif.queued = True
        notif.save()
        logger.info(f"Notification {notification_id} queued for {sent} users")
        return sent
    except Notification.DoesNotExist:
        logger.error(f"Notification {notification_id} not found")
        return 0


@shared_task
def send_bulk_message_task(message_id, user_ids):
    """Send a Message to selected users via email."""
    from dashboard.models import Message
    from users.models import User
    from notifications.services import send_bulk_email

    try:
        msg = Message.objects.get(id=message_id)
        users = User.objects.filter(id__in=user_ids)
        sent = send_bulk_email(
            users=users,
            subject=msg.subject,
            text_body=msg.message,
            template_name='notifications/emails/bulk_message.html',
            context_builder=lambda u: {'user': u, 'content': msg.message, 'dashboard_url': DASHBOARD_URL},
        )
        msg.queued = True
        msg.save()
        logger.info(f"Message {message_id} queued for {sent} users")
        return sent
    except Message.DoesNotExist:
        logger.error(f"Message {message_id} not found")
        return 0
