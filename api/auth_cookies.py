"""JWT cookie helpers for HttpOnly auth (L3.1).

Sets access + refresh tokens as HttpOnly cookies alongside the JSON response.
Mobile clients still use the JSON tokens; web clients use cookies via
`credentials: 'include'`.

Usage in views:
    from api.auth_cookies import set_jwt_cookies, clear_jwt_cookies
    response = Response({...})
    set_jwt_cookies(response, access, refresh)
    return response
"""
from django.conf import settings


ACCESS_COOKIE = 'sp_access'
REFRESH_COOKIE = 'sp_refresh'

_COOKIE_KWARGS = {
    'httponly': True,
    'secure': getattr(settings, 'IS_PRODUCTION', False),
    'samesite': 'Lax',
    'path': '/',
}


def set_jwt_cookies(response, access_token: str, refresh_token: str | None = None):
    response.set_cookie(ACCESS_COOKIE, access_token, max_age=7 * 24 * 3600, **_COOKIE_KWARGS)
    if refresh_token:
        response.set_cookie(REFRESH_COOKIE, refresh_token, max_age=7 * 24 * 3600, **_COOKIE_KWARGS)


def clear_jwt_cookies(response):
    response.delete_cookie(ACCESS_COOKIE, path='/')
    response.delete_cookie(REFRESH_COOKIE, path='/')
