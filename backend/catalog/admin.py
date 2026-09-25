from django.contrib import admin

from catalog.models import FeatureFlag, FeatureFlagAreaOverride, Service, ServiceAreaOverride


class ServiceAreaOverrideInline(admin.TabularInline):
    model = ServiceAreaOverride
    extra = 0


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "status", "sort_order", "updated_at")
    # الإطفاء والإعادة من القائمة نفسها بضغطة: «شيل السرفيس أو رجّعو».
    list_editable = ("status", "sort_order")
    readonly_fields = ("code", "updated_at")
    inlines = [ServiceAreaOverrideInline]

    def has_add_permission(self, request):
        # الخدمة تُعرَّف في الشيفرة (catalog/registry.py) — صفٌّ بلا تنفيذ
        # يظهر للزبون زرًّا لا يفعل شيئًا.
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class FeatureFlagAreaOverrideInline(admin.TabularInline):
    model = FeatureFlagAreaOverride
    extra = 0


@admin.register(FeatureFlag)
class FeatureFlagAdmin(admin.ModelAdmin):
    list_display = ("key", "description", "enabled", "updated_at")
    list_editable = ("enabled",)
    readonly_fields = ("key", "updated_at")
    inlines = [FeatureFlagAreaOverrideInline]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
