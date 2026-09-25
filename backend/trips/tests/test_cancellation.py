"""
سياسة الإلغاء بعد تثبيت السائق، وعودة الطلب إلى البحث حين يلغي السائق،
ورحلات الركّاب المنضمّين إلى رحلة مشتركة.
"""
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from config.testkit import (
    JABLEH,
    auth,
    make_accepted_offer,
    make_customer,
    make_driver,
    make_ride,
    make_trip,
)
from matching.models import OfferStatus, RideOffer
from matching.services.matching import MatchingService
from rides.models import RideMode, RideStatus
from rides.services.ride_request import RideRequestService, RideRequestValidationError
from trips.models import CancellationKind, CancellationRecord, Trip, TripStatus
from trips.services.cancellation import CancellationPolicy
from trips.services.resume import ResumeService
from trips.services.trip import TripService


def _assigned(customer=None, driver=None, minutes_ago=0, arrived_minutes_ago=None, eta=3):
    customer = customer or make_customer()
    driver = driver or make_driver(location=JABLEH)
    ride = make_ride(customer, status=RideStatus.DRIVER_ARRIVING)
    offer = make_accepted_offer(ride, driver, eta_minutes=eta)
    now = timezone.now()
    trip = make_trip(
        ride, driver,
        status=TripStatus.DRIVER_ARRIVED if arrived_minutes_ago is not None else TripStatus.DRIVER_ARRIVING,
        offer=offer,
        arriving_at=now - timedelta(minutes=minutes_ago),
        arrived_at=(now - timedelta(minutes=arrived_minutes_ago)) if arrived_minutes_ago is not None else None,
    )
    return ride, trip, driver


class CustomerCancellationClassificationTests(TestCase):

    def test_within_free_window_is_free(self):
        _, trip, _ = _assigned(minutes_ago=1)
        self.assertEqual(CancellationPolicy.classify_customer(trip), (CancellationKind.FREE, 0))

    def test_driver_late_is_free(self):
        # ETA 3 + سماح 5 = 8 دقائق؛ مضت 12 ولم يصل.
        _, trip, _ = _assigned(minutes_ago=12, eta=3)
        self.assertEqual(
            CancellationPolicy.classify_customer(trip), (CancellationKind.DRIVER_LATE, 0)
        )

    def test_driver_on_time_is_one_strike(self):
        _, trip, _ = _assigned(minutes_ago=4, eta=3)
        self.assertEqual(CancellationPolicy.classify_customer(trip), (CancellationKind.LATE, 1))

    def test_after_driver_waited_is_two_strikes(self):
        _, trip, _ = _assigned(minutes_ago=15, arrived_minutes_ago=6)
        self.assertEqual(
            CancellationPolicy.classify_customer(trip), (CancellationKind.AFTER_WAIT, 2)
        )

    def test_cancel_records_kind(self):
        ride, trip, _ = _assigned(minutes_ago=4, eta=3)
        TripService.cancel(ride_id=ride.id, actor="customer", reason="غيّرت رأيي")
        record = CancellationRecord.objects.get(ride=ride)
        self.assertEqual((record.kind, record.strikes), (CancellationKind.LATE, 1))
        ride.refresh_from_db()
        self.assertEqual(ride.status, RideStatus.CANCELLED)


class CustomerPenaltyTests(TestCase):

    def setUp(self):
        self.customer = make_customer()

    def _late_cancel(self):
        ride, _, _ = _assigned(customer=self.customer, minutes_ago=4)
        TripService.cancel(ride_id=ride.id, actor="customer")

    def test_below_limit_no_penalty(self):
        self._late_cancel()
        self._late_cancel()
        self.assertIsNone(CancellationPolicy.customer_penalty_until(self.customer))

    def test_reaching_limit_penalises(self):
        for _ in range(3):
            self._late_cancel()
        self.assertIsNotNone(CancellationPolicy.customer_penalty_until(self.customer))

    def test_free_cancellations_never_count(self):
        for _ in range(5):
            ride, _, _ = _assigned(customer=self.customer, minutes_ago=0)
            TripService.cancel(ride_id=ride.id, actor="customer")
        self.assertEqual(CancellationPolicy.customer_strikes(self.customer), 0)

    def test_old_strikes_expire(self):
        for _ in range(3):
            self._late_cancel()
        CancellationRecord.objects.update(created_at=timezone.now() - timedelta(days=8))
        self.assertIsNone(CancellationPolicy.customer_penalty_until(self.customer))

    def test_penalised_customer_cannot_use_nearest(self):
        for _ in range(3):
            self._late_cancel()
        with patch("locations.services.LocationService.resolve_area", return_value=None):
            with self.assertRaises(RideRequestValidationError):
                RideRequestService.create_ride_request(
                    customer=self.customer,
                    pickup=make_ride(make_customer()).pickup,
                    destination=make_ride(make_customer()).destination,
                    mode=RideMode.FAST,
                    passenger_count=1,
                    auto_dispatch=True,
                )


class DriverCancellationTests(TestCase):

    def test_driver_cancel_requeues_ride_for_customer(self):
        ride, trip, driver = _assigned(minutes_ago=2)
        TripService.cancel(ride_id=ride.id, actor="driver", reason="عطل", driver=driver)

        ride.refresh_from_db()
        self.assertEqual(ride.status, RideStatus.SEARCHING)
        self.assertGreater(ride.expires_at, timezone.now())
        self.assertFalse(
            RideOffer.objects.filter(ride=ride, driver=driver, status=OfferStatus.ACCEPTED).exists()
        )

    def test_cancelling_driver_cannot_offer_on_same_ride_again(self):
        ride, _, driver = _assigned(minutes_ago=2)
        TripService.cancel(ride_id=ride.id, actor="driver", reason="عطل", driver=driver)
        ride.refresh_from_db()
        driver.refresh_from_db()
        self.assertFalse(MatchingService.can_driver_submit_offer(ride=ride, driver=driver))

    def test_new_driver_takes_over_same_trip_record(self):
        ride, trip, driver = _assigned(minutes_ago=2)
        TripService.cancel(ride_id=ride.id, actor="driver", reason="عطل", driver=driver)
        ride.refresh_from_db()

        other = make_driver(location=JABLEH)
        offer = make_accepted_offer(ride, other)
        new_trip = TripService.ensure_trip(ride, offer=offer)

        self.assertEqual(new_trip.pk, trip.pk)
        self.assertEqual(new_trip.driver_id, other.id)
        self.assertEqual(new_trip.status, TripStatus.DRIVER_ARRIVING)

    def test_driver_blocked_after_daily_limit(self):
        driver = make_driver(location=JABLEH)
        for _ in range(4):
            ride, _, _ = _assigned(driver=driver, minutes_ago=1)
            TripService.cancel(ride_id=ride.id, actor="driver", reason="عطل", driver=driver)
        self.assertIsNotNone(CancellationPolicy.driver_block_until(driver))

        fresh = make_ride(make_customer())
        driver.refresh_from_db()
        self.assertFalse(MatchingService.can_driver_submit_offer(ride=fresh, driver=driver))

    def test_driver_cancel_endpoint_requires_reason(self):
        ride, _, driver = _assigned(minutes_ago=2)
        from rest_framework.test import APIClient

        client = APIClient()
        auth(client, driver)
        url = f"/api/v1/driver/rides/{ride.id}/cancel/"
        self.assertEqual(client.post(url, {}).status_code, 400)
        self.assertEqual(client.post(url, {"reason": "عطل بالسيارة"}).status_code, 200)

    def test_other_driver_cannot_cancel(self):
        ride, _, _ = _assigned(minutes_ago=2)
        from rest_framework.test import APIClient

        client = APIClient()
        auth(client, make_driver(location=JABLEH))
        response = client.post(f"/api/v1/driver/rides/{ride.id}/cancel/", {"reason": "تجربة"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Trip.objects.get(ride=ride).status, TripStatus.DRIVER_ARRIVING)


class DriverMultiTripSnapshotTests(TestCase):

    def test_driver_sees_every_active_passenger(self):
        driver = make_driver(location=JABLEH)
        first, _, _ = _assigned(driver=driver, minutes_ago=3)
        second, _, _ = _assigned(driver=driver, minutes_ago=1)

        snapshot = ResumeService.snapshot(driver.user)
        ids = {snapshot["ride"].id} | {entry["ride"].id for entry in snapshot["other_trips"]}
        self.assertEqual(ids, {first.id, second.id})

    def test_customer_snapshot_has_no_other_trips(self):
        ride, _, _ = _assigned(minutes_ago=1)
        self.assertEqual(ResumeService.snapshot(ride.customer)["other_trips"], [])


class SharedMemberTripTests(TestCase):

    def test_joined_passenger_gets_own_trip_with_own_fare(self):
        from matching.models import SharedGroupStatus, SharedRideGroup, SharedRideGroupMember
        from matching.services.shared_matching import SharedMatchingService

        driver = make_driver(location=JABLEH)
        host = make_ride(make_customer(), mode=RideMode.SHARED, status=RideStatus.DRIVER_SELECTED)
        member = make_ride(
            make_customer(), mode=RideMode.SHARED,
            status=RideStatus.SEARCHING, gross_fare="12000.00",
        )
        offer = make_accepted_offer(host, driver)
        group = SharedRideGroup.objects.create(
            host_offer=offer, driver=driver,
            vehicle=driver.vehicles.first(), status=SharedGroupStatus.ACTIVE,
        )
        SharedRideGroupMember.objects.create(group=group, ride=host, is_host=True)
        SharedRideGroupMember.objects.create(group=group, ride=member)

        SharedMatchingService.propagate_status_to_members(host, RideStatus.DRIVER_SELECTED)

        trip = Trip.objects.get(ride=member)
        self.assertEqual(trip.driver_id, driver.id)
        self.assertEqual(str(trip.final_fare), "12000.00")
        # والسائق يرى الراكبين معًا.
        snapshot = ResumeService.snapshot(driver.user)
        ids = {snapshot["ride"].id} | {e["ride"].id for e in snapshot["other_trips"]}
        self.assertIn(member.id, ids)
