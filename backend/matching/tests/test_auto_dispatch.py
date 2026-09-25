"""
«الأقرب» ونطاق البحث الذي يختاره الزبون.

الحالات الساقطة هنا أهمّ من المسار السعيد: سائقٌ يرفض، سائقٌ يصمت،
نداءٌ مكرَّر من الرفض والانتهاء معًا، قائمةٌ فارغة، حدّ المحاولات، وقبولٌ
يجب أن يوقف السلسلة.
"""

from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.contrib.gis.geos import Point
from django.test import TestCase
from django.utils import timezone

from matching.models import InvitationStatus, RideInvitation
from matching.services.auto_dispatch import AutoDispatchService
from matching.services.invitation import InvitationService
from matching.services.matching import MatchingService
from rides.models import RideMode, RideRequest, RideStatus
from rides.services.ride_request import (
    RideRequestService,
    RideRequestValidationError,
)
from users.models import DriverProfile, User, UserRole
from vehicles.models import Vehicle, VehicleType

NEARBY = "matching.services.nearby.NearbyVehiclesService.for_ride"


class AutoDispatchTests(TestCase):

    def setUp(self):
        self.customer = User.objects.create_user(
            phone="+AD_CUSTOMER", password="x",
            role=UserRole.CUSTOMER, is_verified=True,
        )
        self.drivers = [self._driver(i) for i in range(3)]
        self.ride = RideRequest.objects.create(
            customer=self.customer,
            pickup=Point(31.235, 30.044, srid=4326),
            destination=Point(31.32, 30.07, srid=4326),
            mode=RideMode.FAST,
            passenger_count=1,
            status=RideStatus.SEARCHING,
            expires_at=timezone.now() + timedelta(minutes=10),
            auto_dispatch=True,
        )

    def _driver(self, index):
        user = User.objects.create_user(
            phone=f"+AD_DRIVER_{index}", password="x", role=UserRole.DRIVER,
        )
        driver = DriverProfile.objects.create(
            user=user,
            status=DriverProfile.DriverStatus.ACTIVE,
            online=True,
            current_location=Point(31.24, 30.045, srid=4326),
            available_seats=4,
            last_location_at=timezone.now(),
        )
        Vehicle.objects.create(
            driver=driver, type_id=VehicleType.SEDAN,
            make="Kia", model="Rio", year=2019, color="White",
            plate_number=f"AD-{index}", seats=4, active=True,
        )
        return driver

    def _nearby(self, *drivers):
        return [{"driver_id": d.id, "is_sharing": False} for d in drivers]

    def _pending(self):
        return list(
            RideInvitation.objects.filter(
                ride=self.ride, status=InvitationStatus.PENDING
            )
        )

    # -------------------------------------------------------------

    def test_invites_nearest_with_area_ttl(self):
        with mock.patch(NEARBY, return_value=self._nearby(*self.drivers)):
            invitation = AutoDispatchService.advance(self.ride.id)

        self.assertEqual(invitation.driver_id, self.drivers[0].id)
        # بلا منطقة: الافتراض 15 ثانية، لا قائمة الزبون [20, 40, 60].
        self.assertEqual(invitation.ttl_seconds, 15)

    def test_reject_moves_to_next_driver(self):
        with mock.patch(NEARBY, return_value=self._nearby(*self.drivers)):
            first = AutoDispatchService.advance(self.ride.id)
            with self.captureOnCommitCallbacks(execute=True):
                InvitationService.reject(first.id, self.drivers[0])

        pending = self._pending()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].driver_id, self.drivers[1].id)

    def test_silence_moves_to_next_driver(self):
        with mock.patch(NEARBY, return_value=self._nearby(*self.drivers)):
            first = AutoDispatchService.advance(self.ride.id)
            RideInvitation.objects.filter(id=first.id).update(
                expires_at=timezone.now() - timedelta(seconds=1)
            )
            with self.captureOnCommitCallbacks(execute=True):
                self.assertTrue(InvitationService.expire(first.id))

        pending = self._pending()
        self.assertEqual([p.driver_id for p in pending], [self.drivers[1].id])

    def test_repeated_calls_do_not_double_invite(self):
        with mock.patch(NEARBY, return_value=self._nearby(*self.drivers)):
            AutoDispatchService.advance(self.ride.id)
            self.assertIsNone(AutoDispatchService.advance(self.ride.id))

        self.assertEqual(len(self._pending()), 1)

    def test_skips_driver_who_became_ineligible(self):
        DriverProfile.objects.filter(id=self.drivers[0].id).update(online=False)

        with mock.patch(NEARBY, return_value=self._nearby(*self.drivers)):
            invitation = AutoDispatchService.advance(self.ride.id)

        self.assertEqual(invitation.driver_id, self.drivers[1].id)

    def test_no_drivers_falls_back_to_offers(self):
        with mock.patch(NEARBY, return_value=[]):
            with self.captureOnCommitCallbacks(execute=True):
                self.assertIsNone(AutoDispatchService.advance(self.ride.id))

        self.ride.refresh_from_db()
        self.assertFalse(self.ride.auto_dispatch)
        # الطلب لم يُلغَ: يبقى مفتوحًا لعروض السائقين.
        self.assertEqual(self.ride.status, RideStatus.SEARCHING)

    def test_stops_after_max_attempts(self):
        with mock.patch(
            "matching.services.auto_dispatch.AutoDispatchService.settings_for",
            return_value=(15, 2),
        ), mock.patch(NEARBY, return_value=self._nearby(*self.drivers)):
            first = AutoDispatchService.advance(self.ride.id)
            with self.captureOnCommitCallbacks(execute=True):
                InvitationService.reject(first.id, self.drivers[0])
            second = self._pending()[0]
            with self.captureOnCommitCallbacks(execute=True):
                InvitationService.reject(second.id, self.drivers[1])

        self.assertEqual(self._pending(), [])
        self.ride.refresh_from_db()
        self.assertFalse(self.ride.auto_dispatch)

    def test_accept_ends_the_chain(self):
        with mock.patch(NEARBY, return_value=self._nearby(*self.drivers)):
            first = AutoDispatchService.advance(self.ride.id)
            InvitationService.accept(first.id, self.drivers[0])
            self.assertIsNone(AutoDispatchService.advance(self.ride.id))

        self.ride.refresh_from_db()
        self.assertEqual(self.ride.status, RideStatus.DRIVER_SELECTED)

    def test_plain_ride_is_never_auto_dispatched(self):
        RideRequest.objects.filter(id=self.ride.id).update(auto_dispatch=False)

        with mock.patch(NEARBY, return_value=self._nearby(*self.drivers)):
            self.assertIsNone(AutoDispatchService.advance(self.ride.id))

        self.assertEqual(self._pending(), [])


class SearchRadiusTests(TestCase):

    def setUp(self):
        self.customer = User.objects.create_user(
            phone="+SR_CUSTOMER", password="x",
            role=UserRole.CUSTOMER, is_verified=True,
        )
        user = User.objects.create_user(
            phone="+SR_DRIVER", password="x", role=UserRole.DRIVER,
        )
        # ~0.49 كم عن نقطة الالتقاط.
        self.driver = DriverProfile.objects.create(
            user=user,
            status=DriverProfile.DriverStatus.ACTIVE,
            online=True,
            current_location=Point(31.24, 30.045, srid=4326),
            available_seats=4,
            last_location_at=timezone.now(),
        )
        Vehicle.objects.create(
            driver=self.driver, type_id=VehicleType.SEDAN,
            make="Kia", model="Rio", year=2019, color="White",
            plate_number="SR-1", seats=4, active=True,
        )

    def _ride(self, radius):
        return RideRequest.objects.create(
            customer=self.customer,
            pickup=Point(31.235, 30.044, srid=4326),
            destination=Point(31.32, 30.07, srid=4326),
            mode=RideMode.STANDARD,
            passenger_count=1,
            status=RideStatus.SEARCHING,
            search_radius_km=radius,
        )

    def _candidate_ids(self):
        return set(
            MatchingService.get_eligible_rides_for_driver(self.driver)
            .values_list("id", flat=True)
        )

    def test_driver_outside_customer_radius_does_not_see_ride(self):
        narrow = self._ride(Decimal("0.30"))
        wide = self._ride(Decimal("1.00"))
        default = self._ride(None)

        ids = self._candidate_ids()

        self.assertNotIn(narrow.id, ids)
        self.assertIn(wide.id, ids)
        self.assertIn(default.id, ids)

    def test_matching_radius_follows_customer_choice(self):
        self.assertEqual(MatchingService.get_radius_km(self._ride(Decimal("3"))), 3.0)

    def test_radius_must_be_one_of_area_options(self):
        area = mock.Mock(effective_search_radius_options_km=[1.0, 3.0, 5.0])

        self.assertEqual(
            RideRequestService.resolve_search_radius(area, 3), Decimal("3.00")
        )
        with self.assertRaises(RideRequestValidationError):
            RideRequestService.resolve_search_radius(area, 2)

    def test_radius_ignored_when_area_offers_no_choice(self):
        area = mock.Mock(effective_search_radius_options_km=[])
        self.assertIsNone(RideRequestService.resolve_search_radius(area, 3))
        self.assertIsNone(RideRequestService.resolve_search_radius(None, 3))
