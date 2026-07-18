# payments/services.py
"""
Services layer for payment processing and profile assignment.
"""
from datetime import timedelta
from typing import Optional

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.utils import timezone
from django.db import transaction

from .models import Order, Subscription
from products.models import Profile, Account


class PaymentCompletionService:
    """
    Handles payment completion: subscription creation, profile assignment,
    and WhatsApp notifications.
    """

    def process_completed_payment(self, order: Order) -> bool:
        """
        Traite un paiement complété : met à jour le statut et crée la subscription.

        Args:
            order: La commande complétée

        Returns:
            bool: True si traitement réussi
        """
        with transaction.atomic():
            # Update order status
            order.status = 'completed'
            order.save()

            # Create subscription
            subscription = self._create_subscription(order)

            # Assign profile
            if subscription:
                ProfileAssignmentService().assign_profile(subscription)

                # Notify user via WhatsApp
                from notifications.services import notify_subscription_activated
                transaction.on_commit(lambda: notify_subscription_activated(subscription))


                return True

        return False
    
    def process_validate_payment(self, order: Order) -> bool:
        """
        Traite un paiement validé : met à jour le statut et crée l'abonnement sans lier de profil.
        Pour les renouvellements/prolongements, le mail est envoyé dans _create_subscription.
        Pour les nouveaux abonnements, le mail sera envoyé à la liaison du profil.
        """
        with transaction.atomic():
            order.status = "completed"
            order.save()

            subscription = self._create_subscription(order)

            if subscription:
                return True
        
        return False


    def _create_subscription(self, order: Order) -> Optional[Subscription]:
        """Crée un abonnement pour une commande complétée."""
        # Check if subscription already exists
        if Subscription.objects.filter(order=order).exists():
            return Subscription.objects.get(order=order)

        # Check if this order is a renewal of an existing subscription
        if getattr(order, 'renewal_from', None):
            sub = order.renewal_from

            # Calculate new expiration
            # On utilise la date d'achat de la commande comme point de départ
            # (Pour les renouvellements, elle a été fixée à l'ancienne expiration date)
            start_date = order.purchase_date

            # Add extra days from gift code if applicable
            gift_extra_days = 0
            if getattr(order, 'gift_code', None):
                gift_extra_days = order.gift_code.days
                # Check validity right before applying
                if order.gift_code.is_valid(order.platform):
                    order.gift_code.used_count += 1
                    order.gift_code.save()
                else:
                    gift_extra_days = 0

            # Calculate duration delta
            duration_map = {
                '1 mois': relativedelta(months=1),
                '3 mois': relativedelta(months=3),
                '6 mois': relativedelta(months=6),
                '1 an': relativedelta(years=1),
            }
            delta = duration_map.get(order.duration.lower(), relativedelta(months=1))
            delta += timedelta(days=gift_extra_days)

            sub.expiration_date = start_date + delta
            sub.status = 'active'
            sub.order = order  # Point to the latest order
            sub.save()

            # Link the renewal order to the subscription
            order.subscription = sub
            order.save()

            # Notify renewal and send email notification to admin
            from notifications.services import notify_subscription_renewed
            transaction.on_commit(lambda: notify_subscription_renewed(sub))


            return sub

        # Calculate expiration date based on duration and gift code
        expiration_date = self._calculate_expiration(order)

        subscription = Subscription.objects.create(
            user=order.user,
            order=order,
            expiration_date=expiration_date,
            status='active',
        )

        # Link the initial order to the subscription
        order.subscription = subscription
        order.save()

        # Update user subscription count
        order.user.total_subscriptions += 1
        order.user.save()

        return subscription

    def _calculate_expiration(self, order: Order) -> timezone.datetime:
        """Calcule la date d'expiration basée sur la durée et un éventuel code cadeau."""
        now = timezone.now()
        duration_map = {
            '1 mois': relativedelta(months=1),
            '3 mois': relativedelta(months=3),
            '6 mois': relativedelta(months=6),
            '1 an': relativedelta(years=1),
        }
        delta = duration_map.get(order.duration.lower(), relativedelta(months=1))
        
        # Add extra days from gift code if applicable
        if getattr(order, 'gift_code', None):
            # Check validity right before applying
            if order.gift_code.is_valid(order.platform):
                delta += timedelta(days=order.gift_code.days)
                order.gift_code.used_count += 1
                order.gift_code.save()
                
        return now + delta


class ProfileAssignmentService:
    """Logique d'attribution des profiles aux subscriptions."""

    def assign_profile(self, subscription: Subscription) -> Optional[Profile]:
        """
        Trouve un profile disponible et l'assigne à la subscription.

        Le profile doit:
        - Ne pas être déjà lié à une subscription
        - Appartenir à un compte de la même plateforme
        - Avoir le même type que la commande (mutual, personal, trial)

        Args:
            subscription: La subscription à laquelle assigner un profile

        Returns:
            Profile: Le profile assigné ou None
        """
        if subscription.profile is not None:
            return subscription.profile

        order = subscription.order
        platform = order.platform
        account_type = order.type

        # Find available profile
        candidates = Profile.objects.filter(
            account__platform=platform,
            account__type=account_type,
            account__status='activate',
        ).select_related('account')

        for profile in candidates:
             # Check account-level limits
             if profile.account.available_places > 0:
                 # Check profile-level limits (max 2 users per profile)
                 active_subs_count = profile.subscriptions.filter(status='active').count()
                 if active_subs_count < 2:
                     with transaction.atomic():
                         subscription.profile = profile
                         subscription.save()
                         return profile
        
        return None