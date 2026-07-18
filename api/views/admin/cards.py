"""Admin views: cards + account markers."""
from django.db.models import Q
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response

from products.models import Card, AccountMarker, Account
from api.serializers.admin.cards import AdminCardSerializer, AdminAccountMarkerSerializer


class AdminCardViewSet(viewsets.ModelViewSet):
    """Admin card CRUD with search."""
    permission_classes = [IsAdminUser]
    serializer_class = AdminCardSerializer
    queryset = Card.objects.all().order_by('expiration_date', 'status')

    def get_queryset(self):
        qs = self.queryset
        q = self.request.GET.get('q')
        if q:
            qs = qs.filter(
                Q(nom__icontains=q) |
                Q(telephone__icontains=q)
            )
        return qs


class AdminAccountMarkerViewSet(viewsets.ModelViewSet):
    """Admin account marker CRUD."""
    permission_classes = [IsAdminUser]
    serializer_class = AdminAccountMarkerSerializer
    queryset = AccountMarker.objects.all().order_by('name')
