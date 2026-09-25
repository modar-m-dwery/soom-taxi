# -*- coding: utf-8 -*-
"""
«السعر الذي تختاره هو الذي تدفعه» — يُقاس عند الدفع لا في الواجهة.

قِيس على خادم يعمل: تقدير الإنشاء 5,136، عرض السائق 6,000 قُبل، الرحلة
سُجّلت بـ6,000 — والدفعة فُتحت بـ5,136 لأنّ لقطة الأجرة في الطلب بقيت على
التقدير. هذا الملفّ يثبّت أنّ الاختيار يعيد كتابة اللقطة من العرض الفائز،
وأنّ السائق المؤسّس معفًى من العمولة حتّى حين تُفعَّل.
"""

from decimal import Decimal

from django.test import TestCase

from config.testkit import make_customer, make_driver, make_ride
from locations.models import ServiceArea
from locations.services import LocationService
from django.contrib.gis.geos import Point


def make_area():
    area, _ = ServiceArea.objects.update_or_create(
        code="JAB",
        defaults=dict(name="جبلة", center=Point(35.9275, 35.3617, srid=4326),
                      fallback_radius_km=Decimal("8"), is_active=True),
    )
    LocationService.invalidate_cache()
    return area
from matching.services.matching import MatchingService
from payments.services.payment import PaymentService
from trips.models import Trip
from trips.services.trip import TripService


class SettledFareTests(TestCase):
    def setUp(self):
        self.area = make_area()
        self.customer = make_customer()
        self.driver = make_driver()

    def _select(self, gross="6000.00"):
        ride = make_ride(self.customer, gross_fare="5136.00", service_area=self.area)
        offer = MatchingService.create_offer(
            ride_id=ride.id, driver=self.driver,
            gross_fare=Decimal(gross), eta_minutes=4,
        )
        MatchingService.select_offer(ride_id=ride.id, offer_id=offer.id, customer=self.customer)
        ride.refresh_from_db()
        return ride, offer

    def test_ride_snapshot_follows_the_winning_offer(self):
        ride, offer = self._select()

        self.assertEqual(ride.gross_fare, Decimal("6000.00"))
        self.assertEqual(ride.customer_total, Decimal("6000.00"))
        self.assertEqual(ride.driver_net, Decimal("6000.00"))
        self.assertEqual(ride.platform_fee, Decimal("0.00"))

    def test_payment_opens_on_the_agreed_price(self):
        ride, offer = self._select()
        trip = Trip.objects.get(ride=ride)

        payment = PaymentService.open_for_trip(trip)

        self.assertEqual(payment.amount, Decimal("6000.00"))
        self.assertEqual(payment.driver_net, Decimal("6000.00"))

    def test_founder_is_exempt_even_when_commission_is_on(self):
        # تُفعَّل العمولة لهذه المدينة من لوحة الإدارة: سقف 10%.
        ServiceArea.objects.filter(pk=self.area.pk).update(commission_cap_pct=Decimal("10"))
        self.area.refresh_from_db()

        from pricing.services import PricingService
        original = PricingService.PLATFORM_FEE
        PricingService.PLATFORM_FEE = Decimal("1000.00")
        try:
            # سائق عاديّ: تُخصم منه العمولة (مسقوفة بـ10%).
            ride, _ = self._select()
            self.assertEqual(ride.platform_fee, Decimal("600.00"))
            self.assertEqual(ride.driver_net, Decimal("5400.00"))

            # مؤسّس: صافيه أجرته كاملة.
            founder = make_driver()
            founder.founder_number = 7
            founder.commission_exempt = True
            founder.save(update_fields=["founder_number", "commission_exempt"])
            other_customer = make_customer()
            ride2 = make_ride(other_customer, gross_fare="5136.00", service_area=self.area)
            offer2 = MatchingService.create_offer(
                ride_id=ride2.id, driver=founder, gross_fare=Decimal("6000.00"), eta_minutes=4,
            )
            MatchingService.select_offer(ride_id=ride2.id, offer_id=offer2.id, customer=other_customer)
            ride2.refresh_from_db()
            self.assertEqual(ride2.platform_fee, Decimal("0.00"))
            self.assertEqual(ride2.driver_net, Decimal("6000.00"))
        finally:
            PricingService.PLATFORM_FEE = original
