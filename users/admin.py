from django.contrib import admin
from .models import User

# Register your models here.
class UserAdmin(admin.ModelAdmin):
    list_display = ('first_name', 'last_name', 'country_code', 'phone_number', 'total_subscriptions')


admin.site.register(User, UserAdmin)
