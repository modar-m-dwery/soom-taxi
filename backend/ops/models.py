from django.conf import settings
from django.db import models


class ActionKind(models.TextChoices):
    RELEASE_DRIVER = "release_driver", "تحرير سائق عالق"
    FORCE_COMPLETE = "force_complete", "إنهاء رحلة إداريًا"
    FORCE_CANCEL = "force_cancel", "إلغاء رحلة إداريًا"
    VERIFY_DRIVER = "verify_driver", "توثيق سائق"
    REJECT_DRIVER = "reject_driver", "رفض سائق"
    SUSPEND_DRIVER = "suspend_driver", "إيقاف سائق"


class AdminAction(models.Model):
    """
    سجلّ كل تدخّل إداري.

    هذا الجدول ليس ترفًا: الصلاحيات التي تُنشئها المرحلة 12 حقيقية —
    إنهاء رحلة لم تنتهِ، تحرير سائق، إيقاف حساب. صلاحية بهذا الوزن بلا
    أثر مكتوب هي الباب الذي تُساء منه المنصّات من الداخل، ولا يُكتشف إلا
    بعد شكوى لا جواب لها.

    ولذلك كل خدمة في ops تكتب صفًّا هنا **داخل معاملتها نفسها**: إما أن
    يقع الفعل ويُسجَّل، أو لا يقع. لا حالة ثالثة.
    """

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="admin_actions",
    )

    kind = models.CharField(
        max_length=20,
        choices=ActionKind.choices,
        db_index=True,
    )

    # الهدف مخزَّن كنصّ لا كمفتاح أجنبي: الفعل قد يستهدف سائقًا أو رحلة
    # أو طلبًا، وسجلّ التدقيق يجب أن يبقى حتى لو حُذف الهدف يومًا.
    target_type = models.CharField(max_length=30)
    target_id = models.PositiveIntegerField()

    reason = models.TextField()

    # لقطة مختصرة قبل الفعل وبعده. تجيب على السؤال الذي يُطرح دائمًا بعد
    # شهر: "ما الذي غيّره هذا التدخّل بالضبط؟"
    before = models.JSONField(default=dict, blank=True)
    after = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["target_type", "target_id", "-created_at"]),
            models.Index(fields=["actor", "-created_at"]),
        ]

    def __str__(self):
        return f"AdminAction({self.kind} on {self.target_type}#{self.target_id})"


# =================================================================
# سجلّ التدقيق العامّ
# =================================================================


class AuditEntity(models.TextChoices):
    RIDE = "ride", "طلب رحلة"
    OFFER = "offer", "عرض سائق"
    INVITATION = "invitation", "دعوة مباشرة"
    TRIP = "trip", "رحلة"
    PAYMENT = "payment", "دفعة"
    REFUND = "refund", "استرجاع"
    DRIVER = "driver", "ملفّ سائق"
    DOCUMENT = "document", "وثيقة سائق"
    SHARED_JOIN = "shared_join", "طلب انضمام مشترك"
    SHARED_GROUP = "shared_group", "مجموعة رحلة مشتركة"
    SCHEDULED_TRIP = "scheduled_trip", "رحلة مجدولة مشتركة"
    VEHICLE = "vehicle", "مركبة"
    USER = "user", "مستخدم"
    COMPLAINT = "complaint", "شكوى"


class AuditAction(models.TextChoices):
    CREATED = "created", "أُنشئ"
    STATUS_CHANGED = "status_changed", "تغيّرت الحالة"
    UPDATED = "updated", "عُدِّل"
    DELETED = "deleted", "حُذف"
    ADMIN_ACTION = "admin_action", "تدخّل إداري"
    SECURITY = "security", "حدث أمني"


class AuditLog(models.Model):
    """
    أثر واحد لكلّ انتقال حالة في المنصّة — من فعله، متى، ومن أين إلى أين.

    لماذا هذا الجدول موجود
    ----------------------
    `AdminAction` أعلاه يغطّي تدخّل الإدارة وحده. لكن الوثيقة (§11 و§18)
    تشترط أثرًا لكلّ انتقال، لا للتدخّل الإداري فقط. والفرق يظهر في أوّل
    نزاع مالي حقيقي: «مَن أنهى هذه الرحلة، ومتى، وهل كان السائق قريبًا من
    الوجهة؟» سؤالٌ لا جواب له اليوم إن لم يكن المُنهي مشغّلًا.

    كيف يُملأ
    ---------
    آليًا لا يدويًا. `ops/audit_signals.py` يراقب حقل `status` في كلّ نموذج
    يهمّنا ويكتب صفًّا عند كلّ تغيّر — بلا استعلام إضافي، لأنّ الحالة
    السابقة تُلتقط لحظة قراءة الصفّ من القاعدة لا باستعلام ثانٍ.

    وما لا يمرّ بـ`save()` — تحديثات `queryset.update()` الجماعية — يُسجَّل
    صراحةً في مواضعه المعدودة. الاعتماد على الإشارات وحدها كان سيترك
    انتهاء العروض والرحلات بلا أثر، وهو أكثر ما يُسأل عنه.

    الكتابة داخل المعاملة نفسها
    ---------------------------
    عمدًا. لو انهارت المعاملة بعد كتابة الأثر لبقي سجلّ لانتقال لم يقع —
    وسجلّ تدقيق يكذب أسوأ من غيابه.
    """

    entity_type = models.CharField(
        max_length=20,
        choices=AuditEntity.choices,
        db_index=True,
    )

    # مخزَّن كرقم لا كمفتاح أجنبي: الأثر يجب أن يبقى بعد حذف هدفه.
    entity_id = models.PositiveIntegerField(db_index=True)

    action = models.CharField(
        max_length=20,
        choices=AuditAction.choices,
        default=AuditAction.STATUS_CHANGED,
        db_index=True,
    )

    from_state = models.CharField(max_length=40, blank=True, default="")
    to_state = models.CharField(max_length=40, blank=True, default="", db_index=True)

    # الفاعل مرّتان: مفتاح أجنبي للربط، ونصّ ثابت يبقى لو حُذف الحساب.
    actor_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_entries",
    )

    # "user:+9639...", "system", "celery:expire_stale_offers", "anon"
    actor_label = models.CharField(max_length=64, blank=True, default="", db_index=True)

    actor_role = models.CharField(max_length=20, blank=True, default="")

    reason = models.CharField(max_length=255, blank=True, default="")

    # سياق الانتقال: المسافة عند الوصول، مهلة العرض، رمز البوّابة...
    # لا يوضع فيه شيء يخصّ الهوية: راجع AuditService._scrub
    metadata = models.JSONField(default=dict, blank=True)

    # يربط هذا الأثر بسطور السجلّ وبالطلب الذي سبّبه
    request_id = models.CharField(max_length=32, blank=True, default="", db_index=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            # الاستعلام الأوّل دائمًا: «أرِني تاريخ هذا الكيان»
            models.Index(
                fields=["entity_type", "entity_id", "-created_at"],
                name="audit_entity_timeline_idx",
            ),
            # «ماذا فعل هذا المستخدم؟»
            models.Index(fields=["actor_label", "-created_at"], name="audit_actor_idx"),
            # «كلّ ما دخل هذه الحالة اليوم»
            models.Index(fields=["to_state", "-created_at"], name="audit_state_idx"),
        ]

    def __str__(self):
        arrow = f"{self.from_state or '∅'} → {self.to_state or '∅'}"
        return f"Audit({self.entity_type}#{self.entity_id}: {arrow})"


class LegacyRide(models.Model):
    """
    سطرٌ من صفحة «رحلات» في دفتر واتساب — كما هو، بلا تحويل إلى رحلة حقيقية.

    مرحلة التسعين يومًا تسبق التطبيق: الطلبات تُدار على واتساب وتُسجَّل في
    جدول Google بثلاث صفحات (زبائن، سوّاق، رحلات). يوم الإطلاق يُستورَد
    الدفتر إلى الخادم — وهذا هو «المفصل التاسع» في وثيقة البوّابة.

    لماذا نموذجٌ مستقلّ لا RideRequest/Trip: رحلة واتساب لا حمولة لها
    (لا إحداثيات، لا عرض، لا دفعة، لا قيود محاسبية)، وصناعة صفوف مزيّفة في
    جداول التشغيل تلوّث المؤشّرات ودفتر الأستاذ. هنا تُحفظ كما كُتبت، مربوطةً
    بالمستخدمين بالهاتف، فتُقرأ في السجلّ والمؤشّرات كـ«تاريخ ما قبل التطبيق».

    الأعمدة تطابق صفحة «رحلات» في الوثيقة حرفًا بحرف — لا تُعِد تسميتها هنا
    ولا هناك.
    """

    class Status(models.TextChoices):
        DONE = "done", "تمّ"
        CANCELLED = "cancelled", "ألغيت"
        UNSERVED = "unserved", "لم تُخدَم"

    datetime = models.DateTimeField(help_text="التاريخ والساعة كما في الدفتر.")
    customer_phone = models.CharField(max_length=20, db_index=True)
    driver_phone = models.CharField(max_length=20, blank=True, db_index=True)
    origin = models.CharField("from", max_length=200, blank=True)
    destination = models.CharField("to", max_length=200, blank=True)
    area = models.CharField(max_length=8, blank=True, help_text="JAB / LAT / OUT")
    offers = models.PositiveSmallIntegerField(default=0, help_text="كم سائقًا عرض")
    price = models.PositiveIntegerField(null=True, blank=True, help_text="عدد صحيح بالليرة")
    minutes_to_offer = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="كم دقيقة حتّى وصل أوّل عرض"
    )
    status = models.CharField(max_length=12, choices=Status.choices)
    fail_reason = models.CharField(max_length=200, blank=True)
    rating = models.PositiveSmallIntegerField(null=True, blank=True)

    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="legacy_rides_as_customer",
    )
    driver = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="legacy_rides_as_driver",
    )
    imported_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-datetime"]
        constraints = [
            # السطر نفسه لا يُستورَد مرّتين: التاريخ + الزبون يكفيان مفتاحًا.
            models.UniqueConstraint(
                fields=["datetime", "customer_phone"], name="legacy_ride_unique_row"
            ),
        ]

    def __str__(self):
        return f"{self.datetime:%Y-%m-%d %H:%M} {self.customer_phone} → {self.destination}"
