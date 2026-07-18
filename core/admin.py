from django.contrib import admin
from .models import Platform, PriceTier, Review, Faq


class PriceTierInline(admin.TabularInline):
    model = PriceTier
    extra = 1
    fields = ('account_type', 'category', 'base_price', 'category_description', 'display_computed')
    readonly_fields = ('display_computed',)

    def display_computed(self, obj):
        if obj.pk and obj.base_price:
            p = obj.computed_prices()
            return f"3m: {p['3 mois']}F · 6m: {p['6 mois']}F · 1an: {p['1 an']}F"
        return "—"
    display_computed.short_description = "Prix calculés"


class PlatformAdmin(admin.ModelAdmin):
    list_display = ('name', 'has_personal', 'order', 'display_tiers_summary')
    list_editable = ('order', 'has_personal')
    inlines = [PriceTierInline]

    fieldsets = (
        (None, {
            'fields': ('name', 'sub', 'has_personal', 'order'),
        }),
        ("Media", {
            'fields': ('poster', 'video'),
        }),
    )

    def display_tiers_summary(self, obj):
        tiers = obj.price_tiers.all()
        if not tiers.exists():
            return "Aucun tarif"
        parts = []
        for t in tiers:
            label = f"{t.get_account_type_display()}"
            if t.category:
                label += f" ({t.category})"
            label += f": {t.base_price}F"
            parts.append(label)
        return " | ".join(parts)
    display_tiers_summary.short_description = "Tarifs"


class ReviewAdmin(admin.ModelAdmin):
    list_display = ('user', 'stars', 'comment', 'create_at')
    list_editable = ('stars',)

    fieldsets = [
        (None, {
            'fields': ('user',),
        }),
        ("Etoile", {
            'fields': ('stars',)
        }),
        ("Commentaire (optionnel)", {
            'fields': ('comment',)
        })
    ]


class FaqAdmin(admin.ModelAdmin):
    list_display = ('question', 'answer')

    fieldsets = [
        ('Question', {
            'fields': ('question',),
        }),
        ('Answer', {
            'fields': ('answer',)
        })
    ]


admin.site.register(Platform, PlatformAdmin)
admin.site.register(Review, ReviewAdmin)
admin.site.register(Faq, FaqAdmin)
