"""Admin views: subscriptions + profiles + accounts + markers."""
import logging
from datetime import timedelta

from dateutil.relativedelta import relativedelta
from django.db.models import Count, Q, F
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status, viewsets, mixins
from rest_framework.decorators import action
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response

from payments.models import (
    Subscription, SubscriptionMarker, SubscriptionProfileHistory, Order,
)
from payments.services import PaymentCompletionService
from products.models import Account, Profile, AccountMarker
from core.utils import calculate_price, duration_choices
from notifications.services import (
    notify_subscription_activated,
    notify_subscription_info_updated,
    notify_profile_unlinked,
)

from ...serializers.admin.inventory import (
    AdminSubscriptionSerializer, AdminSubscriptionCreateSerializer,
    AdminSubscriptionMarkerSerializer, AdminSubscriptionProfileHistorySerializer,
    ChangeProfileSerializer, MarkSubscriptionSerializer, AdminRenewSerializer,
    AdminAccountSerializer, AdminProfileSerializer,
)
from ...serializers.admin.cards import AdminAccountMarkerSerializer

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Subscriptions
# ---------------------------------------------------------------------------

class AdminSubscriptionViewSet(viewsets.ModelViewSet):
    """Admin subscription management with profile/marker/renew helpers."""
    permission_classes = [IsAdminUser]
    queryset = Subscription.objects.select_related(
        'user', 'order', 'profile', 'profile__account',
    ).prefetch_related('markers').all()

    def get_serializer_class(self):
        if self.action == 'create':
            return AdminSubscriptionCreateSerializer
        return AdminSubscriptionSerializer

    def get_queryset(self):
        qs = self.queryset
        q = self.request.GET.get('q')
        if q:
            qs = qs.filter(
                Q(user__first_name__icontains=q) |
                Q(user__last_name__icontains=q) |
                Q(order__platform__icontains=q) |
                Q(profile__number__icontains=q)
            )
        platform = self.request.GET.get('platform')
        if platform:
            qs = qs.filter(order__platform=platform)
        duration = self.request.GET.get('duration')
        if duration:
            qs = qs.filter(order__duration=duration)
        account = self.request.GET.get('account')
        if account:
            qs = qs.filter(profile__account__number=account)

        status_filter = self.request.GET.get('status', 'active')
        if status_filter == 'expired':
            qs = qs.filter(Q(status='expired') | Q(expiration_date__lte=timezone.now())).order_by('-order__purchase_date')
        else:
            qs = qs.filter(status='active', expiration_date__gt=timezone.now()).order_by('-order__purchase_date')
        return qs

    @action(detail=True, methods=['post'])
    def change_profile(self, request, pk=None):
        """Link or change the profile on a subscription."""
        sub = self.get_object()
        serializer = ChangeProfileSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        pid = serializer.validated_data['profile_id']
        is_first_link = sub.profile is None
        sub.profile = get_object_or_404(Profile, pk=pid)
        sub.save()
        if is_first_link:
            notify_subscription_activated(sub)
        else:
            notify_subscription_info_updated(sub)
        return Response({'detail': 'Profil lié.'})

    @action(detail=True, methods=['post'])
    def unlink_profile(self, request, pk=None):
        """Unlink the profile from a subscription (records history + notifies)."""
        sub = self.get_object()
        if sub.profile:
            try:
                SubscriptionProfileHistory.objects.create(
                    subscription=sub,
                    profile_number=sub.profile.number,
                    profile_code=sub.profile.code,
                    account_number=sub.profile.account.number if sub.profile.account else '',
                    platform=sub.profile.account.platform if sub.profile.account else '',
                )
            except Exception as e:
                logger.error(f"Error saving profile history for subscription {pk}: {e}")
        notify_profile_unlinked(sub)
        sub.profile = None
        sub.save()
        return Response({'detail': 'Profil délié.'})

    @action(detail=True, methods=['get'])
    def profile_history(self, request, pk=None):
        """List the profile history of a subscription."""
        sub = self.get_object()
        history = SubscriptionProfileHistory.objects.filter(subscription=sub).order_by('-unlinked_at')
        serializer = AdminSubscriptionProfileHistorySerializer(history, many=True)
        return Response({'history': serializer.data})

    @action(detail=True, methods=['post'])
    def mark_expired(self, request, pk=None):
        """Force a subscription to expired status immediately."""
        sub = self.get_object()
        sub.status = 'expired'
        sub.expiration_date = timezone.now()
        sub.save()
        return Response({'detail': f"Abonnement de {sub.user.get_full_name()} forcé à l'expiration."})

    @action(detail=True, methods=['post'])
    def toggle_expiry(self, request, pk=None):
        """Toggle active <-> expired (auto-unlink on expire)."""
        sub = self.get_object()
        if sub.status == 'active':
            sub.status = 'expired'
            sub.profile = None
        else:
            sub.status = 'active'
        sub.save()
        return Response(AdminSubscriptionSerializer(sub).data)

    @action(detail=True, methods=['post'])
    def renew(self, request, pk=None):
        """Admin renewal (no payment). Creates a completed order + extends sub."""
        sub = self.get_object()
        serializer = AdminRenewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        duration = serializer.validated_data['duration']
        valid_durations = [d[0] for d in duration_choices()]
        if duration not in valid_durations:
            duration = '1 mois'
        price = calculate_price(
            platform=sub.order.platform,
            duration=duration,
            account_type=sub.order.type,
        )
        order_motif = 'renewal' if sub.status == 'expired' else 'extension'
        order = Order.objects.create(
            user=sub.user,
            platform=sub.order.platform,
            duration=duration,
            type=sub.order.type,
            price=price,
            status='completed',
            renewal_from=sub,
            purchase_date=sub.expiration_date,
            motif=order_motif,
        )
        PaymentCompletionService()._create_subscription(order)
        return Response({'detail': f"Renouvelé ({duration}) — {price} FCFA."})

    @action(detail=True, methods=['post'])
    def mark(self, request, pk=None):
        """Add a marker to a subscription."""
        sub = self.get_object()
        serializer = MarkSubscriptionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        name = serializer.validated_data['marker_name']
        color = serializer.validated_data.get('marker_color', '#ffffff')
        marker, _ = SubscriptionMarker.objects.get_or_create(name=name, color=color)
        sub.markers.add(marker)
        return Response({'detail': 'Marqueur ajouté.', 'marker': AdminSubscriptionMarkerSerializer(marker).data})

    @action(detail=True, methods=['post', 'delete'])
    def unmark(self, request, pk=None):
        """Remove a marker (or all) from a subscription."""
        sub = self.get_object()
        marker_id = request.data.get('marker_id') or request.GET.get('marker_id')
        if marker_id:
            marker = get_object_or_404(SubscriptionMarker, pk=marker_id)
            sub.markers.remove(marker)
        else:
            sub.markers.clear()
        return Response({'detail': 'Marqueur retiré.'})


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------

class AdminAccountViewSet(viewsets.ModelViewSet):
    """Admin account CRUD + renew + markers."""
    permission_classes = [IsAdminUser]
    serializer_class = AdminAccountSerializer
    queryset = Account.objects.select_related('card').all().order_by('-remaining_day')

    def get_queryset(self):
        qs = self.queryset.prefetch_related('markers').annotate(
            _active_subs_count=Count(
                'profile__subscriptions',
                filter=Q(profile__subscriptions__status='active'),
                distinct=True,
            ),
        )
        platform = self.request.GET.get('platform')
        if platform:
            qs = qs.filter(platform=platform)
        status_filter = self.request.GET.get('status')
        if status_filter == 'activate':
            qs = qs.filter(status='activate')
        elif status_filter == 'desactivate':
            qs = qs.filter(status='desactivate')
        return qs

    @action(detail=True, methods=['post'])
    def renew(self, request, pk=None):
        """Add 1 month to account end_date + increment month_count."""
        account = self.get_object()
        if account.end_date:
            account.end_date += relativedelta(months=1)
        else:
            account.end_date = timezone.now() + relativedelta(months=1)
        account.month_count += 1
        account.save()
        return Response(AdminAccountSerializer(account).data)

    @action(detail=True, methods=['post'])
    def mark(self, request, pk=None):
        """Add a marker to an account."""
        account = self.get_object()
        name = request.data.get('marker_name', '').strip()
        color = request.data.get('marker_color', '#ffffff')
        if not name:
            return Response({'detail': 'marker_name requis.'}, status=status.HTTP_400_BAD_REQUEST)
        marker, _ = AccountMarker.objects.get_or_create(name=name, color=color)
        account.markers.add(marker)
        return Response({'detail': 'Marqueur ajouté.', 'marker': AdminAccountMarkerSerializer(marker).data})

    @action(detail=True, methods=['post', 'delete'])
    def unmark(self, request, pk=None):
        """Remove a marker (or all) from an account."""
        account = self.get_object()
        marker_id = request.data.get('marker_id') if request.method == 'POST' else request.GET.get('marker_id')
        if marker_id:
            marker = get_object_or_404(AccountMarker, pk=marker_id)
            account.markers.remove(marker)
        else:
            account.markers.clear()
        return Response({'detail': 'Marqueur retiré.'})


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------

class AdminProfileViewSet(viewsets.ModelViewSet):
    """Admin profile CRUD."""
    permission_classes = [IsAdminUser]
    serializer_class = AdminProfileSerializer
    queryset = Profile.objects.select_related('account').prefetch_related(
        'subscriptions__user', 'subscriptions__markers',
    ).all().order_by('account__platform', 'account__number', 'number')

    def get_queryset(self):
        qs = self.queryset
        platform = self.request.GET.get('platform')
        if platform:
            qs = qs.filter(account__platform=platform)
        account = self.request.GET.get('account')
        if account:
            qs = qs.filter(account__number=account)
        return qs
