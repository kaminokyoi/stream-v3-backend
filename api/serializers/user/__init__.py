"""Serializers for user-facing API endpoints (/api/v1/user/*).

Access masking (audit §5.7) is applied via SubscriptionAccessService,
never duplicated. The serializers below are thin: they validate input
and delegate business logic to services.
"""
from rest_framework import serializers

from core.models import Review
from payments.models import Order, Subscription, PaymentProof, GiftCode


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

class ProfileUpdateSerializer(serializers.Serializer):
    """Email update (optional field, validated server-side)."""
    email = serializers.EmailField(required=False, allow_blank=True)


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------

class OrderCreateSerializer(serializers.Serializer):
    """Purchase init: validates input and delegates price calculation to core.utils."""
    platform = serializers.CharField(max_length=128)
    duration = serializers.CharField(max_length=8)
    type = serializers.CharField(max_length=100, default='mutual')
    sub_type = serializers.CharField(max_length=50, required=False, allow_blank=True, default='')
    gift_code = serializers.CharField(max_length=50, required=False, allow_blank=True, default='')

    def validate(self, attrs):
        from core.utils import calculate_price
        platform = attrs['platform'].strip()
        duration = attrs['duration'].lower().strip()
        account_type = attrs['type'].strip().lower()
        sub_type = (attrs.get('sub_type') or '').strip()

        if not platform or not duration:
            raise serializers.ValidationError("Plateforme et durée sont requises.")

        price = calculate_price(platform, duration, account_type, sub_type)
        if price <= 0:
            raise serializers.ValidationError("Erreur de calcul du prix ou plateforme invalide.")
        attrs['price'] = price
        attrs['platform'] = platform
        attrs['duration'] = duration
        attrs['type'] = account_type
        attrs['sub_type'] = sub_type
        return attrs


class OrderSerializer(serializers.ModelSerializer):
    """Read serializer for orders (user's own orders only)."""
    status_label = serializers.CharField(source='get_status_display', read_only=True)
    motif_label = serializers.CharField(source='get_motif_display', read_only=True)

    class Meta:
        model = Order
        fields = (
            'id', 'order_id', 'platform', 'price', 'duration', 'type',
            'purchase_date', 'status', 'status_label', 'motif', 'motif_label',
        )
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Renewal
# ---------------------------------------------------------------------------

class RenewalCreateSerializer(serializers.Serializer):
    """Renewal init: creates a new order linked to an existing subscription."""
    duration = serializers.CharField(max_length=8)
    sub_type = serializers.CharField(max_length=50, required=False, allow_blank=True, default='')
    type = serializers.CharField(max_length=100, required=False, allow_blank=True, default='')
    gift_code = serializers.CharField(max_length=50, required=False, allow_blank=True, default='')

    def validate(self, attrs):
        attrs['duration'] = attrs['duration'].lower().strip()
        if not attrs['duration']:
            raise serializers.ValidationError("Durée manquante.")
        return attrs


# ---------------------------------------------------------------------------
# Payment proof upload
# ---------------------------------------------------------------------------

class PaymentProofUploadSerializer(serializers.Serializer):
    """Manual payment proof upload (1-2 screenshots)."""
    proof_image = serializers.ImageField()
    proof_image2 = serializers.ImageField(required=False, allow_null=True)


# ---------------------------------------------------------------------------
# Gift code verification
# ---------------------------------------------------------------------------

class GiftCodeVerifySerializer(serializers.Serializer):
    """Verify a gift code and return granted days."""
    code = serializers.CharField(max_length=50)
    platform = serializers.CharField(max_length=128, required=False, allow_blank=True, default='')

    def validate(self, attrs):
        code = attrs['code'].strip()
        platform = attrs.get('platform', '').strip() or None
        if not code:
            raise serializers.ValidationError("Code requis.")
        try:
            gift = GiftCode.objects.get(code=code)
        except GiftCode.DoesNotExist:
            raise serializers.ValidationError("Code introuvable.")
        if not gift.is_valid(platform):
            raise serializers.ValidationError(
                "Code expiré, désactivé ou non valable pour cette plateforme."
            )
        attrs['days'] = gift.days
        return attrs


# ---------------------------------------------------------------------------
# Reviews
# ---------------------------------------------------------------------------

class ReviewSubmitSerializer(serializers.Serializer):
    """Review submission (stars + optional comment). Bonus handled by ReviewService."""
    stars = serializers.IntegerField(min_value=1, max_value=5)
    comment = serializers.CharField(required=False, allow_blank=True, default='')


class ReviewMeSerializer(serializers.ModelSerializer):
    """Read serializer for the current user's review."""
    class Meta:
        model = Review
        fields = ('id', 'stars', 'comment', 'create_at')
        read_only_fields = fields
