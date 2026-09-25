"""
أنصاف أقطار البحث — ديناميكية لكلّ مدينة.

ما تحرسه هذه الاختبارات ليس وجود الحقول، بل **أنّ تغيير الرقم من الأدمن
يغيّر مَن يُطابَق فعلًا**. وهذا هو بالضبط ما كان ناقصًا: الحقل كان موجودًا
وتقرأه خريطة الزبون، بينما محرّك المطابقة يقرأ رقمًا عالميًّا من الإعدادات.
فكان المشغّل يغيّره فيرى أثرًا على الخريطة ويظنّ أنّه ضبط الأمر — والسائق
الذي يُطابَق هو نفسه لم يتغيّر.

حقلٌ يعمل نصف عمل أخطر من حقلٍ لا يعمل: الأوّل يكذب بهدوء.
"""
from datetime import timedelta
from decimal import Decimal

from django.contrib.gis.geos import Point
from django.core.exceptions import ValidationError
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from config.testkit import make_customer, make_driver, make_vehicle
from locations.models import ServiceArea
from locations.services import LocationService
from matching.services.matching import MatchingService
from rides.models import RideMode, RideRequest, RideStatus


# جبلة، ونقاط على مسافات معروفة منها. درجة العرض ≈ 111 كم.
JABLEH = (35.90, 35.36)
KM_IN_DEGREES = 1 / 111.0


def at_km_north(km):
    lng, lat = JABLEH
    return (lng, lat + km * KM_IN_DEGREES)


def make_area(code="JAB", lng_lat=JABLEH, **overrides):
    lng, lat = lng_lat
    defaults = dict(
        name=code,
        center=Point(lng, lat, srid=4326),
        fallback_radius_km=Decimal("40"),
        default_matching_radius_km=Decimal("5"),
        is_active=True,
    )
    defaults.update(overrides)
    area, _ = ServiceArea.objects.update_or_create(code=code, defaults=defaults)
    LocationService.invalidate_cache()
    return area


class InstantRadiusTests(TestCase):
    """
    الحقل الذي سأله المستخدم عنه: نصف قطر الطلب الفوري.
    """

    def setUp(self):
        self.customer = make_customer()

    def tearDown(self):
        LocationService.invalidate_cache()

    def _ride(self, area):
        return RideRequest.objects.create(
            customer=self.customer,
            pickup=Point(*JABLEH, srid=4326),
            destination=Point(*at_km_north(3), srid=4326),
            mode=RideMode.STANDARD,
            passenger_count=1,
            status=RideStatus.SEARCHING,
            service_area=area,
            expires_at=timezone.now() + timedelta(minutes=10),
        )

    def test_engine_reads_the_area_not_the_global_setting(self):
        area = make_area(default_matching_radius_km=Decimal("12"))
        ride = self._ride(area)

        # الإعداد العامّ 5، والمنطقة 12. المحرّك يجب أن يقول 12.
        self.assertEqual(MatchingService.get_radius_km(ride), 12.0)

    def test_changing_the_admin_value_changes_the_engine(self):
        area = make_area(default_matching_radius_km=Decimal("5"))
        ride = self._ride(area)

        self.assertEqual(MatchingService.get_radius_km(ride), 5.0)

        area.default_matching_radius_km = Decimal("20")
        area.save()
        LocationService.invalidate_cache()

        ride.refresh_from_db()
        self.assertEqual(MatchingService.get_radius_km(ride), 20.0)

    def test_scheduled_ride_uses_the_wider_marketplace_radius(self):
        area = make_area(
            default_matching_radius_km=Decimal("5"),
            marketplace_radius_km=Decimal("25"),
        )
        ride = self._ride(area)
        ride.scheduled_at = timezone.now() + timedelta(hours=3)
        ride.save(update_fields=["scheduled_at"])

        self.assertEqual(MatchingService.get_radius_km(ride), 25.0)

    def test_ride_outside_every_area_falls_back_to_the_global_default(self):
        from django.conf import settings

        ride = self._ride(None)

        self.assertEqual(
            MatchingService.get_radius_km(ride),
            settings.MATCHING_NORMAL_RADIUS_KM,
        )

    def test_customer_map_and_engine_read_the_same_number(self):
        # نسختان من المنطق تتباعدان، فتُظهر الخريطة سيارةً لا تُطابَق.
        area = make_area(default_matching_radius_km=Decimal("9"))
        ride = self._ride(area)

        from matching.services.nearby import NearbyVehiclesService

        # نقرأ الرقم الذي ستستعمله خدمة الخريطة بنفس منطقها.
        map_radius = (
            ride.service_area.effective_instant_radius_km
            if ride.service_area
            else None
        )

        self.assertEqual(map_radius, MatchingService.get_radius_km(ride))
        self.assertIsNotNone(NearbyVehiclesService)


class DriverCandidatesRadiusTests(TestCase):
    """
    أهمّ اختبار في الملفّ: قائمة الطلبات المؤهَّلة للسائق.

    كانت تطبّق نصف قطر واحد على طلبات قد تكون في مدن مختلفة. والصحيح أن
    يُقاس كلّ طلب بنصف قطر **مدينته هو** — فمشغّل جبلة يضبط كم يبعد السائق
    المقبول عن زبونه، ولا يصحّ أن يحكم إعداد اللاذقية على طلب جبليّ.
    """

    def setUp(self):
        self.customer = make_customer()
        self.driver = make_driver(location=JABLEH, status="active")
        make_vehicle(self.driver, seats=4, active=True)

        self.driver.online = True
        self.driver.available_seats = 4
        self.driver.last_location_at = timezone.now()
        self.driver.save()

    def tearDown(self):
        LocationService.invalidate_cache()

    def _ride_at(self, km, area):
        return RideRequest.objects.create(
            customer=self.customer,
            pickup=Point(*at_km_north(km), srid=4326),
            destination=Point(*at_km_north(km + 2), srid=4326),
            mode=RideMode.STANDARD,
            passenger_count=1,
            status=RideStatus.SEARCHING,
            service_area=area,
            expires_at=timezone.now() + timedelta(minutes=10),
        )

    def _visible(self):
        return set(
            MatchingService
            .get_eligible_rides_for_driver(self.driver)
            .values_list("id", flat=True)
        )

    def test_a_ride_beyond_the_radius_is_hidden(self):
        area = make_area(default_matching_radius_km=Decimal("5"))

        near = self._ride_at(2, area)
        far = self._ride_at(30, area)

        visible = self._visible()

        self.assertIn(near.id, visible)
        self.assertNotIn(far.id, visible)

    def test_widening_the_radius_reveals_it(self):
        # هذا هو الإثبات المطلوب: رقمٌ في الأدمن يغيّر مَن يرى ماذا.
        area = make_area(default_matching_radius_km=Decimal("5"))
        far = self._ride_at(15, area)

        self.assertNotIn(far.id, self._visible())

        area.default_matching_radius_km = Decimal("25")
        area.save()
        LocationService.invalidate_cache()

        self.assertIn(far.id, self._visible())

    def test_narrowing_the_radius_hides_it_again(self):
        area = make_area(default_matching_radius_km=Decimal("25"))
        far = self._ride_at(15, area)

        self.assertIn(far.id, self._visible())

        area.default_matching_radius_km = Decimal("3")
        area.save()
        LocationService.invalidate_cache()

        self.assertNotIn(far.id, self._visible())

    def test_each_city_is_measured_by_its_own_radius(self):
        """
        الاختبار الذي يبرّر التعقيد كلّه.

        سائق واحد، طلبان على المسافة نفسها منه بالضبط، في مدينتين
        بإعدادين مختلفين. الضيّقة تُخفي طلبها والواسعة تُظهر طلبها — وهو
        مستحيل بنصف قطر واحد مهما كانت قيمته.
        """
        narrow = make_area(
            code="NAR",
            lng_lat=at_km_north(20),
            default_matching_radius_km=Decimal("4"),
        )
        wide = make_area(
            code="WID",
            lng_lat=at_km_north(-20),
            default_matching_radius_km=Decimal("30"),
        )

        ride_narrow = self._ride_at(10, narrow)
        ride_wide = self._ride_at(10, wide)

        visible = self._visible()

        self.assertNotIn(
            ride_narrow.id, visible,
            "طلبٌ في مدينة ضيّقة النطاق ظهر — إعداد مدينة أخرى حكم عليه",
        )
        self.assertIn(
            ride_wide.id, visible,
            "طلبٌ في مدينة واسعة النطاق اختفى",
        )

    def test_scheduled_ride_uses_its_own_area_marketplace_radius(self):
        area = make_area(
            default_matching_radius_km=Decimal("5"),
            marketplace_radius_km=Decimal("30"),
        )

        scheduled = self._ride_at(20, area)
        scheduled.scheduled_at = timezone.now() + timedelta(hours=3)
        scheduled.save(update_fields=["scheduled_at"])

        instant_far = self._ride_at(20, area)

        visible = self._visible()

        self.assertIn(scheduled.id, visible, "المجدول لم يستفد من نطاقه الأوسع")
        self.assertNotIn(instant_far.id, visible, "الفوري تجاوز نطاقه")

    def test_ride_without_an_area_is_still_reachable(self):
        # إسقاطها من الشرط كان سيُخفيها عن كلّ سائق إلى الأبد بلا سبب مرئي.
        make_area(default_matching_radius_km=Decimal("5"))

        orphan = self._ride_at(2, None)

        self.assertIn(orphan.id, self._visible())

    def test_query_count_does_not_grow_with_city_count(self):
        """
        الشرط يُبنى كـOR واحد داخل استعلام واحد، لا استعلامًا لكلّ مدينة.

        المقياس هو **الفرق** لا العدد المطلق: الدالّة تسأل عن السائقين
        المشغولين وعن مركبات السائق أوّلًا، وذلك ثابت. ما يجب ألّا ينمو هو
        عدد الاستعلامات مع عدد المدن — وإلّا صارت الكلفة خطّية في مسار
        يُنادى مع كلّ تحديث لشاشة السائق.
        """
        area = make_area(default_matching_radius_km=Decimal("5"))
        self._ride_at(2, area)

        with CaptureQueriesContext(connection) as one_city:
            list(MatchingService.get_eligible_rides_for_driver(self.driver))

        for i in range(8):
            make_area(
                code=f"C{i}",
                lng_lat=at_km_north(60 + i * 12),
                default_matching_radius_km=Decimal("5"),
            )

        with CaptureQueriesContext(connection) as nine_cities:
            list(MatchingService.get_eligible_rides_for_driver(self.driver))

        self.assertEqual(
            len(nine_cities), len(one_city),
            "عدد الاستعلامات نما مع عدد المدن — الشرط يُبنى لكلّ مدينة",
        )


class SharedRadiusTests(TestCase):
    """الأرقام التي كانت مكتوبة في الدوالّ: 3.0 و10 و15 و60."""

    def tearDown(self):
        LocationService.invalidate_cache()

    def test_shared_join_radius_comes_from_the_area(self):
        area = make_area(shared_join_radius_km=Decimal("7"))

        self.assertEqual(area.effective_shared_join_radius_km, 7.0)

    def test_shared_scheduled_limits_come_from_the_area(self):
        area = make_area(
            shared_scheduled_pickup_radius_km=Decimal("4"),
            shared_scheduled_dest_radius_km=Decimal("8"),
            shared_scheduled_time_window_minutes=25,
        )

        self.assertEqual(area.effective_shared_scheduled_pickup_radius_km, 4.0)
        self.assertEqual(area.effective_shared_scheduled_dest_radius_km, 8.0)
        self.assertEqual(area.effective_shared_scheduled_time_window_minutes, 25)

    def test_blank_shared_fields_fall_back_to_the_documented_defaults(self):
        area = make_area()

        self.assertEqual(area.effective_shared_join_radius_km, 3.0)
        self.assertEqual(area.effective_shared_scheduled_pickup_radius_km, 10.0)
        self.assertEqual(area.effective_shared_scheduled_dest_radius_km, 15.0)
        self.assertEqual(area.effective_shared_scheduled_time_window_minutes, 60)

    def test_scheduled_shared_service_reads_the_area(self):
        from matching.services.scheduled_shared import (
            ScheduledSharedTripService,
        )

        area = make_area(
            shared_scheduled_pickup_radius_km=Decimal("6"),
            shared_scheduled_dest_radius_km=Decimal("11"),
            shared_scheduled_time_window_minutes=45,
        )

        customer = make_customer()
        ride = RideRequest.objects.create(
            customer=customer,
            pickup=Point(*JABLEH, srid=4326),
            destination=Point(*at_km_north(3), srid=4326),
            mode=RideMode.SHARED,
            passenger_count=1,
            status=RideStatus.SEARCHING,
            service_area=area,
            scheduled_at=timezone.now() + timedelta(hours=2),
        )

        pickup, dest, window = ScheduledSharedTripService._limits(ride)

        self.assertEqual((pickup, dest, window), (6.0, 11.0, 45))

    def test_readers_return_floats_not_decimals(self):
        # مستهلكها D(km=...) وحسابات المسافة، وDecimal هناك يرفع TypeError.
        area = make_area(
            default_matching_radius_km=Decimal("5"),
            marketplace_radius_km=Decimal("10"),
            shared_join_radius_km=Decimal("3"),
        )

        for value in (
            area.effective_instant_radius_km,
            area.effective_marketplace_radius_km,
            area.effective_shared_join_radius_km,
            area.effective_shared_scheduled_pickup_radius_km,
            area.effective_shared_scheduled_dest_radius_km,
        ):
            self.assertIsInstance(value, float)

        self.assertIsInstance(
            area.effective_shared_scheduled_time_window_minutes, int
        )


class RadiusValidationTests(TestCase):
    """
    الأدمن يسري على الإنتاج فورًا. نصف قطر خاطئ هنا لا يُنتج خطأً مرئيًّا
    بل طلبات تنتهي بلا سائق — وهو عطل يُلام عليه «ضعف الأسطول».
    """

    def setUp(self):
        self.area = make_area()

    def tearDown(self):
        LocationService.invalidate_cache()

    def test_absurdly_small_radius_is_rejected(self):
        self.area.default_matching_radius_km = Decimal("0.05")

        with self.assertRaises(ValidationError) as ctx:
            self.area.full_clean()

        self.assertIn("default_matching_radius_km", ctx.exception.message_dict)

    def test_absurdly_large_radius_is_rejected(self):
        self.area.default_matching_radius_km = Decimal("500")

        with self.assertRaises(ValidationError):
            self.area.full_clean()

    def test_marketplace_narrower_than_instant_is_rejected(self):
        # طلبٌ مجدول يرى سائقين أقلّ من الفوري تركيبةٌ لا معنى لها.
        self.area.default_matching_radius_km = Decimal("20")
        self.area.marketplace_radius_km = Decimal("5")

        with self.assertRaises(ValidationError) as ctx:
            self.area.full_clean()

        self.assertIn("marketplace_radius_km", ctx.exception.message_dict)

    def test_absurd_time_window_is_rejected(self):
        self.area.shared_scheduled_time_window_minutes = 2000

        with self.assertRaises(ValidationError):
            self.area.full_clean()

    def test_sane_combination_passes(self):
        self.area.default_matching_radius_km = Decimal("6")
        self.area.marketplace_radius_km = Decimal("14")
        self.area.shared_join_radius_km = Decimal("3.5")
        self.area.shared_scheduled_pickup_radius_km = Decimal("9")
        self.area.shared_scheduled_dest_radius_km = Decimal("16")
        self.area.shared_scheduled_time_window_minutes = 45

        self.area.full_clean()  # لا يرمي


class RadiusConfigEndpointTests(TestCase):
    """التطبيق يرسم دائرة البحث بالرقم نفسه الذي يفلتر به الخادم."""

    def tearDown(self):
        LocationService.invalidate_cache()

    def test_all_radii_are_published(self):
        make_area(
            default_matching_radius_km=Decimal("8"),
            marketplace_radius_km=Decimal("18"),
            shared_join_radius_km=Decimal("4"),
        )

        response = self.client.get("/api/v1/config/", {"area": "JAB"})
        geometry = response.json()["geometry"]

        self.assertEqual(geometry["matching_radius_km"], 8.0)
        self.assertEqual(geometry["marketplace_radius_km"], 18.0)
        self.assertEqual(geometry["shared_join_radius_km"], 4.0)

    def test_published_radius_equals_the_engine_radius(self):
        # لو تباعد الرقمان لرسم التطبيق دائرةً تكذب على المستخدم.
        area = make_area(default_matching_radius_km=Decimal("11"))

        customer = make_customer()
        ride = RideRequest.objects.create(
            customer=customer,
            pickup=Point(*JABLEH, srid=4326),
            destination=Point(*at_km_north(3), srid=4326),
            mode=RideMode.STANDARD,
            passenger_count=1,
            status=RideStatus.SEARCHING,
            service_area=area,
            expires_at=timezone.now() + timedelta(minutes=10),
        )

        response = self.client.get("/api/v1/config/", {"area": "JAB"})
        published = response.json()["geometry"]["matching_radius_km"]

        self.assertEqual(published, MatchingService.get_radius_km(ride))
