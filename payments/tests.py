from django.test import TestCase
from django.core.exceptions import ValidationError
from payments.models import PaymentNumber

class PaymentNumberTestCase(TestCase):
    def test_payment_number_creation(self):
        number = PaymentNumber.objects.create(
            provider='orange',
            number='655887498',
            name='Test Orange User',
            is_active=True
        )
        self.assertEqual(number.provider, 'orange')
        self.assertEqual(number.number, '655887498')
        self.assertEqual(number.name, 'Test Orange User')
        self.assertTrue(number.is_active)

    def test_active_limit_constraint(self):
        # We can activate up to 2 numbers
        n1 = PaymentNumber.objects.create(
            provider='orange',
            number='655887491',
            name='User 1',
            is_active=True
        )
        n2 = PaymentNumber.objects.create(
            provider='orange',
            number='655887492',
            name='User 2',
            is_active=True
        )

        # Activating a third number should fail with ValidationError
        n3 = PaymentNumber(
            provider='orange',
            number='655887493',
            name='User 3',
            is_active=True
        )
        with self.assertRaises(ValidationError):
            n3.save()

        # However, we can save it as inactive
        n3.is_active = False
        n3.save()
        self.assertFalse(n3.is_active)

        # Deactivating one allows us to activate the other
        n1.is_active = False
        n1.save()

        n3.is_active = True
        n3.save()
        self.assertTrue(n3.is_active)

    def test_active_limit_separate_by_provider(self):
        # We can have 2 active Orange AND 2 active MTN numbers
        PaymentNumber.objects.create(provider='orange', number='1', name='O1', is_active=True)
        PaymentNumber.objects.create(provider='orange', number='2', name='O2', is_active=True)
        PaymentNumber.objects.create(provider='mtn', number='3', name='M1', is_active=True)
        PaymentNumber.objects.create(provider='mtn', number='4', name='M2', is_active=True)

        self.assertEqual(PaymentNumber.objects.filter(is_active=True).count(), 4)

