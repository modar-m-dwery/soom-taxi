"""
المشغّل يطفئ ويعيد، والخادم يفرض: التطبيق لا يرى المطفأ، ومَن ينادي الـAPI
مباشرةً يُرفض. واستثناء مدينة يغلب الحالة العامّة.
"""
from unittest.mock import patch

from django.contrib.gis.geos import Point
from django.test import TestCase
from rest_framework.test import APIClient

from catalog.models import FeatureFlag, FeatureFlagAreaOverride, Service, ServiceAreaOverride
from catalog.registry import ServiceStatus
from catalog.services import Catalog
from config.testkit import auth, make_customer, make_driver
from locations.models import ServiceArea
from rides.models import RideMode, TripCategory
from rides.services.ride_request import RideRequestService, RideRequestValidationError


class CatalogTestCase(TestCase):
    """الكاش يعيش بعد الاختبار والقاعدة تُلغى: نمسحه قبل وبعد، فلا تتسرّب
    خدمةٌ أطفأها اختبارٌ إلى اختبارٍ آخر في ملفّ آخر."""

    def setUp(self):
        from catalog.services import invalidate

        invalidate()
        self.addCleanup(invalidate)
        super().setUp()


def _area(code="JAB"):
    return ServiceArea.objects.create(
        code=code, name=code, center=Point(35.92, 35.36, srid=4326),
    )


class SyncTests(CatalogTestCase):

    def test_definitions_are_synced_after_migrate(self):
        self.assertTrue(Service.objects.filter(code="taxi").exists())
        self.assertTrue(Service.objects.filter(code="wedding_convoy", status=ServiceStatus.COMING_SOON).exists())
        self.assertTrue(FeatureFlag.objects.filter(key="nearest", enabled=True).exists())

    def test_sync_never_overrides_operator_choice(self):
        from catalog.sync import sync_definitions

        Service.objects.filter(code="shared").update(status=ServiceStatus.HIDDEN, name="اسمي")
        sync_definitions()
        shared = Service.objects.get(code="shared")
        self.assertEqual((shared.status, shared.name), (ServiceStatus.HIDDEN, "اسمي"))


class ToggleTests(CatalogTestCase):

    def setUp(self):
        super().setUp()
        self.area = _area()

    def _set_service(self, code, status):
        service = Service.objects.get(code=code)
        service.status = status
        service.save()

    def test_turning_off_shared_removes_the_mode(self):
        self._set_service("shared", ServiceStatus.HIDDEN)
        modes = Catalog.ride_modes_for(self.area, [m.value for m in RideMode])
        self.assertNotIn("shared", modes)
        self.assertNotIn("shared", [s["code"] for s in Catalog.services_for(self.area)])

    def test_turning_it_back_on_is_immediate(self):
        self._set_service("shared", ServiceStatus.HIDDEN)
        self.assertFalse(Catalog.service_active("shared"))
        self._set_service("shared", ServiceStatus.ACTIVE)
        self.assertTrue(Catalog.service_active("shared"))

    def test_area_override_wins(self):
        other = _area("LAT")
        ServiceAreaOverride.objects.create(
            service=Service.objects.get(code="service_line"),
            area=self.area, status=ServiceStatus.HIDDEN,
        )
        self.assertFalse(Catalog.service_active("service_line", self.area))
        self.assertTrue(Catalog.service_active("service_line", other))
        self.assertNotIn("service_line", Catalog.trip_categories_for(self.area))

    def test_feature_area_override(self):
        FeatureFlagAreaOverride.objects.create(
            flag=FeatureFlag.objects.get(key="nearest"), area=self.area, enabled=False,
        )
        self.assertFalse(Catalog.feature_enabled("nearest", self.area))
        self.assertTrue(Catalog.feature_enabled("nearest"))

    def test_coming_soon_is_listed_but_not_active(self):
        codes = {s["code"]: s["status"] for s in Catalog.services_for(self.area)}
        self.assertEqual(codes["car_rental"], ServiceStatus.COMING_SOON)
        self.assertFalse(Catalog.service_active("car_rental", self.area))


class EnforcementTests(CatalogTestCase):

    def setUp(self):
        super().setUp()
        self.customer = make_customer()

    def _create(self, **kwargs):
        defaults = dict(
            customer=self.customer,
            pickup=Point(35.9275, 35.3617, srid=4326),
            destination=Point(35.93, 35.37, srid=4326),
            mode=RideMode.STANDARD,
            passenger_count=1,
        )
        defaults.update(kwargs)
        with patch("locations.services.LocationService.resolve_area", return_value=None):
            return RideRequestService.create_ride_request(**defaults)

    def test_shared_ride_refused_when_shared_is_off(self):
        Service.objects.filter(code="shared").update(status=ServiceStatus.HIDDEN)
        from catalog.services import invalidate
        invalidate()
        with self.assertRaises(RideRequestValidationError):
            self._create(mode=RideMode.SHARED)

    def test_intercity_refused_when_off(self):
        service = Service.objects.get(code="intercity")
        service.status = ServiceStatus.HIDDEN
        service.save()
        with self.assertRaises(RideRequestValidationError):
            self._create(
                trip_category=TripCategory.INTERCITY,
                origin_city="جبلة", destination_city="حمص",
            )

    def test_nearest_refused_when_feature_off(self):
        flag = FeatureFlag.objects.get(key="nearest")
        flag.enabled = False
        flag.save()
        with self.assertRaises(RideRequestValidationError):
            self._create(mode=RideMode.FAST, auto_dispatch=True)

    def test_published_trips_endpoint_forbidden_when_off(self):
        service = Service.objects.get(code="published_trips")
        service.status = ServiceStatus.HIDDEN
        service.save()
        client = APIClient()
        auth(client, self.customer)
        self.assertEqual(client.get("/api/v1/trips/").status_code, 403)

    def test_subscriptions_forbidden_when_off(self):
        service = Service.objects.get(code="morning_subscription")
        service.status = ServiceStatus.COMING_SOON
        service.save()
        client = APIClient()
        auth(client, self.customer)
        self.assertEqual(client.get("/api/v1/rides/subscriptions/").status_code, 403)

    def test_config_reports_services_and_features(self):
        client = APIClient()
        auth(client, self.customer)
        body = client.get("/api/v1/config/").json()
        self.assertIn("taxi", [s["code"] for s in body["services"]])
        self.assertIn("nearest", body["features"])
        self.assertIn("city", body["trip_categories"])

    def test_driver_publish_forbidden_when_off(self):
        service = Service.objects.get(code="published_trips")
        service.status = ServiceStatus.HIDDEN
        service.save()
        client = APIClient()
        auth(client, make_driver())
        self.assertEqual(client.post("/api/v1/driver/trips/publish/", {}).status_code, 403)
