"""Serializers for push notifications and device registration."""
from rest_framework import serializers

from notifications.models import PushToken, PushNotification


class PushTokenSerializer(serializers.ModelSerializer):
    class Meta:
        model = PushToken
        fields = ('id', 'token', 'platform', 'is_active', 'created_at')
        read_only_fields = ('id', 'is_active', 'created_at')


class RegisterDeviceSerializer(serializers.Serializer):
    """Body for POST /user/device/register/."""
    token = serializers.CharField(max_length=255)
    platform = serializers.ChoiceField(choices=['ios', 'android'], default='android')


class UnregisterDeviceSerializer(serializers.Serializer):
    """Body for POST /user/device/unregister/."""
    token = serializers.CharField(max_length=255)


class PushNotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = PushNotification
        fields = ('id', 'title', 'body', 'data', 'notification_type', 'is_read', 'created_at', 'read_at')
        read_only_fields = ('id', 'title', 'body', 'data', 'notification_type', 'created_at', 'read_at')
