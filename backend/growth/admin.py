from django.contrib import admin, messages
from django.utils import timezone
from django.utils.html import format_html

from growth.models import (
    Campaign,
    CampaignRecipient,
    CommissionRule,
    DriverGroup,
    IncentiveAward,
    IncentiveProgram,
)


@admin.register(DriverGroup)
class DriverGroupAdmin(admin.ModelAdmin):
    list_display = ("name", "description", "drivers_count")
    filter_horizontal = ("drivers",)
    search_fields = ("name",)

    @admin.display(description="عدد السائقين")
    def drivers_count(self, obj):
        return obj.drivers.count()


@admin.register(CommissionRule)
class CommissionRuleAdmin(admin.ModelAdmin):
    list_display = ("name", "scope", "target", "rate_pct", "fixed_fee", "is_active", "valid_until")
    list_editable = ("rate_pct", "is_active")
    list_filter = ("scope", "is_active", "area")
    autocomplete_fields = ("driver",)
    fieldsets = (
        (None, {"fields": ("name", "scope", "driver", "group", "area", "is_active")}),
        ("المبلغ", {
            "fields": ("rate_pct", "fixed_fee", "min_fee", "max_fee"),
            "description": (
                "الأدقّ يغلب: سائق ← مجموعة ← مدينة ← عامّة. المؤسّسون معفَون "
                "دائمًا، وسقف العمولة القانونيّ للمدينة لا يُتجاوز."
            ),
        }),
        ("الصلاحية", {"fields": ("valid_from", "valid_until")}),
    )

    @admin.display(description="على")
    def target(self, obj):
        return obj.driver or obj.group or obj.area or "الكلّ"


class CampaignRecipientInline(admin.TabularInline):
    model = CampaignRecipient
    extra = 0
    can_delete = False
    readonly_fields = ("user", "credit", "created_at")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ("title", "audience", "credit_amount", "status", "recipients_count", "sent_at")
    list_filter = ("status", "audience")
    actions = ["send_now"]
    inlines = [CampaignRecipientInline]
    fields = (
        "title", "body", "audience", "idle_days", "top_count", "group", "area",
        "credit_amount", "currency", "audience_preview", "status", "sent_at", "recipients_count",
    )
    readonly_fields = ("audience_preview", "status", "sent_at", "recipients_count")

    @admin.display(description="حجم الجمهور الآن")
    def audience_preview(self, obj):
        if obj is None or obj.pk is None:
            return "احفظ أوّلًا لترى العدد."
        from growth.services.campaigns import CampaignService

        return format_html("<b>{}</b> مستخدمًا", CampaignService.preview_count(obj))

    def save_model(self, request, obj, form, change):
        if not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    @admin.action(description="أرسل الآن (رصيد + إشعار)")
    def send_now(self, request, queryset):
        from growth.services.campaigns import CampaignService

        total = 0
        for campaign in queryset:
            total += CampaignService.send(campaign)
        self.message_user(request, f"أُرسل إلى {total} مستخدمًا.", messages.SUCCESS)


@admin.register(IncentiveProgram)
class IncentiveProgramAdmin(admin.ModelAdmin):
    list_display = ("name", "period", "target_trips", "reward_label", "group", "area", "is_active")
    list_editable = ("is_active",)
    list_filter = ("is_active", "period")


@admin.register(IncentiveAward)
class IncentiveAwardAdmin(admin.ModelAdmin):
    list_display = ("created_at", "driver", "program", "period_start", "trips_completed", "status", "delivered_at")
    list_filter = ("status", "program")
    search_fields = ("driver__user__phone", "driver__user__name")
    actions = ["mark_delivered"]
    readonly_fields = ("program", "driver", "period_start", "trips_completed", "created_at")

    @admin.action(description="علّمها «سُلّمت»")
    def mark_delivered(self, request, queryset):
        updated = queryset.filter(status=IncentiveAward.Status.PENDING).update(
            status=IncentiveAward.Status.DELIVERED, delivered_at=timezone.now(),
        )
        self.message_user(request, f"سُلّمت {updated} مكافأة.", messages.SUCCESS)
