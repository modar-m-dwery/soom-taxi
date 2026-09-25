from django.conf import settings
from django.db import models
from django.utils import timezone


# =====================================================================
# ملاحظة على رموز الأجهزة
#
# لا يوجد DeviceToken هنا عمدًا. الجدول موجود أصلًا في users.DeviceToken،
# وإنشاء ثانٍ كان يعني أن تسجيل الدخول يكتب في أحدهما والإرسال يقرأ من
# الآخر — فيُعلَّم كل إشعار "لا أجهزة مسجَّلة" إلى الأبد بلا خطأ يدلّ عليه.
#
# ما ينقص جدولكم (سبب الإبطال، وتمييز تطبيق السائق من الزبون) لم أضفه:
# الأول أُسجّله في الإشعار نفسه، والثاني لا معنى له قبل أن يرسله التطبيق
# عند التسجيل. إضافته حين يُرسله لا قبله.
# =====================================================================


class AppKind(models.TextChoices):
    DRIVER = "driver", "تطبيق السائق"
    CUSTOMER = "customer", "تطبيق الزبون"


class NotificationPriority(models.TextChoices):
    # عاجل: يوقظ الجهاز ويتجاوز وضع التوفير. للدعوات ولحظات الرحلة فقط.
    URGENT = "urgent", "عاجل"
    NORMAL = "normal", "عادي"
    LOW = "low", "منخفض"


class NotificationStatus(models.TextChoices):
    PENDING = "pending", "بالانتظار"
    SENT = "sent", "أُرسل"
    FAILED = "failed", "فشل"
    # لم يُرسَل ولا خطأ فيه: لا أجهزة مسجَّلة، أو المزوّد غير مهيّأ بعد
    SKIPPED = "skipped", "متخطّى"
    # انقضى قبل أن يُرسَل - يُسقَط عمدًا لا يُؤجَّل
    EXPIRED = "expired", "منتهٍ"


class Notification(models.Model):
    """
    صندوق صادر. الإشعار يُكتب في القاعدة أولًا ثم يُرسَل، لا العكس.

    السبب أن الإرسال عبر الشبكة يفشل ويُعاد، وبلا صفّ مكتوب لا نعرف ما
    الذي أُرسل ولا ما الذي ضاع. ولأن الكتابة تجري داخل معاملة الحدث نفسه،
    فلا يمكن أن يصل إشعار عن دعوة تراجعت معاملتها.

    الحقل الأهمّ هنا expires_at.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )

    event_type = models.CharField(max_length=60, db_index=True)

    title = models.CharField(max_length=120)
    body = models.CharField(max_length=300, blank=True)

    # ما يفتحه التطبيق عند الضغط: ride_id، invitation_id، شاشة الوجهة…
    data = models.JSONField(default=dict, blank=True)

    priority = models.CharField(
        max_length=10,
        choices=NotificationPriority.choices,
        default=NotificationPriority.NORMAL,
    )

    # أيّ تطبيق يعني هذا الإشعار. لا يُستعمل للفلترة حاليًا (رمز الجهاز
    # لا يحمل هذه المعلومة بعد) لكنه يصل في الحمولة فيتجاهله التطبيق
    # الآخر بدل أن يعرض بطاقة لا تخصّه.
    app = models.CharField(
        max_length=10,
        choices=AppKind.choices,
        default=AppKind.CUSTOMER,
    )

    status = models.CharField(
        max_length=10,
        choices=NotificationStatus.choices,
        default=NotificationStatus.PENDING,
        db_index=True,
    )

    # -----------------------------------------------------------------
    # الانقضاء — قلب هذه المرحلة
    #
    # دعوة مهلتها عشرون ثانية، وإشعارها يصل بعد ثلاث دقائق لأن الجهاز كان
    # خارج التغطية. السائق يضغط فيجد "انتهت الدعوة". هذا أسوأ من ألّا يصله
    # شيء: إشعار يَعِد بعمل لم يعد موجودًا يُفقد الثقة بكل الإشعارات بعده.
    #
    # فالمنقضي يُسقَط عمدًا ويُسجَّل انقضاؤه، ولا يُؤجَّل ولا يُعاد.
    # -----------------------------------------------------------------
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)

    # منع التكرار: إعادة إرسال أو نقر مزدوج أو مهمة أُعيدت
    dedupe_key = models.CharField(max_length=120, blank=True, db_index=True)

    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.CharField(max_length=300, blank=True)

    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["user", "-created_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["dedupe_key"],
                condition=~models.Q(dedupe_key=""),
                name="unique_notification_dedupe_key",
            ),
        ]

    def __str__(self):
        return f"Notification({self.event_type} -> {self.user_id}, {self.status})"

    @property
    def is_expired(self):
        return self.expires_at is not None and timezone.now() > self.expires_at


# =====================================================================
# القنوات — تفضيلات المستخدم وسجلّ التسليم
# =====================================================================


class ChannelCode(models.TextChoices):
    """
    رموز القنوات المدمجة.

    ليست حاجزًا أمام قناة جديدة: `UserChannelPreference.channel` نصّ بلا
    قيد على هذه القائمة عمدًا، فقناة يضيفها مبرمج لاحقًا تعمل بلا ترحيل.
    هذه القائمة للأدمن ولوضوح القراءة فقط.
    """
    PUSH = "push", "إشعار الدفع"
    TELEGRAM = "telegram", "تليغرام"
    SMS = "sms", "رسالة نصّية"


class UserChannelPreference(models.Model):
    """
    كيف يريد هذا المستخدم أن يصله الإشعار، وبأيّ ترتيب.

    غياب الصفّ ليس نقصًا بل هو الافتراض: مستخدم لم يضبط شيئًا يتلقّى عبر
    القنوات المفعّلة تلقائيًّا (الدفع، ثمّ الرسالة النصّية للحرج وحده) —
    أي بالضبط ما كان يحدث قبل هذه الطبقة. لا صفّ يُنشأ إلّا حين يقرّر
    المستخدم شيئًا مخالفًا، أو حين يربط عنوانًا (chat_id مثلًا).

    `priority` أصغر = أوّلًا. تُرتَّب بها سلسلة المحاولة.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="channel_preferences",
    )

    channel = models.CharField(
        max_length=20,
        choices=ChannelCode.choices,
        db_index=True,
    )

    is_enabled = models.BooleanField(default=True)

    priority = models.PositiveSmallIntegerField(
        default=100,
        help_text="الأصغر يُجرَّب أوّلًا.",
    )

    address = models.CharField(
        max_length=120,
        blank=True,
        default="",
        help_text=(
            "عنوان المستخدم على هذه القناة — chat_id في تليغرام مثلًا. "
            "يبقى فارغًا للقنوات التي لا تحتاج عنوانًا."
        ),
    )

    verified_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["priority", "channel"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "channel"],
                name="unique_user_channel_preference",
            ),
        ]
        indexes = [
            models.Index(fields=["channel", "address"]),
        ]

    def __str__(self):
        return f"{self.user_id}:{self.channel}"


class ChannelDelivery(models.Model):
    """
    محاولة تسليم واحدة على قناة واحدة.

    لماذا جدول مستقلّ بدل حقول على الإشعار: لأنّ الإشعار الواحد قد يُجرَّب
    على ثلاث قنوات، ولأنّ السؤال التشغيلي الحقيقي ليس «هل وصل؟» بل «أيّ
    قناة توصل فعلًا؟». بلا هذا الجدول يبقى ذلك تخمينًا، ويبقى قرار
    الاشتراك بقناة مدفوعة بلا رقم يسنده.

    والصفوف تُقلَّم دوريًّا مع الإشعارات القديمة: هذا سجلّ تشغيل لا أرشيف.
    """

    notification = models.ForeignKey(
        Notification,
        on_delete=models.CASCADE,
        related_name="deliveries",
    )

    channel = models.CharField(max_length=20, db_index=True)

    outcome = models.CharField(max_length=20, db_index=True)

    error = models.CharField(max_length=300, blank=True, default="")

    detail = models.CharField(max_length=120, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["channel", "outcome", "created_at"]),
        ]

    def __str__(self):
        return f"{self.channel}:{self.outcome}"
