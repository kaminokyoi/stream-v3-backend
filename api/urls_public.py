"""Public API routes: /api/v1/public/*"""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from api.views.auth import TwoFAAwareTokenObtainPairView, TwoFAVerifyView
from api.views.public import PlatformViewSet, ReviewViewSet, FaqViewSet

router = DefaultRouter()
router.register(r'platforms', PlatformViewSet, basename='platform')
router.register(r'reviews', ReviewViewSet, basename='review')
router.register(r'faqs', FaqViewSet, basename='faq')

urlpatterns = [
    # Auth (Djoser user management + password)
    path('auth/', include('djoser.urls')),
    # JWT with 2FA gate
    path('auth/jwt/create/', TwoFAAwareTokenObtainPairView.as_view(), name='jwt-create'),
    path('auth/jwt/2fa-verify/', TwoFAVerifyView.as_view(), name='jwt-2fa-verify'),
    path('auth/', include('djoser.urls.jwt')),
    # Catalogue (read-only)
    path('', include(router.urls)),
]
