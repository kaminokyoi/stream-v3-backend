"""Admin serializers: users + orders + proofs."""
from rest_framework import serializers

from users.models import User
from payments.models import Order, PaymentProof


class AdminUserSerializer(serializers.ModelSerializer):
    """Admin user listing with subscription counts."""
    active_subs_count = serializers.IntegerField(read_only=True)
    expired_subs_count = serializers.IntegerField(read_only=True)
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            'id', 'phone_number', 'country_code', 'first_name', 'last_name',
            'full_name', 'email', 'total_orders', 'total_subscriptions',
            'is_active', 'is_staff', 'is_superuser', 'is_admin',
            'active_subs_count', 'expired_subs_count', 'date_joined',
        )
        read_only_fields = ('id', 'total_orders', 'total_subscriptions', 'date_joined')

    def get_full_name(self, obj):
        return obj.get_full_name()


class AdminUserCreateSerializer(serializers.ModelSerializer):
    """Admin creates a user with a phone + password."""
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = User
        fields = (
            'id', 'phone_number', 'country_code', 'first_name', 'last_name',
            'email', 'password', 'is_active', 'is_staff', 'is_superuser',
        )

    def create(self, validated_data):
        password = validated_data.pop('password', '')
        user = User(**validated_data)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save()
        return user


class AdminOrderSerializer(serializers.ModelSerializer):
    """Admin order listing."""
    user_name = serializers.SerializerMethodField()
    user_phone = serializers.SerializerMethodField()
    status_label = serializers.CharField(source='get_status_display', read_only=True)
    motif_label = serializers.CharField(source='get_motif_display', read_only=True)
    type_label = serializers.CharField(source='get_type_display', read_only=True)

    class Meta:
        model = Order
        fields = (
            'id', 'order_id', 'user', 'user_name', 'user_phone', 'platform',
            'price', 'duration', 'type', 'type_label', 'purchase_date',
            'status', 'status_label', 'motif', 'motif_label',
            'renewal_from', 'gift_code', 'subscription',
        )
        read_only_fields = ('order_id', 'purchase_date', 'renewal_from', 'gift_code', 'subscription')

    def get_user_name(self, obj):
        return obj.user.get_full_name() if obj.user else None

    def get_user_phone(self, obj):
        return obj.user.get_phone_number() if obj.user else None


class AdminPaymentProofSerializer(serializers.ModelSerializer):
    """Admin proof listing (with order + user info)."""
    order_platform = serializers.CharField(source='order.platform', read_only=True)
    order_price = serializers.IntegerField(source='order.price', read_only=True)
    order_duration = serializers.CharField(source='order.duration', read_only=True)
    order_motif = serializers.CharField(source='order.motif', read_only=True)
    user_name = serializers.SerializerMethodField()
    user_phone = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()
    image2_url = serializers.SerializerMethodField()
    validated_by_name = serializers.SerializerMethodField()

    class Meta:
        model = PaymentProof
        fields = (
            'id', 'order', 'order_platform', 'order_price', 'order_duration',
            'order_motif', 'user_name', 'user_phone', 'image', 'image_url', 'image2', 'image2_url',
            'submitted_at', 'validated', 'validated_by', 'validated_by_name',
            'validated_at', 'rejected', 'rejection_reason',
        )
        read_only_fields = ('submitted_at', 'validated_at', 'validated_by')

    def get_user_name(self, obj):
        return obj.order.user.get_full_name() if obj.order and obj.order.user else None

    def get_user_phone(self, obj):
        return obj.order.user.get_phone_number() if obj.order and obj.order.user else None

    def get_image_url(self, obj):
        return obj.image.url if obj.image else None

    def get_image2_url(self, obj):
        return obj.image2.url if obj.image2 else None

    def get_validated_by_name(self, obj):
        return obj.validated_by.get_full_name() if obj.validated_by else None


class RejectProofSerializer(serializers.Serializer):
    """Serializer for the reject-proof action body."""
    reason = serializers.CharField(required=False, allow_blank=True, default='Refusé')
