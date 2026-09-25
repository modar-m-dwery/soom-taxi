from django.db import models
from django.utils import timezone
from django.contrib.gis.db import models as gis_models

from rides.models import RideRequest
from users.models import DriverProfile
from vehicles.models import Vehicle


class OfferStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    ACCEPTED = "accepted", "Accepted"
    REJECTED = "rejected", "Rejected"
    EXPIRED = "expired", "Expired"
    CANCELLED = "cancelled", "Cancelled"
    WITHDRAWN = "withdrawn", "Withdrawn"


class ScheduledSharedTripStatus(models.TextChoices):
    OPEN = "open", "Open"
    FULL = "full", "Full"
    BOARDING = "boarding", "Boarding"
    IN_PROGRESS = "in_progress", "In Progress"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"


class ScheduledSharedTripCategory(models.TextChoices):
    """يجب أن تطابق قيميًا rides.models.TripCategory."""
    CITY = "city", "City"
    INTERCITY = "intercity", "Intercity"
    SERVICE_LINE = "service_line", "Service Line"
    RECREATIONAL = "recreational", "Recreational"


class SharedJoinStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    ACCEPTED = "accepted", "Accepted"
    REJECTED = "rejected", "Rejected"
    EXPIRED = "expired", "Expired"
    WITHDRAWN = "withdrawn", "Withdrawn"
    CANCELLED = "cancelled", "Cancelled"


class ScheduledSharedTrip(models.Model):

    driver = models.ForeignKey(
        DriverProfile,
        on_delete=models.PROTECT,
        related_name="scheduled_shared_trips",
    )

    vehicle = models.ForeignKey(
        Vehicle,
        on_delete=models.PROTECT,
        related_name="scheduled_shared_trips",
    )

    pickup = gis_models.PointField(
        geography=True,
        srid=4326,
    )

    destination = gis_models.PointField(
        geography=True,
        srid=4326,
    )

    scheduled_at = models.DateTimeField(
        db_index=True,
    )

    capacity = models.PositiveSmallIntegerField()

    status = models.CharField(
        max_length=20,
        choices=ScheduledSharedTripStatus.choices,
        default=ScheduledSharedTripStatus.OPEN,
        db_index=True,
    )

    # نوع الرحلة: مدينة عادية / سفريات بين مدن / خط سرفيس ثابت / رحلة ترفيهية
    trip_category = models.CharField(
        max_length=20,
        choices=ScheduledSharedTripCategory.choices,
        default=ScheduledSharedTripCategory.CITY,
        db_index=True,
    )

    # عنوان ووصف (تُستخدم أساسًا للرحلات الترفيهية والمنشورة)
    title = models.CharField(
        max_length=150,
        null=True,
        blank=True,
    )

    description = models.TextField(
        null=True,
        blank=True,
    )

    # أسماء المدن (سفريات / سرفيس)
    origin_city = models.CharField(
        max_length=100,
        null=True,
        blank=True,
    )

    destination_city = models.CharField(
        max_length=100,
        null=True,
        blank=True,
    )

    # السعر لكل مقعد (للحجز المباشر بدون عملية مطابقة/عرض)
    price_per_seat = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )

    # المزايا/الخدمات المضمنة (مثال: ["مكيف", "واي فاي", "استراحة"])
    features = models.JSONField(
        default=list,
        blank=True,
    )

    # مسار معروف ومحدد مسبقًا (خاصة بالرحلات الترفيهية/خطوط السرفيس)
    route_geometry = models.JSONField(
        null=True,
        blank=True,
    )

    # هذا مجرد مصدر إنشاء الرحلة (لو أُنشئت من عرض مقبول)، وليس مالك الرحلة.
    # يبقى فارغًا (None) للرحلات "المنشورة" مباشرة (سفريات/سرفيس/ترفيهية).
    source_offer = models.OneToOneField(
        "matching.RideOffer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="scheduled_shared_trip",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["scheduled_at"]

        indexes = [
            models.Index(
                fields=["status", "scheduled_at"]
            ),
            models.Index(
                fields=["driver", "status"]
            ),
            models.Index(
                fields=["trip_category", "status", "scheduled_at"]
            ),
            models.Index(
                fields=["origin_city", "destination_city"]
            ),
        ]

    @property
    def total_reserved_passengers(self):
        return (
            self.members
            .filter(is_active=True)
            .aggregate(
                total=models.Sum(
                    "ride__passenger_count"
                )
            )["total"]
            or 0
        )

    @property
    def remaining_capacity(self):
        return max(
            self.capacity
            - self.total_reserved_passengers,
            0,
        )

    def refresh_status(self):
        if self.status in {
            ScheduledSharedTripStatus.CANCELLED,
            ScheduledSharedTripStatus.COMPLETED,
            ScheduledSharedTripStatus.IN_PROGRESS,
        }:
            return

        if self.remaining_capacity <= 0:
            self.status = ScheduledSharedTripStatus.FULL
        else:
            self.status = ScheduledSharedTripStatus.OPEN

        self.save(
            update_fields=[
                "status",
                "updated_at",
            ]
        )

    def __str__(self):
        return (
            f"ScheduledSharedTrip("
            f"id={self.id}, "
            f"category={self.trip_category}, "
            f"driver={self.driver_id}, "
            f"scheduled_at={self.scheduled_at}, "
            f"status={self.status}"
            f")"
        )


class ScheduledSharedTripMember(models.Model):

    trip = models.ForeignKey(
        ScheduledSharedTrip,
        on_delete=models.CASCADE,
        related_name="members",
    )

    ride = models.OneToOneField(
        RideRequest,
        on_delete=models.PROTECT,
        related_name="scheduled_shared_trip_membership",
    )

    is_host = models.BooleanField(
        default=False,
    )

    is_active = models.BooleanField(
        default=True,
        db_index=True,
    )

    joined_at = models.DateTimeField(
        auto_now_add=True,
    )

    cancelled_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["trip", "ride"],
                name="unique_scheduled_shared_trip_ride",
            ),
        ]

        indexes = [
            models.Index(
                fields=["trip", "is_active"]
            ),
        ]

    def __str__(self):
        return (
            f"ScheduledSharedTripMember("
            f"trip={self.trip_id}, "
            f"ride={self.ride_id}, "
            f"active={self.is_active}"
            f")"
        )


class SharedJoinRequest(models.Model):
    host_ride = models.ForeignKey(
        "rides.RideRequest",
        on_delete=models.CASCADE,
        related_name="shared_join_candidates",
    )
    host_offer = models.ForeignKey(
        "matching.RideOffer",
        on_delete=models.CASCADE,
        related_name="shared_join_requests",
    )
    candidate_ride = models.ForeignKey(
        "rides.RideRequest",
        on_delete=models.CASCADE,
        related_name="shared_join_requests",
    )

    compatibility_score = models.DecimalField(max_digits=5, decimal_places=1)
    scoring_strategy = models.CharField(max_length=30)

    status = models.CharField(
        max_length=20,
        choices=SharedJoinStatus.choices,
        default=SharedJoinStatus.PENDING,
        db_index=True,
    )

    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            # يمنع تكرار نفس زوج (عرض، راكب مرشح)
            # لكنه لا يمنع الراكب من الظهور في عروض مختلفة
            models.UniqueConstraint(
                fields=["host_offer", "candidate_ride"],
                name="unique_host_offer_candidate_ride",
            ),
        ]
        indexes = [
            models.Index(fields=["host_offer", "status"]),
            models.Index(fields=["candidate_ride", "status"]),
        ]


class SharedGroupStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    CANCELLED = "cancelled", "Cancelled"
    COMPLETED = "completed", "Completed"


class SharedRideGroup(models.Model):
    """
    المصدر الوحيد للحقيقة بخصوص سعة الرحلة المشتركة وقت الحجز.
    لا علاقة له بـ DriverProfile.current_occupancy (خاص بمرحلة الرحلة
    الفعلية لاحقًا: DRIVER_ARRIVING/IN_PROGRESS، ومش مسؤولية هذا الموديل).
    """

    host_offer = models.OneToOneField(
        "matching.RideOffer",
        on_delete=models.CASCADE,
        related_name="shared_group",
    )

    driver = models.ForeignKey(
        "users.DriverProfile",
        on_delete=models.PROTECT,
        related_name="shared_ride_groups",
    )
    vehicle = models.ForeignKey(
        "vehicles.Vehicle",
        on_delete=models.PROTECT,
        related_name="shared_ride_groups",
    )

    status = models.CharField(
        max_length=20,
        choices=SharedGroupStatus.choices,
        default=SharedGroupStatus.ACTIVE,
        db_index=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def vehicle_seats(self):
        return self.vehicle.seats

    @property
    def total_passengers(self):
        return (
            self.members
            .aggregate(total=models.Sum("ride__passenger_count"))
            ["total"]
            or 0
        )

    @property
    def remaining_capacity(self):
        return max(self.vehicle_seats - self.total_passengers, 0)

    def __str__(self):
        return f"SharedRideGroup(id={self.id}, offer={self.host_offer_id}, status={self.status})"


class SharedRideGroupMember(models.Model):
    group = models.ForeignKey(
        SharedRideGroup,
        on_delete=models.CASCADE,
        related_name="members",
    )

    # OneToOne يضمن أن الرحلة لا يمكن أن تكون عضوًا في أكثر من مجموعة
    ride = models.OneToOneField(
        "rides.RideRequest",
        on_delete=models.CASCADE,
        related_name="shared_group_membership",
    )

    is_host = models.BooleanField(default=False)

    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["group"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["group"],
                condition=models.Q(is_host=True),
                name="unique_shared_group_host",
            ),
        ]

    def __str__(self):
        return f"SharedRideGroupMember(group={self.group_id}, ride={self.ride_id}, host={self.is_host})"


class RideOffer(models.Model):

    ride = models.ForeignKey(
        RideRequest,
        on_delete=models.CASCADE,
        related_name="offers",
    )

    driver = models.ForeignKey(
        DriverProfile,
        on_delete=models.PROTECT,
        related_name="ride_offers",
    )

    # السعر الذي قدمه السائق
    gross_fare = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )

    # ETA الذي قدمه السائق
    eta_minutes = models.PositiveIntegerField()

    status = models.CharField(
        max_length=20,
        choices=OfferStatus.choices,
        default=OfferStatus.PENDING,
        db_index=True,
    )

    expires_at = models.DateTimeField(
        db_index=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    accepted_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    class Meta:
        ordering = [
            "gross_fare",
            "eta_minutes",
            "created_at",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=["ride", "driver"],
                name="unique_ride_driver_offer",
            ),
        ]

        indexes = [
            models.Index(
                fields=["ride", "status"],
            ),
            models.Index(
                fields=["driver", "status"],
            ),
            models.Index(
                fields=["expires_at", "status"],
            ),
        ]

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at

    def __str__(self):
        return (
            f"RideOffer("
            f"ride={self.ride_id}, "
            f"driver={self.driver_id}, "
            f"status={self.status}, "
            f"fare={self.gross_fare}"
            f")"
        )


class InvitationStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    ACCEPTED = "accepted", "Accepted"
    REJECTED = "rejected", "Rejected"
    EXPIRED = "expired", "Expired"
    CANCELLED = "cancelled", "Cancelled"


class RideInvitation(models.Model):
    """
    دعوة مباشرة من الزبون إلى سائق بعينه اختاره من خريطة السيارات الحيّة.

    ملاحظة مهمة: المهلة هنا هي *صبر الزبون*، لا حجز على السائق. السائق يبقى
    ظاهرًا للجميع وقادرًا على قبول عمل آخر خلالها؛ فإن فعل، تُلغى هذه الدعوة
    فورًا ويُخطَر الزبون في ثانيتها بدل انتظار انقضاء المهلة كاملة.
    """

    ride = models.ForeignKey(
        RideRequest,
        on_delete=models.CASCADE,
        related_name="invitations",
    )

    driver = models.ForeignKey(
        DriverProfile,
        on_delete=models.PROTECT,
        related_name="ride_invitations",
    )

    vehicle = models.ForeignKey(
        Vehicle,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ride_invitations",
    )

    status = models.CharField(
        max_length=20,
        choices=InvitationStatus.choices,
        default=InvitationStatus.PENDING,
        db_index=True,
    )

    # المهلة التي اختارها الزبون من قائمة ServiceArea.invitation_ttl_options
    ttl_seconds = models.PositiveSmallIntegerField(default=20)

    sent_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    # لقطة لحظة الإرسال - لا تُعاد قراءتها من Presence لاحقًا
    approximate_distance_m = models.PositiveIntegerField(null=True, blank=True)
    eta_minutes = models.PositiveIntegerField(null=True, blank=True)
    available_seats = models.PositiveSmallIntegerField(null=True, blank=True)

    # السعر المعروض. counter_fare محجوز لخطة "الزبون يقترح" (لاحقًا)
    quoted_fare = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    counter_fare = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    pricing_policy = models.CharField(max_length=30, blank=True)

    reject_reason = models.CharField(max_length=255, blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-sent_at"]

        constraints = [
            # الضمان الصلب ضد ازدواج الحجز عبر مسار الدعوات - على مستوى
            # قاعدة البيانات لا على مستوى منطق قابل للالتفاف، تمامًا كما
            # يحمي unique_ride_driver_offer مسار العروض.
            models.UniqueConstraint(
                fields=["ride"],
                condition=models.Q(status="accepted"),
                name="unique_accepted_invitation_per_ride",
            ),
            models.UniqueConstraint(
                fields=["ride", "driver"],
                condition=models.Q(status="pending"),
                name="unique_pending_invitation_per_ride_driver",
            ),
        ]

        indexes = [
            models.Index(fields=["driver", "status"]),
            models.Index(fields=["ride", "status"]),
            models.Index(fields=["expires_at", "status"]),
        ]

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at

    def __str__(self):
        return (
            f"RideInvitation("
            f"ride={self.ride_id}, driver={self.driver_id}, status={self.status})"
        )