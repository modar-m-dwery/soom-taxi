import threading

from django.contrib.gis.geos import Point
from django.db import connections
from django.test import TransactionTestCase
from django.utils import timezone

from users.models import User, DriverProfile, UserRole
from vehicles.models import Vehicle, VehicleType
from rides.models import RideRequest, RideMode, RideStatus
from matching.models import RideOffer, OfferStatus
from matching.services.matching import MatchingService


class SelectOfferRaceConditionTests(TransactionTestCase):
    """
    يتحقق أن استدعاء select_offer مرتين بالتوازي (نفس الرحلة، عرضان مختلفان)
    ينجح لعرض واحد فقط، بفضل select_for_update.
    """

    def setUp(self):
        self.customer = User.objects.create_user(
            phone="+RACE_CUSTOMER", password="x",
            role=UserRole.CUSTOMER, is_verified=True,
        )

        self.ride = RideRequest.objects.create(
            customer=self.customer,
            pickup=Point(31.235, 30.044, srid=4326),
            destination=Point(31.32, 30.07, srid=4326),
            mode=RideMode.STANDARD,
            passenger_count=1,
            status=RideStatus.OFFERS_RECEIVED,
        )

        self.offers = []
        for i in range(2):
            user = User.objects.create_user(
                phone=f"+RACE_DRIVER_{i}", password="x", role=UserRole.DRIVER,
            )
            driver = DriverProfile.objects.create(
                user=user, status=DriverProfile.DriverStatus.ACTIVE,
                online=True, current_location=Point(31.24, 30.045, srid=4326),
                available_seats=4, last_location_at=timezone.now(),
            )
            offer = RideOffer.objects.create(
                ride=self.ride, driver=driver,
                gross_fare=40 + i, eta_minutes=5,
                status=OfferStatus.PENDING,
                expires_at=timezone.now() + timezone.timedelta(minutes=5),
            )
            self.offers.append(offer)

    def test_only_one_select_offer_wins(self):
        results = {}

        def try_select(offer, key):
            try:
                MatchingService.select_offer(
                    ride_id=self.ride.id,
                    offer_id=offer.id,
                    customer=self.customer,
                )
                results[key] = "success"
            except Exception as exc:
                results[key] = f"failed: {exc}"
            finally:
                connections.close_all()  # مهم في threads منفصلة

        t1 = threading.Thread(target=try_select, args=(self.offers[0], "t1"))
        t2 = threading.Thread(target=try_select, args=(self.offers[1], "t2"))

        t1.start()
        t2.start()
        t1.join()
        t2.join()

        successes = [k for k, v in results.items() if v == "success"]
        self.assertEqual(len(successes), 1, f"النتائج: {results}")

        self.ride.refresh_from_db()
        self.assertEqual(self.ride.status, RideStatus.DRIVER_SELECTED)