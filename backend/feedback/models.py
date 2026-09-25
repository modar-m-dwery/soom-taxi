from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from trips.models import Trip
from users.models import DriverProfile


class RatingDirection(models.TextChoices):
    CUSTOMER_TO_DRIVER = "c2d", "الزبون يقيّم السائق"
    DRIVER_TO_CUSTOMER = "d2c", "السائق يقيّم الزبون"


class TagPolarity(models.TextChoices):
    POSITIVE = "positive", "إيجابي"
    NEGATIVE = "negative", "سلبي"


class RatingTag(models.Model):
    """
    الوسوم التي تظهر للمستخدم بعد التقييم ("قيادة آمنة"، "تأخّر كثيرًا").

    لماذا جدول لا قائمة ثابتة في الكود؟ لأن هذه نصوص تُعرض للمستخدم وتتغيّر
    بالتجربة والسوق، وتغييرها يجب ألّا يحتاج نشر إصدار جديد. ولأن ما يهمّ
    السائق في الزبون غير ما يهمّ الزبون في السائق، فالوسم مرتبط باتجاهه.
    """

    code = models.SlugField(max_length=40)
    label = models.CharField(max_length=80)

    direction = models.CharField(
        max_length=3,
        choices=RatingDirection.choices,
        db_index=True,
    )
    polarity = models.CharField(
        max_length=10,
        choices=TagPolarity.choices,
        default=TagPolarity.POSITIVE,
    )

    # الوسوم السلبية تظهر عند التقييم المنخفض فقط، والإيجابية عند المرتفع.
    # سؤال "ما الذي أعجبك؟" بعد نجمة واحدة سخيف ويُفقد الثقة.
    min_score = models.PositiveSmallIntegerField(default=1)
    max_score = models.PositiveSmallIntegerField(default=5)

    service_area = models.ForeignKey(
        "locations.ServiceArea",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="rating_tags",
        help_text="اتركه فارغًا ليظهر الوسم في كل المدن.",
    )

    active = models.BooleanField(default=True, db_index=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["direction", "order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["code", "direction"],
                name="unique_tag_code_per_direction",
            ),
        ]

    def __str__(self):
        return f"{self.label} ({self.direction})"

    def applies_to(self, score):
        return self.min_score <= score <= self.max_score


class Rating(models.Model):
    """
    تقييم واحد في اتجاه واحد عن رحلة واحدة.

    قاعدة الحجب المتبادل (§الثقة): لا يرى أيّ طرف تقييم الآخر حتى يقيّم
    هو أيضًا، أو تنتهي المهلة. بلا هذا يتحوّل التقييم إلى ردّ فعل: مَن
    يقيّم ثانيًا يعاقب مَن قيّمه بأقل من خمسة. النتيجة أرقام متضخّمة
    بلا معنى.

    القيد الأحادي (trip, direction) قاعدةُ بيانات لا منطق تطبيق: تقييم
    مكرر عند ضغط مزدوج أو إعادة إرسال يرتطم بالقاعدة لا بفحص قابل للنسيان.
    """

    trip = models.ForeignKey(
        Trip,
        on_delete=models.PROTECT,
        related_name="ratings",
    )

    direction = models.CharField(
        max_length=3,
        choices=RatingDirection.choices,
        db_index=True,
    )

    # الطرفان محفوظان صراحةً لا عبر trip فقط: التجميع يقرأ ملايين الصفوف
    # لاحقًا، وربط كل صف برحلته ثم بسائقها استعلام لا داعي له.
    driver = models.ForeignKey(
        DriverProfile,
        on_delete=models.PROTECT,
        related_name="ratings_received_or_given",
    )
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="trip_ratings",
    )

    rater = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="ratings_written",
    )

    score = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )

    tags = models.JSONField(default=list, blank=True)
    comment = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["trip", "direction"],
                name="unique_rating_per_trip_direction",
            ),
        ]
        indexes = [
            models.Index(fields=["driver", "direction", "-created_at"]),
            models.Index(fields=["customer", "direction", "-created_at"]),
        ]

    def __str__(self):
        return f"Rating(trip={self.trip_id}, {self.direction}, {self.score}★)"


class RatingSummary(models.Model):
    """
    المتوسط والعدد لطرف واحد.

    يُعاد حسابه من الصفوف لا يُزاد تدريجيًا - نفس المبدأ الذي اعتمدناه في
    عدّاد الركّاب: متوسط متدرّج يحمل خطأه إلى الأبد عند أول صفّ محذوف أو
    مضاف يدويًا، أما إعادة الحساب فتصحّح نفسها.
    """

    driver = models.OneToOneField(
        DriverProfile,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="rating_summary",
    )
    customer = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="rating_summary",
    )

    average = models.DecimalField(
        max_digits=3, decimal_places=2, null=True, blank=True
    )
    count = models.PositiveIntegerField(default=0)

    one_star = models.PositiveIntegerField(default=0)
    two_star = models.PositiveIntegerField(default=0)
    three_star = models.PositiveIntegerField(default=0)
    four_star = models.PositiveIntegerField(default=0)
    five_star = models.PositiveIntegerField(default=0)

    recalculated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(driver__isnull=False, customer__isnull=True)
                    | models.Q(driver__isnull=True, customer__isnull=False)
                ),
                name="rating_summary_exactly_one_subject",
            ),
        ]

    def __str__(self):
        subject = self.driver_id or self.customer_id
        return f"RatingSummary({subject}: {self.average} من {self.count})"


# =====================================================================
# الشكاوى
# =====================================================================

class ComplaintCategory(models.TextChoices):
    FARE = "fare", "الأجرة"
    ROUTE = "route", "المسار"
    BEHAVIOR = "behavior", "سلوك"
    SAFETY = "safety", "السلامة"
    VEHICLE = "vehicle", "حالة المركبة"
    NO_SHOW = "no_show", "عدم الحضور"
    LOST_ITEM = "lost_item", "أغراض منسيّة"
    OTHER = "other", "أخرى"


class ComplaintSeverity(models.TextChoices):
    LOW = "low", "منخفضة"
    NORMAL = "normal", "عادية"
    HIGH = "high", "مرتفعة"
    CRITICAL = "critical", "حرجة"


class ComplaintStatus(models.TextChoices):
    OPEN = "open", "مفتوحة"
    IN_REVIEW = "in_review", "قيد المراجعة"
    RESOLVED = "resolved", "محلولة"
    REJECTED = "rejected", "مرفوضة"


class Complaint(models.Model):
    """
    شكوى عن رحلة.

    الحقل الأهم هنا evidence: لقطة مجمّدة من الوقائع لحظة فتح الشكوى.

    السبب مباشر: cleanup_old_trip_locations تحذف نقاط المسار بعد ثلاثين
    يومًا (وهذا صحيح - §17 في الوثيقة). فشكوى تُفتح في اليوم التاسع
    والعشرين وتُراجَع في الحادي والثلاثين كانت ستصبح غير قابلة للحسم
    لأن دليلها حُذف بينهما. التجميد يفصل عمر الدليل عن سياسة الاحتفاظ.
    """

    trip = models.ForeignKey(
        Trip,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="complaints",
    )

    complainant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="complaints_filed",
    )

    against_driver = models.ForeignKey(
        DriverProfile,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="complaints_received",
    )
    against_customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="complaints_received",
    )

    category = models.CharField(
        max_length=20,
        choices=ComplaintCategory.choices,
        db_index=True,
    )
    severity = models.CharField(
        max_length=10,
        choices=ComplaintSeverity.choices,
        default=ComplaintSeverity.NORMAL,
        db_index=True,
    )
    status = models.CharField(
        max_length=12,
        choices=ComplaintStatus.choices,
        default=ComplaintStatus.OPEN,
        db_index=True,
    )

    description = models.TextField()

    evidence = models.JSONField(default=dict, blank=True)

    resolution_note = models.TextField(blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="complaints_resolved",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)

    escalated_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "severity", "-created_at"]),
            models.Index(fields=["against_driver", "-created_at"]),
        ]

    def __str__(self):
        return f"Complaint(#{self.id}, {self.category}, {self.status})"

    @property
    def is_open(self):
        return self.status in (ComplaintStatus.OPEN, ComplaintStatus.IN_REVIEW)
