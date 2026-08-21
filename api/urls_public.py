"""Public API routes: /api/v1/public/*"""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from api.views.auth import TwoFAAwareTokenObtainPairView, TwoFAVerifyView, UserViewSet, CookieTokenRefreshView, LogoutView
from api.views.media import MediaFileView
from api.views.public import PlatformViewSet, ReviewViewSet, FaqViewSet, health_check
from rest_framework_simplejwt.views import TokenVerifyView

router = DefaultRouter()
router.register(r'platforms', PlatformViewSet, basename='platform')
router.register(r'reviews', ReviewViewSet, basename='review')
router.register(r'faqs', FaqViewSet, basename='faq')

user_router = DefaultRouter()
user_router.register(r'users', UserViewSet, basename='user')

urlpatterns = [
    # Health check
    path('health/', health_check, name='health-check'),
    # Auth (Djoser user management + password, with phone-based reset)
    path('auth/', include(user_router.urls)),
    # JWT with 2FA gate + HttpOnly cookies (L3.1)
    path('auth/jwt/create/', TwoFAAwareTokenObtainPairView.as_view(), name='jwt-create'),
    path('auth/jwt/2fa-verify/', TwoFAVerifyView.as_view(), name='jwt-2fa-verify'),
    path('auth/jwt/refresh/', CookieTokenRefreshView.as_view(), name='jwt-refresh'),
    path('auth/jwt/verify/', TokenVerifyView.as_view(), name='jwt-verify'),
    path('auth/logout/', LogoutView.as_view(), name='logout'),
    # Catalogue (read-only)
    path('', include(router.urls)),
    # Media proxy (stable URLs, forced Content-Type, bucket stays private)
    path('media/<path:file_path>', MediaFileView.as_view(), name='media'),
]
