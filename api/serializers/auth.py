"""Custom Djoser serializers for the phone-based User model.

Djoser defaults to email auth; we override to expose phone_number,
country_code and names instead. Email stays optional (for notifications).
"""
from djoser.serializers import UserCreatePasswordRetypeSerializer, UserSerializer as DjoserUserSerializer
from rest_framework import serializers

from users.models import User


class UserCreateSerializer(UserCreatePasswordRetypeSerializer):
    """Registration serializer: phone_number is the unique identifier."""
    class Meta(UserCreatePasswordRetypeSerializer.Meta):
        model = User
        fields = (
            'id',
            'phone_number',
            'country_code',
            'first_name',
            'last_name',
            'email',
            'password',
        )
        extra_kwargs = {
            'email': {'required': False, 'allow_blank': True},
            'password': {'write_only': True},
        }


class UserSerializer(DjoserUserSerializer):
    """Serializer for /auth/users/me/ (current authenticated user)."""
    class Meta(DjoserUserSerializer.Meta):
        model = User
        fields = (
            'id',
            'phone_number',
            'country_code',
            'first_name',
            'last_name',
            'email',
            'total_orders',
            'total_subscriptions',
            'is_staff',
            'is_superuser',
            'date_joined',
        )
        read_only_fields = (
            'id',
            'total_orders',
            'total_subscriptions',
            'is_staff',
            'is_superuser',
            'date_joined',
        )
