from django.contrib import admin

from feedback.models import Complaint, Rating, RatingSummary, RatingTag


@admin.register(RatingTag)
class RatingTagAdmin(admin.ModelAdmin):
    list_display = ("label", "code", "direction", "polarity",
                    "min_score", "max_score", "service_area", "active", "order")
    list_filter = ("direction", "polarity", "active", "service_area")
    search_fields = ("code", "label")
    list_editable = ("active", "order")


@admin.register(Rating)
class RatingAdmin(admin.ModelAdmin):
    list_display = ("id", "trip", "direction", "score", "created_at")
    list_filter = ("direction", "score", "created_at")
    search_fields = ("trip__id", "comment")
    readonly_fields = ("trip", "direction", "driver", "customer",
                       "rater", "score", "tags", "comment", "created_at")

    def has_add_permission(self, request):
        # التقييم يأتي من صاحبه لا من لوحة الإدارة.
        return False


@admin.register(RatingSummary)
class RatingSummaryAdmin(admin.ModelAdmin):
    list_display = ("id", "driver", "customer", "average", "count", "recalculated_at")
    search_fields = ("driver__id", "customer__phone")
    readonly_fields = [f.name for f in RatingSummary._meta.fields]

    def has_add_permission(self, request):
        return False


@admin.register(Complaint)
class ComplaintAdmin(admin.ModelAdmin):
    list_display = ("id", "category", "severity", "status",
                    "against_driver", "created_at", "resolved_at")
    # الفرز الافتراضي بالخطورة: الشكوى الحرجة لا تنتظر دورها الزمني.
    list_filter = ("status", "severity", "category", "created_at")
    search_fields = ("id", "description", "trip__id")
    readonly_fields = ("trip", "complainant", "against_driver", "against_customer",
                       "category", "description", "evidence", "created_at",
                       "escalated_at")

    fieldsets = (
        ("الشكوى", {
            "fields": ("trip", "complainant", "against_driver",
                       "against_customer", "category", "description"),
        }),
        ("المعالجة", {
            "fields": ("severity", "status", "resolution_note",
                       "resolved_by", "resolved_at", "escalated_at"),
        }),
        ("الأدلّة المجمّدة", {
            "classes": ("collapse",),
            "fields": ("evidence",),
            "description": (
                "لقطة من وقائع الرحلة لحظة فتح الشكوى. تبقى صالحة بعد حذف "
                "نقاط المسار بسياسة الاحتفاظ (30 يومًا)."
            ),
        }),
    )

    def has_add_permission(self, request):
        return False
