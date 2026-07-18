# core/models.py
import os

from django.db import models
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model

User = get_user_model()


# Create your models here.
def poster_upload_path(instance, filename):
    name = instance.name.lower().replace(" ", "-")
    filename = f"{name.lower()}-poster.{filename.split('.')[1]}"

    return os.path.join('posters', name, filename.lower())

def video_upload_path(instance, filename):
    name = instance.name.lower().replace(" ", "-")
    filename = f"{name.lower()}-video.{filename.split('.')[1]}"

    return os.path.join('videos', name, filename.lower())


class Platform(models.Model):
    """
    Represents a streaming platform (Netflix, Spotify, etc.).
    Pricing is managed via related PriceTier objects.
    """
    name = models.CharField(verbose_name='Plateforme', max_length=128, unique=True)
    sub = models.CharField(max_length=125, blank=True, verbose_name="Detail")
    poster = models.ImageField(upload_to=poster_upload_path, null=True, blank=True)
    video = models.FileField(upload_to=video_upload_path, null=True, blank=True)
    has_personal = models.BooleanField(default=False, verbose_name="Offre personnelle disponible")
    order = models.PositiveIntegerField(default=0, verbose_name="Ordre d'affichage")

    class Meta:
        verbose_name = "Plateforme"
        verbose_name_plural = "Plateformes"
        ordering = ['order', 'name']

    def __str__(self):
        return self.name

    def delete(self, *args, **kwargs):
        if self.poster:
            self.poster.delete(save=False)
        if self.video:
            self.video.delete(save=False)
        super().delete(*args, **kwargs)

    def get_shared_prices(self) -> dict:
        """Returns computed {duration: price} dict for shared (mutual) tier."""
        tier = self.price_tiers.filter(account_type='mutual', category='').first()
        if tier:
            return tier.computed_prices()
        return {}

    def get_personal_prices(self) -> dict:
        """
        Returns personal pricing data.
        For platforms with categories (Netflix): {category: {duration: price}}
        For simple platforms: {duration: price}
        """
        tiers = self.price_tiers.filter(account_type='personal')
        if not tiers.exists():
            return {}

        categorized = [t for t in tiers if t.category]
        if categorized:
            # Has sub-categories (e.g. Netflix Mobile/Essentiel/Premium)
            result = {}
            for tier in categorized:
                result[tier.category] = {
                    'prices': tier.computed_prices(),
                    'description': tier.category_description,
                }
            return result
        else:
            # Simple personal pricing
            tier = tiers.first()
            return tier.computed_prices() if tier else {}

    def get_all_pricing_json(self) -> dict:
        """Returns full pricing structure suitable for JS injection."""
        data = {
            'name': self.name,
            'has_personal': self.has_personal,
            'shared': self.get_shared_prices(),
            'personal': self.get_personal_prices(),
        }
        return data


class PriceTier(models.Model):
    """
    Stores ONE base monthly price for a Platform + type + optional category.
    Multi-month prices are auto-calculated from the formula:
      3 mois = (M × 3) − 500
      6 mois = (3m × 2) − 1000
      1 an   = (6m × 2) − 2000
    """
    platform = models.ForeignKey(
        Platform,
        on_delete=models.CASCADE,
        related_name='price_tiers',
        verbose_name='Plateforme'
    )
    account_type = models.CharField(
        max_length=20,
        choices=[('mutual', 'Mutualisé'), ('personal', 'Personnel')],
        default='mutual',
        verbose_name='Type'
    )
    category = models.CharField(
        max_length=50, blank=True, default='',
        verbose_name='Catégorie',
        help_text="Sous-catégorie (ex: Mobile, Essentiel, Premium pour Netflix personnel). Laisser vide sinon."
    )
    base_price = models.PositiveIntegerField(
        verbose_name="Prix de base (1 mois)",
        help_text="Tous les autres prix sont calculés automatiquement à partir de ce prix."
    )
    category_description = models.CharField(
        max_length=100, blank=True, default='',
        verbose_name='Description catégorie',
        help_text="Ex: '1 écran, qualité 480p'"
    )

    class Meta:
        verbose_name = "Tarif"
        verbose_name_plural = "Tarifs"
        unique_together = ('platform', 'account_type', 'category')
        ordering = ['account_type', 'base_price']

    def __str__(self):
        parts = [self.platform.name, self.get_account_type_display()]
        if self.category:
            parts.append(self.category)
        parts.append(f"{self.base_price} FCFA/mois")
        return ' — '.join(parts)

    def computed_prices(self) -> dict:
        """Returns {'1 mois': X, '3 mois': Y, '6 mois': Z, '1 an': W}"""
        m = self.base_price
        three = (m * 3) - 500
        six = (three * 2) - 1000
        year = (six * 2) - 2000
        return {
            '1 mois': m,
            '3 mois': three,
            '6 mois': six,
            '1 an': year,
        }


class Review(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, verbose_name="Utilisateur")
    stars = models.PositiveIntegerField(default=0, verbose_name="Nombre d'étoiles")
    comment = models.TextField(blank=True, verbose_name="Commentaire")

    create_at = models.DateTimeField(auto_now_add=True, verbose_name="Depuis")

    def save(self, *args, **kwargs):
        if self.stars is None:
            self.stars = 0
        if self.stars > 5:
            self.stars = 5
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Avi"
        verbose_name_plural = "Avis"


class Faq(models.Model):
    question = models.CharField(max_length=255, verbose_name="Question")
    answer = models.TextField(verbose_name="Réponse")

    def __str__(self):
        return self.question

    class Meta:
        verbose_name = "FAQ"
        verbose_name_plural = "FAQs"
