"""
EngagementResolver — الجواب الوحيد على سؤال: بماذا يرتبط هذا السائق الآن؟

قبل هذا الملف كان الجواب موزّعًا: Redis يحمل busy، والمطابقة تحسب
get_busy_driver_ids من العروض المقبولة، وgo_online تفترض صفرًا. ثلاثة مصادر
لسؤال واحد تعني حتمًا ثلاثة أجوبة مختلفة يومًا ما.

هنا مصدر واحد يقرأ من الرحلات النشطة (وهي الحقيقة الدائمة في PostgreSQL)
ويرجّع قاموسًا مسطّحًا تكتبه طبقة الحضور كما هو:

    {} = حرّ
    {"busy": True}  = مرتبط ولا مقعد لأحد
    {"sharing": True, "trip_mode": "shared", "dest_cell": "sy2k", "free_seats": 2}
"""
import logging
from math import radians, sin, cos, sqrt, atan2

from django.db import transaction

from trips.models import Trip, TripStatus

logger = logging.getLogger("trips.engagement")


ACTIVE_TRIP_STATUSES = [
    TripStatus.CREATED,
    TripStatus.DRIVER_ARRIVING,
    TripStatus.DRIVER_ARRIVED,
    TripStatus.IN_PROGRESS,
]


def _haversine_km(lng1, lat1, lng2, lat2):
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lng1, lat2, lng2])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 6371.0 * 2 * atan2(sqrt(h), sqrt(1 - h))


class EngagementResolver:

    @classmethod
    def active_trips(cls, driver_id):
        return list(
            Trip.objects
            .filter(driver_id=driver_id, status__in=ACTIVE_TRIP_STATUSES)
            .select_related("ride", "ride__service_area", "driver")
            .order_by("created_at")
        )

    @classmethod
    def resolve(cls, driver_id):
        """
        يُستدعى من go_online (عند كل إعادة اتصال) ومن TripService (عند كل
        تغيّر). لذلك يجب أن يبقى استعلامًا واحدًا مفهرسًا لا أكثر.
        """
        trips = cls.active_trips(driver_id)

        if not trips:
            return {}

        driver = trips[0].driver
        occupancy = cls.recompute_occupancy(driver_id, trips=trips)
        free_seats = max(int(driver.available_seats or 0) - occupancy, 0)

        shared_trips = [t for t in trips if cls._is_shared(t)]

        # رحلة فردية واحدة على الأقل تعني أن السيارة محجوزة لصاحبها، مهما
        # بقي فيها من مقاعد. خلط راكب فردي مع مشترك هو نقض للعقد الذي دفع
        # الراكب الفردي ثمنه.
        if len(shared_trips) != len(trips) or free_seats <= 0:
            return {"busy": True}

        destination_cell = cls._route_end_cell(shared_trips, driver)

        if destination_cell is None:
            # بلا وجهة خشنة لا فلترة ممكنة، وعرضه بلا فلترة يعني إظهاره
            # لركّاب في الاتجاه المعاكس. الأسلم أن يبقى مشغولًا.
            return {"busy": True}

        return {
            "sharing": True,
            "trip_mode": cls._mode_of(shared_trips[0]),
            "dest_cell": destination_cell,
            "free_seats": free_seats,
        }

    # -----------------------------------------------------------------
    # المقاعد المحجوزة
    # -----------------------------------------------------------------

    @classmethod
    def recompute_occupancy(cls, driver_id, trips=None):
        """
        current_occupancy لم يكن يُزاد في أي مكان في المشروع - كان صفرًا
        دائمًا. وهذا لا يُلاحَظ في الرحلات الفردية (السيارة محجوزة كلها على
        أي حال) لكنه يجعل المشاركة مستحيلة: بلا عدّاد ركّاب لا معنى لـ
        "مقعد فارغ".

        نُعيد حسابه من الرحلات النشطة بدل زيادته وإنقاصه. الفرق ليس أسلوبيًا:
        الزيادة والإنقاص يتراكم خطؤهما إلى الأبد عند أول انتقال ضائع (إلغاء
        إداري بـupdate مثلًا)، أما إعادة الحساب فتصحّح نفسها في كل مزامنة.
        """
        from users.models import DriverProfile

        trips = trips if trips is not None else cls.active_trips(driver_id)

        occupancy = sum(
            max(int(getattr(trip.ride, "passenger_count", 1) or 1), 1)
            for trip in trips
        )

        with transaction.atomic():
            locked = (
                DriverProfile.objects
                .select_for_update()
                .filter(id=driver_id)
                .first()
            )

            if locked is not None and locked.current_occupancy != occupancy:
                locked.current_occupancy = occupancy
                locked.save(update_fields=["current_occupancy", "updated_at"])

        return occupancy

    # -----------------------------------------------------------------
    # المزامنة إلى طبقة الحضور
    # -----------------------------------------------------------------

    @classmethod
    def sync(cls, driver_id):
        """كتابة فورية. تُستدعى مباشرة فقط خارج المعاملات."""
        from presence.services import PresenceService

        engagement = cls.resolve(driver_id)

        if not engagement:
            # لا رحلة نشطة: صفّر العدّاد أيضًا، وإلا بقي راكب وهمي يشغل
            # مقعدًا في سيارة فارغة.
            cls.recompute_occupancy(driver_id, trips=[])

        try:
            PresenceService.set_engagement(driver_id, engagement)

            driver = cls._driver(driver_id)
            if driver is not None:
                PresenceService.sync_occupancy(
                    driver_id, driver.current_occupancy, driver.available_seats
                )

            # الخريطة الحيّة تُعلَم فورًا، لا عند نبضة GPS التالية.
            # هنا تحديدًا كان الثقب الذي تركته المرحلة 9أ مفتوحًا:
            # الحالة تتغيّر في Redis ولا شيء يخبر مَن يشاهد الآن.
            from realtime.marketplace import MarketplaceService

            MarketplaceService.handle_engagement_change(driver_id)
        except Exception:
            # فشل Redis لا يُبطل عملية على القاعدة. PostgreSQL هو المصدر
            # الدائم، وأول go_online أو نبضة تعيد بناء الحالة من هنا.
            #
            # لكن الابتلاع الصامت كان خطأً: أربع عمليات تحت except واحد،
            # وأيّها فشل يعني حالةً لا تصل الخريطة أبدًا بلا سطر واحد
            # يدلّ عليه. الآن يُسجَّل بالكامل — الفشل لا يُبطل شيئًا لكنه
            # لم يعد غير مرئي.
            logger.exception(
                "engagement sync failed for driver %s (engagement=%s)",
                driver_id, engagement,
            )

        return engagement

    @classmethod
    def sync_on_commit(cls, driver_id):
        """
        النداء الافتراضي من داخل TripService: لا نكتب إلى Redis قبل أن
        تثبت المعاملة، وإلا أعلنّا سائقًا مشغولًا برحلة قد تُلغى بعد سطر.
        """
        transaction.on_commit(lambda: cls.sync(driver_id))

    # -----------------------------------------------------------------
    # HELPERS
    # -----------------------------------------------------------------

    @staticmethod
    def _driver(driver_id):
        from users.models import DriverProfile

        return DriverProfile.objects.filter(id=driver_id).first()

    @staticmethod
    def _mode_of(trip):
        return getattr(trip.ride, "mode", "") or ""

    @classmethod
    def _is_shared(cls, trip):
        from presence.constants import SHARED_MODE

        return cls._mode_of(trip) == SHARED_MODE

    @classmethod
    def _route_end_cell(cls, shared_trips, driver):
        """
        السيارة قد تحمل أكثر من راكب بوجهات مختلفة. الوجهة التي تهمّ مرشّح
        الانضمام هي آخر نقطة نزول - أي الأبعد عن موقع السائق الآن - لأنها
        تحدّد امتداد المسار المتبقي لا أقربه.
        """
        from locations.services import LocationService

        origin = getattr(driver, "current_location", None)

        best_trip = None
        best_distance = -1.0

        for trip in shared_trips:
            destination = getattr(trip.ride, "destination", None)

            if destination is None:
                continue

            if origin is None:
                best_trip = trip
                break

            distance = _haversine_km(
                origin.x, origin.y, destination.x, destination.y
            )

            if distance > best_distance:
                best_distance = distance
                best_trip = trip

        if best_trip is None:
            return None

        destination = best_trip.ride.destination

        try:
            return LocationService.coarse_destination_cell(
                destination.x,
                destination.y,
                area=getattr(best_trip.ride, "service_area", None),
            )
        except Exception:
            return None
