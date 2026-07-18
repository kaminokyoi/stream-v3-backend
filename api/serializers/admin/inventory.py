"""Admin serializers: subscriptions + accounts + profiles + markers."""
from rest_framework import serializers

from payments.models import Subscription, SubscriptionMarker, SubscriptionProfileHistory
from products.models import Account, Profile


class AdminSubscriptionMarkerSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionMarker
        fields = ('id', 'name', 'color')


class AdminSubscriptionProfileHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionProfileHistory
        fields = (
            'id', 'profile_number', 'profile_code', 'account_number',
            'platform', 'linked_at', 'unlinked_at',
        )


class AdminSubscriptionSerializer(serializers.ModelSerializer):
    """Admin subscription listing (no access masking)."""
    user_name = serializers.SerializerMethodField()
    user_phone = serializers.SerializerMethodField()
    platform = serializers.CharField(source='order.platform', read_only=True)
    duration = serializers.CharField(source='order.duration', read_only=True)
    type = serializers.CharField(source='order.type', read_only=True)
    price = serializers.IntegerField(source='order.price', read_only=True)
    profile_number = serializers.CharField(source='profile.number', read_only=True, default='')
    profile_code = serializers.CharField(source='profile.code', read_only=True, default='')
    account_number = serializers.SerializerMethodField()
    markers = AdminSubscriptionMarkerSerializer(many=True, read_only=True)

    class Meta:
        model = Subscription
        fields = (
            'id', 'user', 'user_name', 'user_phone', 'order', 'platform',
            'duration', 'type', 'price', 'expiration_date', 'status',
            'profile', 'profile_number', 'profile_code', 'account_number',
            'markers',
        )
        read_only_fields = ('order',)

    def get_user_name(self, obj):
        return obj.user.get_full_name() if obj.user else None

    def get_user_phone(self, obj):
        return obj.user.get_phone_number() if obj.user else None

    def get_account_number(self, obj):
        return obj.profile.account.number if obj.profile and obj.profile.account else ''


class AdminSubscriptionCreateSerializer(serializers.ModelSerializer):
    """Admin manual subscription creation."""
    class Meta:
        model = Subscription
        fields = ('id', 'user', 'order', 'expiration_date', 'profile', 'status')
        extra_kwargs = {
            'status': {'default': 'active'},
        }


class ChangeProfileSerializer(serializers.Serializer):
    """Serializer for the change-profile action body."""
    profile_id = serializers.IntegerField()


class MarkSubscriptionSerializer(serializers.Serializer):
    """Serializer for the mark action body."""
    marker_name = serializers.CharField(max_length=100)
    marker_color = serializers.CharField(max_length=20, required=False, default='#ffffff')


class AdminRenewSerializer(serializers.Serializer):
    """Serializer for the admin-renew action body."""
    duration = serializers.CharField(max_length=8, default='1 mois')


class AdminAccountSerializer(serializers.ModelSerializer):
    """Admin account listing (full credentials visible)."""
    used_places = serializers.IntegerField(read_only=True)
    available_places = serializers.IntegerField(read_only=True)
    current_remaining_days = serializers.IntegerField(read_only=True)
    card = serializers.SerializerMethodField()
    markers = serializers.SerializerMethodField()

    class Meta:
        model = Account
        fields = (
            'id', 'number', 'platform', 'email', 'password', 'profiles',
            'max_profile', 'type', 'place', 'start_date', 'end_date',
            'month_count', 'card', 'markers', 'remaining_day', 'current_remaining_days',
            'used_places', 'available_places', 'status', 'created_at',
        )
        read_only_fields = ('remaining_day', 'created_at')

    def get_card(self, obj):
        if obj.card_id:
            return {'id': obj.card_id, 'nom': obj.card.nom, 'telephone': obj.card.telephone}
        return None

    def get_markers(self, obj):
        from api.serializers.admin.cards import AdminAccountMarkerSerializer
        return AdminAccountMarkerSerializer(obj.markers.all(), many=True).data


class AdminProfileSubscriptionSerializer(serializers.ModelSerializer):
    """Lightweight subscription info for profile occupation display."""
    user_name = serializers.SerializerMethodField()
    has_markers = serializers.SerializerMethodField()

    class Meta:
        model = Subscription
        fields = ('id', 'user_name', 'expiration_date', 'status', 'has_markers')

    def get_user_name(self, obj):
        return obj.user.get_full_name() if obj.user else None

    def get_has_markers(self, obj):
        return obj.markers.exists()


class AdminProfileSerializer(serializers.ModelSerializer):
    """Admin profile listing."""
    account_platform = serializers.CharField(source='account.platform', read_only=True)
    active_subscriptions_count = serializers.SerializerMethodField()
    active_subscriptions = serializers.SerializerMethodField()

    class Meta:
        model = Profile
        fields = (
            'id', 'number', 'code', 'account', 'account_platform', 'place',
            'created_at', 'active_subscriptions_count', 'active_subscriptions',
        )
        read_only_fields = ('created_at',)

    def get_active_subscriptions_count(self, obj):
        return obj.subscriptions.filter(status__in=['active', 'expired']).count()

    def get_active_subscriptions(self, obj):
        subs = obj.subscriptions.filter(status__in=['active', 'expired']).select_related('user').prefetch_related('markers')
        return AdminProfileSubscriptionSerializer(subs, many=True).data
