"""
استعادة حالة التطبيق عند الفتح.

المشكلة التي يحلّها هذا الملفّ ليست تقنية بل تجربة مستخدم: راكب في
منتصف رحلة يُغلق التطبيق أو ينفد شحن هاتفه. عند الفتح، ماذا يرى؟

بدون هذه الطبقة لا يستطيع التطبيق أن يعرف شيئًا: كل نقاط قراءة الرحلة
في المشروع تتطلّب `ride_id` معروفًا مسبقًا، والتطبيق فقده مع ذاكرته.
النتيجة شاشة رئيسية فارغة وسائق واقف بالباب.

القرار المعماري: نقطة **واحدة** تعيد كل ما يلزم لرسم الشاشة الصحيحة —
الطلب والرحلة والمرحلة والدفعة المعلّقة وغرف الزمن الحقيقي. نداء واحد
عند الإقلاع بدل خمسة، ولا تخمين من طرف التطبيق.

`stage` هو بيت القصيد: قيمة نصّية واحدة يبني عليها التطبيق شاشته بلا
أن يعيد استنتاج المرحلة من مزيج حالتَي الطلب والرحلة — وهو استنتاج لو
تُرك للعميل لاختلف بين أندرويد و iOS.
"""
from matching.models import OfferStatus, RideOffer
from rides.models import RideRequest, RideStatus
from trips.models import Trip, TripStatus
from users.models import UserRole


#: الحالات التي تعني "للمستخدم رحلة قائمة الآن".
#: تشمل SEARCHING عمدًا: زبون أغلق التطبيق أثناء البحث يجب أن يعود
#: ليجد بحثه مستمرًّا لا شاشة بيضاء.
ACTIVE_RIDE_STATUSES = (
    RideStatus.SEARCHING,
    RideStatus.OFFERS_RECEIVED,
    RideStatus.DRIVER_SELECTED,
    RideStatus.DRIVER_ARRIVING,
    RideStatus.DRIVER_ARRIVED,
    RideStatus.IN_PROGRESS,
)

ACTIVE_TRIP_STATUSES = (
    TripStatus.CREATED,
    TripStatus.DRIVER_ARRIVING,
    TripStatus.DRIVER_ARRIVED,
    TripStatus.IN_PROGRESS,
)


class Stage:
    """
    المرحلة كما يفهمها التطبيق. سلسلة مسطّحة لا تركيبة حالتين.

    القيم ثابتة ولا تُغيَّر بعد إطلاق التطبيق: تغيير قيمة هنا يكسر
    شاشة عند مستخدم لم يُحدّث تطبيقه بعد.
    """

    IDLE = "idle"
    SEARCHING = "searching"
    CHOOSING_OFFER = "choosing_offer"
    DRIVER_ASSIGNED = "driver_assigned"
    DRIVER_ARRIVING = "driver_arriving"
    DRIVER_ARRIVED = "driver_arrived"
    IN_PROGRESS = "in_progress"
    AWAITING_PAYMENT = "awaiting_payment"

    ALL = (
        IDLE, SEARCHING, CHOOSING_OFFER, DRIVER_ASSIGNED,
        DRIVER_ARRIVING, DRIVER_ARRIVED, IN_PROGRESS, AWAITING_PAYMENT,
    )


#: من حالة الرحلة الجارية إلى المرحلة. الرحلة أدقّ من الطلب حين توجد.
_TRIP_STAGE = {
    TripStatus.CREATED: Stage.DRIVER_ASSIGNED,
    TripStatus.DRIVER_ARRIVING: Stage.DRIVER_ARRIVING,
    TripStatus.DRIVER_ARRIVED: Stage.DRIVER_ARRIVED,
    TripStatus.IN_PROGRESS: Stage.IN_PROGRESS,
}

#: من حالة الطلب إلى المرحلة، حين لا توجد رحلة بعد.
_RIDE_STAGE = {
    RideStatus.SEARCHING: Stage.SEARCHING,
    RideStatus.OFFERS_RECEIVED: Stage.CHOOSING_OFFER,
    RideStatus.DRIVER_SELECTED: Stage.DRIVER_ASSIGNED,
    RideStatus.DRIVER_ARRIVING: Stage.DRIVER_ARRIVING,
    RideStatus.DRIVER_ARRIVED: Stage.DRIVER_ARRIVED,
    RideStatus.IN_PROGRESS: Stage.IN_PROGRESS,
}


class ResumeService:

    # =================================================================
    # المدخل الوحيد
    # =================================================================

    @classmethod
    def snapshot(cls, user):
        """
        يعيد قاموسًا جاهزًا للتسلسل. لا يرفع استثناءً ولا يعيد `None`:
        مستخدم بلا رحلة يحصل على لقطة صالحة مرحلتها `idle`، لا على 404.

        السبب: 404 على "ما حالتي؟" يجبر التطبيق على معالجة الخطأ في
        أكثر مساراته شيوعًا — وهو المسار الذي يجب أن يكون أبسطها.
        """
        is_driver = (
            user.role == UserRole.DRIVER
            and getattr(user, "driver_profile", None) is not None
        )

        if is_driver:
            ride = cls._driver_active_ride(user.driver_profile)
        else:
            ride = cls._customer_active_ride(user)

        trip = cls._trip_for(ride) if ride is not None else None

        pending_payment = cls._pending_payment(user, is_driver)

        stage = cls._resolve_stage(ride, trip, pending_payment)

        return {
            "has_active_ride": ride is not None,
            "role": "driver" if is_driver else "customer",
            "stage": stage,
            "ride": ride,
            "trip": trip,
            "pending_payment": pending_payment,
            "realtime": cls._realtime_rooms(user, ride, is_driver),
            # السائق في رحلة مشتركة يحمل أكثر من راكب، ولكلٍّ رحلته وأجرته
            # وتسلسله (وصلت/ابدأ/أنهِ). الرحلة أعلاه هي الأحدث؛ هنا البقيّة.
            "other_trips": (
                cls._driver_other_trips(user.driver_profile, ride)
                if is_driver and ride is not None
                else []
            ),
        }

    @classmethod
    def _driver_other_trips(cls, driver_profile, primary):
        offers = (
            RideOffer.objects
            .filter(
                driver=driver_profile,
                status=OfferStatus.ACCEPTED,
                ride__status__in=ACTIVE_RIDE_STATUSES,
            )
            .exclude(ride=primary)
            .select_related("ride", "ride__service_area")
            .order_by("accepted_at", "created_at")
        )
        return [
            {"ride": offer.ride, "trip": cls._trip_for(offer.ride)}
            for offer in offers
        ]

    # =================================================================
    # البحث عن الرحلة القائمة
    # =================================================================

    @staticmethod
    def _customer_active_ride(user):
        return (
            RideRequest.objects
            .filter(customer=user, status__in=ACTIVE_RIDE_STATUSES)
            .select_related("service_area", "published_trip")
            .order_by("-created_at")
            .first()
        )

    @staticmethod
    def _driver_active_ride(driver_profile):
        """
        السائق مرتبط برحلة عبر **عرض مقبول** حصرًا — وهو نفس التعريف
        المعتمد في `MatchingService.get_busy_driver_ids` و
        `DriverRoomConsumer` و`RideConsumer`. أي تعريف آخر هنا كان
        سيجعل التطبيق يرى رحلة لا يراها بقيّة النظام.
        """
        offer = (
            RideOffer.objects
            .filter(
                driver=driver_profile,
                status=OfferStatus.ACCEPTED,
                ride__status__in=ACTIVE_RIDE_STATUSES,
            )
            .select_related("ride", "ride__service_area")
            .order_by("-accepted_at", "-created_at")
            .first()
        )

        return offer.ride if offer is not None else None

    @staticmethod
    def _trip_for(ride):
        return (
            Trip.objects
            .filter(ride=ride)
            .select_related("driver", "driver__user", "vehicle")
            .first()
        )

    # =================================================================
    # الدفعة المعلّقة
    # =================================================================

    @staticmethod
    def _pending_payment(user, is_driver):
        """
        رحلة انتهت ولم تُسدَّد بعد.

        بلا هذا الحقل يسقط أهمّ سيناريو استعادة على الإطلاق: السائق
        أنهى الرحلة، وقبل أن يؤكّد قبض الأجرة أُغلق التطبيق. عند الفتح
        لا شيء يذكّره، فتضيع الأجرة من السجلّ وتبقى الدفعة معلّقة أبدًا.
        """
        try:
            from payments.models import Payment, PaymentStatus
        except ImportError:          # تطبيق المدفوعات غير مثبَّت
            return None

        queryset = Payment.objects.filter(
            status__in=(PaymentStatus.PENDING, PaymentStatus.PROCESSING)
        ).select_related("trip")

        if is_driver:
            queryset = queryset.filter(driver=user.driver_profile)
        else:
            queryset = queryset.filter(customer=user)

        return queryset.order_by("-created_at").first()

    # =================================================================
    # المرحلة وغرف الزمن الحقيقي
    # =================================================================

    @staticmethod
    def _resolve_stage(ride, trip, pending_payment):
        if ride is None:
            # لا رحلة قائمة، لكن قد تكون هناك أجرة تنتظر التأكيد.
            return Stage.AWAITING_PAYMENT if pending_payment else Stage.IDLE

        if trip is not None and trip.status in _TRIP_STAGE:
            return _TRIP_STAGE[trip.status]

        return _RIDE_STAGE.get(ride.status, Stage.IDLE)

    @staticmethod
    def _realtime_rooms(user, ride, is_driver):
        """
        مسارات WebSocket الجاهزة للاشتراك.

        نبنيها في الخادم لا في التطبيق: أي تغيير في مسارات
        `realtime/routing.py` غدًا كان سيتطلّب إصدار تطبيق جديد لو
        كانت مبنيّة في العميل.
        """
        rooms = {"ride_room": None, "driver_room": None}

        if ride is not None:
            rooms["ride_room"] = f"/ws/rides/{ride.id}/"

        if is_driver:
            rooms["driver_room"] = f"/ws/driver/{user.driver_profile.id}/"

        return rooms

    # =================================================================
    # السجلّ
    # =================================================================

    @staticmethod
    def customer_rides(user, status=None):
        """طلبات الزبون، الأحدث أوّلًا. استعلام مرتَّب جاهز للترقيم."""
        queryset = RideRequest.objects.filter(customer=user)

        if status:
            queryset = queryset.filter(status=status)

        return queryset.select_related("service_area").order_by("-created_at")

    @staticmethod
    def trips_for(user, status=None):
        """
        رحلات المستخدم أيًّا كان دوره.

        الترشيح بالدور لا بمحاولة الطرفين: سائق يملك ملفًّا وزبونًا
        بالاسم نفسه غير ممكن في هذا النظام، وتوحيد الاستعلامين بـ`Q`
        كان سينتج خططًا بطيئة على جدول ينمو بلا حدّ.
        """
        driver_profile = getattr(user, "driver_profile", None)

        if user.role == UserRole.DRIVER and driver_profile is not None:
            queryset = Trip.objects.filter(driver=driver_profile)
        else:
            queryset = Trip.objects.filter(customer=user)

        if status:
            queryset = queryset.filter(status=status)

        return queryset.select_related(
            "driver", "driver__user", "vehicle", "ride"
        ).order_by("-created_at")
