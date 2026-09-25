from decimal import Decimal

from django.contrib.gis.geos import Point
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework import status
from rest_framework.authtoken.models import Token

from users.models import User, DriverProfile, UserRole
from vehicles.models import Vehicle, VehicleType
from rides.models import RideRequest, RideMode, RideStatus
from matching.models import RideOffer, OfferStatus


class RideOfferApiFlowTests(APITestCase):

    def setUp(self):
        self.customer = User.objects.create_user(
            phone="+API_CUSTOMER", password="x",
            role=UserRole.CUSTOMER, is_verified=True,
        )
        self.driver_user = User.objects.create_user(
            phone="+API_DRIVER", password="x", role=UserRole.DRIVER,
        )
        self.driver = DriverProfile.objects.create(
            user=self.driver_user,
            status=DriverProfile.DriverStatus.ACTIVE,
            online=True,
            current_location=Point(31.24, 30.045, srid=4326),
            available_seats=4,
            last_location_at=timezone.now(),
        )
        Vehicle.objects.create(
            driver=self.driver, type_id=VehicleType.SEDAN,
            make="Toyota", model="Corolla", year=2020,
            color="White", plate_number="API-0001",
            seats=4, active=True,
        )

        self.customer_token = Token.objects.create(user=self.customer)
        self.driver_token = Token.objects.create(user=self.driver_user)

        self.ride = RideRequest.objects.create(
            customer=self.customer,
            pickup=Point(31.235, 30.044, srid=4326),
            destination=Point(31.32, 30.07, srid=4326),
            mode=RideMode.STANDARD,
            passenger_count=1,
            status=RideStatus.SEARCHING,
        )

    def auth(self, token):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    def test_driver_sees_candidate_ride(self):
        self.auth(self.driver_token)
        response = self.client.get("/api/v1/driver/rides/candidates/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ride_ids = [r["id"] for r in response.data]
        self.assertIn(self.ride.id, ride_ids)

    def test_driver_submits_offer_then_customer_selects_it(self):
        self.auth(self.driver_token)
        response = self.client.post(
            f"/api/v1/driver/rides/{self.ride.id}/offers/",
            {"gross_fare": "45.00", "eta_minutes": 8},
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        offer_id = response.data["id"]

        self.ride.refresh_from_db()
        self.assertEqual(self.ride.status, RideStatus.OFFERS_RECEIVED)

        self.auth(self.customer_token)
        response = self.client.get(
            f"/api/v1/customer/rides/{self.ride.id}/offers/"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

        response = self.client.post(
            f"/api/v1/customer/rides/{self.ride.id}/offers/{offer_id}/select/"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], OfferStatus.ACCEPTED)

        self.ride.refresh_from_db()
        self.assertEqual(self.ride.status, RideStatus.DRIVER_SELECTED)

    def test_customer_cannot_see_other_customers_ride(self):
        other_customer = User.objects.create_user(
            phone="+API_CUSTOMER_2", password="x",
            role=UserRole.CUSTOMER, is_verified=True,
        )
        other_token = Token.objects.create(user=other_customer)
        self.auth(other_token)
        response = self.client.get(
            f"/api/v1/customer/rides/{self.ride.id}/offers/"
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_driver_cannot_submit_offer_when_offline(self):
        self.driver.online = False
        self.driver.save(update_fields=["online"])

        self.auth(self.driver_token)
        response = self.client.post(
            f"/api/v1/driver/rides/{self.ride.id}/offers/",
            {"gross_fare": "45.00", "eta_minutes": 8},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)