"""
«الزبون لم يحضر» وتعويض المشوار الفاضي.

السائق وصل (الخادم تحقّق) وانتظر، ثمّ ألغى الزبون أو لم يحضر: الإلغاء لا
يُحسب على السائق، والمنصّة تعوّضه من حسابها — لا غرامة على الزبون.
"""
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from config.testkit import JABLEH, auth, make_customer, make_driver
from integrity.models import RiskLevel
from integrity.services.scoring import IntegrityService
from payments.models import DriverBalance, LedgerAccount, LedgerEntry, LedgerEntryType
from payments.services.ledger import LedgerService
from rides.models import RideStatus
from trips.models import CancellationKind, CancellationRecord, DriverCancelReason
from trips.services.cancellation import CancellationPolicy
from trips.services.compensation import WastedTripCompensation
from trips.services.trip import TripError, TripService
from locations.tests.test_dynamic_config import make_area
from trips.tests.test_cancellation import _assigned as _assigned_bare

NO_SHOW = DriverCancelReason.CUSTOMER_NO_SHOW
BASE_FARE = Decimal("4000.00")


def _assigned(**kwargs):
    """رحلة بسائقٍ مثبَّت، في منطقة جبلة، وأجرة فتح عدّاد 4000."""
    ride, trip, driver = _assigned_bare(**kwargs)
    ride.service_area = make_area()
    ride.base_fare = BASE_FARE
    ride.save(update_fields=["service_area", "base_fare"])
    trip.refresh_from_db()
    return ride, trip, driver


def _no_show(ride, driver):
    return TripService.cancel(
        ride_id=ride.id, actor="driver", reason="الزبون لم يحضر",
        reason_code=NO_SHOW, driver=driver,
    )


def _balance(driver):
    row = DriverBalance.objects.filter(driver=driver, currency="SYP").first()
    return row.net_balance if row else Decimal("0.00")


class NoShowTests(TestCase):

    def test_rejected_before_arrival(self):
        ride, _, driver = _assigned(minutes_ago=10)
        with self.assertRaises(TripError):
            _no_show(ride, driver)
        self.assertFalse(CancellationRecord.objects.filter(ride=ride).exists())

    def test_rejected_before_wait_is_over(self):
        ride, _, driver = _assigned(minutes_ago=10, arrived_minutes_ago=2)
        with self.assertRaisesMessage(TripError, "بقي 3 د"):
            _no_show(ride, driver)

    def test_counts_against_customer_not_driver(self):
        ride, _, driver = _assigned(minutes_ago=15, arrived_minutes_ago=6)
        _no_show(ride, driver)

        record = CancellationRecord.objects.get(ride=ride)
        self.assertEqual((record.actor, record.kind, record.strikes), ("driver", CancellationKind.NO_SHOW, 2))
        self.assertEqual(CancellationPolicy.customer_strikes(ride.customer), 2)

        # الطلب يُغلق — لا يعود للبحث عن زبونٍ لم يحضر.
        ride.refresh_from_db()
        self.assertEqual(ride.status, RideStatus.CANCELLED)

    def test_no_shows_never_block_the_driver(self):
        driver = make_driver(location=JABLEH)
        for _ in range(5):
            ride, _, _ = _assigned(driver=driver, minutes_ago=15, arrived_minutes_ago=6)
            _no_show(ride, driver)
        self.assertIsNone(CancellationPolicy.driver_block_until(driver))

    def test_endpoint_accepts_reason_code(self):
        ride, _, driver = _assigned(minutes_ago=15, arrived_minutes_ago=6)
        client = APIClient()
        auth(client, driver)
        response = client.post(
            f"/api/v1/driver/rides/{ride.id}/cancel/",
            {"reason": "الزبون لم يحضر", "reason_code": "customer_no_show"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(CancellationRecord.objects.get(ride=ride).kind, CancellationKind.NO_SHOW)

    def test_endpoint_explains_early_no_show(self):
        ride, _, driver = _assigned(minutes_ago=10, arrived_minutes_ago=1)
        client = APIClient()
        auth(client, driver)
        response = client.post(
            f"/api/v1/driver/rides/{ride.id}/cancel/",
            {"reason": "الزبون لم يحضر", "reason_code": "customer_no_show"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("بقي", response.json()["detail"])


class CompensationTests(TestCase):

    def test_no_show_compensates_driver_from_platform(self):
        ride, trip, driver = _assigned(minutes_ago=15, arrived_minutes_ago=6)
        expected = WastedTripCompensation.amount_for(trip)
        self.assertEqual(expected, BASE_FARE, "الافتراضي: أجرة فتح العدّاد")

        _no_show(ride, driver)

        record = CancellationRecord.objects.get(ride=ride)
        self.assertEqual(record.driver_compensation, expected)
        self.assertEqual(_balance(driver), expected)

        entries = LedgerEntry.objects.filter(entry_type=LedgerEntryType.COMPENSATION)
        self.assertEqual(entries.count(), 2)
        self.assertIsNone(entries.first().payment_id)
        LedgerService.assert_balanced(entries.first().transaction_ref)
        self.assertEqual(
            LedgerService.account_balance(LedgerAccount.DRIVER, driver.id), expected,
        )

    def test_customer_cancel_after_wait_compensates(self):
        ride, _, driver = _assigned(minutes_ago=15, arrived_minutes_ago=6)
        TripService.cancel(ride_id=ride.id, actor="customer", reason="تأخّرت")
        self.assertGreater(CancellationRecord.objects.get(ride=ride).driver_compensation, 0)

    def test_early_cancels_are_not_compensated(self):
        # قبل الوصول، وبعد الوصول بلا انتظار كامل: لا مشوار فاضيًا بعد.
        for kwargs in ({"minutes_ago": 4}, {"minutes_ago": 10, "arrived_minutes_ago": 2}):
            ride, _, driver = _assigned(**kwargs)
            TripService.cancel(ride_id=ride.id, actor="customer", reason="غيّرت رأيي")
            self.assertEqual(CancellationRecord.objects.get(ride=ride).driver_compensation, 0)
            self.assertEqual(_balance(driver), 0)

    def test_area_amount_overrides_base_fare(self):
        ride, trip, driver = _assigned(minutes_ago=15, arrived_minutes_ago=6)
        area = ride.service_area
        area.wasted_trip_compensation = Decimal("1500")
        area.save(update_fields=["wasted_trip_compensation"])
        _no_show(ride, driver)
        self.assertEqual(_balance(driver), Decimal("1500.00"))

    def test_zero_disables(self):
        ride, _, driver = _assigned(minutes_ago=15, arrived_minutes_ago=6)
        area = ride.service_area
        area.wasted_trip_compensation = Decimal("0")
        area.save(update_fields=["wasted_trip_compensation"])
        _no_show(ride, driver)
        self.assertEqual(_balance(driver), 0)
        self.assertEqual(CancellationRecord.objects.get(ride=ride).kind, CancellationKind.NO_SHOW)

    def test_same_pair_compensated_once_per_window(self):
        customer = make_customer()
        driver = make_driver(location=JABLEH)
        paid = []
        for _ in range(2):
            ride, _, _ = _assigned(customer=customer, driver=driver, minutes_ago=15, arrived_minutes_ago=6)
            _no_show(ride, driver)
            paid.append(CancellationRecord.objects.get(ride=ride).driver_compensation)
        self.assertGreater(paid[0], 0)
        self.assertEqual(paid[1], 0)

    def test_daily_cap_per_driver(self):
        driver = make_driver(location=JABLEH)
        ride, _, _ = _assigned(driver=driver, minutes_ago=15, arrived_minutes_ago=6)
        area = ride.service_area
        area.wasted_trip_compensation_daily_cap = 2
        area.save(update_fields=["wasted_trip_compensation_daily_cap"])

        _no_show(ride, driver)
        for _ in range(2):
            ride, _, _ = _assigned(driver=driver, minutes_ago=15, arrived_minutes_ago=6)
            _no_show(ride, driver)
        paid = CancellationRecord.objects.filter(driver=driver, driver_compensation__gt=0).count()
        self.assertEqual(paid, 2)

    def test_restricted_driver_not_compensated(self):
        ride, _, driver = _assigned(minutes_ago=15, arrived_minutes_ago=6)
        IntegrityService.set_manual_level(driver.user, RiskLevel.RESTRICTED)
        _no_show(ride, driver)
        self.assertEqual(_balance(driver), 0)

    def test_compensation_offsets_commission_debt(self):
        ride, trip, driver = _assigned(minutes_ago=15, arrived_minutes_ago=6)
        LedgerService.apply_to_driver_balance(driver.id, "SYP", Decimal("-5000.00"))
        _no_show(ride, driver)
        self.assertEqual(_balance(driver), Decimal("-5000.00") + WastedTripCompensation.amount_for(trip))


class NoShowIntegrityTests(TestCase):

    def test_repeated_no_show_same_pair_is_flagged(self):
        from integrity.models import RiskSignal

        customer = make_customer()
        driver = make_driver(location=JABLEH)
        with self.captureOnCommitCallbacks(execute=True):
            for _ in range(2):
                ride, _, _ = _assigned(customer=customer, driver=driver, minutes_ago=15, arrived_minutes_ago=6)
                _no_show(ride, driver)

        kinds = set(RiskSignal.objects.filter(user=driver.user).values_list("kind", flat=True))
        self.assertIn("off_app_suspected", kinds)
        customer_kinds = set(RiskSignal.objects.filter(user=customer).values_list("kind", flat=True))
        self.assertIn("repeated_no_show", customer_kinds)

    def test_no_show_does_not_raise_driver_cancel_rate(self):
        from integrity.services.detectors import Detectors

        driver = make_driver(location=JABLEH)
        for _ in range(9):
            ride, _, _ = _assigned(driver=driver, minutes_ago=15, arrived_minutes_ago=6)
            _no_show(ride, driver)
        self.assertEqual(Detectors.driver_cancel_rate(driver=driver), 0)


class CompensationVisibleToDriverTests(TestCase):

    def test_no_show_response_carries_compensation(self):
        ride, _, driver = _assigned(minutes_ago=15, arrived_minutes_ago=6)
        client = APIClient()
        auth(client, driver)
        body = client.post(
            f"/api/v1/driver/rides/{ride.id}/cancel/",
            {"reason": "الزبون لم يحضر", "reason_code": "customer_no_show"},
            format="json",
        ).json()
        self.assertEqual(body["driver_compensation"], "4000.00")

    def test_ordinary_cancel_has_none(self):
        ride, _, driver = _assigned(minutes_ago=2)
        client = APIClient()
        auth(client, driver)
        body = client.post(
            f"/api/v1/driver/rides/{ride.id}/cancel/", {"reason": "عطل بالسيارة"}, format="json",
        ).json()
        self.assertIsNone(body["driver_compensation"])
