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

    def validate_country_code(self, value):
        return value.lstrip('+') if value else value


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


class NoopPasswordResetEmail:
    """Replaces Djoser's default password-reset email.

    The reset link is dispatched by PasswordResetSerializer through the
    notification task (email to the user, or email to admins when the user
    has no email address), so Djoser's own email is a no-op.
    """

    def __init__(self, request=None, context=None, template_name=None, *args, **kwargs):
        pass

    def send(self, to, from_email=None, **kwargs):
        return None


class PasswordResetSerializer(serializers.Serializer):
    """Phone-based password reset (POST /auth/users/reset_password/).

    Looks up the user by phone_number and dispatches a reset link
    (uidb64 + token) through the existing notification task: email when the
    user has one, otherwise an email to the admins plus a push. Always
    returns 204 so phone numbers are not enumerable.
    """
    phone_number = serializers.CharField()

    def get_user(self, is_active=True):
        return User.objects.filter(
            phone_number=self.data.get('phone_number', ''),
            is_active=is_active,
        ).first()

    def save(self, **kwargs):
        user = self.get_user()
        if not user:
            return None
        from django.conf import settings
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode
        from notifications.tasks import send_password_reset_link_task
        token = default_token_generator.make_token(user)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        frontend_url = getattr(settings, 'FRONTEND_URL', 'https://streampartner.in')
        reset_url = f"{frontend_url}/password-reset/complete?uid={uid}&token={token}"
        try:
            send_password_reset_link_task.apply(args=[user.id, reset_url])
        except Exception:
            pass
        return user
