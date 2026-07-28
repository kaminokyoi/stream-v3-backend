"""Admin 2FA endpoints: status, setup, verify-setup, disable, recovery."""
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response

from users.models import User
from users.twofa_service import TwoFAService


@api_view(['GET'])
@permission_classes([IsAdminUser])
def twofa_status(request):
    user = request.user
    return Response({
        'enabled': user.twofa_enabled,
        'method': user.twofa_method,
        'has_recovery_codes': len(user.twofa_recovery_codes) > 0,
    })


@api_view(['POST'])
@permission_classes([IsAdminUser])
def twofa_setup(request):
    user = request.user
    method = request.data.get('method', 'totp')
    if method not in ('totp', 'email', 'whatsapp'):
        return Response({'detail': 'Méthode invalide. Choisissez: totp, email, whatsapp.'}, status=status.HTTP_400_BAD_REQUEST)

    if method == 'totp':
        secret = TwoFAService.generate_totp_secret()
        qr_b64 = TwoFAService.generate_qr_code_base64(secret, user.phone_number)
        uri = TwoFAService.get_otpauth_uri(secret, user.phone_number)
        user.twofa_secret = secret
        user.save(update_fields=['twofa_secret'])
        return Response({
            'qr_code': qr_b64,
            'otpauth_uri': uri,
            'secret': secret,
            'detail': 'Scannez le QR code avec Google Authenticator et saisissez le code.',
        })
    elif method == 'email':
        if not user.email:
            return Response({'detail': 'Vous devez avoir un email configuré.'}, status=status.HTTP_400_BAD_REQUEST)
        TwoFAService.create_and_send_otp(user, 'email')
        return Response({'detail': f'Un code a été envoyé à {user.email}.'})
    elif method == 'whatsapp':
        TwoFAService.create_and_send_otp(user, 'whatsapp')
        return Response({'detail': f'Un code a été envoyé via WhatsApp au {user.get_phone_number()}.'})


@api_view(['POST'])
@permission_classes([IsAdminUser])
def twofa_verify_setup(request):
    user = request.user
    code = request.data.get('code', '').strip()
    method = request.data.get('method', 'totp')
    if not code:
        return Response({'detail': 'Code requis.'}, status=status.HTTP_400_BAD_REQUEST)

    if not TwoFAService.verify_otp(user, code, method):
        return Response({'detail': 'Code invalide.'}, status=status.HTTP_400_BAD_REQUEST)

    user.twofa_enabled = True
    user.twofa_method = method
    user.save(update_fields=['twofa_enabled', 'twofa_method'])

    recovery_codes = TwoFAService.generate_recovery_codes()
    TwoFAService.store_recovery_codes(user, recovery_codes)

    return Response({
        'detail': '2FA activé avec succès.',
        'recovery_codes': recovery_codes,
    })


@api_view(['POST'])
@permission_classes([IsAdminUser])
def twofa_disable(request):
    user = request.user
    password = request.data.get('password', '')
    if not password or not user.check_password(password):
        return Response({'detail': 'Mot de passe incorrect.'}, status=status.HTTP_400_BAD_REQUEST)

    user.twofa_enabled = False
    user.twofa_secret = ''
    user.twofa_recovery_codes = []
    user.save(update_fields=['twofa_enabled', 'twofa_secret', 'twofa_recovery_codes'])
    return Response({'detail': '2FA désactivé.'})


@api_view(['POST'])
@permission_classes([IsAdminUser])
def twofa_regenerate_recovery(request):
    user = request.user
    if not user.twofa_enabled:
        return Response({'detail': '2FA n\'est pas activé.'}, status=status.HTTP_400_BAD_REQUEST)
    recovery_codes = TwoFAService.generate_recovery_codes()
    TwoFAService.store_recovery_codes(user, recovery_codes)
    return Response({
        'detail': 'Nouveaux codes générés.',
        'recovery_codes': recovery_codes,
    })
