"""Push notification service — sends Expo push notifications and stores records."""
import logging
from typing import List, Dict, Optional

import requests
from django.utils import timezone

from notifications.models import PushToken, PushNotification

logger = logging.getLogger(__name__)

EXPO_PUSH_URL = "https://exp.host/--/api/v2/ios/sendPushNotification"


def _send_to_expo(tokens: List[str], title: str, body: str, data: Dict) -> Dict:
    """Send push to Expo's API. Returns the JSON response."""
    if not tokens:
        return {"sent": 0}

    messages = []
    for token in tokens:
        messages.append({
            "to": token,
            "title": title,
            "body": body,
            "data": data or {},
            "sound": "default",
            "priority": "high",
        })

    try:
        resp = requests.post(
            EXPO_PUSH_URL,
            json=messages,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=10,
        )
        resp.raise_for_status()
        result = resp.json()
        logger.info(f"Push sent to {len(tokens)} device(s): {result.get('data', [])}")
        return result
    except requests.RequestException as e:
        logger.error(f"Push send failed for {len(tokens)} token(s): {e}")
        return {"error": str(e), "sent": 0}


def send_push_to_user(user_id: int, title: str, body: str, data: Dict, notification_type: str = "system") -> None:
    """Send a push notification to a single user (all their active devices).

    Also stores a PushNotification record for history/read tracking.
    """
    from users.models import User
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        logger.warning(f"Push: user {user_id} not found")
        return

    tokens = list(
        PushToken.objects.filter(user=user, is_active=True)
        .values_list('token', flat=True)
    )

    if not tokens:
        logger.info(f"Push: no active tokens for user {user_id}, storing notification only")
    else:
        _send_to_expo(tokens, title, body, data)

    PushNotification.objects.create(
        user=user,
        title=title,
        body=body,
        data=data or {},
        notification_type=notification_type,
    )


def send_push_to_admins(title: str, body: str, data: Dict, notification_type: str = "system") -> None:
    """Send a push notification to all admin users (is_staff or is_superuser).

    Stores a PushNotification record per admin for history/read tracking.
    Uses bulk operations for efficiency.
    """
    from users.models import User
    from django.db.models import Q
    admin_ids = list(
        User.objects.filter(is_active=True)
        .filter(Q(is_staff=True) | Q(is_superuser=True))
        .values_list('id', flat=True)
        .distinct()
    )

    if not admin_ids:
        return

    # Bulk-fetch all admin tokens in 1 query
    all_tokens = list(
        PushToken.objects.filter(user_id__in=admin_ids, is_active=True)
        .values_list('token', flat=True)
    )
    if all_tokens:
        _send_to_expo(all_tokens, title, body, data)

    # Bulk-create PushNotification records
    notifs = [
        PushNotification(
            user_id=uid,
            title=title,
            body=body,
            data=data or {},
            notification_type=notification_type,
        )
        for uid in admin_ids
    ]
    PushNotification.objects.bulk_create(notifs)


def send_push_notification(user_ids: List[int], title: str, body: str, data: Dict, notification_type: str = "system") -> None:
    """Send push to multiple users by ID."""
    for uid in user_ids:
        send_push_to_user(uid, title, body, data, notification_type)


def deactivate_token(token: str) -> None:
    """Mark a push token as inactive (e.g. when user logs out)."""
    PushToken.objects.filter(token=token).update(is_active=False)


def remove_token(token: str) -> None:
    """Delete a push token entirely."""
    PushToken.objects.filter(token=token).delete()
