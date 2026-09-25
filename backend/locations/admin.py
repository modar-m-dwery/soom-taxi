from django import forms
from django.contrib import admin
from django.contrib.gis.admin import GISModelAdmin
from django.contrib.gis.db import models as gis_models
from django.contrib.gis.forms import OSMWidget

from locations.models import (
    PriceChangeWorkflow,
    PricingPolicy,
    ServiceArea,
    SurgeMode,
)


# استيراد كسول: locations يجب ألّا يعتمد على rides وقت تحميل التطبيقات.
def _ride_mode_choices():
    from rides.models import RideMode
    return RideMode.choices


TTL_CHOICES = [
    (10, "10 ثوانٍ"),
    (15, "15 ثانية"),
    (20, "20 ثانية"),
    (30, "30 ثانية"),
    (40, "40 ثانية"),
    (60, "دقيقة"),
    (90, "دقيقة ونصف"),
    (120, "دقيقتان"),
]


class ServiceAreaForm(forms.ModelForm):
    """
    الحقول الثلاثة أدناه مخزَّنة كـJSONField (قوائم)، لكن الأدمن يجب أن يراها
    كمربّعات اختيار حقيقية لا كنص JSON خام. MultipleChoiceField يرجّع قائمة،
    وهي تُسنَد إلى JSONField مباشرة بلا تحويل.
    """

    allowed_pricing_policies = forms.MultipleChoiceField(
        choices=PricingPolicy.choices,
        widget=forms.CheckboxSelectMultiple,
        required=True,
        label="خطط التسعير المسموح بها",
        help_text=(
            "اختر ما يوافق قانون البلد فعلًا. يمكن اختيار أكثر من خطة — "
            "مثلًا سعر ثابت + مزايدة سائقين معًا."
        ),
    )

    invitation_allowed_modes = forms.MultipleChoiceField(
        choices=_ride_mode_choices,
        widget=forms.CheckboxSelectMultiple,
        required=True,
        label="أنماط تُفعَّل فيها الخريطة الحيّة والدعوة المباشرة",
        help_text=(
            "تفعيل 'مشاركة' يُظهر السيارات التي فيها ركّاب — لكن فقط لمن "
            "يجتاز مسارُه درجة التوافق أدناه."
        ),
    )

    invitation_ttl_options = forms.TypedMultipleChoiceField(
        choices=TTL_CHOICES,
        coerce=int,
        widget=forms.CheckboxSelectMultiple,
        required=True,
        label="المهل المعروضة على الزبون",
        help_text="الزبون يختار من هذه القائمة كم ينتظر ردّ السائق.",
    )

    class Meta:
        model = ServiceArea
        fields = "__all__"


@admin.register(ServiceArea)
class ServiceAreaAdmin(GISModelAdmin):
    form = ServiceAreaForm

    formfield_overrides = {
        gis_models.PointField: {
            "widget": OSMWidget(attrs={"map_width": 800, "map_height": 500})
        },
        gis_models.PolygonField: {
            "widget": OSMWidget(attrs={"map_width": 800, "map_height": 500})
        },
    }

    list_display = (
        "code",
        "name",
        "country_code",
        "currency_code",
        "default_pricing_policy",
        "surge_mode",
        "policies_summary",
        "invitation_summary",
        "is_active",
    )

    list_filter = (
        "is_active",
        "country_code",
        "default_pricing_policy",
        "surge_mode",
        "price_change_workflow",
    )

    search_fields = ("code", "name", "country_code", "regulator_name")

    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        (
            "الهوية",
            {
                "fields": (
                    "code",
                    "name",
                    "country_code",
                    "currency_code",
                    "is_active",
                )
            },
        ),
        (
            "الحدود الجغرافية",
            {
                "fields": ("boundary", "center", "fallback_radius_km"),
                "description": (
                    "استخدم boundary للحدود الدقيقة، أو center مع نصف قطر "
                    "كبديل مؤقت. أحدهما إلزامي."
                ),
            },
        ),
        (
            "الخريطة الحيّة",
            {
                "fields": (
                    "marketplace_cell_precision",
                    "shared_destination_precision",
                    "shared_min_compatibility_score",
                )
            },
        ),
        (
            "أنصاف أقطار البحث",
            {
                "fields": (
                    "default_matching_radius_km",
                    "marketplace_radius_km",
                    "shared_join_radius_km",
                    "shared_scheduled_pickup_radius_km",
                    "shared_scheduled_dest_radius_km",
                    "shared_scheduled_time_window_minutes",
                ),
                "description": (
                    "نصف قطر الطلب الفوري هو أهمّ رقم في هذه الصفحة: هو "
                    "الذي يحدّد مَن يُطابَق ومَن يظهر على خريطة الزبون. "
                    "اضبطه على جغرافيا مدينتك — خمسة كيلومترات تعني «كلّ "
                    "المدينة» في جبلة و«لا سائق أبدًا» في ريف متباعد. "
                    "وضبطه خطيرٌ في الاتجاهين: صغيرًا جدًّا ينتهي الطلب بلا "
                    "سائق فيظنّ الزبون أنّ المنصّة فارغة، وكبيرًا جدًّا "
                    "يُطابِق سائقًا يحتاج ثلث ساعة ليصل فيلغي الزبون. "
                    "اترك الباقي فارغًا ليعمل بالافتراضات."
                ),
            },
        ),
        (
            "الدعوة المباشرة",
            {
                "fields": (
                    "invitation_allowed_modes",
                    "invitation_ttl_options",
                    "invitation_ttl_default",
                    "invitation_max_parallel",
                )
            },
        ),
        (
            "سياسة الإلغاء",
            {
                "fields": (
                    "cancel_free_window_seconds",
                    "cancel_driver_late_grace_minutes",
                    "cancel_wait_minutes",
                    "late_cancel_strike_limit",
                    "late_cancel_window_days",
                    "late_cancel_penalty_hours",
                    "driver_cancel_daily_limit",
                    "driver_cancel_block_minutes",
                    "wasted_trip_compensation",
                    "wasted_trip_compensation_daily_cap",
                )
            },
        ),
        (
            "نطاق البحث و«الأقرب»",
            {
                "fields": (
                    "search_radius_options_km",
                    "auto_dispatch_ttl_seconds",
                    "auto_dispatch_max_attempts",
                )
            },
        ),
        (
            "المهل التشغيلية",
            {
                "fields": (
                    "offer_ttl_seconds",
                    "ride_search_window_minutes",
                    "presence_stale_seconds",
                    "presence_fresh_seconds",
                    "location_max_age_seconds",
                    "invitation_reject_cooldown_seconds",
                    "arrival_radius_m",
                    "dropoff_radius_m",
                ),
                "classes": ("collapse",),
                "description": (
                    "اترك الحقل فارغًا ليعمل بالافتراضي العامّ. ما تكتبه هنا "
                    "يسري على الإنتاج فورًا بلا إعادة تشغيل — والتطبيق يقرأ "
                    "هذه القيم من /api/v1/config/ فلا حاجة لإصدار جديد منه. "
                    "خفض مهلة الانقطاع يُنقّي الخريطة ويقسو على الشبكات "
                    "الضعيفة؛ ورفعها يُبقي سائقًا مرئيًّا بعد أن اختفى."
                ),
            },
        ),
        (
            "التسعير — الخطط",
            {
                "fields": (
                    "allowed_pricing_policies",
                    "default_pricing_policy",
                )
            },
        ),
        (
            "التسعير — الحدود والسقوف",
            {
                "fields": (
                    "surge_mode",
                    "surge_max_multiplier",
                    "fare_floor_multiplier",
                    "fare_cap_multiplier",
                    "min_fare_absolute",
                    "customer_proposal_min_ratio",
                    "customer_proposal_counter_ratio",
                    "customer_proposal_step",
                    "driver_min_share_pct",
                    "commission_cap_pct",
                    "allow_renegotiation_after_match",
                ),
                "description": (
                    "اترك أي حقل فارغًا إن لم ينص عليه قانون البلد. "
                    "الفراغ يعني 'بلا قيد'، لا 'صفر'."
                ),
            },
        ),
        (
            "الامتثال",
            {
                "fields": (
                    "price_change_workflow",
                    "regulator_name",
                    "legal_reference",
                    "compliance_note",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "التواريخ",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )

    @admin.display(description="الخطط المفعّلة")
    def policies_summary(self, obj):
        labels = dict(PricingPolicy.choices)
        return "، ".join(
            labels.get(p, p).split("(")[0].strip()
            for p in (obj.allowed_pricing_policies or [])
        ) or "—"

    @admin.display(description="الدعوات")
    def invitation_summary(self, obj):
        modes = "/".join(obj.invitation_allowed_modes or []) or "—"
        ttls = "/".join(str(t) for t in (obj.invitation_ttl_options or [])) or "—"
        return f"{modes} · {ttls}ث · متوازية {obj.invitation_max_parallel}"
