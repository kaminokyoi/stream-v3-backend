# users/models.py

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin, Permission, Group
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

# Gestionnaire pour notre modèle utilisateur personnalisé
class UserManager(BaseUserManager):
    """
    Gestionnaire personnalisé pour le modèle User où le numéro de téléphone est l'identifiant unique
    pour l'authentification au lieu des noms d'utilisateur.
    """
    def create_user(self, phone_number, password, **extra_fields):
        """
        Crée et sauvegarde un utilisateur avec le numéro de téléphone et le mot de passe donnés.
        """
        if not phone_number:
            raise ValueError(_('Le numéro de téléphone doit être renseigné'))
        user = self.model(phone_number=phone_number, **extra_fields)
        user.set_password(password) # Gère le hachage du mot de passe
        user.save(using=self._db)
        return user

    def create_superuser(self, phone_number, password, **extra_fields):

        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError(_('Le superutilisateur doit avoir is_staff=True.'))
        if extra_fields.get('is_superuser') is not True:
            raise ValueError(_('Le superutilisateur doit avoir is_superuser=True.'))

        # (si différents de create_user)
        required_fields = ['first_name', 'last_name', 'country_code'] # Adapté de REQUIRED_FIELDS ci-dessous
        for field_name in required_fields:
             if not extra_fields.get(field_name):
                 raise ValueError(_(f'Le champ {field_name} est requis pour le superutilisateur'))


        return self.create_user(phone_number, password, **extra_fields)



class User(AbstractBaseUser, PermissionsMixin):

    first_name = models.CharField(max_length=100, verbose_name='Prénom')
    last_name = models.CharField(max_length=100, verbose_name='Nom')
    country_code = models.CharField(max_length=5, verbose_name='Indicatif')
    phone_number = models.CharField(max_length=20, unique=True, verbose_name='Téléphone')

    total_orders = models.PositiveIntegerField(default=0, verbose_name='Total des commandes')
    total_subscriptions = models.PositiveIntegerField(default=0, verbose_name='Total des abonnements')
    
    email = models.EmailField(blank=True, null=True, unique=True, verbose_name="Email")

    groups = models.ManyToManyField(
        Group,
        verbose_name=_('groups'),
        blank=True,
        help_text=_(
            'The groups this user belongs to. A user will get all permissions '
            'granted to each of their groups.'
        ),
        related_name="customuser_set", # Nom unique pour l'accesseur inverse
        related_query_name="customuser",
    )
    user_permissions = models.ManyToManyField(
        Permission,
        verbose_name=_('user permissions'),
        blank=True,
        help_text=_('Specific permissions for this user.'),
        related_name="customuser_set",
    )

    is_active = models.BooleanField(default=True, verbose_name="Actif")
    is_staff = models.BooleanField(default=False, verbose_name="Staff")
    is_admin = models.BooleanField(default=False, verbose_name="Admin")
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = 'phone_number'
    REQUIRED_FIELDS = ['first_name', 'last_name', 'country_code']

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}"

    def get_short_name(self):
        return self.first_name

    def get_phone_number(self):
        return f"+{self.country_code}{self.phone_number}" if not self.country_code.startswith('+') else f"{self.country_code}{self.phone_number}"

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    class Meta:
        verbose_name = 'Utilisateur'
        verbose_name_plural = 'Utilisateurs'

