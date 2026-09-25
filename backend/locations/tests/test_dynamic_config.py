"""
البارامترات الديناميكية ونقطة الإعداد.

ما تحرسه هذه الاختبارات ليس وجود الحقول بل **أن تغييرها يسري فعلًا**.
حقلٌ في الأدمن لا يغيّر سلوك الخادم أسوأ من عدم وجوده: يعطي المشغّل وهم
التحكّم، ويجعله يبحث عن العطل في كلّ مكان إلّا في الحقل الذي ظنّه يعمل.
"""
from datetime import timedelta
from decimal import Decimal

from django.contrib.gis.geos import Point
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APITestCase

from config.testkit import auth, make_customer
from locations.models import ServiceArea
from locations.services import LocationService
from vehicles.models import VehicleCategory


JABLEH_LNG, JABLEH_LAT = 35.90, 35.36


def make_area(code="JAB", **overrides):
    defaults = dict(
        name="جبلة",
        center=Point(JABLEH_LNG, JABLEH_LAT, srid=4326),
        fallback_radius_km=Decimal("8"),
        marketplace_cell_precision=7,
        default_matching_radius_km=Decimal("5"),
        is_active=True,
    )
    defaults.update(overrides)
    area, _ = ServiceArea.objects.update_or_create(code=code, defaults=defaults)
    LocationService.invalidate_cache()
    return area


class ServiceAreaTimingTests(TestCase):
    """القيمة الفعلية: قيمة المنطقة إن وُجدت، وإلّا الافتراضي العامّ."""

    def setUp(self):
        self.area = make_area()

    def test_blank_field_falls_back_to_global_default(self):
        self.assertIsNone(self.area.offer_ttl_seconds)

        from django.conf import settings

        self.assertEqual(
            self.area.effective_offer_ttl_seconds,
            settings.RIDE_OFFER_TTL_SECONDS,
        )

    def test_area_value_wins_over_global(self):
        self.area.offer_ttl_seconds = 45
        self.area.save()

        self.assertEqual(self.area.effective_offer_ttl_seconds, 45)

    def test_every_timing_has_an_effective_reader(self):
        # الحارس ضدّ حقل يُضاف وينسى صاحبه أن يقرأه أحد.
        pairs = [
            ("offer_ttl_seconds", "effective_offer_ttl_seconds", 55),
            ("ride_search_window_minutes", "effective_ride_search_window_minutes", 7),
            ("presence_stale_seconds", "effective_presence_stale_seconds", 90),
            ("presence_fresh_seconds", "effective_presence_fresh_seconds", 25),
            ("location_max_age_seconds", "effective_location_max_age_seconds", 45),
            (
                "invitation_reject_cooldown_seconds",
                "effective_invitation_reject_cooldown_seconds",
                30,
            ),
            ("arrival_radius_m", "effective_arrival_radius_m", 350),
            ("dropoff_radius_m", "effective_dropoff_radius_m", 500),
        ]

        for field, reader, value in pairs:
            with self.subTest(field=field):
                setattr(self.area, field, value)
                self.assertEqual(getattr(self.area, reader), value)


class ServiceAreaValidationTests(TestCase):
    """
    الأدمن يسري على الإنتاج فورًا بلا مراجعة — فالحارس هنا لا في مكان آخر.
    """

    def setUp(self):
        self.area = make_area()

    def test_absurd_offer_ttl_is_rejected(self):
        self.area.offer_ttl_seconds = 2
        with self.assertRaises(ValidationError) as ctx:
            self.area.full_clean()
        self.assertIn("offer_ttl_seconds", ctx.exception.message_dict)

    def test_search_window_of_a_whole_day_is_rejected(self):
        self.area.ride_search_window_minutes = 2000
        with self.assertRaises(ValidationError):
            self.area.full_clean()

    def test_fresh_must_be_shorter_than_stale(self):
        # العكس يجعل السائق يومض: متأخّر ثمّ حاضر ثمّ يختفي.
        self.area.presence_fresh_seconds = 90
        self.area.presence_stale_seconds = 60

        with self.assertRaises(ValidationError) as ctx:
            self.area.full_clean()

        self.assertIn("presence_fresh_seconds", ctx.exception.message_dict)

    def test_dropoff_narrower_than_arrival_is_rejected(self):
        self.area.arrival_radius_m = 400
        self.area.dropoff_radius_m = 100

        with self.assertRaises(ValidationError) as ctx:
            self.area.full_clean()

        self.assertIn("dropoff_radius_m", ctx.exception.message_dict)

    def test_sane_combination_passes(self):
        self.area.offer_ttl_seconds = 60
        self.area.presence_fresh_seconds = 20
        self.area.presence_stale_seconds = 70
        self.area.arrival_radius_m = 200
        self.area.dropoff_radius_m = 300

        self.area.full_clean()  # لا يرمي


class RideSearchWindowTests(TestCase):
    """
    الرقم الذي كان مكتوبًا في الدالّة: timedelta(minutes=10).
    """

    def setUp(self):
        self.customer = make_customer()

    def _create_ride(self):
        from rides.services.ride_request import RideRequestService

        return RideRequestService.create_ride_request(
            customer=self.customer,
            pickup=Point(JABLEH_LNG, JABLEH_LAT, srid=4326),
            destination=Point(JABLEH_LNG + 0.01, JABLEH_LAT + 0.01, srid=4326),
            mode="standard",
            passenger_count=1,
        )

    def test_area_window_is_applied(self):
        make_area(ride_search_window_minutes=3)

        ride = self._create_ride()

        window = ride.expires_at - ride.created_at
        self.assertAlmostEqual(
            window.total_seconds(), timedelta(minutes=3).total_seconds(), delta=5
        )

    def test_default_window_is_ten_minutes(self):
        make_area(ride_search_window_minutes=None)

        ride = self._create_ride()

        window = ride.expires_at - ride.created_at
        self.assertAlmostEqual(
            window.total_seconds(), timedelta(minutes=10).total_seconds(), delta=5
        )

    def test_scheduled_ride_never_expires(self):
        from django.utils import timezone
        from rides.services.ride_request import RideRequestService

        make_area(ride_search_window_minutes=3)

        ride = RideRequestService.create_ride_request(
            customer=self.customer,
            pickup=Point(JABLEH_LNG, JABLEH_LAT, srid=4326),
            destination=Point(JABLEH_LNG + 0.01, JABLEH_LAT + 0.01, srid=4326),
            mode="standard",
            passenger_count=1,
            scheduled_at=timezone.now() + timedelta(hours=2),
        )

        self.assertIsNone(ride.expires_at)


class AppConfigEndpointTests(APITestCase):
    """
    النقطة التي لم تكن موجودة: إعدادٌ لا يصل إلى العميل نصف إعداد.
    """

    def setUp(self):
        self.url = reverse("app-config")
        self.area = make_area(
            offer_ttl_seconds=45,
            ride_search_window_minutes=6,
            arrival_radius_m=250,
        )

    def test_readable_without_authentication(self):
        # التطبيق يحتاجها ليرسم شاشته الأولى، قبل تسجيل الدخول.
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_resolves_area_from_coordinates(self):
        response = self.client.get(
            self.url, {"lat": JABLEH_LAT, "lng": JABLEH_LNG}
        )

        self.assertEqual(response.data["area_code"], "JAB")
        self.assertEqual(response.data["resolved_from"], "coordinates")

    def test_resolves_area_from_code(self):
        response = self.client.get(self.url, {"area": "jab"})

        self.assertEqual(response.data["area_code"], "JAB")
        self.assertEqual(response.data["resolved_from"], "code")

    def test_returns_area_values_not_global_defaults(self):
        response = self.client.get(
            self.url, {"lat": JABLEH_LAT, "lng": JABLEH_LNG}
        )

        timings = response.data["timings"]
        self.assertEqual(timings["offer_ttl_seconds"], 45)
        self.assertEqual(timings["ride_search_window_minutes"], 6)
        self.assertEqual(response.data["geometry"]["arrival_radius_m"], 250)

    def test_admin_change_is_visible_immediately(self):
        # جوهر الأمر كلّه: بلا إعادة تشغيل ولا نشر ولا إصدار تطبيق.
        first = self.client.get(self.url, {"area": "JAB"})
        self.assertEqual(first.data["timings"]["offer_ttl_seconds"], 45)

        self.area.offer_ttl_seconds = 120
        self.area.save()
        LocationService.invalidate_cache()

        second = self.client.get(self.url, {"area": "JAB"})
        self.assertEqual(second.data["timings"]["offer_ttl_seconds"], 120)

    def test_coordinates_outside_every_area_are_not_faked(self):
        # بعيد في البحر: نقول "لا منطقة" ولا نُعطيه قواعد مدينة أخرى.
        response = self.client.get(self.url, {"lat": 33.0, "lng": 33.0})

        self.assertIsNone(response.data["area_code"])
        self.assertEqual(response.data["resolved_from"], "none")
        # ومع ذلك الشكل كامل: تطبيقٌ يقرأ null في كلّ حقل ينهار.
        self.assertIn("offer_ttl_seconds", response.data["timings"])
        self.assertTrue(response.data["ride_modes"])

    def test_does_not_leak_commercial_settings(self):
        response = self.client.get(self.url, {"area": "JAB"})

        flat = str(response.data)
        for secret in (
            "driver_min_share_pct",
            "commission_cap_pct",
            "regulator_name",
            "road_detour_factor",
        ):
            self.assertNotIn(secret, flat)

    def test_invitation_ttl_options_are_published(self):
        # هذه بالضبط الثغرة: الخادم يرفض أيّ مهلة خارج القائمة، ولم تكن
        # للتطبيق طريقة لقراءتها إلّا بإرسال قيمة خاطئة وقراءة الخطأ.
        response = self.client.get(self.url, {"area": "JAB"})

        options = response.data["timings"]["invitation_ttl_options"]
        self.assertTrue(options)
        self.assertIn(response.data["timings"]["invitation_ttl_default"], options)


class VehicleCategoryTests(TestCase):

    def setUp(self):
        self.area = make_area()

    def test_defaults_were_seeded_by_migration(self):
        codes = set(VehicleCategory.objects.values_list("code", flat=True))
        # الفئات السورية (0004) فعّالة، والقديمة باقية مطفأةً لا محذوفة.
        self.assertTrue({"taxi", "private", "jeep", "van", "micro"} <= codes)
        active = set(VehicleCategory.active_codes(None))
        self.assertTrue({"taxi", "private", "jeep", "van", "micro"} <= active)
        self.assertFalse({"sedan", "hatchback", "suv"} & active)

    def test_new_category_needs_no_code_change(self):
        # «تكتك» صارت مزروعة (مطفأة) في 0004؛ فئة جديدة فعلًا: بولمان.
        VehicleCategory.objects.create(
            code="bus", name="بولمان", seats=40, sort_order=5
        )

        self.assertIn("bus", VehicleCategory.active_codes(self.area))

    def test_disabled_category_disappears(self):
        VehicleCategory.objects.filter(code="van").update(is_active=False)

        self.assertNotIn("van", VehicleCategory.active_codes(self.area))

    def test_category_can_be_scoped_to_one_city(self):
        other = make_area(
            code="LAT",
            name="اللاذقية",
            center=Point(35.7797, 35.5317, srid=4326),
        )

        micro = VehicleCategory.objects.create(code="microbus", name="ميكروباص")
        micro.areas.add(other)

        self.assertIn("microbus", VehicleCategory.active_codes(other))
        self.assertNotIn("microbus", VehicleCategory.active_codes(self.area))

    def test_category_without_areas_is_available_everywhere(self):
        self.assertIn("taxi", VehicleCategory.active_codes(self.area))
        self.assertIn("taxi", VehicleCategory.active_codes(None))

    def test_code_must_be_url_safe_lowercase(self):
        for bad in ("Sedan", "تكتك", "tuk tuk", "tuk/tuk"):
            with self.subTest(code=bad):
                with self.assertRaises(ValidationError):
                    VehicleCategory(code=bad, name="x").full_clean()

    def test_category_in_use_cannot_be_deleted(self):
        from django.db.models import ProtectedError

        from config.testkit import make_driver, make_vehicle

        driver = make_driver()
        make_vehicle(driver, vehicle_type="taxi")

        with self.assertRaises(ProtectedError):
            VehicleCategory.objects.get(code="taxi").delete()


class DynamicVehicleTypeApiTests(APITestCase):
    """عقد الـAPI لم يتغيّر: الرمز نصّ كما كان، والتحقّق صار من القاعدة."""

    def setUp(self):
        self.area = make_area()
        self.customer = make_customer()
        auth(self.client, self.customer)
        self.payload = {
            "pickup_lat": JABLEH_LAT,
            "pickup_lng": JABLEH_LNG,
            "destination_lat": JABLEH_LAT + 0.01,
            "destination_lng": JABLEH_LNG + 0.01,
            "mode": "standard",
            "passenger_count": 1,
        }

    def test_seeded_category_is_accepted(self):
        response = self.client.post(
            "/api/v1/rides/", {**self.payload, "requested_vehicle_type": "taxi"},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["requested_vehicle_type"], "taxi")

    def test_category_added_at_runtime_is_accepted(self):
        VehicleCategory.objects.filter(code="tuktuk").update(is_active=True)

        response = self.client.post(
            "/api/v1/rides/", {**self.payload, "requested_vehicle_type": "tuktuk"},
            format="json",
        )

        self.assertEqual(response.status_code, 201)

    def test_unknown_category_is_rejected(self):
        response = self.client.post(
            "/api/v1/rides/",
            {**self.payload, "requested_vehicle_type": "helicopter"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("requested_vehicle_type", response.data["fields"])

    def test_disabled_category_is_rejected(self):
        VehicleCategory.objects.filter(code="van").update(is_active=False)

        response = self.client.post(
            "/api/v1/rides/", {**self.payload, "requested_vehicle_type": "van"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)


class VehicleTypeWireFormatTests(APITestCase):
    """
    الحارس ضدّ أخطر آثار تحويل العمود إلى مفتاح أجنبي.

    `vehicle.type` صار يرجّع **كائنًا** لا نصًّا. من كتبه في مخطّط أو حمولة
    حصل على "سيدان (sedan)" من `__str__` — أي أنّ العقد ينكسر بلا استثناء
    ولا سطر سجلّ، ويُكتشف في التطبيق لا في الخادم. الصحيح `type_id`، وهو
    مجّاني أيضًا (لا استعلام).

    هذه الاختبارات تُثبّت الشكل على السلك، فأيّ عودة إلى `.type` تسقط هنا.
    """

    def setUp(self):
        from config.testkit import make_driver, make_vehicle

        self.area = make_area()
        self.driver = make_driver()
        self.vehicle = make_vehicle(self.driver, vehicle_type="taxi")
        auth(self.client, self.driver.user)

    def test_vehicle_list_returns_the_code_as_a_string(self):
        response = self.client.get("/api/v1/vehicles/")

        self.assertEqual(response.status_code, 200)

        rows = response.data
        rows = rows["results"] if isinstance(rows, dict) else rows

        self.assertEqual(rows[0]["type"], "taxi")
        self.assertIsInstance(rows[0]["type"], str)

    def test_model_attribute_returns_the_code_not_the_object(self):
        self.vehicle.refresh_from_db()

        self.assertEqual(self.vehicle.type_id, "taxi")
        self.assertIsInstance(self.vehicle.type_id, str)

    def test_reading_the_code_costs_no_extra_query(self):
        # سبب اختيار type_id على خاصية جديدة: القراءة من عمود المفتاح
        # مجّانية، والوصول إلى `.type` يجلب الصفّ.
        from vehicles.models import Vehicle

        vehicle = Vehicle.objects.get(id=self.vehicle.id)

        with self.assertNumQueries(0):
            self.assertEqual(vehicle.type_id, "taxi")

    def test_filtering_by_the_code_still_works(self):
        from vehicles.models import Vehicle

        self.assertTrue(Vehicle.objects.filter(type="taxi").exists())
        self.assertFalse(Vehicle.objects.filter(type="van").exists())
