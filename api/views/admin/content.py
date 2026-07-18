"""Admin views: content (platforms, faqs, reviews, giftcodes, payment numbers, messaging)."""
import logging

from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets, mixins
from rest_framework.decorators import action
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import Platform, PriceTier, Faq, Review
from payments.models import GiftCode, PaymentNumber
from dashboard.models import Notification, Message
from dashboard.tasks import send_bulk_notification_task, send_bulk_message_task
from users.models import User

from ...serializers.admin.content import (
    AdminPlatformSerializer, AdminPriceTierSerializer, AdminFaqSerializer,
    AdminReviewSerializer, AdminGiftCodeSerializer, AdminPaymentNumberSerializer,
    AdminNotificationSerializer, AdminMessageSerializer, SendMessagingSerializer,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Platforms
# ---------------------------------------------------------------------------

class AdminPlatformViewSet(viewsets.ModelViewSet):
    """Admin platform CRUD + nested price tiers."""
    permission_classes = [IsAdminUser]
    serializer_class = AdminPlatformSerializer
    queryset = Platform.objects.all().order_by('order', 'name')


class AdminPriceTierViewSet(viewsets.ModelViewSet):
    """Admin price-tier CRUD."""
    permission_classes = [IsAdminUser]
    serializer_class = AdminPriceTierSerializer
    queryset = PriceTier.objects.all().order_by('account_type', 'base_price')


# ---------------------------------------------------------------------------
# FAQ
# ---------------------------------------------------------------------------

class AdminFaqViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAdminUser]
    serializer_class = AdminFaqSerializer
    queryset = Faq.objects.all().order_by('id')


# ---------------------------------------------------------------------------
# Reviews
# ---------------------------------------------------------------------------

class AdminReviewViewSet(mixins.ListModelMixin,
                         mixins.DestroyModelMixin,
                         viewsets.GenericViewSet):
    """Admin review listing + delete."""
    permission_classes = [IsAdminUser]
    serializer_class = AdminReviewSerializer
    queryset = Review.objects.select_related('user').order_by('-create_at')

    def get_queryset(self):
        qs = self.queryset
        q = self.request.GET.get('q')
        if q:
            qs = qs.filter(
                Q(user__first_name__icontains=q) |
                Q(user__last_name__icontains=q) |
                Q(user__email__icontains=q) |
                Q(comment__icontains=q)
            )
        stars = self.request.GET.get('stars')
        if stars:
            try:
                qs = qs.filter(stars=int(stars))
            except (ValueError, TypeError):
                pass
        return qs


# ---------------------------------------------------------------------------
# Gift codes
# ---------------------------------------------------------------------------

class AdminGiftCodeViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAdminUser]
    serializer_class = AdminGiftCodeSerializer
    queryset = GiftCode.objects.all().order_by('-start_date')

    @action(detail=True, methods=['post'])
    def toggle(self, request, pk=None):
        """Toggle active status."""
        code = self.get_object()
        code.status = not code.status
        code.save()
        return Response(AdminGiftCodeSerializer(code).data)


# ---------------------------------------------------------------------------
# Payment numbers
# ---------------------------------------------------------------------------

class AdminPaymentNumberViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAdminUser]
    serializer_class = AdminPaymentNumberSerializer
    queryset = PaymentNumber.objects.all().order_by('provider', '-created_at')

    @action(detail=True, methods=['post'])
    def toggle(self, request, pk=None):
        """Toggle active status (with the 2-active-per-provider rule)."""
        number = self.get_object()
        if not number.is_active:
            active_count = PaymentNumber.objects.filter(
                provider=number.provider, is_active=True
            ).exclude(pk=number.pk).count()
            if active_count >= 2:
                return Response(
                    {'detail': f"Impossible d'activer plus de 2 numéros {number.get_provider_display()}."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            number.is_active = True
        else:
            number.is_active = False
        number.save()
        return Response(AdminPaymentNumberSerializer(number).data)


# ---------------------------------------------------------------------------
# Messaging
# ---------------------------------------------------------------------------

class AdminNotificationViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAdminUser]
    serializer_class = AdminNotificationSerializer
    queryset = Notification.objects.all().order_by('-created_at')

    @action(detail=True, methods=['post'])
    def send(self, request, pk=None):
        """Bulk-send a notification to selected users (or all)."""
        notif = self.get_object()
        serializer = SendMessagingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if data.get('channel') and data['channel'] != notif.channel:
            notif.channel = data['channel']
            notif.save(update_fields=['channel'])
        if data.get('send_to_all'):
            user_ids = list(User.objects.values_list('id', flat=True))
        else:
            user_ids = data.get('recipients', [])
        if not user_ids:
            return Response({'detail': 'Aucun destinataire sélectionné.'}, status=status.HTTP_400_BAD_REQUEST)
        send_bulk_notification_task.delay(notif.id, user_ids)
        return Response({'detail': f"Notification en cours d'envoi à {len(user_ids)} utilisateur(s)."})


class AdminMessageViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAdminUser]
    serializer_class = AdminMessageSerializer
    queryset = Message.objects.all().order_by('-created_at')

    @action(detail=True, methods=['post'])
    def send(self, request, pk=None):
        """Bulk-send a message to selected users (or all)."""
        msg = self.get_object()
        serializer = SendMessagingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if data.get('channel') and data['channel'] != msg.channel:
            msg.channel = data['channel']
            msg.save(update_fields=['channel'])
        if data.get('send_to_all'):
            user_ids = list(User.objects.values_list('id', flat=True))
        else:
            user_ids = data.get('recipients', [])
        if not user_ids:
            return Response({'detail': 'Aucun destinataire sélectionné.'}, status=status.HTTP_400_BAD_REQUEST)
        send_bulk_message_task.delay(msg.id, user_ids)
        return Response({'detail': f"Message en cours d'envoi à {len(user_ids)} utilisateur(s)."})
