"""API URL configuration.

Structure (audit §9):
  /api/v1/public/*   — no auth (Djoser auth + catalogue + legal pages)
  /api/v1/user/*     — JWT required (own resources only)        [Phase 4]
  /api/v1/admin/*    — JWT + is_superuser                       [Phase 5]

The existing HTML URLs (/, /cadmin/, /payments/, ...) remain untouched
and coexist with the API routes.
"""
from django.urls import include, path

app_name = 'api'

urlpatterns = [
    path('v1/public/', include('api.urls_public')),
    path('v1/user/', include('api.urls_user')),
    path('v1/admin/', include('api.urls_admin')),
]
