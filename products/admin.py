from django.contrib import admin
from .models import Account, Profile

# Register your models here.
class AccountAdmin(admin.ModelAdmin):
    list_display = (
        'number', 'platform',
        'email', 'password',
        'type', 'profiles',
        'max_profile'
    )


class ProfileAdmin(admin.ModelAdmin):
    list_display = ('number', 'code', 'account', 'platform_display')

    def platform_display(self, obj):
        return obj.account.platform
    platform_display.short_description = "Plateforme"

admin.site.register(Account, AccountAdmin)
admin.site.register(Profile, ProfileAdmin)
