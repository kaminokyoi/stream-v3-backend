"""Serializers for public endpoints (no auth required)."""
from rest_framework import serializers

from core.models import Platform, PriceTier, Review, Faq


class PriceTierSerializer(serializers.ModelSerializer):
    """Computed prices derived from base_price (audit §5.2)."""
    prices = serializers.SerializerMethodField()

    class Meta:
        model = PriceTier
        fields = ('account_type', 'category', 'category_description', 'base_price', 'prices')

    def get_prices(self, obj):
        return obj.computed_prices()


class PlatformPricingSerializer(serializers.ModelSerializer):
    """Platform with full pricing structure (shared + personal categories)."""
    shared_prices = serializers.SerializerMethodField()
    personal_prices = serializers.SerializerMethodField()
    has_personal = serializers.BooleanField()

    class Meta:
        model = Platform
        fields = ('id', 'name', 'sub', 'has_personal', 'shared_prices', 'personal_prices')

    def get_shared_prices(self, obj):
        return obj.get_shared_prices()

    def get_personal_prices(self, obj):
        return obj.get_personal_prices()


class PlatformListSerializer(serializers.ModelSerializer):
    """Platform listing with pricing for catalogues."""
    shared_prices = serializers.SerializerMethodField()
    personal_prices = serializers.SerializerMethodField()
    has_personal = serializers.BooleanField()

    class Meta:
        model = Platform
        fields = ('id', 'name', 'sub', 'has_personal', 'order',
                  'shared_prices', 'personal_prices')

    def get_shared_prices(self, obj):
        return obj.get_shared_prices()

    def get_personal_prices(self, obj):
        return obj.get_personal_prices()


class ReviewPublicSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = ('id', 'user_name', 'stars', 'comment', 'create_at')

    def get_user_name(self, obj):
        return obj.user.get_full_name() if obj.user else None


class FaqSerializer(serializers.ModelSerializer):
    class Meta:
        model = Faq
        fields = ('id', 'question', 'answer')
