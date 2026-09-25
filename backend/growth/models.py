"""
أدوات المشغّل للنموّ: عمولةٌ لكلّ سائق أو مجموعة، عروضٌ تُرسل فورًا مع
إشعار، وحوافز إنجاز بالوقود.
"""

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


def _money_field(**kwargs):
    return models.DecimalField(max_digits=12, decimal_places=2, **kwargs)


# =====================================================================
# مجموعات السائقين
# =====================================================================

class DriverGroup(models.Model):
    """«المؤسّسون»، «سائقو الريف»، «سيارات الفان»… مجموعةٌ تُعطى عمولةً أو حافزًا."""

    name = models.CharField(max_length=80, unique=True)
    description = models.CharField(max_length=200, blank=True)
    drivers = models.ManyToManyField(
        "users.DriverProfile", blank=True, related_name="growth_groups",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "مجموعة سائقين"
        verbose_name_plural = "مجموعات السائقين"

    def __str__(self):
        return self.name


# =====================================================================
# العمولة
# =====================================================================

class CommissionRule(models.Model):
    """
    نسبة المنصّة من الأجرة. الأدقّ يغلب: سائقٌ بعينه ← مجموعته ← مدينته ←
    القاعدة العامّة. وفي كلّ الأحوال:
      - المؤسّس (`commission_exempt`) صفرٌ دائمًا — وعدٌ موقَّع.
      - سقف المدينة القانونيّ (`commission_cap_pct`) لا يُتجاوز.
    """

    class Scope(models.TextChoices):
        DRIVER = "driver", "سائق بعينه"
        GROUP = "group", "مجموعة سائقين"
        AREA = "area", "مدينة"
        DEFAULT = "default", "عامّة"

    SPECIFICITY = {Scope.DRIVER: 4, Scope.GROUP: 3, Scope.AREA: 2, Scope.DEFAULT: 1}

    name = models.CharField(max_length=80)
    scope = models.CharField(max_length=10, choices=Scope.choices)
    driver = models.ForeignKey(
        "users.DriverProfile", null=True, blank=True, on_delete=models.CASCADE,
        related_name="commission_rules",
    )
    group = models.ForeignKey(
        DriverGroup, null=True, blank=True, on_delete=models.CASCADE,
        related_name="commission_rules",
    )
    area = models.ForeignKey(
        "locations.ServiceArea", null=True, blank=True, on_delete=models.CASCADE,
        related_name="commission_rules",
        help_text="اختياريّ مع السائق/المجموعة: يقصر القاعدة على مدينة.",
    )
    rate_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("50"))],
        help_text="نسبة من الأجرة (0–50).",
    )
    fixed_fee = _money_field(
        default=Decimal("0"), validators=[MinValueValidator(Decimal("0"))],
        help_text="مبلغ ثابت يُضاف على كلّ رحلة.",
    )
    min_fee = _money_field(null=True, blank=True)
    max_fee = _money_field(null=True, blank=True)
    valid_from = models.DateTimeField(null=True, blank=True)
    valid_until = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_active", "scope", "name"]
        verbose_name = "قاعدة عمولة"
        verbose_name_plural = "قواعد العمولة"

    def __str__(self):
        return f"{self.name} ({self.rate_pct}% + {self.fixed_fee})"

    def clean(self):
        required = {
            self.Scope.DRIVER: ("driver", self.driver_id),
            self.Scope.GROUP: ("group", self.group_id),
            self.Scope.AREA: ("area", self.area_id),
        }
        if self.scope in required and not required[self.scope][1]:
            raise ValidationError({required[self.scope][0]: "مطلوب لهذا النطاق."})
        if self.min_fee is not None and self.max_fee is not None and self.min_fee > self.max_fee:
            raise ValidationError({"max_fee": "الحدّ الأعلى أصغر من الأدنى."})


# =====================================================================
# العروض الفوريّة
# =====================================================================

class Campaign(models.Model):
    """
    عرضٌ يُطبَّق فور الإرسال: رصيدٌ في حساب كلّ زبون من الجمهور (يُخصم
    تلقائيًّا من رحلته التالية) أو رسالةٌ وحدها — ومعه إشعار دفع.
    """

    class Audience(models.TextChoices):
        ALL_CUSTOMERS = "all_customers", "كلّ الزبائن"
        IDLE_CUSTOMERS = "idle_customers", "الزبائن الخاملون"
        NEW_CUSTOMERS = "new_customers", "زبائن سجّلوا ولم يركبوا"
        TOP_CUSTOMERS = "top_customers", "أنشط الزبائن"
        ALL_DRIVERS = "all_drivers", "كلّ السائقين"
        IDLE_DRIVERS = "idle_drivers", "السائقون الخاملون"
        TOP_DRIVERS = "top_drivers", "أنشط السائقين"
        DRIVER_GROUP = "driver_group", "مجموعة سائقين"

    class Status(models.TextChoices):
        DRAFT = "draft", "مسوّدة"
        SENT = "sent", "أُرسل"

    title = models.CharField(max_length=80, help_text="عنوان الإشعار.")
    body = models.CharField(max_length=240, help_text="نصّ الإشعار.")
    audience = models.CharField(max_length=20, choices=Audience.choices)
    idle_days = models.PositiveSmallIntegerField(
        default=14, help_text="للخاملين: بلا رحلة منذ هذه الأيّام.",
    )
    top_count = models.PositiveSmallIntegerField(
        default=50, help_text="للأنشط: كم مستخدمًا.",
    )
    group = models.ForeignKey(
        DriverGroup, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="campaigns",
    )
    area = models.ForeignKey(
        "locations.ServiceArea", null=True, blank=True, on_delete=models.SET_NULL,
        help_text="فارغ = كلّ المدن.",
    )
    credit_amount = _money_field(
        default=Decimal("0"), validators=[MinValueValidator(Decimal("0"))],
        help_text="للزبائن: رصيد يُخصم من الرحلة التالية. صفر = رسالة فقط.",
    )
    currency = models.CharField(max_length=3, default="SYP")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    sent_at = models.DateTimeField(null=True, blank=True)
    recipients_count = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "عرض/حملة"
        verbose_name_plural = "العروض والحملات"

    def __str__(self):
        return self.title

    @property
    def targets_drivers(self):
        return self.audience in {
            self.Audience.ALL_DRIVERS, self.Audience.IDLE_DRIVERS,
            self.Audience.TOP_DRIVERS, self.Audience.DRIVER_GROUP,
        }

    def clean(self):
        if self.audience == self.Audience.DRIVER_GROUP and not self.group_id:
            raise ValidationError({"group": "اختر المجموعة."})
        if self.targets_drivers and self.credit_amount:
            raise ValidationError({
                "credit_amount": "الرصيد للزبائن وحدهم؛ حافز السائق من «برامج الحوافز».",
            })


class CampaignRecipient(models.Model):
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name="recipients")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    credit = models.ForeignKey(
        "payments.CustomerCredit", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # الإرسال مرّتين لا يمنح الرصيد مرّتين.
        unique_together = [("campaign", "user")]


# =====================================================================
# الحوافز
# =====================================================================

class IncentiveProgram(models.Model):
    """
    «30 مشوارًا هذا الأسبوع = 10 ليترات بنزين». مكافأةٌ مقابل إنجاز لا
    مقابل تسجيل — المكافأة على التسجيل تجلب من يسجّل ويختفي.
    """

    class Period(models.TextChoices):
        DAY = "day", "يوميّ"
        WEEK = "week", "أسبوعيّ"
        MONTH = "month", "شهريّ"

    class RewardKind(models.TextChoices):
        FUEL_LITERS = "fuel_liters", "ليترات وقود"
        OTHER = "other", "مكافأة أخرى (يُسلّمها المشغّل)"

    name = models.CharField(max_length=80)
    description = models.CharField(max_length=200, blank=True)
    period = models.CharField(max_length=10, choices=Period.choices, default=Period.WEEK)
    target_trips = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])
    min_rating = models.DecimalField(
        max_digits=3, decimal_places=2, null=True, blank=True,
        help_text="اختياريّ: لا مكافأة تحت هذا التقييم.",
    )
    reward_kind = models.CharField(max_length=20, choices=RewardKind.choices, default=RewardKind.FUEL_LITERS)
    reward_amount = models.DecimalField(max_digits=8, decimal_places=2)
    reward_label = models.CharField(
        max_length=60, blank=True, help_text="كيف تظهر المكافأة للسائق: «10 ليترات بنزين».",
    )
    group = models.ForeignKey(
        DriverGroup, null=True, blank=True, on_delete=models.SET_NULL,
        help_text="فارغ = كلّ السائقين.",
    )
    area = models.ForeignKey(
        "locations.ServiceArea", null=True, blank=True, on_delete=models.SET_NULL,
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_active", "name"]
        verbose_name = "برنامج حوافز"
        verbose_name_plural = "برامج الحوافز"

    def __str__(self):
        return self.name


class IncentiveAward(models.Model):
    """مكافأةٌ استحقّها سائق — يسلّمها المشغّل ويعلّمها «سُلّمت»."""

    class Status(models.TextChoices):
        PENDING = "pending", "بانتظار التسليم"
        DELIVERED = "delivered", "سُلّمت"

    program = models.ForeignKey(IncentiveProgram, on_delete=models.PROTECT, related_name="awards")
    driver = models.ForeignKey("users.DriverProfile", on_delete=models.CASCADE, related_name="incentive_awards")
    period_start = models.DateField()
    trips_completed = models.PositiveIntegerField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    delivered_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # مكافأةٌ واحدة لكلّ برنامج وسائق وفترة — التقييم المكرَّر لا يضاعفها.
        unique_together = [("program", "driver", "period_start")]
        ordering = ["-created_at"]
        verbose_name = "مكافأة مستحقّة"
        verbose_name_plural = "المكافآت المستحقّة"
