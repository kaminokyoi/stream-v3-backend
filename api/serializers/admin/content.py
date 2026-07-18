"""Admin serializers: content + giftcodes + reviews + payment numbers + messaging."""
from rest_framework import serializers

from core.models import Platform, PriceTier, Faq, Review
from payments.models import GiftCode, PaymentNumber
from dashboard.models import Notification, Message


# ---------------------------------------------------------------------------
# Platforms + Price tiers
# ---------------------------------------------------------------------------

class AdminPriceTierSerializer(serializers.ModelSerializer):
    prices = serializers.SerializerMethodField()

    class Meta:
        model = PriceTier
        fields = ('id', 'platform', 'account_type', 'category', 'base_price',
                  'category_description', 'prices')

    def get_prices(self, obj):
        return obj.computed_prices()


class AdminPlatformSerializer(serializers.ModelSerializer):
    class Meta:
        model = Platform
        fields = ('id', 'name', 'sub', 'poster', 'video', 'has_personal', 'order')


class AdminReviewSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = ('id', 'user', 'user_name', 'stars', 'comment', 'create_at')
        read_only_fields = ('create_at',)

    def get_user_name(self, obj):
        return obj.user.get_full_name() if obj.user else None


class AdminFaqSerializer(serializers.ModelSerializer):
    class Meta:
        model = Faq
        fields = ('id', 'question', 'answer')


# ---------------------------------------------------------------------------
# Gift codes
# ---------------------------------------------------------------------------

class AdminGiftCodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = GiftCode
        fields = ('id', 'code', 'days', 'platform', 'start_date', 'end_date',
                  'status', 'usage_limit', 'used_count')


# ---------------------------------------------------------------------------
# Payment numbers
# ---------------------------------------------------------------------------

class AdminPaymentNumberSerializer(serializers.ModelSerializer):
    provider_label = serializers.CharField(source='get_provider_display', read_only=True)

    class Meta:
        model = PaymentNumber
        fields = ('id', 'provider', 'provider_label', 'number', 'name',
                  'is_active', 'created_at')
        read_only_fields = ('created_at',)


# ---------------------------------------------------------------------------
# Messaging: Notification + Message
# ---------------------------------------------------------------------------

class AdminNotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ('id', 'title', 'message', 'notification_type', 'channel',
                  'image', 'created_at', 'queued')
        read_only_fields = ('created_at',)


class AdminMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = ('id', 'subject', 'message', 'message_type', 'channel',
                  'created_at', 'queued')
        read_only_fields = ('created_at',)


class SendMessagingSerializer(serializers.Serializer):
    """Body for the send-notification / send-message action."""
    recipients = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        help_text="List of user IDs. If omitted with send_to_all=true, sends to all."
    )
    send_to_all = serializers.BooleanField(default=False)
    channel = serializers.CharField(max_length=64, required=False, allow_blank=True)
