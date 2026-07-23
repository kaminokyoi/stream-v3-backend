"""Admin views: dashboard stats + charts + download-image utility."""
import json
import logging
import mimetypes
import os
from datetime import timedelta
from urllib.parse import urlparse, unquote
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

from django.conf import settings
from django.core.cache import cache
from django.db.models import Sum, Count, Q
from django.db.models.functions import TruncDay, TruncMonth
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from payments.models import Order, Subscription
from users.models import User

logger = logging.getLogger(__name__)


class AdminDashboardView(APIView):
    """Admin dashboard overview: stats + chart data.

    GET /api/v1/admin/dashboard/                 -> base stats
    GET /api/v1/admin/dashboard/?action=chart_data&type=revenue&period=7_days
                                                 -> chart data
    """
    permission_classes = [IsAdminUser]

    def get(self, request):
        action = request.GET.get('action')
        if action == 'chart_data':
            return self._chart_data(request)
        return self._stats(request)

    # ----- Stats (default) — cached 60s -----
    def _stats(self, request):
        cache_key = 'admin_dashboard_stats'
        cached = cache.get(cache_key)
        if cached:
            return Response(cached)

        now = timezone.now()
        total_revenue = Order.objects.filter(status='completed').aggregate(Sum('price'))['price__sum'] or 0
        total_users = User.objects.count()
        active_subs = Subscription.objects.filter(status='active', expiration_date__gt=now).count()
        expired_subs = Subscription.objects.filter(Q(status='expired') | Q(expiration_date__lte=now)).count()
        last_orders = Order.objects.select_related('user').order_by('-purchase_date')[:5]
        # Platform popularity (count of all orders per platform, sorted by count desc)
        platforms = (
            Order.objects.values('platform').annotate(count=Count('id')).order_by('-count')
        )
        stats_data = {
            'total_revenue': total_revenue,
            'total_users': total_users,
            'active_subs': active_subs,
            'expired_subs': expired_subs,
            'platform_labels': [p['platform'] for p in platforms],
            'platform_data': [p['count'] for p in platforms],
            'last_orders': [
                {
                    'order_id': str(o.order_id),
                    'platform': o.platform,
                    'price': o.price,
                    'status': o.status,
                    'user_name': o.user.get_full_name() if o.user else None,
                    'purchase_date': o.purchase_date,
                }
                for o in last_orders
            ],
        }
        cache.set(cache_key, stats_data, 60)
        return Response(stats_data)

    # ----- Chart data -----
    def _chart_data(self, request):
        try:
            c_type = request.GET.get('type', 'revenue')
            period = request.GET.get('period', '7_days')
            valid_types = ['revenue', 'users', 'subs_active', 'subs_expired']
            valid_periods = ['today', '7_days', '30_days', '6_months', '1_year', 'custom']
            if c_type not in valid_types:
                c_type = 'revenue'
            if period not in valid_periods:
                period = '7_days'
            start_date = request.GET.get('start_date')
            end_date = request.GET.get('end_date')
            if c_type == 'revenue':
                data = self._revenue_data(period, start_date, end_date)
            elif c_type == 'users':
                data = self._users_data(period, start_date, end_date)
            elif c_type == 'subs_active':
                data = self._subs_data(period, True, start_date, end_date)
            elif c_type == 'subs_expired':
                data = self._subs_data(period, False, start_date, end_date)
            else:
                data = {'labels': [], 'data': []}
            if not isinstance(data, dict) or 'labels' not in data or 'data' not in data:
                data = {'labels': [], 'data': []}
            return Response({
                'labels': data['labels'],
                'data': data['data'],
                'total': sum(data['data']),
                'order_count': data.get('order_count'),
            })
        except Exception as e:
            logger.error(f"Error in chart_data: {e}")
            return Response(
                {'labels': [], 'data': [], 'error': 'Erreur lors de la récupération des données'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def _time_filter(self, period, field='purchase_date', start_date=None, end_date=None):
        now = timezone.now()
        trunc = TruncMonth if period in ('6_months', '1_year') else TruncDay
        if period == 'custom' and start_date and end_date:
            from datetime import datetime
            try:
                s = timezone.make_aware(datetime.strptime(start_date, '%Y-%m-%d'))
                e = timezone.make_aware(datetime.strptime(end_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59))
                return s, TruncDay(field), e
            except (ValueError, TypeError):
                pass
        if period == 'today':
            return now.replace(hour=0, minute=0, second=0, microsecond=0), TruncDay(field), now
        if period == '30_days':
            start = now - timedelta(days=30)
            return start.replace(hour=0, minute=0, second=0, microsecond=0), TruncDay(field), now
        if period == '6_months':
            start = now - timedelta(days=180)
            return start.replace(hour=0, minute=0, second=0, microsecond=0), TruncMonth(field), now
        if period == '1_year':
            start = now - timedelta(days=365)
            return start.replace(hour=0, minute=0, second=0, microsecond=0), TruncMonth(field), now
        # Default: 7_days
        start = now - timedelta(days=7)
        return start.replace(hour=0, minute=0, second=0, microsecond=0), TruncDay(field), now

    def _revenue_data(self, period, start_date=None, end_date=None):
        start, trunc, end = self._time_filter(period, 'purchase_date', start_date, end_date)
        qs = Order.objects.filter(status='completed', purchase_date__gte=start)
        if end:
            qs = qs.filter(purchase_date__lte=end)
        qs = qs.annotate(period=trunc).values('period').annotate(
            total=Sum('price'), order_count=Count('id')
        ).order_by('period')
        return {
            'labels': [e['period'].strftime('%d/%m') for e in qs],
            'data': [e['total'] or 0 for e in qs],
            'order_count': sum(e['order_count'] for e in qs),
        }

    def _users_data(self, period, start_date=None, end_date=None):
        start, trunc, end = self._time_filter(period, 'date_joined', start_date, end_date)
        qs = User.objects.filter(date_joined__gte=start)
        if end:
            qs = qs.filter(date_joined__lte=end)
        qs = qs.annotate(period=trunc).values('period').annotate(count=Count('id')).order_by('period')
        return {'labels': [e['period'].strftime('%d/%m') for e in qs], 'data': [e['count'] for e in qs]}

    def _subs_data(self, period, active, start_date=None, end_date=None):
        start, trunc, end = self._time_filter(period, 'order__purchase_date', start_date, end_date)
        status = 'active' if active else 'expired'
        qs = Subscription.objects.filter(status=status, order__purchase_date__gte=start)
        if end:
            qs = qs.filter(order__purchase_date__lte=end)
        qs = qs.annotate(period=trunc).values('period').annotate(count=Count('id')).order_by('period')
        return {'labels': [e['period'].strftime('%d/%m') for e in qs], 'data': [e['count'] for e in qs]}


class DownloadImageView(APIView):
    """Reusable image download (S3 URL or local /media/ path).

    GET /api/v1/admin/download-image/?url=...
    """
    permission_classes = [IsAdminUser]

    def get(self, request):
        image_url = request.GET.get('url', '')
        if not image_url:
            return Response({'detail': 'URL manquante.'}, status=status.HTTP_400_BAD_REQUEST)
        is_remote = image_url.startswith(('http://', 'https://'))
        if is_remote:
            try:
                parsed = urlparse(image_url)
                filename = os.path.basename(unquote(parsed.path)) or 'download'
                content_type, _ = mimetypes.guess_type(filename)
                req = Request(image_url, headers={'User-Agent': 'Django/download'})
                remote_file = urlopen(req, timeout=30)
                file_data = remote_file.read()
                remote_file.close()
                resp = HttpResponse(file_data, content_type=content_type or 'application/octet-stream')
                resp['Content-Disposition'] = f'attachment; filename="{filename}"'
                return resp
            except HTTPError as e:
                return Response({'detail': f'Erreur lors du téléchargement : {e.code}'}, status=e.code)
            except (URLError, OSError):
                return Response({'detail': 'Impossible de joindre le fichier distant.'}, status=status.HTTP_502_BAD_GATEWAY)
        relative_path = image_url.replace('/media/', '', 1)
        file_path = os.path.join(settings.MEDIA_ROOT, relative_path)
        if not os.path.exists(file_path):
            return Response({'detail': 'Fichier introuvable.'}, status=status.HTTP_404_NOT_FOUND)
        content_type, _ = mimetypes.guess_type(file_path)
        filename = os.path.basename(file_path)
        with open(file_path, 'rb') as f:
            resp = HttpResponse(f.read(), content_type=content_type or 'application/octet-stream')
            resp['Content-Disposition'] = f'attachment; filename="{filename}"'
            return resp
