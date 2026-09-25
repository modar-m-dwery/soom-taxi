from django.conf import settings
from django.contrib.gis.db import models as gis_models
from django.db import models

from matching.models import RideOffer
from rides.models import RideRequest
from users.models import DriverProfile
from vehicles.models import Vehicle


class TripStatus(models.TextChoices):
    CREATED = "created", "Created"
    DRIVER_ARRIVING = "driver_arriving", "Driver Arriving"
    DRIVER_ARRIVED = "driver_arrived", "Driver Arrived"
    IN_PROGRESS = "in_progress", "In Progress"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"
    DISPUTED = "disputed", "Disputed"


class CompletionSource(models.TextChoices):
    DRIVER_APP = "driver_app", "تطبيق السائق"
    ADMIN = "admin", "الإدارة"
    AUTO = "auto", "إنهاء تلقائي"


class Trip(models.Model):
    """
    الرحلة الفعلية بعد تثبيت السائق — تقابل RideRequest واحدًا بالضبط.

    لماذا كيان منفصل عن RideRequest؟ لأن الطلب شيء والرحلة شيء آخر: الطلب
    قد يُلغى أو ينتهي أو يُرفض عشر مرات قبل أن تبدأ رحلة واحدة. وفصلهما هو
    ما يسمح بسجل زمني نظيف للرحلة ومسار GPS مرتبط بها وحدها.

    حالة RideRequest تُحدَّث بالتوازي داخل نفس المعاملة، فلا يمكن أن يفترقا.
    """

    ride = models.OneToOneField(
        RideRequest,
        on_delete=models.PROTECT,
        related_name="trip",
    )

    driver = models.ForeignKey(
        DriverProfile,
        on_delete=models.PROTECT,
        related_name="trips",
    )

    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="trips",
    )

    vehicle = models.ForeignKey(
        Vehicle,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="trips",
    )

    # مصدر التثبيت: عرض مقبول (سواء جاء من مزايدة أو من دعوة مباشرة)
    offer = models.ForeignKey(
        RideOffer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="trips",
    )

    status = models.CharField(
        max_length=20,
        choices=TripStatus.choices,
        default=TripStatus.CREATED,
        db_index=True,
    )

    # -----------------------------------------------------------------
    # السجل الزمني — كل خطوة بختمها الخاص، لا حقل واحد يُعاد كتابته
    # -----------------------------------------------------------------

    created_at = models.DateTimeField(auto_now_add=True)
    arriving_at = models.DateTimeField(null=True, blank=True)
    arrived_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    # -----------------------------------------------------------------
    # القياس
    # -----------------------------------------------------------------

    distance_m = models.PositiveIntegerField(null=True, blank=True)
    duration_s = models.PositiveIntegerField(null=True, blank=True)
    gps_points_count = models.PositiveIntegerField(default=0)

    final_fare = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default="SYP")

    # -----------------------------------------------------------------
    # التحقق الجغرافي (§20.3 في الوثيقة: مطابقة موقع السائق قبل Arrived)
    # -----------------------------------------------------------------

    pickup_verified = models.BooleanField(default=False)
    dropoff_verified = models.BooleanField(default=False)

    # الحالات الشاذة تذهب للمراجعة بدل أن تُعتبر مكتملة تلقائيًا (§17.1)
    needs_review = models.BooleanField(default=False, db_index=True)
    review_reason = models.CharField(max_length=255, blank=True)

    cancelled_by = models.CharField(max_length=20, blank=True)
    cancel_reason = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["driver", "status"]),
            models.Index(fields=["customer", "-created_at"]),
            models.Index(fields=["status", "created_at"]),
        ]

    def __str__(self):
        return f"Trip(id={self.id}, ride={self.ride_id}, status={self.status})"

    @property
    def is_active(self):
        return self.status in {
            TripStatus.CREATED,
            TripStatus.DRIVER_ARRIVING,
            TripStatus.DRIVER_ARRIVED,
            TripStatus.IN_PROGRESS,
        }


class TripLocation(models.Model):
    """
    نقطة على مسار الرحلة. تُسجَّل أثناء IN_PROGRESS فقط — لا قبلها ولا بعدها.

    تسجيل كل نبضة GPS من كل سائق طوال اليوم يحوّل هذا الجدول إلى سجل تتبّع
    ضخم بلا فائدة تشغيلية. ما يهم قانونيًا وتشغيليًا هو مسار الرحلة نفسه:
    للنزاعات، وحساب المسافة، وإعادة تشغيل الرحلة عند الشكوى.
    """

    trip = models.ForeignKey(
        Trip,
        on_delete=models.CASCADE,
        related_name="locations",
    )

    location = gis_models.PointField(geography=True, srid=4326)

    speed = models.FloatField(null=True, blank=True)
    heading = models.FloatField(null=True, blank=True)
    accuracy = models.FloatField(null=True, blank=True)
    source = models.CharField(max_length=20, blank=True)

    timestamp = models.DateTimeField(db_index=True)

    class Meta:
        ordering = ["timestamp"]
        indexes = [
            models.Index(fields=["trip", "timestamp"]),
        ]

    def __str__(self):
        return f"TripLocation(trip={self.trip_id}, at={self.timestamp})"


class TripCompletionRecord(models.Model):
    """
    §17.3 في الوثيقة: سجل مستقل لكل رحلة ناجحة.

    لماذا سجل منفصل والبيانات موجودة في Trip؟ لأن سياسة الاحتفاظ تختلف:
    نقاط GPS تُحذف بعد مدة، لكن هذا السجل يبقى. هو الإثبات الدائم بأن
    الرحلة وقعت فعلًا، بأرقامها ولحظاتها، حتى بعد تنظيف المسار.
    """

    trip = models.OneToOneField(
        Trip,
        on_delete=models.PROTECT,
        related_name="completion_record",
    )

    completed_at = models.DateTimeField()
    start_time = models.DateTimeField(null=True, blank=True)
    end_time = models.DateTimeField(null=True, blank=True)

    pickup_point = gis_models.PointField(geography=True, srid=4326)
    dropoff_point = gis_models.PointField(geography=True, srid=4326, null=True, blank=True)

    distance_m = models.PositiveIntegerField(default=0)
    duration_s = models.PositiveIntegerField(default=0)

    final_fare = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default="SYP")

    gps_start_verified = models.BooleanField(default=False)
    gps_arrival_verified = models.BooleanField(default=False)
    gps_end_verified = models.BooleanField(default=False)
    gps_points_count = models.PositiveIntegerField(default=0)

    completion_source = models.CharField(
        max_length=20,
        choices=CompletionSource.choices,
        default=CompletionSource.DRIVER_APP,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-completed_at"]

    def __str__(self):
        return f"TripCompletionRecord(trip={self.trip_id}, fare={self.final_fare})"


class CancellationKind(models.TextChoices):
    FREE = "free", "مجّانيّ"
    DRIVER_LATE = "driver_late", "السائق تأخّر"
    LATE = "late", "متأخّر"
    AFTER_WAIT = "after_wait", "بعد انتظار السائق"
    DRIVER = "driver", "ألغاه السائق"


class CancellationRecord(models.Model):
    """
    كلّ إلغاءٍ بعد تثبيت سائق، مصنَّفًا. منه تُعدّ المخالفات وتُقرّر
    العقوبات، ومنه تقرأ الإدارة من يلغي ولماذا.
    """

    ride = models.ForeignKey(
        RideRequest, on_delete=models.CASCADE, related_name="cancellations",
    )
    trip = models.ForeignKey(
        "Trip", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="cancellations",
    )
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="ride_cancellations",
    )
    driver = models.ForeignKey(
        DriverProfile, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="ride_cancellations",
    )
    actor = models.CharField(max_length=10)
    kind = models.CharField(max_length=20, choices=CancellationKind.choices)
    # 0 للمجّانيّ، 1 للمتأخّر، 2 بعد الانتظار، 1 لإلغاء السائق.
    strikes = models.PositiveSmallIntegerField(default=0)
    reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["customer", "created_at"]),
            models.Index(fields=["driver", "created_at"]),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"Cancellation({self.ride_id}, {self.actor}, {self.kind})"
