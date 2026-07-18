# payment/signals.py

from django.db.models.signals import post_delete
from django.dispatch import receiver
from .models import Order


@receiver(post_delete, sender=Order)
def handle_order_deletion(sender, instance, **kwargs):
    """Décrémente le compteur de commandes de l'utilisateur."""
    # Vérifie que l'utilisateur existe (peut être None à cause de on_delete=SET_NULL)
    if instance.user is not None:
        instance.user.total_orders = max(0, instance.user.total_orders - 1)
        instance.user.save(update_fields=['total_orders'])

