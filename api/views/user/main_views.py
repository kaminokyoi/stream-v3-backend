"""User API views (/api/v1/user/*).

All endpoints require JWT authentication and restrict access to the
authenticated user's own resources. Subscription access masking is
applied via SubscriptionAccessService (audit §5.7).
"""
import logging

from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets, mixins
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, JSONParser

from core.models import Review
from core.services import SubscriptionAccessService, ReviewService
from core.utils import calculate_price
from payments.models import Order, Subscription, PaymentProof, GiftCode
from payments.services import PaymentCompletionService
from notifications.services import notify_purchase_received

from api.serializers.user import (
    ProfileUpdateSerializer,
    OrderCreateSerializer,
    OrderSerializer,
    RenewalCreateSerializer,
    PaymentProofUploadSerializer,
    GiftCodeVerifySerializer,
    ReviewSubmitSerializer,
    ReviewMeSerializer,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

class ProfileView(APIView):
    """Current user profile: GET (me) / PATCH (update email)."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from api.serializers.auth import UserSerializer
        serializer = UserSerializer(request.user)
        data = dict(serializer.data)
        data['needs_email'] = not bool(request.user.email)
        return Response(data)

    def patch(self, request):
        serializer = ProfileUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data.get('email', '')
        if email:
            from users.models import User
            if User.objects.filter(email=email).exclude(pk=request.user.pk).exists():
                return Response(
                    {'email': "Cette adresse e-mail est déjà utilisée."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            request.user.email = email
            request.user.save(update_fields=['email'])
        from api.serializers.auth import UserSerializer
        return Response(UserSerializer(request.user).data)


# ---------------------------------------------------------------------------
# Dashboard (aggregated)
# ---------------------------------------------------------------------------

class DashboardView(APIView):
    """User dashboard: subscriptions (masked), orders, notifications, pricing."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        subs_data, notifs_data = SubscriptionAccessService.build_dashboard_subscriptions(user)
        orders_data, pending_orders_data = SubscriptionAccessService.build_dashboard_orders(user)

        from core.utils import get_all_prices
        from core.models import Platform
        user_review = Review.objects.filter(user=user).first()
        return Response({
            'needs_email': not bool(user.email),
            'subscriptions': subs_data,
            'pending_orders': pending_orders_data,
            'orders': orders_data,
            'notifications': notifs_data,
            'platforms': [
                {'id': p.id, 'name': p.name, 'has_personal': p.has_personal}
                for p in Platform.objects.filter(price_tiers__isnull=False).distinct()
            ],
            'pricing': get_all_prices(),
            'user_review': (
                {'id': user_review.id, 'stars': user_review.stars, 'comment': user_review.comment}
                if user_review else None
            ),
            'show_review_modal': SubscriptionAccessService.should_show_review_modal(user),
        })


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------

class OrderViewSet(mixins.ListModelMixin,
                   mixins.RetrieveModelMixin,
                   viewsets.GenericViewSet):
    """User orders: list, detail, create (purchase init), cancel."""
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user).order_by('-purchase_date')

    def create(self, request):
        """Purchase init: create a new order with server-side price calculation."""
        serializer = OrderCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        gift_code_obj = None
        gift_code_str = data.get('gift_code', '').strip()
        if gift_code_str:
            try:
                gift = GiftCode.objects.get(code=gift_code_str)
                if gift.is_valid(data['platform']):
                    gift_code_obj = gift
            except GiftCode.DoesNotExist:
                pass

        order = Order.objects.create(
            user=request.user,
            platform=data['platform'],
            duration=data['duration'],
            type=data['type'],
            price=data['price'],
            status='pending_payment',
            gift_code=gift_code_obj,
            motif='subscription',
        )
        return Response(
            {
                'message': 'Commande créée',
                'order_id': str(order.order_id),
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel an order (delete if not completed)."""
        order = self.get_object()
        if order.status == 'completed':
            return Response(
                {'detail': "Impossible d'annuler une commande déjà complétée."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        PaymentProof.objects.filter(order=order).delete()
        order_id_str = str(order.order_id)
        order.delete()
        logger.info(f"Order {order_id_str} cancelled by user {request.user.id}")
        return Response({'detail': 'Commande annulée avec succès.'}, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Subscriptions (read-only + renewal action)
# ---------------------------------------------------------------------------

class SubscriptionViewSet(mixins.ListModelMixin,
                          mixins.RetrieveModelMixin,
                          viewsets.GenericViewSet):
    """User subscriptions: list, detail (with access masking), renewal."""
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Subscription.objects.filter(
            user=self.request.user
        ).select_related('order', 'profile', 'profile__account').exclude(
            status='expired', profile__isnull=True
        ).order_by('-status', 'expiration_date')

    def _get_masked_subs(self, request):
        """Return the masked subscriptions list for the current user."""
        subs_data, _ = SubscriptionAccessService.build_dashboard_subscriptions(request.user)
        return subs_data

    def list(self, request):
        subs_data = self._get_masked_subs(request)
        return Response({'results': subs_data, 'count': len(subs_data)})

    def retrieve(self, request, pk=None):
        subs_data = self._get_masked_subs(request)
        sub = next((s for s in subs_data if s['id'] == int(pk)), None)
        if sub is None:
            return Response({'detail': 'Abonnement introuvable.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(sub)

    @action(detail=True, methods=['post'])
    def renewal(self, request, pk=None):
        """Renewal init: create a new order linked to this subscription."""
        sub = get_object_or_404(Subscription, pk=pk, user=request.user)
        serializer = RenewalCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        new_duration = data['duration']
        sub_type = data.get('sub_type', '')
        req_type = data.get('type', '')
        order_type = req_type.strip().lower() if req_type else sub.order.type

        price = calculate_price(sub.order.platform, new_duration, order_type, sub_type)
        if price <= 0:
            return Response(
                {'detail': 'Erreur de calcul du prix.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        gift_code_obj = None
        gift_code_str = data.get('gift_code', '').strip()
        if gift_code_str:
            try:
                gift = GiftCode.objects.get(code=gift_code_str)
                if gift.is_valid(sub.order.platform):
                    gift_code_obj = gift
            except GiftCode.DoesNotExist:
                pass

        order_motif = 'renewal' if sub.status == 'expired' else 'extension'

        new_order = Order.objects.create(
            user=request.user,
            platform=sub.order.platform,
            duration=new_duration,
            type=order_type,
            price=price,
            status='pending_payment',
            renewal_from=sub,
            gift_code=gift_code_obj,
            purchase_date=sub.expiration_date,
            motif=order_motif,
        )
        return Response(
            {
                'message': 'Renouvellement initié',
                'order_id': str(new_order.order_id),
            },
            status=status.HTTP_201_CREATED,
        )


# ---------------------------------------------------------------------------
# Payment proof upload
# ---------------------------------------------------------------------------

class PaymentProofView(APIView):
    """Upload a payment proof for an order (manual Mobile Money payment)."""
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, JSONParser]

    def post(self, request, order_id):
        order = get_object_or_404(Order, order_id=order_id, user=request.user)
        serializer = PaymentProofUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        proof = PaymentProof(order=order, image=serializer.validated_data['proof_image'])
        if serializer.validated_data.get('proof_image2'):
            proof.image2 = serializer.validated_data['proof_image2']
        proof.save()

        order.status = 'pending_validation'
        order.save()

        notify_purchase_received(order)

        return Response(
            {
                'success': True,
                'message': "Preuve envoyée avec succès ! Validation en cours.",
                'order_id': str(order.order_id),
                'order_status': order.status,
            },
            status=status.HTTP_201_CREATED,
        )


# ---------------------------------------------------------------------------
# Gift code verification
# ---------------------------------------------------------------------------

class GiftCodeVerifyView(APIView):
    """Verify a gift code and return the number of granted days."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = GiftCodeVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response({
            'valid': True,
            'days': serializer.validated_data['days'],
        })


# ---------------------------------------------------------------------------
# Reviews
# ---------------------------------------------------------------------------

class ReviewView(APIView):
    """User review: GET (my review) / POST (submit, bonus handled by ReviewService)."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        review = Review.objects.filter(user=request.user).first()
        if not review:
            return Response({'detail': 'Aucun avis.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = ReviewMeSerializer(review)
        return Response(serializer.data)

    def post(self, request):
        serializer = ReviewSubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = ReviewService.submit_review(
            request.user,
            serializer.validated_data['stars'],
            serializer.validated_data.get('comment', ''),
        )
        return Response(result, status=status.HTTP_200_OK)
