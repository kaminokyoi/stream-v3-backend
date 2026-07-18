from django.conf import settings
from django.db import models


class PushToken(models.Model):
    """Expo push token for a user's device. Supports multiple devices per user."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='push_tokens',
        verbose_name='Utilisateur',
    )
    token = models.CharField(max_length=255, unique=True, verbose_name='Token Expo')
    platform = models.CharField(
        max_length=10,
        choices=[('ios', 'iOS'), ('android', 'Android')],
        default='android',
        verbose_name='Plateforme',
    )
    is_active = models.BooleanField(default=True, verbose_name='Actif')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Date de création')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Date de mise à jour')

    class Meta:
        verbose_name = 'Token Push'
        verbose_name_plural = 'Tokens Push'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.get_full_name()} — {self.platform} ({self.token[:20]}...)"


class PushNotification(models.Model):
    """Push notification record — stored for history and read/unread tracking."""
    NOTIFICATION_TYPES = [
        ('order', 'Commande'),
        ('subscription', 'Abonnement'),
        ('payment', 'Paiement'),
        ('user', 'Utilisateur'),
        ('system', 'Système'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='push_notifications',
        verbose_name='Destinataire',
    )
    title = models.CharField(max_length=255, verbose_name='Titre')
    body = models.TextField(verbose_name='Contenu')
    data = models.JSONField(default=dict, blank=True, verbose_name='Données (deep linking)')
    notification_type = models.CharField(
        max_length=20,
        choices=NOTIFICATION_TYPES,
        default='system',
        verbose_name='Type',
    )
    is_read = models.BooleanField(default=False, verbose_name='Lu')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Date de création')
    read_at = models.DateTimeField(null=True, blank=True, verbose_name='Date de lecture')

    class Meta:
        verbose_name = 'Notification Push'
        verbose_name_plural = 'Notifications Push'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_read']),
            models.Index(fields=['user', 'notification_type']),
        ]

    def __str__(self):
        return f"{self.title} → {self.user.get_full_name()}"
