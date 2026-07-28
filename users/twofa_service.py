"""Two-Factor Authentication service — TOTP, Email OTP, WhatsApp OTP."""
import base64
import hashlib
import io
import logging
import secrets
import uuid
from datetime import timedelta

import pyotp
import qrcode
import requests
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from users.models import User, TwoFACode

logger = logging.getLogger(__name__)

OTP_TTL_SECONDS = 300  # 5 minutes
OTP_CACHE_PREFIX = '2fa_token_'
RECOVERY_CODE_COUNT = 10


class TwoFAService:

    @staticmethod
    def generate_totp_secret() -> str:
        return pyotp.random_base32()

    @staticmethod
    def get_totp(secret: str) -> pyotp.TOTP:
        return pyotp.TOTP(secret, interval=30, digits=6)

    @staticmethod
    def verify_totp(secret: str, code: str) -> bool:
        if not secret or not code:
            return False
        return TwoFAService.get_totp(secret).verify(code, valid_window=1)

    @staticmethod
    def get_otpauth_uri(secret: str, phone: str) -> str:
        return pyotp.totp.TOTP(secret).provisioning_uri(name=phone, issuer_name='StreamPartner Admin')

    @staticmethod
    def generate_qr_code_base64(secret: str, phone: str) -> str:
        uri = TwoFAService.get_otpauth_uri(secret, phone)
        img = qrcode.make(uri)
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        return base64.b64encode(buf.getvalue()).decode()

    @staticmethod
    def generate_otp_code() -> str:
        return str(secrets.randbelow(1000000)).zfill(6)

    @staticmethod
    def generate_recovery_codes() -> list[str]:
        return [secrets.token_hex(8).upper() for _ in range(RECOVERY_CODE_COUNT)]

    @staticmethod
    def hash_recovery_code(code: str) -> str:
        return hashlib.sha256(code.encode()).hexdigest()

    @staticmethod
    def store_recovery_codes(user: User, codes: list[str]) -> None:
        hashed = [TwoFAService.hash_recovery_code(c) for c in codes]
        user.twofa_recovery_codes = hashed
        user.save(update_fields=['twofa_recovery_codes'])

    @staticmethod
    def verify_recovery_code(user: User, code: str) -> bool:
        if not code or not user.twofa_recovery_codes:
            return False
        hashed = TwoFAService.hash_recovery_code(code)
        if hashed in user.twofa_recovery_codes:
            user.twofa_recovery_codes.remove(hashed)
            user.save(update_fields=['twofa_recovery_codes'])
            return True
        return False

    @staticmethod
    def create_2fa_token(user_id: int) -> str:
        token = str(uuid.uuid4())
        cache.set(f'{OTP_CACHE_PREFIX}{token}', user_id, OTP_TTL_SECONDS)
        return token

    @staticmethod
    def get_user_from_2fa_token(token: str) -> User | None:
        user_id = cache.get(f'{OTP_CACHE_PREFIX}{token}')
        if not user_id:
            return None
        return User.objects.filter(id=user_id).first()

    @staticmethod
    def delete_2fa_token(token: str) -> None:
        cache.delete(f'{OTP_CACHE_PREFIX}{token}')

    @staticmethod
    def create_and_send_otp(user: User, method: str) -> TwoFACode:
        code = TwoFAService.generate_otp_code()
        expires = timezone.now() + timedelta(seconds=OTP_TTL_SECONDS)
        twofa_code = TwoFACode.objects.create(
            user=user, code=code, method=method, expires_at=expires,
        )
        if method == 'email':
            TwoFAService._send_email_otp(user, code)
        elif method == 'whatsapp':
            TwoFAService._send_whatsapp_otp(user, code)
        return twofa_code

    @staticmethod
    def verify_otp(user: User, code: str, method: str) -> bool:
        if method == 'totp':
            return TwoFAService.verify_totp(user.twofa_secret, code)
        now = timezone.now()
        twofa_code = TwoFACode.objects.filter(
            user=user, code=code, method=method,
            verified=False, expires_at__gt=now,
        ).first()
        if twofa_code:
            twofa_code.verified = True
            twofa_code.save(update_fields=['verified'])
            return True
        return False

    @staticmethod
    def _send_email_otp(user: User, code: str) -> None:
        from notifications.tasks import send_email_task
        if not user.email:
            logger.warning(f"Cannot send 2FA email to user {user.id}: no email")
            return
        subject = "Votre code de vérification 2FA"
        text = f"Votre code de vérification est : {code}\nIl expire dans 5 minutes."
        html = f"""
        <html><body style="font-family: Arial, sans-serif; background-color: #050505; color: #ffffff; padding: 20px;">
          <div style="max-width: 400px; margin: 0 auto; background-color: #121212; border: 1px solid #333; border-radius: 12px; padding: 30px; text-align: center;">
            <h2 style="color: #2a9d8f;">Code de vérification 2FA</h2>
            <p style="color: #cccccc; font-size: 14px;">Voici votre code de vérification :</p>
            <div style="font-size: 32px; font-weight: bold; color: #ffffff; letter-spacing: 8px; margin: 20px 0;">{code}</div>
            <p style="color: #888; font-size: 12px;">Ce code expire dans 5 minutes.</p>
          </div>
        </body></html>
        """
        send_email_task.delay(user.email, subject, text, html)

    @staticmethod
    def _send_whatsapp_otp(user: User, code: str) -> None:
        base_url = getattr(settings, 'WHATOMATE_BASE_URL', 'https://wapi.streampartner.in')
        api_key = getattr(settings, 'WHATOMATE_API_KEY', '')
        template_name = getattr(settings, 'WHATOMATE_TEMPLATE_NAME', 'otp')
        if not api_key:
            logger.error("WHATOMATE_API_KEY not configured")
            return
        phone = user.get_phone_number()
        try:
            resp = requests.post(
                f'{base_url}/api/messages/template',
                headers={
                    'X-API-Key': api_key,
                    'Content-Type': 'application/json',
                },
                json={
                    'phone_number': phone,
                    'template_name': template_name,
                    'template_params': {'1': code},
                },
                timeout=10,
            )
            if not resp.ok:
                logger.error(f"Whatomate API error: {resp.status_code} {resp.text}")
        except Exception as e:
            logger.error(f"Whatomate request failed: {e}")
