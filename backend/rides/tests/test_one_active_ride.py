"""
طلبٌ واحد قائم لكلّ زبون.

عُثر على العطل بنقرة مزدوجة من التطبيق ثمّ بنداءين مباشرين: ثلاثة طلبات
«searching» لزبون واحد في أقلّ من دقيقة، كلّها تصل السائقين. الحارس في
create_ride_request والواجهة تردّ 409 بنصّ عربيّ.
"""

from decimal import Decimal

from django.contrib.gis.geos import Point
from django.test import TestCase
from rest_framework.test import APITestCase

from config.testkit import auth, make_customer
from locations.models import ServiceArea
from locations.services import LocationService
from rides.models import RideRequest, RideStatus
from rides.services.ride_request import (
    RideRequestConflictError,
    RideRequestService,
)

JABLEH_LNG, JABLEH_LAT = 35.9275, 35.3617


def _area():
    ServiceArea.objects.update_or_create(
        code="JAB",
        defaults=dict(
            name="جبلة",
            center=Point(JABLEH_LNG, JABLEH_LAT, srid=4326),
            fallback_radius_km=Decimal("8"),
            marketplace_cell_precision=7,
            default_matching_radius_km=Decimal("5"),
            is_active=True,
        ),
    )
    LocationService.invalidate_cache()


def _create(customer):
    return RideRequestService.create_ride_request(
        customer=customer,
        pickup=Point(JABLEH_LNG, JABLEH_LAT, srid=4326),
        destination=Point(JABLEH_LNG + 0.01, JABLEH_LAT + 0.01, srid=4326),
        mode="standard",
        passenger_count=1,
    )


class OneActiveRideServiceTests(TestCase):
    def setUp(self):
        _area()
        self.customer = make_customer()

    def test_second_request_while_searching_is_rejected(self):
        _create(self.customer)
        with self.assertRaises(RideRequestConflictError):
            _create(self.customer)
        self.assertEqual(RideRequest.objects.filter(customer=self.customer).count(), 1)

    def test_new_request_allowed_after_previous_ended(self):
        ride = _create(self.customer)
        ride.status = RideStatus.CANCELLED
        ride.save(update_fields=["status"])
        _create(self.customer)
        self.assertEqual(RideRequest.objects.filter(customer=self.customer).count(), 2)


class OneActiveRideApiTests(APITestCase):
    def setUp(self):
        _area()
        self.customer = make_customer()
        auth(self.client, self.customer)

    def test_api_returns_409_with_arabic_detail(self):
        body = {
            "pickup_lat": JABLEH_LAT, "pickup_lng": JABLEH_LNG,
            "destination_lat": JABLEH_LAT + 0.01, "destination_lng": JABLEH_LNG + 0.01,
            "mode": "standard", "trip_category": "city", "passenger_count": 1,
        }
        first = self.client.post("/api/v1/rides/", body, format="json")
        self.assertEqual(first.status_code, 201, first.content)
        second = self.client.post("/api/v1/rides/", body, format="json")
        self.assertEqual(second.status_code, 409, second.content)
        self.assertIn("قائم", second.json()["detail"])
