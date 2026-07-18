"""User-facing views: device registration + push notification history."""
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from notifications.models import PushToken, PushNotification
from notifications.push_service import deactivate_token
from api.serializers.user.notifications import (
    PushTokenSerializer,
    RegisterDeviceSerializer,
    UnregisterDeviceSerializer,
    PushNotificationSerializer,
)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def register_device(request):
    """Register a push token for the authenticated user."""
    serializer = RegisterDeviceSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    token = serializer.validated_data['token']
    platform = serializer.validated_data['platform']

    obj, created = PushToken.objects.update_or_create(
        token=token,
        defaults={
            'user': request.user,
            'platform': platform,
            'is_active': True,
        },
    )

    return Response({
        'detail': 'Token enregistré.' if created else 'Token mis à jour.',
        'id': obj.id,
    }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def unregister_device(request):
    """Deactivate a push token (on logout)."""
    serializer = UnregisterDeviceSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    token = serializer.validated_data['token']
    deactivate_token(token)
    return Response({'detail': 'Token désactivé.'})


class PushNotificationListView(generics.ListAPIView):
    """List push notifications for the authenticated user."""
    serializer_class = PushNotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = PushNotification.objects.filter(user=self.request.user)
        is_read = self.request.GET.get('is_read')
        if is_read is not None:
            qs = qs.filter(is_read=is_read == 'true')
        notification_type = self.request.GET.get('type')
        if notification_type:
            qs = qs.filter(notification_type=notification_type)
        return qs


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mark_notification_read(request, pk=None):
    """Mark a single notification as read."""
    try:
        notif = PushNotification.objects.get(id=pk, user=request.user)
    except PushNotification.DoesNotExist:
        return Response({'detail': 'Notification introuvable.'}, status=status.HTTP_404_NOT_FOUND)
    notif.is_read = True
    notif.read_at = timezone.now()
    notif.save(update_fields=['is_read', 'read_at'])
    return Response({'detail': 'Marquée comme lue.'})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def mark_all_notifications_read(request):
    """Mark all unread notifications as read for the authenticated user."""
    count = PushNotification.objects.filter(user=request.user, is_read=False).update(
        is_read=True,
        read_at=timezone.now(),
    )
    return Response({'detail': f'{count} notification(s) marquée(s) comme lue(s).'})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def unread_notifications_count(request):
    """Get the count of unread notifications."""
    count = PushNotification.objects.filter(user=request.user, is_read=False).count()
    return Response({'count': count})
