from django.contrib import admin

from ops.models import AdminAction, LegacyRide


@admin.register(AdminAction)
class AdminActionAdmin(admin.ModelAdmin):
    list_display = ("id", "created_at", "kind", "actor",
                    "target_type", "target_id")
    list_filter = ("kind", "target_type", "created_at")
    search_fields = ("actor__phone", "reason", "target_id")
    readonly_fields = [f.name for f in AdminAction._meta.fields]

    def has_add_permission(self, request):
        # السجلّ يُكتب من الخدمات لا من اللوحة.
        return False

    def has_change_permission(self, request, obj=None):
        # سجلّ تدقيق قابل للتعديل ليس سجلّ تدقيق.
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(LegacyRide)
class LegacyRideAdmin(admin.ModelAdmin):
    list_display = ("datetime", "customer_phone", "driver_phone", "origin", "destination",
                    "area", "offers", "price", "minutes_to_offer", "status", "rating")
    list_filter = ("status", "area")
    search_fields = ("customer_phone", "driver_phone", "origin", "destination")
    date_hierarchy = "datetime"
