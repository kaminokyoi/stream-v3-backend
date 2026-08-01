"""Public API routes: /api/v1/public/*"""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from api.views.auth import TwoFAAwareTokenObtainPairView, TwoFAVerifyView, UserViewSet
from api.views.public import PlatformViewSet, ReviewViewSet, FaqViewSet

router = DefaultRouter()
router.register(r'platforms', PlatformViewSet, basename='platform')
router.register(r'reviews', ReviewViewSet, basename='review')
router.register(r'faqs', FaqViewSet, basename='faq')

user_router = DefaultRouter()
user_router.register(r'users', UserViewSet, basename='user')

urlpatterns = [
    # Auth (Djoser user management + password, with phone-based reset)
    path('auth/', include(user_router.urls)),
    # JWT with 2FA gate
    path('auth/jwt/create/', TwoFAAwareTokenObtainPairView.as_view(), name='jwt-create'),
    path('auth/jwt/2fa-verify/', TwoFAVerifyView.as_view(), name='jwt-2fa-verify'),
    path('auth/', include('djoser.urls.jwt')),
    # Catalogue (read-only)
    path('', include(router.urls)),
]
