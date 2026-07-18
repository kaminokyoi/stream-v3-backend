from django.contrib import admin
from .models import Order, Subscription, GiftCode

# Register your models here.
admin.site.register(Order)
admin.site.register(Subscription)
admin.site.register(GiftCode)
