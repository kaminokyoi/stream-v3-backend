"""Reusable encrypted field for sensitive data (Card.numero, twofa_secret, etc.).

Uses Fernet symmetric encryption keyed by settings.FERNET_KEY (falls back to
a derived SECRET_KEY if missing)."""
import base64
import hashlib
import logging

from django.conf import settings
from django.db import models
from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)


def get_fernet() -> Fernet:
    key = getattr(settings, 'FERNET_KEY', None)
    if not key:
        key = base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest())
    return Fernet(key)


class EncryptedCharField(models.CharField):
    """CharField that transparently encrypts/decrypts at the DB boundary.

    Existing plain-text values are gracefully preserved (decrypt fails, returns
    the original value) so migrations on previously-plain columns don't break
    reads. A one-shot re-save data migration encrypts existing rows in place.
    """

    def from_db_value(self, value, expression, connection):
        if value is None:
            return value
        try:
            return get_fernet().decrypt(value.encode()).decode()
        except Exception:
            logger.warning(
                "EncryptedCharField: failed to decrypt value (len=%d). Possible key mismatch or legacy plain-text value.",
                len(str(value)),
            )
            return value

    def to_python(self, value):
        if value is None:
            return value
        try:
            return get_fernet().decrypt(value.encode()).decode()
        except Exception:
            return value

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value is None or value == '':
            return value
        try:
            get_fernet().decrypt(value.encode())
            return value
        except Exception:
            return get_fernet().encrypt(str(value).encode()).decode()