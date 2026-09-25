"""
نزاهة المنصّة: إشاراتٌ تُسجَّل على الحسابات، ونقاطُ خطرٍ تتلاشى مع الوقت،
وقضايا يراجعها إنسان.

المبدأ: الآلة **تلاحظ وتقيّد**، والإنسان **يحكم**. لا حظر تلقائيّ أبدًا —
أقصى ما يفعله النظام وحده هو تقييدٌ قابل للتراجع (بلا خصومات، بلا «اختر
سيارتك»، بلا «الأقرب» والحوافز للسائق)، مع قضيّة مفتوحة وملاحظة تشرح السبب.
"""

from django.conf import settings
from django.db import models
from django.utils import timezone

from integrity import registry


class RiskLevel(models.TextChoices):
    CLEAR = "clear", "سليم"
    WATCH = "watch", "تحت المراقبة"
    REVIEW = "review", "بحاجة مراجعة"
    RESTRICTED = "restricted", "مقيّد"


LEVEL_ORDER = {
    RiskLevel.CLEAR: 0,
    RiskLevel.WATCH: 1,
    RiskLevel.REVIEW: 2,
    RiskLevel.RESTRICTED: 3,
}


class SignalStatus(models.TextChoices):
    ACTIVE = "active", "فعّالة"
    DISMISSED = "dismissed", "مُسقطة (إنذار كاذب)"


class RiskProfile(models.Model):
    """حالة حسابٍ واحد. تُعاد حسابها من الإشارات، فلا تنحرف عن الحقيقة."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="risk_profile",
    )
    score = models.PositiveSmallIntegerField(default=0)
    level = models.CharField(
        max_length=12, choices=RiskLevel.choices, default=RiskLevel.CLEAR, db_index=True,
    )
    # قرار الإدارة يغلب الحساب: «سليم» يُسكت إنذارًا معروفًا، و«مقيّد» يبقي
    # التقييد ولو تلاشت النقاط. `manual_until` فارغ = حتّى إشعار آخر.
    manual_level = models.CharField(
        max_length=12, choices=RiskLevel.choices, blank=True, default="",
    )
    manual_until = models.DateTimeField(null=True, blank=True)
    signals_count = models.PositiveIntegerField(default=0)
    last_signal_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-score"]
        verbose_name = "ملفّ خطر"
        verbose_name_plural = "ملفّات الخطر"

    def __str__(self):
        return f"{self.user} — {self.get_level_display()} ({self.score})"

    def manual_active(self, now=None):
        if not self.manual_level:
            return False
        now = now or timezone.now()
        return self.manual_until is None or self.manual_until > now

    def effective_level(self, now=None):
        return self.manual_level if self.manual_active(now) else self.level

    @property
    def is_restricted(self):
        return self.effective_level() == RiskLevel.RESTRICTED


class RiskSignal(models.Model):
    """ملاحظةٌ آليّة واحدة: «رأينا هذا، وهذا دليله»."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="risk_signals",
    )
    kind = models.CharField(max_length=40, db_index=True)
    weight = models.PositiveSmallIntegerField()
    status = models.CharField(
        max_length=12, choices=SignalStatus.choices, default=SignalStatus.ACTIVE,
        db_index=True,
    )
    evidence = models.JSONField(default=dict, blank=True)
    ride = models.ForeignKey(
        "rides.RideRequest", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+",
    )
    trip = models.ForeignKey(
        "trips.Trip", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )
    # الطرف الآخر في نمطٍ ثنائيّ (تواطؤ، شغل خارج التطبيق).
    counterpart = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+",
    )
    # يمنع تكرار الإشارة نفسها عند إعادة تشغيل الكاشف: كاشفٌ يعمل كلّ نصف
    # ساعة على نافذة أسبوع يرى النمط نفسه ثلاثمئة مرّة — ويجب أن يُحسب مرّة.
    dedupe_key = models.CharField(max_length=160, unique=True, null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "status", "created_at"])]
        verbose_name = "إشارة"
        verbose_name_plural = "الإشارات"

    def __str__(self):
        return f"{self.kind_label} ← {self.user}"

    @property
    def kind_label(self):
        kind = registry.KINDS.get(self.kind)
        return kind.label if kind else self.kind


class RiskNote(models.Model):
    """ملاحظة على الحساب: آليّة (author فارغ) أو من موظّف."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="risk_notes",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+",
    )
    text = models.TextField()
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "ملاحظة"
        verbose_name_plural = "الملاحظات"

    def __str__(self):
        return self.text[:60]


class CaseStatus(models.TextChoices):
    OPEN = "open", "مفتوحة"
    CONFIRMED = "confirmed", "مؤكَّدة (غش)"
    DISMISSED = "dismissed", "مرفوضة (إنذار كاذب)"


class RiskCase(models.Model):
    """حسابٌ بلغ حدّ المراجعة. قضيّة مفتوحة واحدة لكلّ حساب في أيّ وقت."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="risk_cases",
    )
    status = models.CharField(
        max_length=12, choices=CaseStatus.choices, default=CaseStatus.OPEN, db_index=True,
    )
    reason = models.CharField(max_length=255)
    score_at_open = models.PositiveSmallIntegerField(default=0)
    opened_at = models.DateTimeField(default=timezone.now)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+",
    )
    resolution_note = models.TextField(blank=True)

    class Meta:
        ordering = ["-opened_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user"], condition=models.Q(status="open"),
                name="integrity_one_open_case_per_user",
            ),
        ]
        verbose_name = "قضيّة مراجعة"
        verbose_name_plural = "قضايا المراجعة"

    def __str__(self):
        return f"قضيّة #{self.pk} — {self.user}"
