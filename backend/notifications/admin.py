from django.contrib import admin

from notifications.models import (
    ChannelDelivery,
    Notification,
    UserChannelPreference,
)


# DeviceToken لا يُسجَّل هنا: هو نموذج users، ولوحته هناك.


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("id", "event_type", "user", "app", "priority",
                    "status", "attempts", "created_at", "sent_at")
    # الفلترة بالحالة أولًا: ما يهمّ التشغيل هو FAILED وEXPIRED لا المُرسَل.
    list_filter = ("status", "priority", "app", "event_type", "created_at")
    search_fields = ("user__phone", "title", "body", "dedupe_key")
    readonly_fields = [f.name for f in Notification._meta.fields]

    def has_add_permission(self, request):
        return False


@admin.register(UserChannelPreference)
class UserChannelPreferenceAdmin(admin.ModelAdmin):
    list_display = (
        "user", "channel", "is_enabled", "priority", "has_address", "verified_at",
    )
    list_filter = ("channel", "is_enabled")
    search_fields = ("user__phone", "user__name", "address")
    list_select_related = ("user",)
    ordering = ("user", "priority")

    @admin.display(description="مربوط", boolean=True)
    def has_address(self, obj):
        return bool(obj.address)


@admin.register(ChannelDelivery)
class ChannelDeliveryAdmin(admin.ModelAdmin):
    """
    السؤال الذي يجيب عنه هذا الجدول: **أيّ قناة توصل فعلًا؟**

    بلا هذه الأرقام يبقى قرار الاشتراك بقناة مدفوعة تخمينًا. رتّب بـ
    outcome لترى نسبة النجاح لكلّ قناة.
    """

    list_display = ("created_at", "channel", "outcome", "notification", "error")
    list_filter = ("channel", "outcome", "created_at")
    search_fields = ("notification__event_type", "error")
    list_select_related = ("notification",)
    date_hierarchy = "created_at"
    ordering = ("-created_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        # سجلّ تسليم لا يُعدَّل: تعديله يعني تزوير الرقم الذي يُبنى عليه قرار.
        return False
