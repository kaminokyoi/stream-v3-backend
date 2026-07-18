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
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

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
