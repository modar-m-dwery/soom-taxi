from django.conf import settings
from django.contrib.gis.db import models as gis_models
from django.db import models
from django.utils import timezone



class RideMode(models.TextChoices):
    """فئة/درجة الخدمة داخل المدينة. لا علاقة لها بكون الرحلة فردية أو مجدولة."""
    FAST = "fast", "Fast"
    EXPRESS = "express", "Express"
    STANDARD = "standard", "Standard"
    SAVING = "saving", "Saving"
    SHARED = "shared", "Shared"


class TripCategory(models.TextChoices):
    """
    نوع الرحلة من ناحية الغرض/النطاق. مستقل تمامًا عن:
    - mode (فئة الخدمة)
    - scheduled_at (هل هي مجدولة أم فورية)
    """
    CITY = "city", "City Ride"
    INTERCITY = "intercity", "Intercity Trip"
    SERVICE_LINE = "service_line", "Service Line"
    RECREATIONAL = "recreational", "Recreational Trip"


class RideStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    SEARCHING = "searching", "Searching"
    OFFERS_RECEIVED = "offers_received", "Offers Received"
    DRIVER_SELECTED = "driver_selected", "Driver Selected"
    DRIVER_ARRIVING = "driver_arriving", "Driver Arriving"
    DRIVER_ARRIVED = "driver_arrived", "Driver Arrived"
    IN_PROGRESS = "in_progress", "In Progress"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"
    EXPIRED = "expired", "Expired"


class RideRequest(models.Model):

    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="ride_requests",
    )

    # ---------------------------------
    # Vehicle
    # ---------------------------------

    # بلا choices عمدًا: الفئات المتاحة صفوف في VehicleCategory تتغيّر وقت
    # التشغيل، وتجميدها هنا يجعل الترحيل يتغيّر كلّما أضاف المشغّل فئة —
    # وهو ترحيلٌ بلا أثر على المخطّط أصلًا. التحقّق يقع في الـserializer.
    requested_vehicle_type = models.CharField(
        max_length=20,
        null=True,
        blank=True,
    )

    # الطلب المولَّد من اشتراك صباح — للتتبّع والمؤشّرات، ولمنع تكرار اليوم.
    subscription = models.ForeignKey(
        "rides.RideSubscription",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="rides",
    )

    # ---------------------------------
    # Locations
    # ---------------------------------

    pickup = gis_models.PointField(
        geography=True,
        srid=4326,
    )

    destination = gis_models.PointField(
        geography=True,
        srid=4326,
    )

    # ---------------------------------
    # Ride
    # ---------------------------------

    mode = models.CharField(
        max_length=20,
        choices=RideMode.choices,
    )

    # نوع الرحلة (مدينة / سفريات بين مدن / خط سرفيس ثابت / رحلة ترفيهية)
    trip_category = models.CharField(
        max_length=20,
        choices=TripCategory.choices,
        default=TripCategory.CITY,
        db_index=True,
    )

    # أسماء المدن للسفريات وخطوط السرفيس (لأغراض العرض والفلترة)
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

    # الرحلة المنشورة اللي انضم لها هذا الطلب مباشرة (سرفيس/ترفيهية/سفريات جاهزة)
    # ملاحظة: لرحلات City العادية المشتركة، الربط يتم عبر ScheduledSharedTripMember
    # كالمعتاد. هذا الحقل مخصص فقط لعرض/تتبع سريع بدون استعلام إضافي.
    published_trip = models.ForeignKey(
        "matching.ScheduledSharedTrip",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="direct_bookings",
    )

    passenger_count = models.PositiveSmallIntegerField(
        default=1,
    )

    scheduled_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    status = models.CharField(
        max_length=30,
        choices=RideStatus.choices,
        default=RideStatus.SEARCHING,
        db_index=True,
    )

    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
    )

    # ---------------------------------
    # Pricing snapshot
    # ---------------------------------

    base_fare = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )

    distance_fare = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )

    time_fare = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )

    gross_fare = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )

    platform_fee = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )

    customer_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )

    driver_net = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )

    # ---------------------------------
    # Pricing policy snapshot
    # منطقة الخدمة وقواعدها لحظة إنشاء الطلب - لا يُعاد حسابها لاحقًا
    # ---------------------------------

    service_area = models.ForeignKey(
        "locations.ServiceArea",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rides",
    )

    pricing_policy = models.CharField(
        max_length=30,
        blank=True,
    )

    currency = models.CharField(
        max_length=3,
        default="SYP",
    )

    fare_floor = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )

    fare_cap = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )

    # السوم بنمط inDrive: السعر الذي عرضه الزبون. السائقون يقبلونه كما هو
    # أو يعرضون أعلى منه، ولا يُعرض عليه أقلّ منه. يُرفع ولا يُخفض.
    customer_proposed_fare = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )

    surge_multiplier = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=1,
    )

    # ---------------------------------
    # Old estimation
    # Haversine / fallback
    # ---------------------------------

    estimated_distance_km = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )

    estimated_duration_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    # ---------------------------------
    # Real road routing
    # OSRM
    # ---------------------------------

    route_distance_km = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )

    route_duration_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    route_geometry = models.JSONField(
        null=True,
        blank=True,
    )

    # مصدر المسار: "provider" مسار حقيقي من مزوّد الخرائط، "estimated"
    # تقدير داخلي حين تعذّر المزوّد. يُحفظ لأنّ السعر مبنيّ عليه: أيّ
    # نزاع على أجرة يبدأ بسؤال «هل كانت المسافة محسوبة أم مقدَّرة؟»
    route_source = models.CharField(
        max_length=20,
        blank=True,
        default="",
        db_index=True,
        help_text="provider | estimated",
    )

    # نطاق البحث الذي اختاره الزبون، مقصوصًا إلى نصف قطر منطقته. فارغ =
    # نصف قطر المنطقة كما كان.
    search_radius_km = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
    )

    # «الأقرب»: الخادم يدعو أقرب سائق بنفسه، ثمّ التالي إن رفض أو صمت.
    auto_dispatch = models.BooleanField(default=False)

    # ---------------------------------
    # Timestamps
    # ---------------------------------

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:

        ordering = ["-created_at"]

        indexes = [

            models.Index(
                fields=[
                    "customer",
                    "-created_at",
                ]
            ),

            models.Index(
                fields=[
                    "status",
                    "created_at",
                ]
            ),

            models.Index(
                fields=[
                    "mode",
                    "status",
                ]
            ),

            models.Index(
                fields=[
                    "requested_vehicle_type",
                    "status",
                ]
            ),

            models.Index(
                fields=[
                    "trip_category",
                    "status",
                ]
            ),

        ]

    def __str__(self):

        return (
            f"RideRequest("
            f"id={self.id}, "
            f"customer={self.customer_id}, "
            f"mode={self.mode}, "
            f"category={self.trip_category}, "
            f"status={self.status}"
            f")"
        )

    @property
    def is_expired(self):

        if self.expires_at is None:
            return False

        return timezone.now() >= self.expires_at

class RideSubscription(models.Model):
    """
    «اشتراك الصباح» — مشوارٌ يتكرّر كلّ يوم عمل في الوقت نفسه.

    من خطّة التسعين يومًا: «مشوارٌ كلّ يوم 7:30 يُحجز أسبوعًا برسالة واحدة،
    وبسعرٍ أقلّ قليلًا — أذكى منتج في الخطّة: طلبٌ مضمون لك، ودخلٌ مؤكَّد
    للسائق كلّ صباح». في واتساب يكتبه الموظّف في دفتره؛ هنا صفٌّ واحد
    يولّد الطلب المجدول تلقائيًّا قبل موعده بـ`lead_minutes`.

    ليس رحلةً بل مولِّد رحلات: كلّ حدوثٍ يصير RideRequest مجدولًا عاديًّا
    (scheduled_at) يمرّ بالمزاد نفسه ويُقاس بنصف قطر «المجدول» — فلا مسار
    ثانٍ في المطابقة ولا في التسعير ولا في الدفع.
    """

    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ride_subscriptions",
    )
    label = models.CharField(max_length=60, blank=True, help_text="مثال: «إلى الجامعة».")
    pickup = gis_models.PointField(geography=True, srid=4326)
    destination = gis_models.PointField(geography=True, srid=4326)
    departure_time = models.TimeField(help_text="وقت الانطلاق بالتوقيت المحلّي للمدينة.")
    # أيام الأسبوع بأرقام بايثون: 0=الاثنين … 6=الأحد. الافتراض أيام العمل السورية.
    weekdays = models.JSONField(default=list)
    mode = models.CharField(max_length=20, default=RideMode.STANDARD)
    passenger_count = models.PositiveSmallIntegerField(default=1)
    requested_vehicle_type = models.CharField(max_length=20, null=True, blank=True)
    lead_minutes = models.PositiveSmallIntegerField(
        default=30, help_text="قبل الموعد بكم دقيقة يُنشأ الطلب ويُعرض على السائقين.",
    )
    is_active = models.BooleanField(default=True)
    last_materialized_on = models.DateField(
        null=True, blank=True, help_text="آخر يومٍ أُنشئ له طلب — يمنع التكرار.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["departure_time", "id"]

    def __str__(self):
        return f"RideSubscription(#{self.id} {self.customer_id} {self.departure_time})"

    SYRIAN_WORKWEEK = [6, 0, 1, 2, 3]  # الأحد–الخميس

    def runs_on(self, weekday):
        return weekday in (self.weekdays or self.SYRIAN_WORKWEEK)
