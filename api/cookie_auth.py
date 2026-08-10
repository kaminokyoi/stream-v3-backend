"""JWT authentication that also reads tokens from HttpOnly cookies (L3.1).

Order of precedence:
  1. Authorization: JWT <access> header (mobile + legacy web)
  2. sp_access HttpOnly cookie (web with credentials: 'include')
"""
from rest_framework_simplejwt.authentication import JWTAuthentication


class CookieJWTAuthentication(JWTAuthentication):
    def get_header(self, request):
        header = super().get_header(request)
        if header is not None:
            return header
        # Fall back to HttpOnly cookie
        access = request.COOKIES.get('sp_access')
        if access:
            return f'JWT {access}'.encode()
        return None