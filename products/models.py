# product/models.py

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.conf import settings
from core.utils import platform_choices
from dateutil.relativedelta import relativedelta
from cryptography.fernet import Fernet
import base64
import hashlib


def get_fernet():
    key = getattr(settings, 'FERNET_KEY', None)
    if not key:
        key = base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest())
    return Fernet(key)


class EncryptedCharField(models.CharField):
    def from_db_value(self, value, expression, connection):
        if value is None:
            return value
        try:
            return get_fernet().decrypt(value.encode()).decode()
        except Exception:
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


class Card(models.Model):
    numero = EncryptedCharField(max_length=255, verbose_name="Numéro")
    nom = models.CharField(max_length=255, verbose_name="Nom de la carte")
    cvv = models.CharField(max_length=10, verbose_name="CVV")
    telephone = models.CharField(max_length=50, verbose_name="Numéro de téléphone")
    expiration_date = models.DateField(verbose_name="Date d'expiration")
    status = models.CharField(
        default='actif',
        choices=[
            ('actif', 'Actif'),
            ('inactif', 'Inactif'),
        ],
        max_length=10,
        verbose_name="Statut"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Date de création')

    @property
    def formatted_numero(self):
        clean_num = str(self.numero).replace(" ", "")
        return " ".join([clean_num[i:i+4] for i in range(0, len(clean_num), 4)])

    @property
    def masked_numero(self):
        clean_num = str(self.numero).replace(" ", "")
        if len(clean_num) <= 4:
            return clean_num
        masked = "*" * (len(clean_num) - 4) + clean_num[-4:]
        return " ".join([masked[i:i+4] for i in range(0, len(masked), 4)])

    class Meta:
        verbose_name = 'Carte'
        verbose_name_plural = 'Cartes'
        ordering = ['expiration_date', 'status']

    def __str__(self):
        return f"Carte {self.nom} - {self.telephone}"


class AccountMarker(models.Model):
    name = models.CharField(max_length=100, verbose_name="Nom")
    color = models.CharField(max_length=20, default='#ffffff', verbose_name="Couleur")

    def __str__(self):
        return self.name + " - " + self.color

    class Meta:
        verbose_name = "Marqueur"
        verbose_name_plural = "Marqueurs"


class Account(models.Model):
    number = models.CharField(max_length=100, verbose_name="Numéro")
    platform = models.CharField(choices=platform_choices, max_length=255, verbose_name="Plateforme")
    email = models.EmailField(verbose_name="Email")
    password = models.CharField(max_length=255, verbose_name="Mot de passe")

    profiles = models.PositiveIntegerField(default=0, verbose_name="N° Profile")
    max_profile = models.PositiveIntegerField(default=5, verbose_name="Profile maximum")

    type = models.CharField(
        default='mutual',
        choices=[
            ('mutual', 'Mutualisé'),
            ('personal', 'Personnel'),
        ],
        max_length=100
    )

    # New fields
    place = models.PositiveIntegerField(default=2, verbose_name="Places disponibles",
                                        help_text="Nombre maximum d'abonnements pouvant être liés à ce compte")
    start_date = models.DateTimeField(null=True, blank=True, verbose_name="Date de début")
    end_date = models.DateTimeField(null=True, blank=True, verbose_name="Date de fin")
    month_count = models.PositiveIntegerField(default=0, verbose_name="Nombre de mois")
    card = models.ForeignKey(Card, null=True, blank=True, on_delete=models.SET_NULL, verbose_name="Carte")
    markers = models.ManyToManyField(AccountMarker, blank=True, related_name="accounts", verbose_name="Marqueurs")
    remaining_day = models.PositiveIntegerField(default=0, verbose_name="Jours restants")
    status = models.CharField(
        default='activate',
        choices=[
            ('activate', 'Activé'),
            ('desactivate', 'Désactivé'),
        ],
        max_length=20,
        verbose_name="Statut"
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Date de création')

    def add_profile(self):
        if self.profiles >= self.max_profile:
            return False
        self.profiles += 1
        self.save()
        return True

    def delete_profile(self):
        self.profiles -= 1
        self.save()

    @property
    def used_places(self):
        """Number of active subscriptions linked to profiles of this account."""
        from payments.models import Subscription
        return Subscription.objects.filter(
            profile__account=self,
            status='active'
        ).count()

    @property
    def available_places(self):
        """Number of available places for new subscriptions."""
        return max(0, self.place - self.used_places)

    def update_remaining_days(self):
        """Recalculate remaining_day based on end_date."""
        if self.end_date:
            delta = self.end_date - timezone.now()
            self.remaining_day = max(0, delta.days)
        else:
            self.remaining_day = 0
        self.save(update_fields=['remaining_day'])

    @property
    def current_remaining_days(self):
        """Calculate exact remaining days dynamically from today."""
        if self.end_date:
            delta = self.end_date.date() - timezone.now().date()
            return max(0, delta.days)
        return 0

    def __str__(self):
        return f"Compte n°{self.number} {self.platform}"

    def save(self, *args, **kwargs):
        if self.type == 'personal':
            self.max_profile = 1
        # Auto-calculate end_date from start_date + month_count
        if self.start_date and self.month_count:
            self.end_date = self.start_date + relativedelta(months=self.month_count)
        # Auto-calculate remaining_day on save if end_date is set
        if self.end_date:
            delta = self.end_date - timezone.now()
            self.remaining_day = max(0, delta.days)
        super().save(*args, **kwargs)

    @property
    def used_profiles(self):
        return self.profiles

    class Meta:
        verbose_name = 'Compte'
        verbose_name_plural = 'Comptes'
        constraints = [
            models.UniqueConstraint(fields=['number', 'platform'], name='unique_account_number_per_platform'),
            models.UniqueConstraint(fields=['email', 'platform'], name='unique_account_email_per_platform')
        ]
        ordering = ['-remaining_day']


class Profile(models.Model):
    number = models.CharField(verbose_name='Numéro', max_length=128)
    code = models.CharField(verbose_name='Code', max_length=128)
    account = models.ForeignKey(Account, on_delete=models.CASCADE, null=True, verbose_name="Compte")
    place = models.PositiveIntegerField(
        default=1,
        choices=[(1, 'Place 1'), (2, 'Place 2')],
        verbose_name="Place",
        help_text="Numéro de place (1 ou 2)"
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Date de création')

    def __str__(self):
        return f'Profile n°{self.number} {self.account.platform}'

    def save(self, *args, **kwargs):
        if not self.pk:
            if not self.account.add_profile():
                raise ValidationError("Ce compte a atteint le nombre maximum de profils")
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = 'Profil'
        verbose_name_plural = 'Profils'
        constraints = [
            models.UniqueConstraint(fields=['number', 'account'], name='unique_profile_number_per_account')
        ]
