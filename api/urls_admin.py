"""Admin API routes: /api/v1/admin/*

All endpoints require JWT authentication + is_superuser (IsAdminUser).
"""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from api.views.admin import (
    AdminUserViewSet, AdminOrderViewSet, AdminPaymentProofViewSet,
    AdminSubscriptionViewSet, AdminAccountViewSet, AdminProfileViewSet,
    AdminPlatformViewSet, AdminPriceTierViewSet, AdminFaqViewSet,
    AdminReviewViewSet, AdminGiftCodeViewSet, AdminPaymentNumberViewSet,
    AdminNotificationViewSet, AdminMessageViewSet,
    AdminDashboardView, DownloadImageView,
)
from api.views.admin.cards import AdminCardViewSet, AdminAccountMarkerViewSet
from api.views.admin.twofa import (
    twofa_status, twofa_setup, twofa_verify_setup,
    twofa_disable, twofa_regenerate_recovery,
)

router = DefaultRouter()
router.register(r'users', AdminUserViewSet, basename='admin-user')
router.register(r'orders', AdminOrderViewSet, basename='admin-order')
router.register(r'proofs', AdminPaymentProofViewSet, basename='admin-proof')
router.register(r'subscriptions', AdminSubscriptionViewSet, basename='admin-subscription')
router.register(r'accounts', AdminAccountViewSet, basename='admin-account')
router.register(r'profiles', AdminProfileViewSet, basename='admin-profile')
router.register(r'platforms', AdminPlatformViewSet, basename='admin-platform')
router.register(r'price-tiers', AdminPriceTierViewSet, basename='admin-pricetier')
router.register(r'faqs', AdminFaqViewSet, basename='admin-faq')
router.register(r'reviews', AdminReviewViewSet, basename='admin-review')
router.register(r'giftcodes', AdminGiftCodeViewSet, basename='admin-giftcode')
router.register(r'payment-numbers', AdminPaymentNumberViewSet, basename='admin-paymentnumber')
router.register(r'messaging/notifications', AdminNotificationViewSet, basename='admin-notification')
router.register(r'messaging/messages', AdminMessageViewSet, basename='admin-message')
router.register(r'cards', AdminCardViewSet, basename='admin-card')
router.register(r'account-markers', AdminAccountMarkerViewSet, basename='admin-accountmarker')

urlpatterns = [
    # Dashboard (stats + chart data)
    path('dashboard/', AdminDashboardView.as_view(), name='admin-dashboard'),
    # Image download utility
    path('download-image/', DownloadImageView.as_view(), name='admin-download-image'),
    # 2FA
    path('2fa/status/', twofa_status, name='admin-2fa-status'),
    path('2fa/setup/', twofa_setup, name='admin-2fa-setup'),
    path('2fa/verify-setup/', twofa_verify_setup, name='admin-2fa-verify-setup'),
    path('2fa/disable/', twofa_disable, name='admin-2fa-disable'),
    path('2fa/regenerate-recovery/', twofa_regenerate_recovery, name='admin-2fa-regenerate'),
    # CRUD routers
    path('', include(router.urls)),
]
