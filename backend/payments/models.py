"""
نماذج الدفع.

القرار المعماري الحاكم لهذا الملف:

    البوابة لا تملك عمودًا في الجدول.

أي بوابة دفع جديدة — عندما تُفتح البلد أمام مزوّد عالمي، أو يظهر مزوّد
محلّي — تُضاف بملفّ واحد في `payments/gateways/` وسطر واحد في الإعدادات،
بلا ترحيل قاعدة بيانات وبلا لمس هذه النماذج. ما يجعل ذلك ممكنًا ثلاثة
حقول: `gateway_code` نصّ حرّ، و`gateway_reference` للمعرّف الخارجي،
و`gateway_payload` من نوع JSON يستوعب أي شكل بيانات يرسله المزوّد.

القرار الثاني: المال يُقيَّد قيدًا مزدوجًا لا يُعدَّل.

`LedgerEntry` سجلّ غير قابل للتعديل ولا الحذف. تصحيح الخطأ يكون بقيد
معاكس لا بتعديل القيد الأصلي — وهذه ليست شكليّة محاسبية: بدونها لا
تستطيع أن تُثبت لسائق كم استحقّ ولا لمراجع كم حصّلت المنصّة.
"""
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from users.models import DriverProfile


# =====================================================================
# الثوابت
# =====================================================================

MONEY_MAX_DIGITS = 14
MONEY_DECIMALS = 2

ZERO = Decimal("0.00")


class PaymentStatus(models.TextChoices):
    """
    حالات الدفعة.

    لا تُقرأ كتسلسل خطّي: النقدي يقفز من PENDING إلى PAID مباشرة، والبوابة
    الإلكترونية قد تمرّ بـAUTHORIZED. جدول الانتقالات المسموحة معرَّف
    صراحةً في `PaymentService` لا هنا — النموذج يحمل الحالة، والخدمة تحمل
    القانون.
    """

    PENDING = "pending", "بانتظار التحصيل"
    PROCESSING = "processing", "قيد المعالجة لدى المزوّد"
    AUTHORIZED = "authorized", "محجوز ولم يُحصَّل"
    PAID = "paid", "محصَّل"
    PARTIALLY_REFUNDED = "partially_refunded", "مُعاد جزئيًا"
    REFUNDED = "refunded", "مُعاد بالكامل"
    FAILED = "failed", "فشل نهائي"
    CANCELLED = "cancelled", "ملغى"


#: الحالات التي لا تخرج منها الدفعة أبدًا. أي محاولة انتقال منها تُرفض.
TERMINAL_STATUSES = frozenset(
    {
        PaymentStatus.REFUNDED,
        PaymentStatus.FAILED,
        PaymentStatus.CANCELLED,
    }
)

#: الحالات التي تعني أن المال وصل فعلًا (كليًا أو جزئيًا).
SETTLED_STATUSES = frozenset(
    {
        PaymentStatus.PAID,
        PaymentStatus.PARTIALLY_REFUNDED,
    }
)


class LedgerAccount(models.TextChoices):
    """
    أطراف القيد.

    الفصل بين `DRIVER` و`DRIVER_CASH` هو أدقّ قرار في هذا الملفّ، وقد
    كلّف اكتشافُ الحاجة إليه محاكاةً كاملة للدفتر:

        DRIVER      : ما بين السائق والمنصّة حصرًا. موجب = له، سالب = عليه.
        DRIVER_CASH : النقد الذي قبضه بيده من الزبون. خارج التسوية تمامًا.

    لو خُلطا لكان رصيد السائق في رحلة نقدية بأجرة ٢٥٠٠٠ وعمولة ٢٥٠٠
    يظهر ٢٢٥٠٠ (كأن المنصّة تدين له!) بدل ‎-٢٥٠٠ (وهو المدين لها).
    وكانت `recompute_driver_balance` — شبكة الأمان نفسها — ستُفسد الرصيد
    الصحيح كلّما استُدعيت.
    """

    CUSTOMER = "customer", "الزبون"
    DRIVER = "driver", "السائق — تسوية مع المنصّة"
    DRIVER_CASH = "driver_cash", "السائق — نقد بيده"
    PLATFORM = "platform", "المنصّة"
    GATEWAY = "gateway", "بوابة الدفع"


class LedgerDirection(models.TextChoices):
    DEBIT = "debit", "مدين"
    CREDIT = "credit", "دائن"


class LedgerEntryType(models.TextChoices):
    TRIP_FARE = "trip_fare", "أجرة رحلة"
    PLATFORM_COMMISSION = "platform_commission", "عمولة المنصّة"
    DRIVER_EARNING = "driver_earning", "استحقاق السائق"
    REFUND = "refund", "إعادة مبلغ"
    SETTLEMENT = "settlement", "تسوية"
    ADJUSTMENT = "adjustment", "تسوية يدوية"
    PROMOTION = "promotion", "خصم ترويجي تتحمّله المنصّة"
    COMPENSATION = "compensation", "تعويض مشوار فاضي تتحمّله المنصّة"


class RefundStatus(models.TextChoices):
    PENDING = "pending", "قيد التنفيذ"
    COMPLETED = "completed", "منفَّذ"
    FAILED = "failed", "فشل"


class AttemptAction(models.TextChoices):
    CHARGE = "charge", "تحصيل"
    CAPTURE = "capture", "تثبيت الحجز"
    REFUND = "refund", "إعادة"
    WEBHOOK = "webhook", "إشعار وارد"
    CANCEL = "cancel", "إلغاء"


def _money_field(**kwargs):
    kwargs.setdefault("max_digits", MONEY_MAX_DIGITS)
    kwargs.setdefault("decimal_places", MONEY_DECIMALS)
    return models.DecimalField(**kwargs)


# =====================================================================
# الدفعة
# =====================================================================

class Payment(models.Model):
    """
    دفعة واحدة تقابل رحلة واحدة.

    `OneToOne` على الرحلة عمدًا: رحلة واحدة = التزام مالي واحد. تعدُّد
    المحاولات يُسجَّل في `PaymentAttempt`، وتعدُّد الإعادات في `Refund` —
    لا بتكرار صفوف الدفعة، وإلّا لم يعد لسؤال "كم على هذه الرحلة؟" جواب
    واحد.
    """

    trip = models.OneToOneField(
        "trips.Trip",
        on_delete=models.PROTECT,
        related_name="payment",
    )

    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="payments",
    )

    driver = models.ForeignKey(
        DriverProfile,
        on_delete=models.PROTECT,
        related_name="payments",
    )

    # -----------------------------------------------------------------
    # المبالغ — لقطة مجمَّدة لحظة إنشاء الدفعة
    #
    # لا تُعاد قراءتها من الرحلة لاحقًا: تعديل التسعيرة بعد شهر يجب ألّا
    # يغيّر ما دفعه زبون فعلًا.
    # -----------------------------------------------------------------

    amount = _money_field(
        validators=[MinValueValidator(Decimal("0"))],
        help_text="إجمالي ما على الزبون. يقابل customer_total في الطلب.",
    )

    platform_fee = _money_field(
        default=ZERO,
        validators=[MinValueValidator(Decimal("0"))],
        help_text="عمولة المنصّة من هذا المبلغ.",
    )

    driver_net = _money_field(
        default=ZERO,
        validators=[MinValueValidator(Decimal("0"))],
        help_text="صافي استحقاق السائق = الأجرة المتّفق عليها - platform_fee.",
    )

    # الخصم الترويجيّ: ما تتحمّله المنصّة عن الزبون (أوّل مشوار، رصيد إحالة).
    # `amount` = ما يدفعه الزبون فعلًا = الأجرة - الخصم. صافي السائق لا يتأثّر:
    # الفرق دَينٌ على المنصّة له، يُكتب قيدًا (PROMOTION) ويظهر في رصيده.
    discount_amount = _money_field(
        default=ZERO,
        validators=[MinValueValidator(Decimal("0"))],
    )
    discount_reason = models.CharField(max_length=40, blank=True)

    amount_refunded = _money_field(
        default=ZERO,
        validators=[MinValueValidator(Decimal("0"))],
    )

    currency = models.CharField(max_length=3, default="SYP")

    # -----------------------------------------------------------------
    # البوابة — نصّ حرّ لا مفتاح أجنبي
    #
    # هذا بالضبط ما يجعل إضافة بوابة جديدة بلا ترحيل: البوابة تُعرَّف في
    # الكود والإعدادات، لا في جدول.
    # -----------------------------------------------------------------

    gateway_code = models.CharField(
        max_length=40,
        db_index=True,
        help_text="رمز البوابة كما هو معرَّف في payments/gateways/.",
    )

    gateway_reference = models.CharField(
        max_length=255,
        blank=True,
        db_index=True,
        help_text="معرّف العملية لدى المزوّد. فارغ للنقدي.",
    )

    gateway_payload = models.JSONField(
        default=dict,
        blank=True,
        help_text="أي بيانات إضافية يحتاجها المزوّد. لا مخطّط ثابت عمدًا.",
    )

    status = models.CharField(
        max_length=24,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING,
        db_index=True,
    )

    # -----------------------------------------------------------------
    # الحماية من التكرار
    #
    # مفتاح فريد لكل نيّة دفع. إعادة إرسال الطلب نفسه (شبكة متقطّعة،
    # ضغطة مزدوجة) تُعيد الدفعة القائمة بدل أن تُنشئ ثانية.
    # -----------------------------------------------------------------

    idempotency_key = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
    )

    failure_reason = models.CharField(max_length=300, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    paid_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["driver", "status"]),
            models.Index(fields=["customer", "-created_at"]),
            models.Index(fields=["gateway_code", "status"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gte=Decimal("0")),
                name="payment_amount_non_negative",
            ),
            models.CheckConstraint(
                condition=models.Q(amount_refunded__lte=models.F("amount")),
                name="payment_refund_not_exceeding_amount",
            ),
        ]

    def __str__(self):
        return (
            f"Payment(id={self.pk}, trip={self.trip_id}, "
            f"{self.amount} {self.currency}, {self.status})"
        )

    # -----------------------------------------------------------------

    @property
    def is_settled(self):
        return self.status in SETTLED_STATUSES

    @property
    def is_terminal(self):
        return self.status in TERMINAL_STATUSES

    @property
    def refundable_amount(self):
        """ما تبقّى قابلًا للإعادة. صفر إن لم تكن الدفعة محصَّلة."""
        if not self.is_settled:
            return ZERO
        return self.amount - self.amount_refunded

    def clean(self):
        # الاتّساق الحسابي يُفحص هنا أيضًا لا في الخدمة وحدها: أي مسار آخر
        # يصل إلى النموذج (أمر إداري، لوحة الإدارة) يجب أن يخضع للقاعدة.
        if self.platform_fee > self.amount:
            raise ValidationError(
                {"platform_fee": "العمولة لا يمكن أن تتجاوز إجمالي المبلغ."}
            )
        if self.amount_refunded > self.amount:
            raise ValidationError(
                {"amount_refunded": "المُعاد لا يمكن أن يتجاوز المبلغ الأصلي."}
            )


# =====================================================================
# محاولات الاتصال بالبوابة
# =====================================================================

class PaymentAttempt(models.Model):
    """
    سجلّ لكل نداء خرج إلى بوابة أو دخل منها. للتشخيص وفضّ النزاع.

    يُكتب حتى عند الفشل — بل خصوصًا عنده. أكثر أسئلة الدفع إلحاحًا
    ("لماذا فشلت عملية هذا الزبون قبل ساعتين؟") لا جواب لها بدون هذا الجدول.
    """

    payment = models.ForeignKey(
        Payment,
        on_delete=models.CASCADE,
        related_name="payment_attempts",
    )

    gateway_code = models.CharField(max_length=40)
    action = models.CharField(max_length=20, choices=AttemptAction.choices)

    ok = models.BooleanField(default=False)
    permanent_failure = models.BooleanField(
        default=False,
        help_text="فشل لا تُجدي إعادة المحاولة معه.",
    )

    error = models.CharField(max_length=300, blank=True)

    request_payload = models.JSONField(default=dict, blank=True)
    response_payload = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["payment", "-created_at"])]

    def __str__(self):
        state = "ok" if self.ok else "fail"
        return f"PaymentAttempt({self.action}, {self.gateway_code}, {state})"


# =====================================================================
# الإعادة
# =====================================================================

class Refund(models.Model):
    payment = models.ForeignKey(
        Payment,
        on_delete=models.PROTECT,
        related_name="refunds",
    )

    amount = _money_field(validators=[MinValueValidator(Decimal("0.01"))])
    currency = models.CharField(max_length=3, default="SYP")

    reason = models.CharField(max_length=300)

    status = models.CharField(
        max_length=20,
        choices=RefundStatus.choices,
        default=RefundStatus.PENDING,
        db_index=True,
    )

    gateway_reference = models.CharField(max_length=255, blank=True)

    idempotency_key = models.CharField(max_length=64, unique=True)

    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="requested_refunds",
    )

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Refund({self.amount} {self.currency}, {self.status})"


# =====================================================================
# دفتر القيود — غير قابل للتعديل
# =====================================================================

class LedgerEntryQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise NotImplementedError(
            "قيود الدفتر غير قابلة للتعديل. صحّح بقيد معاكس."
        )

    def delete(self):
        raise NotImplementedError(
            "قيود الدفتر غير قابلة للحذف. صحّح بقيد معاكس."
        )


class LedgerEntry(models.Model):
    """
    قيد واحد في دفتر مزدوج. كل حركة مال تُنتج قيدين على الأقل يتوازنان.

    مثال رحلة نقدية بأجرة 25000 وعمولة 2500:

        مدين  : الزبون    25000   (دفع نقدًا)
        دائن  : السائق    25000   (قبض نقدًا)
        مدين  : السائق     2500   (صار مدينًا للمنصّة بالعمولة)
        دائن  : المنصّة     2500

    مجموع المدين = مجموع الدائن دائمًا. هذه الخاصية يفحصها
    `LedgerService.assert_balanced` بعد كل عملية.
    """

    # فارغ لحركةٍ بلا دفعة: تعويض سائقٍ عن رحلةٍ أُلغيت لا دفعة لها أصلًا.
    payment = models.ForeignKey(
        Payment,
        on_delete=models.PROTECT,
        related_name="ledger_entries",
        null=True,
        blank=True,
    )

    account = models.CharField(
        max_length=20,
        choices=LedgerAccount.choices,
        db_index=True,
    )

    account_ref = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
        help_text="معرّف صاحب الحساب: رقم المستخدم أو السائق. فارغ للمنصّة.",
    )

    direction = models.CharField(max_length=10, choices=LedgerDirection.choices)

    amount = _money_field(validators=[MinValueValidator(Decimal("0.01"))])
    currency = models.CharField(max_length=3, default="SYP")

    entry_type = models.CharField(
        max_length=30,
        choices=LedgerEntryType.choices,
        db_index=True,
    )

    #: يجمع القيدين المتقابلين في حركة واحدة. مفيد للتدقيق والعكس.
    transaction_ref = models.CharField(max_length=64, db_index=True)

    memo = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    objects = LedgerEntryQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["account", "account_ref", "-created_at"]),
            models.Index(fields=["transaction_ref"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=Decimal("0")),
                name="ledger_amount_positive",
            ),
        ]

    def __str__(self):
        return (
            f"LedgerEntry({self.direction} {self.amount} {self.currency} "
            f"→ {self.account}:{self.account_ref})"
        )

    def save(self, *args, **kwargs):
        # الإدراج مسموح مرة واحدة فقط. أي حفظ لاحق محاولة تعديل.
        if self.pk is not None:
            raise NotImplementedError(
                "قيود الدفتر غير قابلة للتعديل. صحّح بقيد معاكس."
            )
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise NotImplementedError(
            "قيود الدفتر غير قابلة للحذف. صحّح بقيد معاكس."
        )


# =====================================================================
# رصيد السائق
# =====================================================================

class DriverBalance(models.Model):
    """
    الرصيد الجاري لكل سائق بكل عملة.

    ليس مصدر الحقيقة — الدفتر هو. هذا الجدول تجميعة محسوبة تُحدَّث داخل
    المعاملة نفسها، لأن جمع مليون قيد عند كل فتح للتطبيق غير عملي.
    `SettlementService.recompute` يعيد بناءه من الدفتر عند الشكّ.

    الإشارة: موجب = المنصّة تدين للسائق (رحلات إلكترونية).
             سالب = السائق يدين للمنصّة (عمولات رحلات نقدية).
    """

    driver = models.ForeignKey(
        DriverProfile,
        on_delete=models.PROTECT,
        related_name="balances",
    )

    currency = models.CharField(max_length=3, default="SYP")

    net_balance = _money_field(
        default=ZERO,
        help_text="موجب: للسائق عند المنصّة. سالب: على السائق للمنصّة.",
    )

    lifetime_earned = _money_field(default=ZERO)
    lifetime_commission = _money_field(default=ZERO)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["driver", "currency"],
                name="unique_driver_balance_per_currency",
            )
        ]
        indexes = [models.Index(fields=["driver", "currency"])]

    def __str__(self):
        return f"DriverBalance(driver={self.driver_id}, {self.net_balance} {self.currency})"

    @property
    def owes_platform(self):
        return self.net_balance < ZERO

    @property
    def amount_owed_to_platform(self):
        return -self.net_balance if self.net_balance < ZERO else ZERO


class CustomerCredit(models.Model):
    """
    رصيدٌ ترويجيّ لزبون — مكافأة إحالة اليوم، وغدًا أيّ حملة.

    يُستهلك تلقائيًّا عند فتح الدفعة التالية (كلّه أو جزءٌ منه)، ويُربط
    بالدفعة التي استهلكته فلا يُصرف مرّتين. لا يُحوَّل نقدًا ولا يُسترَدّ.
    """

    class Reason(models.TextChoices):
        REFERRER = "referral_referrer", "دعا زبونًا أتمّ رحلته الأولى"
        REFEREE = "referral_referee", "أتمّ رحلته الأولى بدعوة"
        MANUAL = "manual", "منح يدويّ"
        CAMPAIGN = "campaign", "عرض من الإدارة"

    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="credits",
    )
    amount = _money_field(validators=[MinValueValidator(Decimal("0.01"))])
    currency = models.CharField(max_length=3, default="SYP")
    reason = models.CharField(max_length=32, choices=Reason.choices)
    source_payment = models.ForeignKey(
        Payment, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="granted_credits",
        help_text="الدفعة التي استحقّت المكافأة (رحلة المدعوّ الأولى).",
    )
    consumed_by = models.ForeignKey(
        Payment, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="consumed_credits",
    )
    consumed_amount = _money_field(default=ZERO)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    @property
    def remaining(self):
        return self.amount - self.consumed_amount

    def __str__(self):
        return f"credit {self.amount} {self.currency} → {self.customer_id} ({self.reason})"
