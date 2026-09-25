from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.measure import D
from django.db import models, transaction
from django.utils import timezone

from ops.models import AuditEntity
from ops.services.audit import AuditService

from matching.models import (
    OfferStatus,
    RideOffer,
    ScheduledSharedTripMember,
    SharedRideGroupMember,
    SharedJoinRequest,
    SharedJoinStatus,
)

from rides.models import (
    RideMode,
    RideStatus,
    RideRequest,
)

from users.models import DriverProfile

from vehicles.models import Vehicle


class MatchingError(Exception):
    pass


# الحالات التي لا تزال الرحلة فيها "مفتوحة" لاستقبال/تقديم عروض
OPEN_RIDE_STATUSES = [
    RideStatus.SEARCHING,
    RideStatus.OFFERS_RECEIVED,
]

# حالات العرض التي تمنع تقديم عرض جديد لنفس (ride, driver)
BLOCKING_OFFER_STATUSES = [
    OfferStatus.PENDING,
    OfferStatus.ACCEPTED,
]


class MatchingService:

    @staticmethod
    def is_scheduled(ride):
        return ride.scheduled_at is not None

    @staticmethod
    def is_shared(ride):
        return ride.mode == RideMode.SHARED

    @staticmethod
    def is_marketplace_ride(ride):
        return ride.scheduled_at is not None

    @classmethod
    def get_driver_limit(cls, ride):
        if cls.is_marketplace_ride(ride):
            return settings.MATCHING_MARKETPLACE_DRIVER_LIMIT
        return settings.MATCHING_NORMAL_DRIVER_LIMIT

    @staticmethod
    def _expire_offer_if_stale(offer_id):
        """
        ترانزاكشن مستقلة تُثبَّت فورًا. لا تشيل استثناء، فمهما حصل
        بعدها، تحديث EXPIRED هذا لن يُلغى بـ rollback.
        """
        with transaction.atomic():
            offer = (
                RideOffer.objects
                .select_for_update()
                .filter(
                    id=offer_id,
                    status=OfferStatus.PENDING,
                    expires_at__lte=timezone.now(),
                )
                .first()
            )

            if not offer:
                return

            offer.status = OfferStatus.EXPIRED
            offer.save(update_fields=["status", "updated_at"])

            if offer.ride.mode == RideMode.SHARED:
                from matching.services.shared_matching import SharedMatchingService
                SharedMatchingService.cancel_group_for_offer(offer)

    @staticmethod
    def _expire_ride_if_stale(ride_id):
        with transaction.atomic():
            expired = (
                RideRequest.objects
                .filter(
                    id=ride_id,
                    status__in=OPEN_RIDE_STATUSES,
                    expires_at__isnull=False,
                    expires_at__lte=timezone.now(),
                )
                .update(status=RideStatus.EXPIRED)
            )

            if expired:
                AuditService.record(
                    AuditEntity.RIDE,
                    ride_id,
                    to_state=RideStatus.EXPIRED,
                    reason="انتهت مهلة الطلب أثناء المطابقة",
                    ride_id=ride_id,
                )

    @classmethod
    def get_radius_km(cls, ride):
        """
        نصف قطر البحث لهذا الطلب — من مدينته لا من إعدادات المنصّة.

        كان هذا الموضع يقرأ رقمًا عالميًّا من الإعدادات بينما خريطة الزبون
        تقرأ `area.default_matching_radius_km`. النتيجة أنّ المشغّل يغيّر
        نصف القطر من الأدمن، فيتغيّر ما يراه الزبون على الخريطة **ولا
        يتغيّر مَن يُطابَق فعلًا** — وهذا أسوأ من ألّا يعمل الحقل أصلًا،
        لأنّ المشغّل يرى أثرًا فيظنّ أنّه ضبط الأمر كلّه.

        والمدينة تأتي من الطلب لا من السائق: القواعد التنظيمية تتبع مكان
        بدء الخدمة، وقد أُثبتت هذه القاعدة في `rides/services`.
        """
        area = getattr(ride, "service_area", None)

        # نطاقٌ اختاره الزبون — قُصّ إلى نصف قطر منطقته عند الإنشاء.
        if ride.search_radius_km and not cls.is_marketplace_ride(ride):
            return float(ride.search_radius_km)

        if area is not None:
            if cls.is_marketplace_ride(ride):
                return area.effective_marketplace_radius_km
            return area.effective_instant_radius_km

        # طلبٌ خارج كلّ منطقة معروفة: الافتراض العامّ خيرٌ من صفر.
        if cls.is_marketplace_ride(ride):
            return settings.MATCHING_MARKETPLACE_RADIUS_KM
        return settings.MATCHING_NORMAL_RADIUS_KM

    @staticmethod
    def is_driver_location_fresh(driver):
        if not driver.last_location_at:
            return False

        max_age = getattr(
            settings,
            "MATCHING_LOCATION_MAX_AGE_SECONDS",
            60,
        )

        age = (
            timezone.now() - driver.last_location_at
        ).total_seconds()

        return age <= max_age

    @classmethod
    def get_busy_driver_ids(cls):
        active_ride_statuses = [
            RideStatus.DRIVER_SELECTED,
            RideStatus.DRIVER_ARRIVING,
            RideStatus.DRIVER_ARRIVED,
            RideStatus.IN_PROGRESS,
        ]
        return (
            RideOffer.objects
            .filter(
                status=OfferStatus.ACCEPTED,
                ride__status__in=active_ride_statuses,
            )
            .values_list("driver_id", flat=True)
        )

    @classmethod
    def get_unavailable_driver_ids(cls, ride=None):
        """
        مَن لا يصلح لهذا الطلب تحديدًا.

        بلا ride: السلوك القديم حرفيًا (أي ارتباط = مشغول)، فكل نداء
        قديم يبقى صحيحًا.

        مع طلب مشترك: نستثني فقط مَن عنده رحلة نشطة غير مشتركة. سائق كل
        رحلاته مشتركة وفيه مقعد فارغ ليس مشغولًا - وكفاية المقاعد يفحصها
        can_driver_submit_offer على حدة بالأرقام لا بالتخمين.

        ولماذا لم نغيّر get_busy_driver_ids نفسها؟ لأن ثلاثة مواضع أخرى
        تعرّف بها "السائق المرتبط بهذه الرحلة" لأغراض أخرى تمامًا (غرفة
        الرحلة، صلاحية الدخول، بثّ الموقع)، وتوسيعها هناك يفتح لسائق
        مشترك رحلةً ليست له.
        """
        active_ride_statuses = [
            RideStatus.DRIVER_SELECTED,
            RideStatus.DRIVER_ARRIVING,
            RideStatus.DRIVER_ARRIVED,
            RideStatus.IN_PROGRESS,
        ]

        queryset = RideOffer.objects.filter(
            status=OfferStatus.ACCEPTED,
            ride__status__in=active_ride_statuses,
        )

        if ride is not None and cls.is_shared(ride) and not cls.is_scheduled(ride):
            queryset = queryset.exclude(ride__mode=RideMode.SHARED)

        return queryset.values_list("driver_id", flat=True)

    # -----------------------------------------------------------
    # اتجاه: من رحلة -> سائقين مؤهلين (يستخدم لبناء قائمة العروض للرحلة)
    # -----------------------------------------------------------
    @classmethod
    def get_eligible_drivers(cls, ride):

        if ride.status not in OPEN_RIDE_STATUSES:
            return DriverProfile.objects.none()

        radius_km = cls.get_radius_km(ride)
        driver_limit = cls.get_driver_limit(ride)
        required_seats = ride.passenger_count
        busy_driver_ids = list(cls.get_unavailable_driver_ids(ride))

        drivers = (
            DriverProfile.objects
            .filter(
                status=DriverProfile.DriverStatus.ACTIVE,
                online=True,
                current_location__isnull=False,
                vehicles__active=True,
                vehicles__seats__gte=required_seats,
            )
            .exclude(id__in=busy_driver_ids)
            .annotate(
                remaining_seats_calc=(
                    models.F("available_seats") - models.F("current_occupancy")
                )
            )
            .filter(remaining_seats_calc__gte=required_seats)
        )

        if ride.requested_vehicle_type:
            drivers = drivers.filter(
                vehicles__type=ride.requested_vehicle_type,
                vehicles__active=True,
            )

        drivers = (
            drivers
            .annotate(distance=Distance("current_location", ride.pickup))
            .filter(distance__lte=D(km=radius_km))
            .select_related("user")
            .distinct()
            .order_by("distance")
        )

        fresh_driver_ids = [
            driver.id
            for driver in drivers
            if cls.is_driver_location_fresh(driver)
        ]

        if not fresh_driver_ids:
            return DriverProfile.objects.none()

        return (
            drivers
            .filter(id__in=fresh_driver_ids)
            .order_by("distance")[:driver_limit]
        )

    # -----------------------------------------------------------
    # اتجاه معاكس: من سائق -> رحلات مؤهلة (يستخدم في شاشة السائق)
    # هذا يحل مشكلة N+1 لأنه لا يلف على كل الرحلات
    # -----------------------------------------------------------
    @classmethod
    def get_eligible_rides_for_driver(cls, driver):

        if driver.status != DriverProfile.DriverStatus.ACTIVE:
            return RideRequest.objects.none()

        if not driver.online:
            return RideRequest.objects.none()

        if not driver.current_location:
            return RideRequest.objects.none()

        if not cls.is_driver_location_fresh(driver):
            return RideRequest.objects.none()

        remaining_seats = driver.available_seats - driver.current_occupancy

        if remaining_seats <= 0:
            return RideRequest.objects.none()

        if driver.id in set(cls.get_busy_driver_ids()):
            return RideRequest.objects.none()

        active_vehicles = Vehicle.objects.filter(
            driver=driver,
            active=True,
        )

        if not active_vehicles.exists():
            return RideRequest.objects.none()

        max_vehicle_seats = (
            active_vehicles
            .aggregate(models.Max("seats"))["seats__max"]
            or 0
        )

        driver_vehicle_types = set(
            active_vehicles.values_list("type", flat=True)
        )

        max_seats = min(remaining_seats, max_vehicle_seats)

        rides = (
            RideRequest.objects
            .filter(
                status__in=OPEN_RIDE_STATUSES,
                passenger_count__lte=max_seats,
            )
            .filter(
                models.Q(requested_vehicle_type__isnull=True)
                | models.Q(requested_vehicle_type__in=driver_vehicle_types)
            )
            .exclude(
                offers__driver=driver,
                offers__status__in=BLOCKING_OFFER_STATUSES,
            )
        )

        # === إصلاح: RideMode.SCHEDULED غير موجود أصلاً؛ المعيار الصحيح
        # لتصنيف الرحلة "مجدولة/marketplace" هو وجود scheduled_at،
        # كما هو مطبق في is_marketplace_ride بالأعلى ===
        rides = (
            rides
            .annotate(distance=Distance("pickup", driver.current_location))
            .filter(cls._radius_filter())
            .exclude(cancellations__driver=driver, cancellations__actor="driver")
            # الزبون ضيّق نطاقه: سائقٌ ضمن نصف قطر المنطقة وخارج نطاقه لا يراه.
            .filter(
                models.Q(search_radius_km__isnull=True)
                | models.Q(distance__lte=models.F("search_radius_km") * 1000)
            )
            .order_by("distance")
        )

        return rides

    @classmethod
    def _radius_filter(cls):
        """
        شرط المسافة، بنصف قطر **كلّ مدينة على حِدة**.

        لماذا لا يكفي رقم واحد هنا: هذه القائمة تفلتر *طلبات* لا سائقين،
        وطلبات القائمة الواحدة قد تكون في مدن مختلفة — سائق على حدّ جبلة
        واللاذقية يرى طلبات المدينتين، وهو سلوك صحيح ومطلوب. تطبيق نصف قطر
        جبلة على طلب لاذقيّ يعني أن يحكم إعدادُ مدينةٍ على طلب مدينةٍ أخرى.

        ولماذا مدينة الطلب لا مدينة السائق: المشغّل يضبط «كم يبعد السائق
        المقبول عن زبوني»، وصاحب هذا الحكم هو من يملك الزبون. سائقٌ من
        مدينة واسعة الأنصاف لا يكسب حقّ الوصول إلى طلبات مدينة ضيّقة
        لمجرّد أنّه مسجَّل هناك.

        والتنفيذ استعلامٌ واحد لا استعلامٌ لكلّ مدينة: المناطق وحدات لا
        آلاف وهي مخزَّنة مؤقّتًا، فنبني منها OR واحدًا مقيّدًا بعددها.
        """
        from locations.services import LocationService

        condition = models.Q()

        for area in LocationService.get_active_service_areas():
            instant = D(km=area.effective_instant_radius_km)
            marketplace = D(km=area.effective_marketplace_radius_km)

            condition |= models.Q(
                service_area=area,
                scheduled_at__isnull=True,
                distance__lte=instant,
            ) | models.Q(
                service_area=area,
                scheduled_at__isnull=False,
                distance__lte=marketplace,
            )

        # طلبات بلا منطقة (نقطة التقاط خارج كلّ حدّ معروف): الافتراض العامّ.
        # إسقاطها من الشرط كان سيُخفيها عن كلّ سائق إلى الأبد بلا سبب مرئي.
        condition |= models.Q(
            service_area__isnull=True,
            scheduled_at__isnull=True,
            distance__lte=D(km=settings.MATCHING_NORMAL_RADIUS_KM),
        ) | models.Q(
            service_area__isnull=True,
            scheduled_at__isnull=False,
            distance__lte=D(km=settings.MATCHING_MARKETPLACE_RADIUS_KM),
        )

        return condition

    @classmethod
    def can_driver_submit_offer(cls, ride, driver):

        if ride.status not in OPEN_RIDE_STATUSES:
            return False

        if driver.status != DriverProfile.DriverStatus.ACTIVE:
            return False

        if not driver.online:
            return False

        # سائقٌ تجاوز حدّ الإلغاء بعد القبول موقوفٌ مؤقّتًا، ومَن ألغى هذا
        # الطلب بعينه لا يعود إليه.
        from trips.services.cancellation import CancellationPolicy

        if CancellationPolicy.driver_block_until(
            driver, getattr(ride, "service_area", None)
        ):
            return False

        if ride.cancellations.filter(driver=driver, actor="driver").exists():
            return False

        if not driver.current_location:
            return False

        if not cls.is_driver_location_fresh(driver):
            return False

        required_seats = ride.passenger_count
        remaining_seats = driver.available_seats - driver.current_occupancy

        if remaining_seats < required_seats:
            return False

        if driver.id in set(cls.get_unavailable_driver_ids(ride)):
            return False

        vehicle_qs = Vehicle.objects.filter(
            driver=driver,
            active=True,
            seats__gte=required_seats,
        )

        if ride.requested_vehicle_type:
            vehicle_qs = vehicle_qs.filter(
                type=ride.requested_vehicle_type,
            )

        if not vehicle_qs.exists():
            return False

        radius_km = cls.get_radius_km(ride)

        distance = (
            DriverProfile.objects
            .filter(id=driver.id)
            .annotate(distance=Distance("current_location", ride.pickup))
            .values_list("distance", flat=True)
            .first()
        )

        if distance is None or distance.km > radius_km:
            return False

        return True

    @classmethod
    def create_offer(cls, ride_id, driver, gross_fare, eta_minutes):

        cls._expire_ride_if_stale(ride_id)

        return cls._create_offer_atomic(
            ride_id=ride_id,
            driver=driver,
            gross_fare=gross_fare,
            eta_minutes=eta_minutes,
        )

    @classmethod
    @transaction.atomic
    def _create_offer_atomic(cls, ride_id, driver, gross_fare, eta_minutes):

        ride = (
            RideRequest.objects
            .select_for_update()
            .get(id=ride_id)
        )

        if ride.status not in OPEN_RIDE_STATUSES:
            raise MatchingError("Ride is no longer available.")

        if ride.is_expired:
            raise MatchingError("Ride request has expired.")

        # مسار العروض هو "مزايدة السائقين" صراحةً - لا الخطة الافتراضية
        # للمنطقة. في مدينة ذات تعرفة إلزامية (الأردن مثلًا) لا تكون هذه
        # الخطة مفعّلة أصلًا، فيُرفض العرض برسالة واضحة بدل أن يمرّ سعر
        # مخالف للقانون.
        from locations.models import PricingPolicy
        from pricing.services import PricingPolicyError, PricingService

        ride_quote = {
            "gross_fare": ride.gross_fare,
            "fare_floor": ride.fare_floor,
            "fare_cap": ride.fare_cap,
            "pricing_policy": PricingPolicy.DRIVER_BIDDING,
            "currency": ride.currency,
        }
        policy = PricingPolicy.DRIVER_BIDDING

        # الزبون عرض سعره: السائق يقبله كما هو أو يعرض أعلى منه ضمن سقف،
        # ولا يعرض أقلّ منه — سعر الزبون نفسه اجتاز أرضيّته عند عرضه.
        if ride.customer_proposed_fare is not None:
            proposed = ride.customer_proposed_fare
            counter_cap = cls._counter_cap(ride)
            ride_quote["fare_floor"] = proposed
            ride_quote["fare_cap"] = counter_cap
            ride_quote["pricing_policy"] = PricingPolicy.CUSTOMER_BIDDING
            policy = PricingPolicy.CUSTOMER_BIDDING

        try:
            gross_fare = PricingService.validate_proposed_fare(
                proposed_fare=gross_fare,
                quote=ride_quote,
                service_area=ride.service_area,
                policy=policy,
                proposer="driver",
            )
        except PricingPolicyError as exc:
            raise MatchingError(str(exc))

        if eta_minutes <= 0:
            raise MatchingError("ETA must be greater than zero.")

        if not cls.can_driver_submit_offer(ride=ride, driver=driver):
            raise MatchingError("Driver is not eligible for this ride.")

        # مهلة العرض لكلّ مدينة: مدينة كثيفة تُغلق المزاد في ثوانٍ، ومدينة
        # متباعدة تحتاج ضعف ذلك. الطلب يحمل منطقته أصلًا فلا استعلام إضافي.
        offer_ttl = (
            ride.service_area.effective_offer_ttl_seconds
            if ride.service_area_id
            else settings.RIDE_OFFER_TTL_SECONDS
        )

        expires_at = timezone.now() + timedelta(seconds=offer_ttl)

        # المجدول: الزبون حجز لغدٍ ولن يجلس يراقب الشاشة ثلاثين ثانية. العرض
        # يبقى حيًّا حتّى موعد الانطلاق فيختاره متى فتح التطبيق — وُجد
        # بجهازين: عرضٌ على حجز الغد انقضى قبل أن يراه أحد (العيب #37).
        if cls.is_scheduled(ride) and ride.scheduled_at > expires_at:
            expires_at = ride.scheduled_at

        existing = (
            RideOffer.objects
            .select_for_update()
            .filter(ride=ride, driver=driver)
            .first()
        )

        if existing:
            is_still_blocking = (
                existing.status in BLOCKING_OFFER_STATUSES
                and not (
                    existing.status == OfferStatus.PENDING
                    and existing.expires_at <= timezone.now()
                )
            )

            if is_still_blocking:
                raise MatchingError("Driver has already submitted an offer.")

            existing.gross_fare = gross_fare
            existing.eta_minutes = eta_minutes
            existing.status = OfferStatus.PENDING
            existing.expires_at = expires_at
            existing.accepted_at = None

            existing.save(
                update_fields=[
                    "gross_fare", "eta_minutes", "status",
                    "expires_at", "accepted_at", "updated_at",
                ]
            )
            offer = existing
        else:
            offer = RideOffer.objects.create(
                ride=ride,
                driver=driver,
                gross_fare=gross_fare,
                eta_minutes=eta_minutes,
                status=OfferStatus.PENDING,
                expires_at=expires_at,
            )

        if ride.status == RideStatus.SEARCHING:
            ride.status = RideStatus.OFFERS_RECEIVED
            ride.save(update_fields=["status", "updated_at"])

        if (
            cls.is_shared(ride)
            and not cls.is_scheduled(ride)
        ):
            from matching.services.shared_matching import (
                SharedMatchingService,
            )

            SharedMatchingService.broadcast_offer_to_candidates(
                offer
            )
        from django.db import transaction as _transaction
        from realtime.events import EventBus
        from matching.serializers import RideOfferSerializer

        _transaction.on_commit(
            lambda: EventBus.publish(
                group_name=f"ride_{ride.id}",
                event_type="offer.created",
                entity_type="ride",
                entity_id=ride.id,
                payload=RideOfferSerializer(offer).data,
            )
        )

        return offer

    @classmethod
    def select_offer(cls, ride_id, offer_id, customer):
        try:
            return cls._select_offer_atomic(
                ride_id=ride_id,
                offer_id=offer_id,
                customer=customer,
            )

        except MatchingError as exc:
            if str(exc) == "Offer has expired.":

                RideOffer.objects.filter(
                    id=offer_id,
                    status=OfferStatus.PENDING,
                    expires_at__lte=timezone.now(),
                ).update(
                    status=OfferStatus.EXPIRED,
                    updated_at=timezone.now(),
                )

            raise

    @classmethod
    @transaction.atomic
    def _select_offer_atomic(cls, ride_id, offer_id, customer):

        ride = (
            RideRequest.objects
            .select_for_update()
            .get(
                id=ride_id,
                customer=customer,
            )
        )

        offer = (
            RideOffer.objects
            .select_for_update()
            .select_related("driver")
            .get(
                id=offer_id,
                ride=ride,
            )
        )

        driver = (
            DriverProfile.objects
            .select_for_update()
            .get(id=offer.driver_id)
        )

        now = timezone.now()

        if ride.status not in OPEN_RIDE_STATUSES:
            raise MatchingError(
                "Ride is no longer available."
            )

        if offer.status != OfferStatus.PENDING:
            raise MatchingError(
                "Offer is no longer available."
            )

        if offer.expires_at <= now:
            raise MatchingError(
                "Offer has expired."
            )

        if driver.status != DriverProfile.DriverStatus.ACTIVE:
            raise MatchingError(
                "Driver is no longer active."
            )

        if not driver.online:
            raise MatchingError(
                "Driver is no longer online."
            )

        # نفس التعريف الموحّد: رحلة مشتركة أخرى لا تمنع، ورحلة فردية تمنع.
        already_busy = (
            driver.id in set(cls.get_unavailable_driver_ids(ride))
        )

        # وكفاية المقاعد تُفحص هنا أيضًا لا في الإنشاء فقط: بين تقديم
        # العرض واختياره قد يكون راكب آخر شغل المقعد.
        if not already_busy:
            remaining = driver.available_seats - driver.current_occupancy

            if remaining < ride.passenger_count:
                raise MatchingError("Driver no longer has enough free seats.")

        if already_busy:
            raise MatchingError(
                "Driver has just been assigned to another ride."
            )

        offer.status = OfferStatus.ACCEPTED
        offer.accepted_at = now

        offer.save(
            update_fields=[
                "status",
                "accepted_at",
                "updated_at",
            ]
        )

        cancelled_offers = list(
            RideOffer.objects
            .select_for_update()
            .filter(
                ride=ride,
                status=OfferStatus.PENDING,
            )
            .exclude(id=offer.id)
        )

        for cancelled_offer in cancelled_offers:
            cancelled_offer.status = OfferStatus.CANCELLED
            cancelled_offer.save(update_fields=["status", "updated_at"])

            if (
                ride.mode == RideMode.SHARED
                and ride.scheduled_at is None
            ):
                from matching.services.shared_matching import (
                    SharedMatchingService
                )

                SharedMatchingService.cancel_group_for_offer(
                    cancelled_offer
                )

        ride.status = RideStatus.DRIVER_SELECTED

        # الأجرة الفعلية هي العرض الفائز لا تقدير الإنشاء — وإلّا فُتحت
        # الدفعة على التقدير (قِيس: عرض 6,000 قُبل، ودفعة 5,136).
        from pricing.services import PricingService
        fare_fields = PricingService.settle_from_offer(ride, offer, driver)
        # استيراد محلي: invitation.py يستورد من هذا الملف، فالاستيراد في
        # الأعلى يخلق حلقة.
        from matching.services.invitation import InvitationService

        InvitationService.cancel_pending_for_ride(ride, reason="offer_selected")
        # إنشاء الرحلة الفعلية. idempotent، فتكرار الاستدعاء بلا أثر.
        from trips.services.trip import TripService

        TripService.ensure_trip(ride, offer=offer)
        ride.save(
            update_fields=[
                "status",
                "updated_at",
                *fare_fields,
            ]
        )
        if (
            cls.is_shared(ride)
            and cls.is_scheduled(ride)
        ):
            from matching.services.scheduled_shared import (
                ScheduledSharedTripService,
            )

            ScheduledSharedTripService.create_from_accepted_offer(
                offer
            )

        from matching.services.shared_matching import (
            SharedMatchingService,
        )

        SharedMatchingService.propagate_status_to_members(
            ride,
            RideStatus.DRIVER_SELECTED,
        )
        from django.db import transaction as _transaction
        from realtime.events import EventBus
        from matching.serializers import RideOfferSerializer

        offer_payload = RideOfferSerializer(offer).data
        ride_id = ride.id
        driver_id = offer.driver_id

        # أعضاء الرحلة المشتركة الفورية: رحلاتهم تغيّرت حالتها في
        # propagate_status_to_members أعلاه، لكن لم يكن يصلهم أي حدث على
        # غرفهم الخاصة - كانوا يرون رحلتهم عالقة في "بحث" إلى الأبد.
        member_ride_ids = list(
            SharedRideGroupMember.objects
            .filter(group__host_offer__ride=ride)
            .exclude(ride=ride)
            .values_list("ride_id", flat=True)
        )

        def _publish_and_lock():
            from presence.services import PresenceService

            EventBus.publish(
                group_name=f"ride_{ride_id}",
                event_type="offer.accepted",
                entity_type="ride",
                entity_id=ride_id,
                payload=offer_payload,
            )

            # السائق صاحب العرض لا ينضمّ إلى غرفة الرحلة قبل أن تُقبل
            # - فلا يصله ما يُبثّ فيها. بلا هذا السطر كان يبقى على شاشة
            # الطلبات إلى أن يعيد تشغيل التطبيق، والزبون ينتظر سيارةً
            # سائقُها لا يعرف أنّه اختير. قِيس على تطبيق السائق نفسه.
            EventBus.publish(
                group_name=f"driver_{driver_id}",
                event_type="offer.accepted",
                entity_type="ride",
                entity_id=ride_id,
                payload=offer_payload,
            )

            for member_ride_id in member_ride_ids:
                EventBus.publish(
                    group_name=f"ride_{member_ride_id}",
                    event_type="ride.driver_selected",
                    entity_type="ride",
                    entity_id=member_ride_id,
                    payload={
                        "ride_id": member_ride_id,
                        "status": RideStatus.DRIVER_SELECTED,
                        "host_ride_id": ride_id,
                        "driver_id": driver_id,
                    },
                )

            # لا نكتب الحالة هنا: TripService.ensure_trip سجّل مزامنة
            # الارتباط على on_commit قبل هذه الدالة، وهي تعرف الفرق بين
            # BUSY وSHARING وتُعلم الخريطة بنفسها. الكتابة هنا كانت تشطب
            # نتيجتها بعد سطرين لأن on_commit تُنفَّذ بترتيب التسجيل.
            pass

        _transaction.on_commit(_publish_and_lock)

        return offer

    # =========================================================
    # نقطة دخول موحّدة لإلغاء رحلة العميل. توجّه تلقائيًا لمنطق
    # التنظيف الصحيح حسب نوع الرحلة، دون إسقاط باقي الركاب في
    # الرحلات المشتركة (يتم فقط ترقية مضيف جديد إن لزم الأمر).
    # =========================================================

    # =========================================================
    # الزبون يقترح سعره (السوم بنمط inDrive)
    # =========================================================

    DEFAULT_PROPOSAL_MIN_RATIO = Decimal("0.70")
    DEFAULT_COUNTER_RATIO = Decimal("1.50")
    #: بلا سقف في المنطقة: ثلاثة أضعاف التسعيرة — يمنع خطأ إصبع (صفر زائد).
    PROPOSAL_SANITY_CAP = Decimal("3")

    @classmethod
    def proposal_bounds(cls, ride):
        """(أرضيّة، سقف) ما يقترحه الزبون لهذا الطلب."""
        from pricing.services import PricingService

        area = ride.service_area
        quote = Decimal(ride.gross_fare)
        ratio = getattr(area, "customer_proposal_min_ratio", None) or cls.DEFAULT_PROPOSAL_MIN_RATIO
        floor = (quote * Decimal(ratio)).quantize(Decimal("0.01"))
        min_fare = PricingService._min_fare_absolute(area)
        if min_fare is not None:
            floor = max(floor, min_fare)
        cap = ride.fare_cap if ride.fare_cap is not None else (quote * cls.PROPOSAL_SANITY_CAP)
        return floor, Decimal(cap).quantize(Decimal("0.01"))

    @classmethod
    def _counter_cap(cls, ride):
        """أعلى عرض للسائق على سعر الزبون: نسبة المنطقة، ولا يتجاوز سقفها."""
        area = ride.service_area
        ratio = getattr(area, "customer_proposal_counter_ratio", None) or cls.DEFAULT_COUNTER_RATIO
        cap = (Decimal(ride.customer_proposed_fare) * Decimal(ratio)).quantize(Decimal("0.01"))
        if ride.fare_cap is not None:
            cap = min(cap, Decimal(ride.fare_cap))
        return max(cap, Decimal(ride.customer_proposed_fare))

    @classmethod
    @transaction.atomic
    def propose_fare(cls, ride_id, customer, fare):
        """
        الزبون يعرض سعره أو يرفعه. يُرفع ولا يُخفض: خفضُه بعد أن تحرّك
        سائقون على السعر الأعلى طُعمٌ بالاتّجاه المعاكس.
        """
        from locations.models import PricingPolicy
        from pricing.services import PricingPolicyError, PricingService

        ride = RideRequest.objects.select_for_update().get(id=ride_id, customer=customer)

        if ride.status not in OPEN_RIDE_STATUSES or ride.is_expired:
            raise MatchingError("الطلب لم يعد مفتوحًا للعروض.")
        if ride.auto_dispatch:
            raise MatchingError("«الأقرب» يرسل الطلب بسعر المنصّة — اقتراح السعر في «سوم» وحده.")

        area = ride.service_area
        if area is not None and not area.allows_policy(PricingPolicy.CUSTOMER_BIDDING):
            raise MatchingError("اقتراح السعر غير مفعّل في منطقتك.")

        floor, cap = cls.proposal_bounds(ride)
        current = ride.customer_proposed_fare
        if current is not None:
            floor = max(floor, Decimal(current) + Decimal("0.01"))

        try:
            fare = PricingService.validate_proposed_fare(
                proposed_fare=fare,
                quote={
                    "gross_fare": ride.gross_fare,
                    "fare_floor": floor,
                    "fare_cap": cap,
                    "pricing_policy": PricingPolicy.CUSTOMER_BIDDING,
                    "currency": ride.currency,
                },
                service_area=area,
                policy=PricingPolicy.CUSTOMER_BIDDING,
                proposer="customer",
            )
        except PricingPolicyError as exc:
            if current is not None and Decimal(fare) <= Decimal(current):
                raise MatchingError("سعرك معروضٌ الآن — تستطيع رفعه فقط.")
            raise MatchingError(str(exc))

        ride.customer_proposed_fare = fare
        ride.save(update_fields=["customer_proposed_fare", "updated_at"])

        from realtime.events import EventBus

        transaction.on_commit(
            lambda: EventBus.publish(
                group_name=f"ride_{ride.id}",
                event_type="ride.fare_proposed",
                entity_type="ride",
                entity_id=ride.id,
                payload={"customer_proposed_fare": str(fare)},
            )
        )
        return ride

    @classmethod
    @transaction.atomic
    def cancel_ride(cls, ride_id, customer, reason="", reason_code=""):

        ride = (
            RideRequest.objects
            .select_for_update()
            .get(id=ride_id, customer=customer)
        )

        if ride.status in (
            RideStatus.COMPLETED,
            RideStatus.CANCELLED,
            RideStatus.IN_PROGRESS,
        ):
            raise MatchingError(
                "Ride cannot be cancelled at this stage."
            )

        # 1) رحلة مشتركة مجدولة؟
        scheduled_membership = (
            ScheduledSharedTripMember.objects
            .filter(ride=ride, is_active=True)
            .first()
        )

        if scheduled_membership:
            from matching.services.scheduled_shared import (
                ScheduledSharedTripService,
            )
            ScheduledSharedTripService.cancel_ride_membership(ride_id=ride.id)

        # 2) رحلة مشتركة فورية؟
        instant_membership = (
            SharedRideGroupMember.objects
            .filter(ride=ride)
            .first()
        )

        if instant_membership:
            from matching.services.shared_matching import (
                SharedMatchingService,
            )
            SharedMatchingService.cancel_ride_membership(ride_id=ride.id)

        # 3) إلغاء أي عروض معلّقة على هذه الرحلة
        pending_offer_ids = list(
            RideOffer.objects.filter(
                ride=ride, status=OfferStatus.PENDING
            ).values_list("id", flat=True)
        )

        RideOffer.objects.filter(id__in=pending_offer_ids).update(
            status=OfferStatus.CANCELLED,
            updated_at=timezone.now(),
        )

        AuditService.record_bulk(
            AuditEntity.OFFER,
            pending_offer_ids,
            from_state=OfferStatus.PENDING,
            to_state=OfferStatus.CANCELLED,
            reason="ألغى الزبون الطلب",
            ride_id=ride.id,
        )

        # 4) إلغاء أي طلبات انضمام معلّقة كانت مرسلة لهذا العميل كمرشح
        pending_join_ids = list(
            SharedJoinRequest.objects.filter(
                candidate_ride=ride, status=SharedJoinStatus.PENDING
            ).values_list("id", flat=True)
        )

        SharedJoinRequest.objects.filter(id__in=pending_join_ids).update(
            status=SharedJoinStatus.WITHDRAWN,
            updated_at=timezone.now(),
        )

        AuditService.record_bulk(
            AuditEntity.SHARED_JOIN,
            pending_join_ids,
            from_state=SharedJoinStatus.PENDING,
            to_state=SharedJoinStatus.WITHDRAWN,
            reason="ألغى الزبون الطلب",
            ride_id=ride.id,
        )

        ride.status = RideStatus.CANCELLED
        ride.save(update_fields=["status", "updated_at"])
        
        from django.db import transaction as _transaction
        from realtime.events import EventBus

        ride_id = ride.id
        ride_status = ride.status

        # 5) إسقاط أي دعوات مباشرة معلّقة على هذه الرحلة
        from matching.services.invitation import InvitationService

        InvitationService.cancel_pending_for_ride(ride, reason="ride_cancelled")

        # السائق الذي كان مثبّتًا على هذه الرحلة (إن وُجد) يجب أن يعود متاحًا
        assigned_driver_id = (
            RideOffer.objects
            .filter(ride=ride, status=OfferStatus.ACCEPTED)
            .values_list("driver_id", flat=True)
            .first()
        )
        # 6) إلغاء الرحلة الفعلية إن كانت قد أُنشئت
        from trips.models import Trip
        from trips.services.trip import TripError, TripService

        if Trip.objects.filter(ride=ride).exists():
            try:
                TripService.cancel(
                    ride_id=ride.id, actor="customer",
                    reason=reason, reason_code=reason_code,
                )
            except TripError:
                # رحلة جارية لا تُلغى إلا كنزاع — والفحص في الأعلى منعها أصلًا
                pass

        def _publish_and_release():
            from presence.services import PresenceService

            EventBus.publish(
                group_name=f"ride_{ride_id}",
                event_type="ride.cancelled",
                entity_type="ride",
                entity_id=ride_id,
                payload={"ride_id": ride_id, "status": ride_status},
            )

            if assigned_driver_id:
                from trips.services.engagement import EngagementResolver

                # تحرير أعمى كان يُخرج سائقًا مشتركًا من حالته وهو
                # ما زال يقلّ راكبًا آخر. أعِد الحساب بدل الافتراض.
                EngagementResolver.sync(assigned_driver_id)

        _transaction.on_commit(_publish_and_release)

        return ride