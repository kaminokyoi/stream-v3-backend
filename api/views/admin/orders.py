"""Admin views: users + orders + proofs."""
import csv
import logging
from datetime import datetime

from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status, viewsets, mixins
from rest_framework.decorators import action
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from users.models import User
from payments.models import Order, PaymentProof
from payments.services import PaymentCompletionService
from notifications.tasks import send_rejection_proof_email

from ...serializers.admin.orders import (
    AdminUserSerializer, AdminUserCreateSerializer,
    AdminOrderSerializer, AdminPaymentProofSerializer, RejectProofSerializer,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

class AdminUserViewSet(viewsets.ModelViewSet):
    """Admin user management + CSV import/export."""
    permission_classes = [IsAdminUser]
    queryset = User.objects.all().order_by('-date_joined')

    def get_queryset(self):
        qs = self.queryset.annotate(
            active_subs_count=Count('subscription', filter=Q(subscription__status='active')),
            expired_subs_count=Count('subscription', filter=Q(subscription__status='expired')),
        )
        q = self.request.GET.get('q')
        if q:
            qs = qs.filter(
                Q(first_name__icontains=q) |
                Q(last_name__icontains=q) |
                Q(phone_number__icontains=q) |
                Q(email__icontains=q)
            )
        status_filter = self.request.GET.get('status')
        if status_filter == 'active':
            qs = qs.filter(is_active=True)
        elif status_filter == 'inactive':
            qs = qs.filter(is_active=False)
        email_filter = self.request.GET.get('email')
        if email_filter == 'with_email':
            qs = qs.filter(email__isnull=False).exclude(email='')
        elif email_filter == 'without_email':
            qs = qs.filter(Q(email__isnull=True) | Q(email=''))
        country = self.request.GET.get('country')
        if country:
            qs = qs.filter(country_code=country)
        return qs.order_by('-date_joined')

    def get_serializer_class(self):
        if self.action == 'create':
            return AdminUserCreateSerializer
        return AdminUserSerializer

    @action(detail=False, methods=['get'])
    def export_csv(self, request):
        """Export all users to CSV."""
        qs = self.get_queryset()
        fields = ['first_name', 'last_name', 'country_code', 'phone_number', 'date_joined', 'password']
        response = HttpResponse(content_type="text/csv")
        response['Content-Disposition'] = f'attachment; filename="users_{timezone.now().strftime("%Y-%m-%d")}.csv"'
        writer = csv.writer(response)
        writer.writerow(fields)
        for u in qs:
            row = []
            for f in fields:
                val = getattr(u, f, '') or ''
                if callable(val):
                    val = val()
                row.append(str(val))
            writer.writerow(row)
        return response

    @action(detail=False, methods=['post'])
    def import_csv(self, request):
        """Import users from a CSV file."""
        f = request.FILES.get('file')
        if not f:
            return Response({'detail': 'No file uploaded.'}, status=status.HTTP_400_BAD_REQUEST)
        decoded = f.read().decode('utf-8-sig').splitlines()
        reader = csv.DictReader(decoded)
        count, skipped, errors = 0, 0, 0
        for row in reader:
            phone = (row.get('phone_number') or row.get('phone') or '').strip()
            if not phone:
                errors += 1
                continue
            if User.objects.filter(phone_number=phone).exists():
                skipped += 1
                continue
            try:
                u = User(
                    phone_number=phone,
                    first_name=(row.get('first_name') or '').strip(),
                    last_name=(row.get('last_name') or '').strip(),
                    country_code=(row.get('country_code') or '237').strip(),
                    password=row.get('password', ''),
                )
                is_active = (row.get('is_active') or '1').strip()
                u.is_active = is_active in ('1', 'True', 'true', 'yes')
                is_staff = (row.get('is_staff') or '0').strip()
                u.is_staff = is_staff in ('1', 'True', 'true', 'yes')
                date_joined = (row.get('date_joined') or '').strip()
                if date_joined:
                    try:
                        u.date_joined = timezone.make_aware(
                            datetime.strptime(date_joined, '%Y-%m-%d %H:%M:%S')
                        )
                    except (ValueError, TypeError):
                        pass
                last_login = (row.get('last_login') or '').strip()
                if last_login:
                    try:
                        u.last_login = timezone.make_aware(
                            datetime.strptime(last_login, '%Y-%m-%d %H:%M:%S')
                        )
                    except (ValueError, TypeError):
                        pass
                u.save()
                count += 1
            except Exception as row_err:
                logger.error(f"Error importing user {phone}: {row_err}")
                errors += 1
        msg = f"{count} imported."
        if skipped:
            msg += f" {skipped} skipped (already exist)."
        if errors:
            msg += f" {errors} errors."
        return Response({'detail': msg, 'imported': count, 'skipped': skipped, 'errors': errors})


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------

class AdminOrderViewSet(viewsets.ModelViewSet):
    """Admin order CRUD (read-only mostly, create/edit for edge cases)."""
    permission_classes = [IsAdminUser]
    serializer_class = AdminOrderSerializer
    queryset = Order.objects.all().select_related('user').order_by('-purchase_date')

    def get_queryset(self):
        qs = self.get_queryset_base()
        q = self.request.GET.get('q')
        if q:
            qs = qs.filter(
                Q(user__first_name__icontains=q) |
                Q(user__last_name__icontains=q) |
                Q(platform__icontains=q) |
                Q(order_id__icontains=q)
            )
        status_filter = self.request.GET.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        platform = self.request.GET.get('platform')
        if platform:
            qs = qs.filter(platform=platform)
        return qs

    def get_queryset_base(self):
        return Order.objects.all().select_related('user').order_by('-purchase_date')


# ---------------------------------------------------------------------------
# Payment proofs
# ---------------------------------------------------------------------------

class AdminPaymentProofViewSet(mixins.ListModelMixin,
                               mixins.RetrieveModelMixin,
                               viewsets.GenericViewSet):
    """Admin payment proofs: list, validate, validate-only, reject."""
    permission_classes = [IsAdminUser]
    serializer_class = AdminPaymentProofSerializer
    queryset = PaymentProof.objects.select_related('order', 'order__user', 'validated_by').order_by('-submitted_at')

    def get_queryset(self):
        qs = self.queryset
        q = self.request.GET.get('q')
        if q:
            qs = qs.filter(
                Q(order__user__first_name__icontains=q) |
                Q(order__user__last_name__icontains=q) |
                Q(order__order_id__icontains=q)
            )
        validation_status = self.request.GET.get('validation_status')
        if validation_status == 'pending':
            qs = qs.filter(validated=False, rejected=False)
        elif validation_status == 'validated':
            qs = qs.filter(validated=True)
        elif validation_status == 'rejected':
            qs = qs.filter(rejected=True)
        platform = self.request.GET.get('platform')
        if platform:
            qs = qs.filter(order__platform=platform)
        return qs

    @action(detail=True, methods=['post'])
    def validate(self, request, pk=None):
        """Validate proof + activate subscription (PaymentCompletionService)."""
        proof = self.get_object()
        proof.validated = True
        proof.validated_at = timezone.now()
        proof.validated_by = request.user
        proof.save()
        service = PaymentCompletionService()
        service.process_completed_payment(proof.order)
        return Response({'detail': "Preuve validée et abonnement activé."})

    @action(detail=True, methods=['post'])
    def validate_only(self, request, pk=None):
        """Validate proof WITHOUT activating the subscription."""
        proof = self.get_object()
        proof.validated = True
        proof.validated_at = timezone.now()
        proof.validated_by = request.user
        proof.save()
        service = PaymentCompletionService()
        service.process_validate_payment(proof.order)
        return Response({'detail': "Preuve validée (sans activation de l'abonnement)."})

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """Reject proof + notify user."""
        proof = self.get_object()
        serializer = RejectProofSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reason = serializer.validated_data.get('reason', 'Refusé')
        proof.rejected = True
        proof.rejection_reason = reason
        order_id = proof.order.order_id
        proof.save()
        proof.order.status = 'failed'
        proof.order.save()
        user = proof.order.user
        if user and user.email:
            send_rejection_proof_email.delay(
                user.email, user.first_name, reason, order_id, proof.order.platform
            )
        return Response({'detail': 'Refusé.'})
