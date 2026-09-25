# -*- coding: utf-8 -*-
"""
أوّل مشوار بنصف السعر، وزبون يجلب زبونًا — كما في خطّة التسعين يومًا.

ما يُثبَّت:
  • الخصم يطبَّق مرّةً واحدة، بسقفٍ لا نسبة، ويطفئه الصفر.
  • السائق يستحقّ أجرته كاملة؛ الفرق على المنصّة والدفتر يبقى متوازنًا.
  • مكافأة الإحالة تُصرف للطرفين بعد أوّل رحلة محصَّلة للمدعوّ، مرّةً واحدة،
    وتُستهلك تلقائيًّا في الرحلة التالية.
"""

from decimal import Decimal

from django.contrib.gis.geos import Point
from django.test import TestCase
from rest_framework.test import APITestCase

from config.testkit import auth, make_customer, make_driver, make_ride
from locations.models import ServiceArea
from locations.services import LocationService
from matching.services.matching import MatchingService
from payments.models import CustomerCredit, LedgerEntry, Payment, PaymentStatus
from payments.services.ledger import LedgerService
from payments.services.payment import PaymentService
from payments.services.promotions import PromotionService
from trips.models import Trip
from users.models import CustomerProfile


def make_area(**overrides):
    defaults = dict(
        name="جبلة", center=Point(35.9275, 35.3617, srid=4326),
        fallback_radius_km=Decimal("8"), is_active=True,
        first_ride_discount_pct=Decimal("50"), first_ride_discount_cap=Decimal("10000"),
        referral_reward=Decimal("5000"),
    )
    defaults.update(overrides)
    area, _ = ServiceArea.objects.update_or_create(code="JAB", defaults=defaults)
    LocationService.invalidate_cache()
    return area


def complete_and_pay(customer, driver, area, gross="30000.00"):
    """رحلة كاملة: طلب ← عرض ← اختيار ← وصل/بدأ/أنهى ← تحصيل نقدي."""
    from trips.services.trip import TripService

    ride = make_ride(customer, gross_fare=gross, service_area=area)
    offer = MatchingService.create_offer(
        ride_id=ride.id, driver=driver, gross_fare=Decimal(gross), eta_minutes=3,
    )
    MatchingService.select_offer(ride_id=ride.id, offer_id=offer.id, customer=customer)

    def at(point):
        from users.models import DriverProfile
        from django.utils import timezone
        DriverProfile.objects.filter(pk=driver.pk).update(
            current_location=point, last_location_at=timezone.now(),
        )

    at(ride.pickup)
    TripService.arrived(ride_id=ride.id, driver=driver)
    TripService.start(ride_id=ride.id, driver=driver)
    at(ride.destination)
    trip = TripService.complete(ride_id=ride.id, driver=driver)
    payment = Payment.objects.get(trip=trip)
    PaymentService.charge(payment.pk, actor=driver.user)
    payment.refresh_from_db()
    return payment


class FirstRideDiscountTests(TestCase):
    def setUp(self):
        self.area = make_area()
        self.driver = make_driver()

    def test_first_ride_is_discounted_with_cap_and_driver_keeps_full_fare(self):
        customer = make_customer()
        payment = complete_and_pay(customer, self.driver, self.area, gross="30000.00")

        # 50% = 15,000 لكنّ السقف 10,000.
        self.assertEqual(payment.discount_amount, Decimal("10000.00"))
        self.assertEqual(payment.discount_reason, "first_ride")
        self.assertEqual(payment.amount, Decimal("20000.00"))
        self.assertEqual(payment.driver_net, Decimal("30000.00"))
        self.assertEqual(payment.status, PaymentStatus.PAID)

        # الدفتر متوازن، والمنصّة مدينة للسائق بالفرق.
        LedgerService.assert_balanced(
            LedgerEntry.objects.filter(payment=payment).first().transaction_ref
        )
        promo = LedgerEntry.objects.filter(payment=payment, entry_type="promotion")
        self.assertEqual(promo.count(), 2)
        balance = LedgerService.account_balance("driver", str(self.driver.id))
        self.assertEqual(balance, Decimal("10000.00"))

    def test_discount_is_once_per_customer(self):
        customer = make_customer()
        complete_and_pay(customer, self.driver, self.area)
        second = complete_and_pay(customer, self.driver, self.area, gross="20000.00")

        self.assertEqual(second.discount_amount, Decimal("0.00"))
        self.assertEqual(second.amount, Decimal("20000.00"))
        self.assertTrue(CustomerProfile.objects.get(user=customer).first_ride_discount_used)

    def test_zero_pct_disables_it(self):
        make_area(first_ride_discount_pct=Decimal("0"))
        customer = make_customer()
        payment = complete_and_pay(customer, self.driver, self.area)

        self.assertEqual(payment.discount_amount, Decimal("0.00"))
        self.assertEqual(payment.amount, Decimal("30000.00"))


class ReferralTests(TestCase):
    def setUp(self):
        self.area = make_area(first_ride_discount_pct=Decimal("0"))
        self.driver = make_driver()
        self.referrer = make_customer()
        self.referee = make_customer()
        self.referrer_code = CustomerProfile.objects.get_or_create(user=self.referrer)[0].referral_code

    def test_reward_both_after_first_paid_trip_only_once(self):
        PromotionService.apply_referral_code(self.referee, self.referrer_code)

        first = complete_and_pay(self.referee, self.driver, self.area)
        self.assertEqual(CustomerCredit.objects.filter(customer=self.referrer).count(), 1)
        self.assertEqual(CustomerCredit.objects.filter(customer=self.referee).count(), 1)
        self.assertEqual(PromotionService.credit_balance(self.referrer), Decimal("5000.00"))

        # رحلة ثانية للمدعوّ: لا مكافأة جديدة، لكن رصيده يُستهلك.
        second = complete_and_pay(self.referee, self.driver, self.area, gross="8000.00")
        self.assertEqual(CustomerCredit.objects.count(), 2)
        self.assertEqual(second.discount_amount, Decimal("5000.00"))
        self.assertEqual(second.discount_reason, "credit")
        self.assertEqual(second.amount, Decimal("3000.00"))
        self.assertEqual(PromotionService.credit_balance(self.referee), Decimal("0.00"))

    def test_code_rules(self):
        with self.assertRaises(ValueError):
            PromotionService.apply_referral_code(self.referee, "NOPE99")
        with self.assertRaises(ValueError):
            PromotionService.apply_referral_code(self.referrer, self.referrer_code)  # نفسه
        PromotionService.apply_referral_code(self.referee, self.referrer_code)
        with self.assertRaises(ValueError):
            PromotionService.apply_referral_code(self.referee, self.referrer_code)  # مرّتين

    def test_code_must_come_before_first_trip(self):
        complete_and_pay(self.referee, self.driver, self.area)
        with self.assertRaises(ValueError):
            PromotionService.apply_referral_code(self.referee, self.referrer_code)


class ReferralApiTests(APITestCase):
    def setUp(self):
        make_area()
        self.customer = make_customer()
        self.friend = make_customer()
        auth(self.client, self.customer)

    def test_get_and_apply(self):
        mine = self.client.get("/api/v1/me/referral/")
        self.assertEqual(mine.status_code, 200, mine.content)
        self.assertEqual(len(mine.data["referral_code"]), 6)
        self.assertTrue(mine.data["first_ride_discount_available"])

        friend_code = CustomerProfile.objects.get_or_create(user=self.friend)[0].referral_code
        applied = self.client.post("/api/v1/me/referral/", {"code": friend_code.lower()}, format="json")
        self.assertEqual(applied.status_code, 200, applied.content)
        self.assertEqual(applied.data["referred_by_code"], friend_code)

        bad = self.client.post("/api/v1/me/referral/", {"code": "ZZZZZZ"}, format="json")
        self.assertEqual(bad.status_code, 400)
        self.assertIn("رمز", bad.data["detail"])

    def test_profile_older_than_feature_gets_a_code_lazily(self):
        # زبونٌ سجّل قبل ميزة الإحالة: ملفّه موجود ورمزه فارغ.
        CustomerProfile.objects.filter(user=self.customer).update(referral_code=None)
        mine = self.client.get("/api/v1/me/referral/")
        self.assertEqual(mine.status_code, 200)
        self.assertEqual(len(mine.data["referral_code"] or ""), 6)

