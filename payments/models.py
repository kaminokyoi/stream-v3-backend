# payment/models.py


import uuid
from django.db import models
from users.models import User
from products.models import Profile
from django.utils import timezone
from core.utils import platform_choices, calculate_expiration


def payment_proof_path(instance, filename):
    """Upload path for payment proofs."""
    return f'payment_proofs/{instance.order.order_id}/{filename}'


# Create your models here.
class Order(models.Model):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, verbose_name='Utilisateur')
    order_id = models.UUIDField(default=uuid.uuid4, verbose_name='Order Id')
    platform = models.CharField(choices=platform_choices, verbose_name='Plateforme', max_length=128)
    price = models.PositiveIntegerField(verbose_name='Prix')
    duration = models.CharField(verbose_name='Durée', max_length=8)
    purchase_date = models.DateTimeField(default=timezone.now, verbose_name='Date d\'achat')
    status = models.CharField(
        default='pending_payment',
        max_length=50,
        choices=[
            ('pending_payment', 'En attente de paiement'),
            ('pending_validation', 'En attente de validation'),
            ('completed', 'Complété'),
            ('failed', 'Échoué'),
        ],
        verbose_name='Statut'
    )

    motif = models.CharField(
        max_length=20,
        default='subscription',
        choices=[
            ('subscription', 'Abonnement'),
            ('renewal', 'Renouvellement'),
            ('extension', 'Prolongement'),
        ],
        verbose_name='Motif'
    )

    type = models.CharField(
        default='mutual',
        choices=[
            ('mutual', 'Mutualisé'),
            ('personal', 'Personnel'),
        ],
        max_length=100
    )

    renewal_from = models.ForeignKey(
        'Subscription',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='renewals',
        verbose_name="Renouvellement de"
    )

    gift_code = models.ForeignKey(
        'GiftCode',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Code Promo utilisé"
    )

    subscription = models.ForeignKey(
        'Subscription',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='order_history',
        verbose_name="Abonnement lié"
    )

    def save(self, *args, **kwargs):
        if not self.pk and self.user:
            from django.db.models import F
            User = self.user.__class__
            User.objects.filter(pk=self.user.pk).update(total_orders=F('total_orders') + 1)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Order {self.order_id} - {self.platform}"

    class Meta:
        verbose_name = "Commande"
        verbose_name_plural = "Commandes"
        indexes = [
            models.Index(fields=['status', 'purchase_date'], name='order_status_date_idx'),
            models.Index(fields=['-purchase_date'], name='order_purchase_date_desc'),
            models.Index(fields=['platform', 'status'], name='order_platform_status_idx'),
        ]


class Subscription(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='subscriptions')
    expiration_date = models.DateTimeField(verbose_name="Date d'expiration")

    profile = models.ForeignKey(
        Profile,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        verbose_name="Profile",
        related_name='subscriptions',
    )

    markers = models.ManyToManyField(
        'SubscriptionMarker',
        blank=True,
        related_name='subscriptions',
        verbose_name="Marqueurs",
    )

    status = models.CharField(default="active", verbose_name="Statut", max_length=10)

    def __str__(self):
        return f"Abonnement {self.order.platform}"
    
    def save(self, *args, **kwargs):
        if not self.pk and not hasattr(self, 'expiration_date') or not self.expiration_date:
            self.expiration_date = calculate_expiration(self.order.duration, self.order.purchase_date)
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Abonnement"
        verbose_name_plural = "Abonnements"
        indexes = [
            models.Index(fields=['status', 'expiration_date'], name='sub_status_exp_idx'),
            models.Index(fields=['user', 'status'], name='sub_user_status_idx'),
        ]


class PaymentProof(models.Model):
    """Preuve de paiement manuel (Mobile Money)."""
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='proof')
    image = models.ImageField(upload_to=payment_proof_path, verbose_name="Capture d'écran")
    image2 = models.ImageField(upload_to=payment_proof_path, null=True, blank=True, verbose_name="Capture d'écran 2 (optionnel)")
    submitted_at = models.DateTimeField(auto_now_add=True, verbose_name="Date de soumission")

    # Validation par admin
    validated = models.BooleanField(default=False, verbose_name="Validé")
    validated_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='validated_proofs',
        verbose_name="Validé par"
    )
    validated_at = models.DateTimeField(null=True, blank=True, verbose_name="Date de validation")

    # Rejection
    rejected = models.BooleanField(default=False, verbose_name="Refusé")
    rejection_reason = models.TextField(blank=True, verbose_name="Raison du refus")

    def __str__(self):
        if self.validated:
            status = "Validé"
        elif self.rejected:
            status = "Refusé"
        else:
            status = "En attente"
        return f"Preuve {self.order.order_id} - {status}"
    
    def delete(self, *args, **kwargs):
        self.image.delete()

        super().delete(*args, **kwargs)

    class Meta:
        verbose_name = "Preuve de paiement"
        verbose_name_plural = "Preuves de paiement"
        indexes = [
            models.Index(fields=['validated', 'rejected', '-submitted_at'], name='proof_status_idx'),
        ]


class GiftCode(models.Model):
    """Code cadeau offrant des jours supplémentaires sur un abonnement."""
    code = models.CharField(max_length=50, unique=True, verbose_name="Code")
    days = models.PositiveIntegerField(default=2, verbose_name="Jours offerts")
    platform = models.ForeignKey(
        'core.Platform',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='gift_codes',
        verbose_name="Plateforme",
        help_text="Laisser vide pour un code valable sur toutes les plateformes."
    )
    start_date = models.DateTimeField(verbose_name="Date de début")
    end_date = models.DateTimeField(verbose_name="Date de fin")
    status = models.BooleanField(default=True, verbose_name="Actif")
    usage_limit = models.PositiveIntegerField(
        default=0,
        verbose_name="Limite d'utilisation",
        help_text="Nombre maximum d'utilisations (0 pour illimité)"
    )
    used_count = models.PositiveIntegerField(default=0, verbose_name="Nombre de fois utilisé")

    def is_valid(self, platform_name=None):
        """Check if the gift code is currently valid, optionally for a specific platform."""
        from django.utils import timezone
        now = timezone.now()
        if not (self.status and self.start_date <= now <= self.end_date):
            return False
            
        # Check usage limits
        if self.usage_limit > 0 and self.used_count >= self.usage_limit:
            return False

        # If the code is platform-specific, check the platform matches
        if self.platform and platform_name:
            return self.platform.name == platform_name
        return True

    def __str__(self):
        label = f"GiftCode {self.code} ({self.days}j)"
        if self.platform:
            label += f" [{self.platform.name}]"
        return label

    class Meta:
        verbose_name = "Code Promo"
        verbose_name_plural = "Codes Promos"


class SubscriptionProfileHistory(models.Model):
    """Historique des profils liés à un abonnement.
    Enregistre chaque fois qu'un profil est délié d'un abonnement.
    """
    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.CASCADE,
        related_name='profile_history',
        verbose_name="Abonnement"
    )
    profile_number = models.CharField(max_length=128, verbose_name="Numéro du profil")
    profile_code = models.CharField(max_length=128, blank=True, default='', verbose_name="Code PIN du profil")
    account_number = models.CharField(max_length=128, blank=True, default='', verbose_name="Numéro du compte")
    platform = models.CharField(max_length=255, blank=True, default='', verbose_name="Plateforme")
    linked_at = models.DateTimeField(null=True, blank=True, verbose_name="Lié le")
    unlinked_at = models.DateTimeField(auto_now_add=True, verbose_name="Délié le")

    def __str__(self):
        return f"Historique: Abonnement #{self.subscription_id} → Profil #{self.profile_number}"

    class Meta:
        verbose_name = "Historique de profil"
        verbose_name_plural = "Historiques de profils"
        ordering = ['-unlinked_at']

class SubscriptionMarker(models.Model):
    name = models.CharField(max_length=100, verbose_name="Nom")
    color = models.CharField(max_length=20, default='#ffffff', verbose_name="Couleur")

    def __str__(self):
        return self.name + " - " + self.color

    class Meta:
        verbose_name = "Marqueur"
        verbose_name_plural = "Marqueurs"


class PaymentNumber(models.Model):
    PROVIDER_CHOICES = [
        ('orange', 'Orange Money'),
        ('mtn', 'MTN Mobile Money'),
    ]

    provider = models.CharField(max_length=10, choices=PROVIDER_CHOICES, verbose_name="Opérateur")
    number = models.CharField(max_length=50, verbose_name="Numéro de téléphone")
    name = models.CharField(max_length=100, verbose_name="Nom du propriétaire")
    is_active = models.BooleanField(default=False, verbose_name="Actif")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Créé le")

    class Meta:
        verbose_name = "Numéro de Paiement"
        verbose_name_plural = "Numéros de Paiement"
        ordering = ['provider', '-created_at']

    def __str__(self):
        return f"{self.get_provider_display()} - {self.number} ({self.name})"

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.is_active:
            active_count = PaymentNumber.objects.filter(provider=self.provider, is_active=True).exclude(pk=self.pk).count()
            if active_count >= 2:
                raise ValidationError({
                    'is_active': f"Vous ne pouvez pas activer plus de 2 numéros pour {self.get_provider_display()} à la fois."
                })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)