# users/signals.py

from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from django.utils import timezone

from .utils import get_client_ip


@receiver(user_logged_in)
def notify_admin_login(sender, request, user, **kwargs):
    """Queue an admin-login alert email (IP + geolocation) via Celery.

    The blocking geolocation HTTP call runs inside the task so the login
    request is never delayed.
    """
    is_admin_path = False
    if request:
        path = request.path.lower()
        is_admin_path = 'admin' in path or 'cadmin' in path or 'csw-sp-v2' in path

    if not (user.is_staff or user.is_superuser or is_admin_path):
        return

    ip = get_client_ip(request)
    from notifications.tasks import notify_admin_login_task
    notify_admin_login_task.delay(user.id, ip, timezone.now().isoformat())
