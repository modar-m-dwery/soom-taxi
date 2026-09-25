from django.contrib import admin
from django.utils.html import format_html

from ads.models import Ad


@admin.register(Ad)
class AdAdmin(admin.ModelAdmin):
    list_display = ("preview", "title", "placement", "is_active", "starts_at", "ends_at", "impressions", "clicks", "ctr")
    list_editable = ("is_active",)
    list_filter = ("placement", "is_active", "areas")
    filter_horizontal = ("areas",)
    readonly_fields = ("impressions", "clicks", "preview")

    @admin.display(description="")
    def preview(self, obj):
        if not obj.pk or not obj.image:
            return "—"
        return format_html('<img src="/api/v1/ads/{}/image/" style="height:40px;border-radius:6px">', obj.pk)

    @admin.display(description="نسبة النقر ٪")
    def ctr(self, obj):
        return obj.ctr
