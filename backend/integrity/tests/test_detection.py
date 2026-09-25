"""
الكشف: الإشارات الآنيّة (الإلغاء، الشكوى، الموقع) والكواشف الدوريّة
(الأجهزة، الثنائيّات، الرحلات القصيرة، تطويل المسار، نسبة الإلغاء).
"""
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from config.testkit import (
    JABLEH,
    auth,
    make_accepted_offer,
    make_customer,
    make_driver,
    make_ride,
    make_trip,
)
from feedback.models import ComplaintCategory
from feedback.services.complaint import ComplaintService
from integrity import registry
from integrity.models import RiskSignal
from integrity.services import hooks
from integrity.services.detectors import Detectors
from rides.models import RideStatus
from trips.models import CancellationKind, CancellationRecord, TripStatus
from trips.services.trip import TripService
from users.models import OTPChallenge


def _signals(user, kind):
    return RiskSignal.objects.filter(user=user, kind=kind)


def _assigned(customer, driver, arrived=False, minutes_ago=4):
    ride = make_ride(customer, status=RideStatus.DRIVER_ARRIVING)
    offer = make_accepted_offer(ride, driver)
    now = timezone.now()
    trip = make_trip(
        ride, driver,
        status=TripStatus.DRIVER_ARRIVED if arrived else TripStatus.DRIVER_ARRIVING,
        offer=offer,
        arriving_at=now - timedelta(minutes=minutes_ago),
        arrived_at=(now - timedelta(minutes=1)) if arrived else None,
    )
    return ride, trip


def _login(phone, device):
    OTPChallenge.objects.create(
        phone=phone, code_salt="s", code_hash="h", max_attempts=5,
        expires_at=timezone.now() + timedelta(minutes=5),
        consumed_at=timezone.now(), device_id=device,
    )


# =====================================================================
# الإلغاء
# =====================================================================

class CancellationSignalTests(APITestCase):

    def setUp(self):
        self.customer = make_customer()
        self.driver = make_driver(location=JABLEH)

    def test_driver_asked_reason_flags_driver(self):
        ride, _ = _assigned(self.customer, self.driver)
        auth(self.client, self.customer)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse("customer-cancel-trip", args=[ride.id]),
                {"reason": "قال لي ألغي ونكمّل برّا", "reason_code": "driver_asked"},
                format="json",
            )
        self.assertEqual(response.status_code, 200, response.content)
        record = CancellationRecord.objects.get(ride=ride)
        self.assertEqual(record.reason_code, "driver_asked")
        self.assertEqual(
            _signals(self.driver.user, registry.DRIVER_ASKED_TO_CANCEL.code).count(), 1,
        )
        self.assertFalse(_signals(self.customer, registry.DRIVER_ASKED_TO_CANCEL.code).exists())

    def test_unknown_reason_code_is_rejected(self):
        ride, _ = _assigned(self.customer, self.driver)
        auth(self.client, self.customer)
        response = self.client.post(
            reverse("customer-cancel-trip", args=[ride.id]),
            {"reason_code": "whatever"}, format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_reason_code_is_optional(self):
        ride, _ = _assigned(self.customer, self.driver)
        auth(self.client, self.customer)
        response = self.client.post(
            reverse("customer-cancel-trip", args=[ride.id]), {"reason": "x"}, format="json",
        )
        self.assertEqual(response.status_code, 200)

    def test_repeated_arrive_then_cancel_same_pair_is_off_app(self):
        for _ in range(2):
            ride, _ = _assigned(self.customer, self.driver, arrived=True)
            with self.captureOnCommitCallbacks(execute=True):
                TripService.cancel(ride.id, actor="customer", reason="")
        self.assertEqual(_signals(self.driver.user, registry.OFF_APP_SUSPECTED.code).count(), 1)
        customer_signal = _signals(self.customer, registry.OFF_APP_SUSPECTED.code).get()
        self.assertEqual(customer_signal.weight, registry.OFF_APP_SUSPECTED.weight // 2)
        self.assertEqual(customer_signal.counterpart, self.driver.user)

    def test_prankster_waits_do_not_blame_the_driver(self):
        # الزبون أنطر السائق نفسه مرّتين ثمّ ألغى: الضحيّة السائق، لا شريكه.
        for _ in range(2):
            ride, trip = _assigned(self.customer, self.driver, arrived=True)
            record = CancellationRecord.objects.create(
                ride=ride, trip=trip, customer=self.customer, driver=self.driver,
                actor="customer", kind=CancellationKind.AFTER_WAIT, strikes=2,
            )
            hooks.on_cancellation(record)
        self.assertFalse(_signals(self.driver.user, registry.OFF_APP_SUSPECTED.code).exists())
        self.assertTrue(_signals(self.customer, registry.REPEATED_NO_SHOW.code).exists())

    def test_single_arrive_then_cancel_is_not_suspicious(self):
        ride, _ = _assigned(self.customer, self.driver, arrived=True)
        with self.captureOnCommitCallbacks(execute=True):
            TripService.cancel(ride.id, actor="customer")
        self.assertFalse(RiskSignal.objects.exists())

    def test_single_no_show_is_not_flagged(self):
        ride, trip = _assigned(self.customer, make_driver(), arrived=True)
        record = CancellationRecord.objects.create(
            ride=ride, trip=trip, customer=self.customer, driver=trip.driver,
            actor="customer", kind=CancellationKind.AFTER_WAIT, strikes=2,
        )
        hooks.on_cancellation(record)
        self.assertFalse(_signals(self.customer, registry.REPEATED_NO_SHOW.code).exists())

    def test_repeated_no_show(self):
        for _ in range(3):
            ride, trip = _assigned(self.customer, make_driver(), arrived=True)
            record = CancellationRecord.objects.create(
                ride=ride, trip=trip, customer=self.customer, driver=trip.driver,
                actor="customer", kind=CancellationKind.AFTER_WAIT, strikes=2,
            )
            hooks.on_cancellation(record)
        self.assertEqual(_signals(self.customer, registry.REPEATED_NO_SHOW.code).count(), 1)

    def test_small_sample_does_not_flag_driver(self):
        for i in range(5):
            ride, trip = _assigned(make_customer(), self.driver)
            if i < 2:
                CancellationRecord.objects.create(
                    ride=ride, trip=trip, customer=ride.customer, driver=self.driver,
                    actor="driver", kind=CancellationKind.DRIVER, strikes=1,
                )
        self.assertEqual(Detectors.driver_cancel_rate(driver=self.driver), 0)

    def test_driver_cancel_rate(self):
        for i in range(8):
            ride, trip = _assigned(make_customer(), self.driver)
            if i < 3:
                CancellationRecord.objects.create(
                    ride=ride, trip=trip, customer=ride.customer, driver=self.driver,
                    actor="driver", kind=CancellationKind.DRIVER, strikes=1,
                )
        self.assertEqual(Detectors.driver_cancel_rate(driver=self.driver), 1)
        # مرّة واحدة بالأسبوع مهما أُعيد التشغيل
        self.assertEqual(Detectors.driver_cancel_rate(driver=self.driver), 0)

    def test_hook_failure_never_breaks_cancellation(self):
        ride, _ = _assigned(self.customer, self.driver)
        with patch(
            "integrity.services.scoring.IntegrityService.record", side_effect=RuntimeError("db down"),
        ):
            with self.captureOnCommitCallbacks(execute=True):
                trip = TripService.cancel(
                    ride.id, actor="customer", reason_code="driver_asked",
                )
        self.assertEqual(trip.status, TripStatus.CANCELLED)


# =====================================================================
# الشكاوى والسوم
# =====================================================================

class FareBaitTests(TestCase):

    def test_fare_complaint_on_offer_trip_flags_driver(self):
        customer, driver = make_customer(), make_driver()
        ride = make_ride(customer, status=RideStatus.COMPLETED)
        offer = make_accepted_offer(ride, driver, gross_fare="20000.00")
        trip = make_trip(
            ride, driver, status=TripStatus.COMPLETED, offer=offer, completed_at=timezone.now(),
        )
        trip.final_fare = Decimal("30000.00")
        trip.save(update_fields=["final_fare"])
        with self.captureOnCommitCallbacks(execute=True):
            ComplaintService.open(
                ride.id, customer, ComplaintCategory.FARE,
                "اتفقنا على سعر وطلب أكثر بعد الركوب",
            )
        signal = _signals(driver.user, registry.FARE_ABOVE_AGREED.code).get()
        self.assertEqual(signal.evidence["agreed_fare"], "20000.00")

    def test_other_categories_are_ignored(self):
        customer, driver = make_customer(), make_driver()
        ride = make_ride(customer, status=RideStatus.COMPLETED)
        offer = make_accepted_offer(ride, driver)
        make_trip(ride, driver, status=TripStatus.COMPLETED, offer=offer, completed_at=timezone.now())
        with self.captureOnCommitCallbacks(execute=True):
            ComplaintService.open(ride.id, customer, ComplaintCategory.VEHICLE, "السيارة كانت وسخة جدًا")
        self.assertFalse(RiskSignal.objects.exists())


# =====================================================================
# الموقع
# =====================================================================

class LocationSignalTests(TestCase):

    def setUp(self):
        self.driver = make_driver()

    def test_implausible_speed_signal_once_per_window(self):
        for _ in range(20):
            hooks.on_location_rejected(self.driver.id, "implausible_speed", 35.9, 35.3, (35.0, 35.0, 1.0))
        self.assertEqual(_signals(self.driver.user, registry.GPS_IMPLAUSIBLE_SPEED.code).count(), 1)

    def test_other_rejections_are_not_fraud(self):
        hooks.on_location_rejected(self.driver.id, "null_island", 0, 0)
        self.assertFalse(RiskSignal.objects.exists())

    def test_mock_location(self):
        hooks.on_mock_location(self.driver.id, 35.9, 35.3)
        hooks.on_mock_location(self.driver.id, 35.9, 35.3)
        self.assertEqual(_signals(self.driver.user, registry.GPS_MOCK_LOCATION.code).count(), 1)

    def test_unknown_driver_is_ignored(self):
        self.assertIsNone(hooks.on_mock_location(999999, 35.9, 35.3))


# =====================================================================
# الكواشف الدوريّة
# =====================================================================

class DeviceDetectorTests(TestCase):

    def test_shared_device_pair_with_trip(self):
        driver = make_driver()
        customer = make_customer()
        _login(driver.user.phone, "dev-A")
        _login(customer.phone, "dev-A")
        make_trip(make_ride(customer), driver, status=TripStatus.COMPLETED, completed_at=timezone.now())

        self.assertEqual(Detectors.shared_device_pairs(), 2)
        self.assertEqual(Detectors.shared_device_pairs(), 0)
        signal = _signals(driver.user, registry.SHARED_DEVICE_PAIR.code).get()
        self.assertEqual(signal.counterpart, customer)

    def test_shared_device_without_trips_is_fine(self):
        driver = make_driver()
        customer = make_customer()
        _login(driver.user.phone, "dev-A")
        _login(customer.phone, "dev-A")
        self.assertEqual(Detectors.shared_device_pairs(), 0)

    def test_multi_account_and_promo_harvest(self):
        from config.testkit import make_completed_trip
        from payments.models import Payment
        from payments.services.payment import PaymentService

        accounts = [make_customer() for _ in range(3)]
        for user in accounts:
            _login(user.phone, "dev-SIMS")
        for user in accounts[:2]:
            trip = make_completed_trip(customer=user)
            PaymentService.open_for_trip(trip)
        Payment.objects.filter(customer__in=accounts[:2]).update(discount_reason="first_ride")

        Detectors.multi_account_devices()
        for user in accounts:
            self.assertTrue(_signals(user, registry.MULTI_ACCOUNT_DEVICE.code).exists())
        self.assertEqual(
            RiskSignal.objects.filter(kind=registry.PROMO_MULTI_ACCOUNT.code).count(), 2,
        )

    def test_two_accounts_per_device_is_normal(self):
        for user in (make_customer(), make_customer()):
            _login(user.phone, "family-phone")
        self.assertEqual(Detectors.multi_account_devices(), 0)

    def test_referral_same_device(self):
        referrer = make_customer()
        referee = make_customer()
        referee.customer_profile.referred_by = referrer
        referee.customer_profile.save()
        _login(referrer.phone, "dev-R")
        _login(referee.phone, "dev-R")
        self.assertEqual(Detectors.referral_same_device(), 2)


class TripPatternDetectorTests(TestCase):

    def _completed(self, customer, driver, distance_m=500, duration_s=240, route_km="0.60"):
        ride = make_ride(customer, status=RideStatus.COMPLETED)
        ride.route_distance_km = Decimal(route_km)
        ride.save(update_fields=["route_distance_km"])
        return make_trip(
            ride, driver, status=TripStatus.COMPLETED, completed_at=timezone.now(),
            distance_m=distance_m, duration_s=duration_s,
        )

    def test_repeat_pair_short_trips(self):
        customer, driver = make_customer(), make_driver()
        for _ in range(4):
            self._completed(customer, driver)
        self.assertEqual(Detectors.repeat_pair_short_trips(), 2)
        self.assertEqual(Detectors.repeat_pair_short_trips(), 0)

    def test_daily_commute_is_not_farming(self):
        customer, driver = make_customer(), make_driver()
        for _ in range(4):
            self._completed(customer, driver, distance_m=6000, duration_s=900, route_km="6.00")
        self.assertEqual(Detectors.repeat_pair_short_trips(), 0)

    def test_short_trip_farming(self):
        driver = make_driver()
        for _ in range(8):
            self._completed(make_customer(), driver, distance_m=300, duration_s=90)
        self.assertEqual(Detectors.short_trip_farming(), 1)
        self.assertTrue(_signals(driver.user, registry.SHORT_TRIP_FARMING.code).exists())

    def test_route_inflation_uses_estimate_when_routing_is_off(self):
        trip = self._completed(make_customer(), make_driver(), distance_m=9000, duration_s=1500)
        trip.ride.route_distance_km = None
        trip.ride.estimated_distance_km = Decimal("3.00")
        trip.ride.save(update_fields=["route_distance_km", "estimated_distance_km"])
        self.assertIsNotNone(Detectors.route_inflation_for_trip(trip))

    def test_route_inflation(self):
        driver = make_driver()
        trip = self._completed(make_customer(), driver, distance_m=9000, duration_s=1500, route_km="3.00")
        signal = Detectors.route_inflation_for_trip(trip)
        self.assertIsNotNone(signal)
        self.assertEqual(signal.evidence["ratio"], 3.0)

    def test_small_detour_is_fine(self):
        trip = self._completed(make_customer(), make_driver(), distance_m=4000, duration_s=700, route_km="3.00")
        self.assertIsNone(Detectors.route_inflation_for_trip(trip))

    def test_run_all_survives_a_broken_detector(self):
        with patch.object(Detectors, "short_trip_farming", side_effect=RuntimeError("x")):
            results = Detectors.run_all()
        self.assertEqual(results["short_trip_farming"], "error")
        self.assertIn("route_inflation", results)
