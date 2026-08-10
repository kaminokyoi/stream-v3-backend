"""Custom JWT views with 2FA support.

Flow:
  1. POST /auth/jwt/create  →  credentials validated
       - If 2FA disabled → returns {access, refresh} (normal SimpleJWT)
       - If 2FA enabled  → returns {2fa_required: true, twofa_token, method}
                           and sends an OTP (only for email/whatsapp)
  2. POST /auth/jwt/2fa-verify  →  {twofa_token, code}
       - Verifies the OTP
       - Returns {access, refresh} on success
"""
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.throttling import AnonRateThrottle
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from djoser.views import UserViewSet as DjoserUserViewSet

from users.twofa_service import TwoFAService
from api.auth_cookies import set_jwt_cookies, clear_jwt_cookies


class LoginThrottle(AnonRateThrottle):
    scope = 'login'


class OtpThrottle(AnonRateThrottle):
    scope = 'otp'


class RegisterThrottle(AnonRateThrottle):
    scope = 'register'


class UserViewSet(DjoserUserViewSet):
    """Djoser user viewset with phone-based password reset.

    Djoser's default reset_password action sends its own email and never
    calls serializer.save(); we override it so the link is dispatched
    through PasswordResetSerializer (notification task, email or admin
    fallback), matching the phone-based reset flow.
    """

    def get_throttles(self):
        if self.action == 'create':
            return [RegisterThrottle()]
        return super().get_throttles()

    @action(["post"], detail=False)
    def reset_password(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(status=status.HTTP_204_NO_CONTENT)


class TwoFAAwareTokenObtainPairView(TokenObtainPairView):
    """jwt/create with 2FA gate.
    """
    serializer_class = TokenObtainPairSerializer
    throttle_classes = [LoginThrottle]

    def post(self, request, *args, **kwargs):
        # First validate credentials via the standard serializer.
        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except Exception:
            # Re-raise the standard 401 for bad credentials.
            raise

        user = serializer.user
        if user is None:
            return Response(serializer.validated_data, status=status.HTTP_200_OK)

        if not user.twofa_enabled:
            response = Response(serializer.validated_data, status=status.HTTP_200_OK)
            access = serializer.validated_data.get('access')
            refresh = serializer.validated_data.get('refresh')
            if access:
                set_jwt_cookies(response, access, refresh)
            return response

        method = user.twofa_method or 'totp'
        twofa_token = TwoFAService.create_2fa_token(user.id)

        if method in ('email', 'whatsapp'):
            TwoFAService.create_and_send_otp(user, method)

        from users.twofa_service import OTP_TTL_SECONDS

        return Response(
            {
                '2fa_required': True,
                'twofa_token': twofa_token,
                'method': method,
                'expires_in': OTP_TTL_SECONDS,
            },
            status=status.HTTP_200_OK,
        )


class TwoFAVerifyView(APIView):
    """POST /auth/jwt/2fa-verify — exchange twofa_token + code for a JWT pair."""
    permission_classes = [AllowAny]
    throttle_classes = [OtpThrottle]

    def post(self, request, *args, **kwargs):
        twofa_token = request.data.get('twofa_token', '')
        code = (request.data.get('code') or '').strip()

        if not twofa_token or not code:
            return Response(
                {'detail': 'twofa_token et code sont requis.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = TwoFAService.get_user_from_2fa_token(twofa_token)
        if user is None:
            return Response(
                {'detail': 'Token invalide ou expiré.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        method = user.twofa_method or 'totp'

        # Recovery code fallback
        is_recovery = (
            len(code) == 16
            and TwoFAService.verify_recovery_code(user, code)
        )
        otp_ok = (
            not is_recovery
            and TwoFAService.verify_otp(user, code, method)
        )
        if not (is_recovery or otp_ok):
            return Response(
                {'detail': 'Code de vérification invalide.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        TwoFAService.delete_2fa_token(twofa_token)

        refresh = TokenObtainPairSerializer.get_token(user)
        access_str = str(refresh.access_token)
        refresh_str = str(refresh)
        response = Response(
            {
                'access': access_str,
                'refresh': refresh_str,
            },
            status=status.HTTP_200_OK,
        )
        set_jwt_cookies(response, access_str, refresh_str)
        return response


class CookieTokenRefreshView(TokenRefreshView):
    """jwt/refresh with HttpOnly cookie support (L3.1).

    Reads the refresh token from the request body (mobile/legacy) OR from the
    `sp_refresh` cookie (web). Always sets new cookies alongside the JSON
    response so both auth methods stay in sync.
    """

    def post(self, request, *args, **kwargs):
        if not request.data.get('refresh'):
            cookie_refresh = request.COOKIES.get('sp_refresh')
            if cookie_refresh:
                request.data['refresh'] = cookie_refresh
        response = super().post(request, *args, **kwargs)
        access = response.data.get('access') if hasattr(response, 'data') else None
        refresh = response.data.get('refresh') if hasattr(response, 'data') else None
        if access:
            set_jwt_cookies(response, access, refresh)
        return response


class LogoutView(APIView):
    """POST /auth/logout — clear JWT cookies (L3.1)."""

    permission_classes = [AllowAny]

    def post(self, request):
        response = Response({'detail': 'Déconnecté.'}, status=status.HTTP_200_OK)
        clear_jwt_cookies(response)
        return response
