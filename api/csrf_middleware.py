"""CSRF double-submit middleware for cookie-based JWT auth (L2.5).

Flow:
  1. On any response, set a non-HttpOnly cookie `sp_csrf` with a random token.
  2. On unsafe requests (POST/PUT/PATCH/DELETE), compare the `X-CSRF-Token`
     header against the `sp_csrf` cookie value. Reject with 403 on mismatch.

This is the standard double-submit pattern — effective because:
  - The cookie is HttpOnly=false so JS can read it
  - The header can only be set by same-origin JS (CORS blocks cross-origin)
  - Combined with SameSite=Lax on JWT cookies, provides defense-in-depth
"""
import secrets

from django.conf import settings

CSRF_COOKIE = 'sp_csrf'
UNSAFE_METHODS = {'POST', 'PUT', 'PATCH', 'DELETE'}

_EXEMPT_PATHS = {
    '/api/v1/public/auth/jwt/create/',
    '/api/v1/public/auth/jwt/2fa-verify/',
    '/api/v1/public/auth/jwt/refresh/',
}


class DoubleSubmitCSRFMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Allow disabling via settings (tests, dev)
        if not getattr(settings, 'DOUBLE_SUBMIT_CSRF_ENABLED', True):
            return self.get_response(request)

        if request.method in UNSAFE_METHODS and not self._is_exempt(request):
            # Skip CSRF for cross-origin requests — CORS handles those.
            # SameSite=Lax cookies won't be sent cross-origin anyway, so
            # requiring a CSRF cookie would block legitimate API clients.
            origin = request.META.get('HTTP_ORIGIN', '')
            host = request.get_host()
            if origin and host not in origin:
                return self.get_response(request)

            cookie_token = request.COOKIES.get(CSRF_COOKIE)
            header_token = request.META.get('HTTP_X_CSRF_TOKEN', '')
            if not cookie_token or not header_token or not secrets.compare_digest(cookie_token, header_token):
                from django.http import JsonResponse
                return JsonResponse(
                    {'detail': 'CSRF token manquant ou invalide.'},
                    status=403,
                )

        response = self.get_response(request)

        # Set/refresh the CSRF cookie on every response
        if not request.COOKIES.get(CSRF_COOKIE):
            response.set_cookie(
                CSRF_COOKIE,
                secrets.token_urlsafe(32),
                httponly=False,
                secure=getattr(settings, 'IS_PRODUCTION', False),
                samesite='Lax',
                path='/',
            )

        return response

    def _is_exempt(self, request):
        """Exempt login/2FA/refresh endpoints (no CSRF token yet)."""
        path = request.path_info.rstrip('/')
        for exempt in _EXEMPT_PATHS:
            if path == exempt.rstrip('/'):
                return True
        return False