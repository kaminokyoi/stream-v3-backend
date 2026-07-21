"""Admin serializers: cards + account markers."""
from rest_framework import serializers

from products.models import Card, AccountMarker


class AdminAccountMarkerSerializer(serializers.ModelSerializer):
    class Meta:
        model = AccountMarker
        fields = ('id', 'name', 'color')


class AdminCardSerializer(serializers.ModelSerializer):
    """Admin card listing with decrypted numero + computed properties."""
    masked_numero = serializers.SerializerMethodField()
    formatted_numero = serializers.SerializerMethodField()
    linked_accounts = serializers.SerializerMethodField()

    class Meta:
        model = Card
        fields = (
            'id', 'numero', 'masked_numero', 'formatted_numero',
            'nom', 'cvv', 'telephone', 'expiration_date', 'status',
            'linked_accounts', 'created_at',
        )
        read_only_fields = ('created_at',)

    def get_masked_numero(self, obj):
        numero = obj.numero
        if not numero or numero.startswith('gAAAAA'):
            return '**** **** **** ****'
        return obj.masked_numero

    def get_formatted_numero(self, obj):
        numero = obj.numero
        if not numero or numero.startswith('gAAAAA'):
            return 'Erreur de déchiffrement'
        return obj.formatted_numero

    def get_linked_accounts(self, obj):
        return list(obj.account_set.values_list('number', flat=True))
