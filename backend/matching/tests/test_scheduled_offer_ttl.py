# -*- coding: utf-8 -*-
"""عرضٌ على طلب مجدول يعيش حتّى موعد الانطلاق لا ثلاثين ثانية (العيب #37)."""

from datetime import timedelta
from decimal import Decimal

from django.contrib.gis.geos import Point
from django.test import TestCase
from django.utils import timezone

from config.testkit import make_customer, make_driver
from locations.models import ServiceArea
from locations.services import LocationService
from matching.services.matching import MatchingService
from rides.services.ride_request import RideRequestService

JAB = (35.9275, 35.3617)


class ScheduledOfferTtlTests(TestCase):
    def setUp(self):
        ServiceArea.objects.update_or_create(
            code="JAB",
            defaults=dict(name="جبلة", center=Point(*JAB, srid=4326),
                          fallback_radius_km=Decimal("8"), is_active=True),
        )
        LocationService.invalidate_cache()
        self.customer = make_customer()
        self.driver = make_driver()

    def _ride(self, scheduled_at=None):
        return RideRequestService.create_ride_request(
            customer=self.customer,
            pickup=Point(*JAB, srid=4326),
            destination=Point(35.9318, 35.3683, srid=4326),
            mode="standard", passenger_count=1, scheduled_at=scheduled_at,
        )

    def test_instant_offer_keeps_the_short_ttl(self):
        offer = MatchingService.create_offer(
            ride_id=self._ride().id, driver=self.driver,
            gross_fare=Decimal("5000"), eta_minutes=3,
        )
        self.assertLess(offer.expires_at - timezone.now(), timedelta(minutes=10))

    def test_scheduled_offer_lives_until_departure(self):
        departure = timezone.now() + timedelta(days=1)
        offer = MatchingService.create_offer(
            ride_id=self._ride(scheduled_at=departure).id, driver=self.driver,
            gross_fare=Decimal("5000"), eta_minutes=3,
        )
        self.assertEqual(offer.expires_at, departure)
