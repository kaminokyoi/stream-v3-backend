"""User API routes: /api/v1/user/*

All endpoints require JWT authentication and restrict access to the
authenticated user's own resources.
"""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from api.views.user import (
    ProfileView,
    DashboardView,
    OrderViewSet,
    SubscriptionViewSet,
    PaymentProofView,
    GiftCodeVerifyView,
    ReviewView,
)
from api.views.user.notifications import (
    register_device,
    unregister_device,
    PushNotificationListView,
    mark_notification_read,
    mark_all_notifications_read,
    unread_notifications_count,
)

router = DefaultRouter()
router.register(r'orders', OrderViewSet, basename='order')
router.register(r'subscriptions', SubscriptionViewSet, basename='subscription')

urlpatterns = [
    # Profile
    path('profile/', ProfileView.as_view(), name='profile'),
    # Dashboard (aggregated)
    path('dashboard/', DashboardView.as_view(), name='dashboard'),
    # Payment proof upload (manual Mobile Money)
    path('payments/manual/<uuid:order_id>/', PaymentProofView.as_view(), name='payment-proof'),
    # Gift code verification
    path('gift-code/verify/', GiftCodeVerifyView.as_view(), name='gift-code-verify'),
    # Reviews (submit + my review)
    path('reviews/', ReviewView.as_view(), name='review'),
    # Device registration (push notifications)
    path('device/register/', register_device, name='device-register'),
    path('device/unregister/', unregister_device, name='device-unregister'),
    # Push notifications
    path('notifications/', PushNotificationListView.as_view(), name='push-notifications'),
    path('notifications/<int:pk>/mark_read/', mark_notification_read, name='push-mark-read'),
    path('notifications/mark_all_read/', mark_all_notifications_read, name='push-mark-all-read'),
    path('notifications/unread_count/', unread_notifications_count, name='push-unread-count'),
    # Orders + Subscriptions (router)
    path('', include(router.urls)),
]
