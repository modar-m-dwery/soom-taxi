from django.contrib import admin

from .models import Vehicle, VehicleCategory


@admin.register(VehicleCategory)
class VehicleCategoryAdmin(admin.ModelAdmin):
    """
    من هنا تُضاف فئة مركبة جديدة — بلا شيفرة ولا ترحيل ولا إصدار تطبيق.
    الفئة تظهر في /api/v1/config/ فور الحفظ، والتطبيق يقرأها من هناك.
    """

    list_display = (
        "code", "name", "seats", "sort_order",
        "is_active", "areas_label", "vehicles_count",
    )
    list_filter = ("is_active", "areas")
    search_fields = ("code", "name", "name_en")
    filter_horizontal = ("areas",)
    ordering = ("sort_order", "code")

    fieldsets = (
        (None, {
            "fields": ("code", "name", "name_en", "seats", "sort_order"),
            "description": (
                "الرمز هو ما يرسله التطبيق ويخزّنه — اختره مرّة واحدة ولا "
                "تغيّره: أجهزة منشورة تحمله، وتغييره يجعلها ترسل رمزًا لم "
                "يعد موجودًا. لإيقاف فئة أزل علامة «مفعّلة» بدل تعديل رمزها."
            ),
        }),
        ("التوفّر", {
            "fields": ("is_active", "areas"),
            "description": (
                "اترك المدن فارغة لتتوفّر الفئة في كلّ المدن. "
                "وإيقاف التفعيل يُخفيها من التطبيق فورًا بلا مسّ مركبة "
                "مسجَّلة ولا رحلة سابقة."
            ),
        }),
        ("التسعير", {
            "fields": ("fare_multiplier",),
            "classes": ("collapse",),
            "description": "محجوز لتسعير الفئات — لا أثر له اليوم.",
        }),
    )

    @admin.display(description="المدن")
    def areas_label(self, obj):
        names = [a.code for a in obj.areas.all()]
        return "، ".join(names) if names else "كلّ المدن"

    @admin.display(description="مركبات")
    def vehicles_count(self, obj):
        return obj.vehicles.count()

    def get_readonly_fields(self, request, obj=None):
        # الرمز عقدٌ منشور: يُكتب مرّة عند الإنشاء ثمّ يُقفل.
        return ("code",) if obj else ()

    def has_delete_permission(self, request, obj=None):
        # الحذف محميّ بـPROTECT على أيّ حال، لكنّ منعه هنا يعطي المشغّل
        # رسالةً مفهومة بدل صفحة خطأ من قاعدة البيانات.
        if obj is not None and obj.vehicles.exists():
            return False
        return super().has_delete_permission(request, obj)


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "driver",
        "type",
        "make",
        "model",
        "year",
        "color",
        "plate_number",
        "seats",
        "active",
    )

    list_filter = (
        "type",
        "active",
        "year",
    )

    search_fields = (
        "plate_number",
        "make",
        "model",
        "driver__user__phone",
        "driver__user__name",
    )

    list_select_related = (
        "driver",
        "driver__user",
        "type",
    )

    actions = [
        "activate_vehicles",
        "deactivate_vehicles",
    ]

    @admin.action(description="Activate selected vehicles")
    def activate_vehicles(self, request, queryset):
        queryset.update(active=True)

    @admin.action(description="Deactivate selected vehicles")
    def deactivate_vehicles(self, request, queryset):
        queryset.update(active=False)