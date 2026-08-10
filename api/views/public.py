"""Public endpoints (no auth required).

Prefix: /api/v1/public/
  - auth/users/                       Djoser register
  - auth/jwt/create|refresh|verify    SimpleJWT
  - auth/password/                    Djoser password reset
  - platforms/                        Catalogue
  - platforms/{id}/pricing/           Full pricing structure
  - reviews/                          Public reviews
  - faqs/                             FAQ
  - pages/{cgu|cgv|ml|pc}/            Legal content (static)
"""
from rest_framework import viewsets, mixins
from rest_framework.decorators import action, api_view, permission_classes as perm_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status

from core.models import Platform, Review, Faq
from ..serializers.public import (
    PlatformListSerializer,
    PlatformPricingSerializer,
    ReviewPublicSerializer,
    FaqSerializer,
)


class PlatformViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin,
                      viewsets.GenericViewSet):
    """Public platform catalogue (read-only)."""
    queryset = Platform.objects.filter(price_tiers__isnull=False).distinct()
    permission_classes = [AllowAny]
    serializer_class = PlatformListSerializer

    @action(detail=True, methods=['get'])
    def pricing(self, request, pk=None):
        """Full pricing structure (shared + personal categories) for a platform."""
        platform = self.get_object()
        serializer = PlatformPricingSerializer(platform)
        return Response(serializer.data)


class ReviewViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Public reviews (read-only). Submission happens via /api/v1/user/reviews/."""
    queryset = Review.objects.select_related('user').order_by('-create_at')
    permission_classes = [AllowAny]
    serializer_class = ReviewPublicSerializer


class FaqViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Public FAQ (read-only)."""
    queryset = Faq.objects.all().order_by('id')
    permission_classes = [AllowAny]
    serializer_class = FaqSerializer


@api_view(['GET'])
@perm_classes([AllowAny])
def health_check(request):
    """Health check: verifies DB + cache connectivity."""
    from django.db import connection
    from django.core.cache import cache
    components = {}

    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            cursor.fetchone()
        components['database'] = 'ok'
    except Exception as e:
        components['database'] = f'error: {e}'

    try:
        cache.set('_health_check', '1', timeout=10)
        cache.get('_health_check')
        components['cache'] = 'ok'
    except Exception as e:
        components['cache'] = f'error: {e}'

    all_ok = all(v == 'ok' for v in components.values())
    return Response(
        {'status': 'healthy' if all_ok else 'degraded', 'components': components},
        status=status.HTTP_200_OK if all_ok else status.HTTP_503_SERVICE_UNAVAILABLE,
    )
