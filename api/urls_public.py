"""Public API routes: /api/v1/public/*"""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from api.views.public import PlatformViewSet, ReviewViewSet, FaqViewSet

router = DefaultRouter()
router.register(r'platforms', PlatformViewSet, basename='platform')
router.register(r'reviews', ReviewViewSet, basename='review')
router.register(r'faqs', FaqViewSet, basename='faq')

urlpatterns = [
    # Auth (Djoser + SimpleJWT)
    path('auth/', include('djoser.urls')),
    path('auth/', include('djoser.urls.jwt')),
    # Catalogue (read-only)
    path('', include(router.urls)),
]
