"""
TripService — آلة حالات الرحلة الفعلية.

المبدأ الحاكم (§14 و§18 في الوثيقة): لا يوجد endpoint يغيّر status مباشرة.
كل انتقال يمرّ من هنا، يطبّق شروطه المسبقة، يحدّث RideRequest بالتوازي في
نفس المعاملة، ثم يطلق الحدث بعد الـcommit.

التسلسل إلزامي ولا يُتجاوَز:

    CREATED -> DRIVER_ARRIVING -> DRIVER_ARRIVED -> IN_PROGRESS -> COMPLETED

ولا يمكن "بدء" رحلة لم يصل سائقها، ولا "إنهاء" رحلة لم تبدأ.
"""
from math import radians, sin, cos, sqrt, atan2

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from rides.models import RideRequest, RideStatus
from trips.models import (
    CompletionSource,
    Trip,
    TripCompletionRecord,
    TripLocation,
    TripStatus,
)


class TripError(Exception):
    pass


# نصف قطر التحقق من الوصول. أضيق مما قد يبدو عمدًا: الهدف منع تسجيل وصول
# كاذب من مسافة بعيدة (وهو مدخل احتيال حقيقي لأنه يبدأ عدّاد عدم حضور
# الزبون)، لا معاقبة انحراف GPS الطبيعي.
#
# ولأنّ هندسة المدن تختلف — حيّ بأزقّة ضيّقة وإشارة ضعيفة يحتاج هامشًا أوسع
# من شارع مفتوح — صار الرقمان قابلين للضبط لكلّ منطقة، والثابت هنا افتراض
# لمن لم يضبط. اقرأهما عبر الدالّتين لا مباشرةً.
ARRIVAL_RADIUS_M = getattr(settings, "TRIP_ARRIVAL_RADIUS_M", 200)

# أوسع من نصف قطر الوصول: الوجهة قد تتغيّر قليلًا أثناء الرحلة بطلب الراكب،
# وهذا سلوك مشروع لا يستحق حجب الإنهاء.
DROPOFF_RADIUS_M = getattr(settings, "TRIP_DROPOFF_RADIUS_M", 300)


def _arrival_radius_m(ride):
    area = getattr(ride, "service_area", None)
    return area.effective_arrival_radius_m if area else ARRIVAL_RADIUS_M


def _dropoff_radius_m(ride):
    area = getattr(ride, "service_area", None)
    return area.effective_dropoff_radius_m if area else DROPOFF_RADIUS_M

LOCATION_MIN_INTERVAL_S = getattr(settings, "TRIP_LOCATION_MIN_INTERVAL_SECONDS", 5)
LOCATION_MIN_DISTANCE_M = getattr(settings, "TRIP_LOCATION_MIN_DISTANCE_M", 30)

LOCATION_MAX_AGE_S = getattr(settings, "MATCHING_LOCATION_MAX_AGE_SECONDS", 60)


def _haversine_m(lng1, lat1, lng2, lat2):
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lng1, lat2, lng2])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 6371000.0 * 2 * atan2(sqrt(h), sqrt(1 - h))


class TripService:

    # =================================================================
    # الإنشاء
    # =================================================================

    @classmethod
    def ensure_trip(cls, ride, offer=None):
        """
        إنشاء الرحلة من عرض مقبول — idempotent تمامًا.

        تُستدعى من ثلاثة أماكن: قبول عرض، قبول دعوة مباشرة، وأول استدعاء
        لـarrived كشبكة أمان. تعدّد المصادر مقصود: أي مسار تثبيت جديد
        مستقبلًا يحصل على رحلة صحيحة بلا تعديل هنا.
        """
        from matching.models import OfferStatus, RideOffer

        existing = Trip.objects.filter(ride=ride).first()
        # رحلةٌ ألغاها سائقها عادت إلى البحث: السائق الجديد يأخذ السجلّ نفسه
        # (الرحلة واحدة لكلّ طلب)، وسجلّ الإلغاء يحفظ من كان قبله.
        if (
            existing is not None
            and existing.status == TripStatus.CANCELLED
            and existing.cancelled_by == "driver"
            and ride.status not in (RideStatus.CANCELLED, RideStatus.EXPIRED)
        ):
            return cls._reassign(existing, ride, offer)
        if existing is not None:
            if existing.is_active:
                cls._sync_engagement(existing.driver_id)
            return existing

        if offer is None:
            offer = (
                RideOffer.objects
                .filter(ride=ride, status=OfferStatus.ACCEPTED)
                .select_related("driver")
                .order_by("-accepted_at")
                .first()
            )

        if offer is None:
            raise TripError("لا يوجد سائق مثبَّت على هذا الطلب.")

        driver = offer.driver
        vehicle = driver.vehicles.filter(active=True).order_by("-seats").first()

        trip, _created = Trip.objects.get_or_create(
            ride=ride,
            defaults={
                "driver": driver,
                "customer": ride.customer,
                "vehicle": vehicle,
                "offer": offer,
                "status": TripStatus.DRIVER_ARRIVING,
                "arriving_at": timezone.now(),
                "final_fare": offer.gross_fare,
                "currency": getattr(ride, "currency", None) or "SYP",
            },
        )

        # السائق مرتبط برحلة الآن. المزامنة هي التي تقرر BUSY أم SHARING،
        # وتحجز المقاعد، ولا نقرر نحن هنا شيئًا.
        cls._sync_engagement(driver.id)

        return trip

    @classmethod
    def _reassign(cls, trip, ride, offer):
        from matching.models import OfferStatus, RideOffer

        if offer is None:
            offer = (
                RideOffer.objects
                .filter(ride=ride, status=OfferStatus.ACCEPTED)
                .select_related("driver")
                .order_by("-accepted_at")
                .first()
            )
        if offer is None:
            raise TripError("لا يوجد سائق مثبَّت على هذا الطلب.")

        driver = offer.driver
        trip.driver = driver
        trip.vehicle = driver.vehicles.filter(active=True).order_by("-seats").first()
        trip.offer = offer
        trip.status = TripStatus.DRIVER_ARRIVING
        trip.arriving_at = timezone.now()
        trip.arrived_at = None
        trip.started_at = None
        trip.cancelled_at = None
        trip.cancelled_by = ""
        trip.cancel_reason = ""
        trip.final_fare = offer.gross_fare
        trip.save()
        cls._sync_engagement(driver.id)
        return trip

    # =================================================================
    # وصل السائق
    # =================================================================

    @classmethod
    @transaction.atomic
    def arrived(cls, ride_id, driver):
        ride, trip = cls._lock(ride_id, driver)

        if trip.status == TripStatus.DRIVER_ARRIVED:
            return trip  # idempotent: نقر مزدوج أو إعادة إرسال

        if trip.status not in (TripStatus.CREATED, TripStatus.DRIVER_ARRIVING):
            raise TripError(
                f"لا يمكن تسجيل الوصول والرحلة في حالة '{trip.status}'."
            )

        distance_m, fresh = cls._driver_distance_to(driver, ride.pickup)

        if not fresh:
            raise TripError(
                "موقعك غير محدَّث. تأكد من تشغيل GPS وأعد المحاولة."
            )

        if distance_m is None:
            raise TripError("تعذّر تحديد موقعك.")

        arrival_radius = _arrival_radius_m(ride)

        if distance_m > arrival_radius:
            raise TripError(
                f"أنت على بعد {int(distance_m)} متر من نقطة الالتقاء. "
                f"اقترب إلى أقل من {arrival_radius} مترًا لتسجيل الوصول."
            )

        now = timezone.now()

        trip.status = TripStatus.DRIVER_ARRIVED
        trip.arrived_at = now
        trip.pickup_verified = True
        trip.save(update_fields=["status", "arrived_at", "pickup_verified", "updated_at"])

        cls._sync_ride(ride, RideStatus.DRIVER_ARRIVED)
        cls._publish(trip, "driver.arrived", {"distance_m": int(distance_m)})

        return trip

    # =================================================================
    # بدء الرحلة
    # =================================================================

    @classmethod
    @transaction.atomic
    def start(cls, ride_id, driver):
        ride, trip = cls._lock(ride_id, driver)

        if trip.status == TripStatus.IN_PROGRESS:
            return trip

        if trip.status != TripStatus.DRIVER_ARRIVED:
            raise TripError(
                "لا يمكن بدء الرحلة قبل تسجيل الوصول إلى نقطة الالتقاء."
            )

        now = timezone.now()

        trip.status = TripStatus.IN_PROGRESS
        trip.started_at = now
        trip.save(update_fields=["status", "started_at", "updated_at"])

        cls._sync_ride(ride, RideStatus.IN_PROGRESS)
        cls._publish(trip, "trip.started", {"started_at": now.isoformat()})

        return trip

    # =================================================================
    # إنهاء الرحلة — أهم انتقال
    # =================================================================

    @classmethod
    @transaction.atomic
    def complete(cls, ride_id, driver, source=CompletionSource.DRIVER_APP):
        ride, trip = cls._lock(ride_id, driver)

        if trip.status == TripStatus.COMPLETED:
            return trip

        if trip.status != TripStatus.IN_PROGRESS:
            raise TripError("لا يمكن إنهاء رحلة لم تبدأ بعد.")

        now = timezone.now()

        # -------------------------------------------------------------
        # تحقق الوجهة: هنا لا نحجب، بل نُعلِّم للمراجعة.
        #
        # الفرق عن "وصلت" مقصود: منع وصول كاذب يحمي الزبون من عدّاد
        # عدم حضور ظالم، أما منع الإنهاء فيحبس السائق في رحلة انتهت فعلًا
        # لأن الراكب طلب النزول قبل الوجهة بقليل - وهذا سلوك مشروع.
        # -------------------------------------------------------------
        distance_to_dest, fresh = cls._driver_distance_to(driver, ride.destination)

        dropoff_verified = bool(
            fresh
            and distance_to_dest is not None
            and distance_to_dest <= _dropoff_radius_m(ride)
        )

        if not dropoff_verified:
            trip.needs_review = True
            trip.review_reason = (
                "موقع الإنهاء بعيد عن الوجهة"
                if distance_to_dest is not None
                else "تعذّر التحقق من موقع الإنهاء"
            )

        # -------------------------------------------------------------
        # القياس: المسار المسجَّل أولًا، وتقدير المسار المحسوب كبديل
        # -------------------------------------------------------------
        distance_m = cls._measured_distance_m(trip)

        if distance_m is None and ride.route_distance_km:
            distance_m = int(float(ride.route_distance_km) * 1000)

        duration_s = None
        if trip.started_at:
            duration_s = int((now - trip.started_at).total_seconds())

        trip.status = TripStatus.COMPLETED
        trip.completed_at = now
        trip.dropoff_verified = dropoff_verified
        trip.distance_m = distance_m
        trip.duration_s = duration_s
        trip.gps_points_count = trip.locations.count()
        trip.save()

        cls._sync_ride(ride, RideStatus.COMPLETED)
        cls._create_completion_record(trip, ride, source)
        cls._open_payment(trip)
        cls._evaluate_incentives(trip.driver_id)
        cls._publish_completed(trip, ride)

        return trip

    @staticmethod
    def _evaluate_incentives(driver_id):
        """بعد التثبيت: حافزٌ بُلغ هدفه يصل الآن. فشل الطابور لا يُسقط الإنهاء."""
        def _go():
            try:
                from growth.tasks import evaluate_driver_incentives

                evaluate_driver_incentives.delay(driver_id)
            except Exception:  # noqa: BLE001 — المسح اليوميّ يلتقطه
                pass

        transaction.on_commit(_go)

    @staticmethod
    def _open_payment(trip):
        """
        يفتح دفعة الرحلة. متكافئ، ولا يُسقط الإنهاء عند الفشل.

        القرار هنا مقصود: خللٌ في التسعير يجب ألّا يحبس سائقًا في رحلة
        انتهت فعلًا وراكبها نزل. الدفعة الناقصة يلتقطها
        `payments.tasks.backfill_missing_payments` خلال دقائق، أمّا
        السائق المحبوس فمشكلة فورية لا يحلّها أحد.
        """
        import logging

        logger = logging.getLogger(__name__)

        try:
            from payments.services.payment import PaymentService

            PaymentService.open_for_trip(trip)
        except Exception:
            logger.exception(
                "payments: تعذّر فتح دفعة للرحلة %s — ستُستدرَك لاحقًا.",
                trip.pk,
            )

    # =================================================================
    # الإلغاء
    # =================================================================

    @classmethod
    @transaction.atomic
    def cancel(cls, ride_id, actor="customer", reason="", driver=None, reason_code=""):
        ride, trip = cls._lock(ride_id, driver)

        if trip.status == TripStatus.CANCELLED:
            return trip

        if trip.status in (TripStatus.COMPLETED, TripStatus.DISPUTED):
            raise TripError("لا يمكن إلغاء رحلة منتهية.")

        if trip.status == TripStatus.IN_PROGRESS:
            raise TripError(
                "الرحلة جارية — الإلغاء بعد البدء يحتاج فتح نزاع لا إلغاءً عاديًا."
            )

        now = timezone.now()

        from trips.models import CancellationKind, DriverCancelReason
        from trips.services.cancellation import CancellationPolicy
        from trips.services.compensation import WastedTripCompensation

        no_show = actor == "driver" and reason_code == DriverCancelReason.CUSTOMER_NO_SHOW
        if no_show:
            error = CancellationPolicy.no_show_error(trip, now)
            if error:
                raise TripError(error)
            kind, strikes = CancellationKind.NO_SHOW, 2
        elif actor == "driver":
            kind, strikes = CancellationKind.DRIVER, 1
        elif actor == "customer":
            kind, strikes = CancellationPolicy.classify_customer(trip, now)
        else:
            kind, strikes = None, 0

        trip.status = TripStatus.CANCELLED
        trip.cancelled_at = now
        trip.cancelled_by = actor
        trip.cancel_reason = (reason or "")[:255]
        trip.save(
            update_fields=[
                "status", "cancelled_at", "cancelled_by",
                "cancel_reason", "updated_at",
            ]
        )

        compensation = None
        if kind is not None:
            record = CancellationPolicy.record(trip, actor, kind, strikes, reason, reason_code)
            compensation = WastedTripCompensation.apply(record)

        if actor == "driver" and not no_show:
            cls._requeue_after_driver_cancel(ride, trip, now)
            cls._sync_engagement(trip.driver_id)
            cls._publish(
                trip,
                "ride.cancelled_by_driver",
                {"cancelled_by": actor, "reason": reason, "requeued": True},
            )
            return trip

        cls._sync_ride(ride, RideStatus.CANCELLED)
        cls._sync_engagement(trip.driver_id)
        cls._publish(
            trip,
            "ride.cancelled",
            {
                "cancelled_by": actor, "reason": reason, "kind": kind or "",
                # مبلغٌ عُوِّض به السائق عن المشوار الفاضي — "0.00" إن لم يُعوَّض.
                "driver_compensation": str(compensation or "0.00"),
            },
        )

        return trip

    @classmethod
    def _requeue_after_driver_cancel(cls, ride, trip, now):
        """
        الزبون لا يُترك بلا سيارة لأنّ السائق غيّر رأيه: الطلب يعود إلى
        البحث بمهلة كاملة جديدة، وعرض السائق الملغي يسقط فلا يُحسب مشغولًا.
        """
        from datetime import timedelta

        from django.conf import settings as dj_settings

        from matching.models import OfferStatus, RideOffer

        RideOffer.objects.filter(
            ride=ride, driver_id=trip.driver_id, status=OfferStatus.ACCEPTED,
        ).update(status=OfferStatus.CANCELLED, updated_at=now)

        area = ride.service_area
        window = (
            area.effective_ride_search_window_minutes
            if area is not None
            else getattr(dj_settings, "RIDE_SEARCH_WINDOW_MINUTES", 10)
        )
        ride.status = RideStatus.SEARCHING
        if ride.scheduled_at is None:
            ride.expires_at = now + timedelta(minutes=window)
        ride.save(update_fields=["status", "expires_at", "updated_at"])

    # =================================================================
    # تسجيل نقاط المسار
    # =================================================================

    @classmethod
    def record_location(cls, trip, lng, lat, speed=None, heading=None,
                        accuracy=None, source="app", at=None):
        """
        يُستدعى من DriverRoomConsumer عند كل نبضة GPS. يُسجّل فقط أثناء
        IN_PROGRESS، وبخنق مزدوج: فاصل زمني أدنى ومسافة دنيا.

        بلا الخنق، سائق واقف في زحمة عشر دقائق يكتب 120 صفًا لنقطة واحدة.
        """
        if trip is None or trip.status != TripStatus.IN_PROGRESS:
            return None

        at = at or timezone.now()

        last = trip.locations.order_by("-timestamp").first()

        if last is not None:
            if (at - last.timestamp).total_seconds() < LOCATION_MIN_INTERVAL_S:
                return None

            moved = _haversine_m(lng, lat, last.location.x, last.location.y)
            if moved < LOCATION_MIN_DISTANCE_M:
                return None

        from django.contrib.gis.geos import Point

        return TripLocation.objects.create(
            trip=trip,
            location=Point(lng, lat, srid=4326),
            speed=speed,
            heading=heading,
            accuracy=accuracy,
            source=source or "",
            timestamp=at,
        )

    @classmethod
    def get_active_trip(cls, driver_id):
        return cls._active_qs(driver_id).order_by("-created_at").first()

    @classmethod
    def get_active_trips(cls, driver_id):
        """
        سائق على رحلة مشتركة له أكثر من رحلة نشطة في وقت واحد - رحلة لكل
        راكب. النسخة المفردة أعلاه كانت تُرجّع الأحدث فقط، ما يعني أن مسار
        الراكب الأول يتوقف عن التسجيل لحظة صعود الثاني: سجلّ ناقص بالضبط
        في الرحلات التي تكثر فيها النزاعات.
        """
        return list(cls._active_qs(driver_id).order_by("created_at"))

    @classmethod
    def record_location_for_driver(cls, driver_id, lng, lat, **kwargs):
        """نقطة دخول واحدة من DriverRoomConsumer: تُسجَّل على كل رحلة جارية."""
        recorded = []

        for trip in cls.get_active_trips(driver_id):
            point = cls.record_location(trip, lng, lat, **kwargs)

            if point is not None:
                recorded.append(point)

        return recorded

    @staticmethod
    def _active_qs(driver_id):
        return Trip.objects.filter(
            driver_id=driver_id,
            status__in=[
                TripStatus.CREATED,
                TripStatus.DRIVER_ARRIVING,
                TripStatus.DRIVER_ARRIVED,
                TripStatus.IN_PROGRESS,
            ],
        )

    # =================================================================
    # HELPERS
    # =================================================================

    @classmethod
    def _lock(cls, ride_id, driver=None):
        """
        ترتيب القفل: RideRequest ثم Trip — نفس ترتيب باقي المشروع، فلا
        يمكن أن يتقاطع مع select_offer أو accept_invitation في ترتيب معاكس.
        """
        # of=("self",) مقصود: بلا هذا القيد يترجم جانغو select_related مع
        # select_for_update إلى FOR UPDATE على الجدولين، فيقفل صفّ منطقة
        # الخدمة — أي أنّ رحلتين في المدينة نفسها تتسلسلان بلا سبب. نريد
        # نصفَي القطر من المنطقة، لا قفلها.
        ride = (
            RideRequest.objects
            .select_for_update(of=("self",))
            .select_related("service_area")
            .get(id=ride_id)
        )

        trip = (
            Trip.objects
            .select_for_update()
            .select_related("driver", "ride")
            .filter(ride=ride)
            .first()
        )

        if trip is None:
            trip = cls.ensure_trip(ride)
            trip = Trip.objects.select_for_update().get(id=trip.id)

        if driver is not None and trip.driver_id != driver.id:
            raise TripError("هذه الرحلة ليست لك.")

        return ride, trip

    @staticmethod
    def _sync_ride(ride, status):
        ride.status = status
        ride.save(update_fields=["status", "updated_at"])

    @staticmethod
    def _driver_distance_to(driver, point):
        """يرجّع (المسافة بالأمتار، هل الموقع حديث)."""
        if driver is None or point is None or driver.current_location is None:
            return None, False

        fresh = True
        if driver.last_location_at is not None:
            age = (timezone.now() - driver.last_location_at).total_seconds()
            fresh = age <= LOCATION_MAX_AGE_S
        else:
            fresh = False

        distance = _haversine_m(
            driver.current_location.x, driver.current_location.y,
            point.x, point.y,
        )

        return distance, fresh

    @staticmethod
    def _measured_distance_m(trip):
        """مجموع المسافات بين نقاط المسار المسجَّلة."""
        points = list(trip.locations.order_by("timestamp").values_list("location", flat=True))

        if len(points) < 2:
            return None

        total = 0.0
        for a, b in zip(points, points[1:]):
            total += _haversine_m(a.x, a.y, b.x, b.y)

        return int(round(total))

    @classmethod
    def _create_completion_record(cls, trip, ride, source):
        last = trip.locations.order_by("-timestamp").first()

        TripCompletionRecord.objects.get_or_create(
            trip=trip,
            defaults={
                "completed_at": trip.completed_at,
                "start_time": trip.started_at,
                "end_time": trip.completed_at,
                "pickup_point": ride.pickup,
                "dropoff_point": last.location if last else ride.destination,
                "distance_m": trip.distance_m or 0,
                "duration_s": trip.duration_s or 0,
                "final_fare": trip.final_fare,
                "currency": trip.currency,
                "gps_start_verified": bool(trip.started_at),
                "gps_arrival_verified": trip.pickup_verified,
                "gps_end_verified": trip.dropoff_verified,
                "gps_points_count": trip.gps_points_count,
                "completion_source": source,
            },
        )

    # -----------------------------------------------------------------
    # ارتباط السائق — نداء واحد لكل انتقال
    # -----------------------------------------------------------------

    @staticmethod
    def _sync_engagement(driver_id):
        """
        في المرحلة 9أ كان هنا نداءان متقابلان: _mark_busy و_release_driver.
        وهذا يكفي حين تكون الإجابة ثنائية. مع المشاركة لم تعد كذلك: إنهاء
        رحلة لسائق يحمل راكبًا آخر ليس "تحريرًا"، وقبول رحلة مشتركة ليس
        "حجزًا". الصحيح في الحالتين فعل واحد: أعِد حساب الحقيقة من القاعدة.

        فائدة جانبية غير صغيرة: أي انتقال ضائع (إلغاء إداري، سقوط عامل
        Celery، تدخّل يدوي بـupdate) يصحّح نفسه عند أول مزامنة تالية، بدل
        أن يبقى عدّاد الركّاب منحرفًا إلى الأبد.
        """
        from trips.services.engagement import EngagementResolver

        EngagementResolver.sync_on_commit(driver_id)

    # -----------------------------------------------------------------
    # الأحداث
    # -----------------------------------------------------------------

    @staticmethod
    def _payload(trip, extra=None):
        payload = {
            "trip_id": trip.id,
            "ride_id": trip.ride_id,
            "driver_id": trip.driver_id,
            "status": trip.status,
            "final_fare": str(trip.final_fare),
            "currency": trip.currency,
        }
        if extra:
            payload.update(extra)
        return payload

    @classmethod
    def _publish(cls, trip, event_type, extra=None):
        from realtime.events import EventBus

        payload = cls._payload(trip, extra)
        ride_id = trip.ride_id

        transaction.on_commit(
            lambda: EventBus.publish(
                group_name=f"ride_{ride_id}",
                event_type=event_type,
                entity_type="ride",
                entity_id=ride_id,
                payload=payload,
            )
        )

    @classmethod
    def _publish_completed(cls, trip, ride):
        from realtime.events import EventBus

        payload = cls._payload(trip, {
            "distance_m": trip.distance_m,
            "duration_s": trip.duration_s,
            "gps_points_count": trip.gps_points_count,
            "needs_review": trip.needs_review,
            "review_reason": trip.review_reason,
            "completed_at": trip.completed_at.isoformat(),
        })

        ride_id = trip.ride_id
        driver_id = trip.driver_id

        def _go():
            from trips.services.engagement import EngagementResolver
            from config.observability.safety import run_all

            run_all(
                lambda: EventBus.publish(
                    group_name=f"ride_{ride_id}",
                    event_type="trip.completed",
                    entity_type="ride",
                    entity_id=ride_id,
                    payload=payload,
                ),
                lambda: EventBus.publish(
                    group_name=f"driver_{driver_id}",
                    event_type="trip.completed",
                    entity_type="driver",
                    entity_id=driver_id,
                    payload=payload,
                ),
                lambda: EngagementResolver.sync(driver_id),
                event="trip.completed",
            )

        transaction.on_commit(_go)
