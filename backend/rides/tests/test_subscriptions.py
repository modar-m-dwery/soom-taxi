# -*- coding: utf-8 -*-
"""
اشتراك الصباح: صفٌّ واحد يولّد طلبًا مجدولًا كلّ يوم عمل قبل موعده بنصف ساعة.

يُثبَّت: التوقيت محلّيّ (دمشق)، الإنشاء مرّةً في اليوم، أيام العطلة تُتخطّى،
والطلب المجدول لا يمنع مشوار اليوم الفوريّ (ولا العكس).
"""

from datetime import date, datetime, time, timedelta, timezone as dt_timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.contrib.gis.geos import Point
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APITestCase

from config.testkit import auth, make_customer
from locations.models import ServiceArea
from locations.services import LocationService
from rides.models import RideRequest, RideStatus, RideSubscription
from rides.services.ride_request import RideRequestService
from rides.services.subscription import SubscriptionService

DAMASCUS = ZoneInfo("Asia/Damascus")
JAB = (35.9275, 35.3617)


def make_area():
    area, _ = ServiceArea.objects.update_or_create(
        code="JAB",
        defaults=dict(name="جبلة", center=Point(*JAB, srid=4326),
                      fallback_radius_km=Decimal("8"), is_active=True),
    )
    LocationService.invalidate_cache()
    return area


def local(year, month, day, hour, minute):
    """لحظة بتوقيت دمشق → UTC."""
    return datetime(year, month, day, hour, minute, tzinfo=DAMASCUS).astimezone(dt_timezone.utc)


def next_monday():
    """أوّل اثنين بعد أسبوع من اليوم — التواريخ الثابتة صارت ماضيًا بعد أيام
    من كتابة الفحص، و`create_ride_request` يرفض موعدًا مضى."""
    today = datetime.now(DAMASCUS).date()
    ahead = (7 - today.weekday()) % 7 + 7
    return today + timedelta(days=ahead)


class SubscriptionMaterializationTests(TestCase):
    def setUp(self):
        make_area()
        self.customer = make_customer()
        self.subscription = RideSubscription.objects.create(
            customer=self.customer, label="إلى الجامعة",
            pickup=Point(*JAB, srid=4326), destination=Point(35.9318, 35.3683, srid=4326),
            departure_time=time(7, 30), weekdays=[],  # فارغ = الأحد–الخميس
            passenger_count=1, lead_minutes=30,
        )

    def test_next_occurrence_skips_weekend_and_uses_local_time(self):
        # الخميس 2026-09-17 الساعة 8:00 محلّيًّا → التالي الأحد 7:30.
        now = local(2026, 9, 17, 8, 0)
        nxt = SubscriptionService.next_occurrence(self.subscription, now)
        self.assertEqual(nxt.astimezone(DAMASCUS), datetime(2026, 9, 20, 7, 30, tzinfo=DAMASCUS))

    def test_ride_is_created_within_lead_window_once(self):
        # الاثنين 7:05 محلّيًّا: بقيت 25 دقيقة < 30 → يُنشأ.
        mon = next_monday()
        now = local(mon.year, mon.month, mon.day, 7, 5)
        self.assertEqual(SubscriptionService.materialize_due(now), 1)

        ride = RideRequest.objects.get(subscription=self.subscription)
        self.assertEqual(ride.status, RideStatus.SEARCHING)
        self.assertEqual(ride.scheduled_at, local(mon.year, mon.month, mon.day, 7, 30))
        self.assertEqual(ride.customer, self.customer)

        # دورة ثانية بعد دقيقتين: لا طلب جديد.
        self.assertEqual(SubscriptionService.materialize_due(now + timedelta(minutes=2)), 0)
        self.assertEqual(RideRequest.objects.filter(subscription=self.subscription).count(), 1)

    def test_too_early_creates_nothing(self):
        mon = next_monday()
        now = local(mon.year, mon.month, mon.day, 6, 0)  # 90 دقيقة قبل الموعد
        self.assertEqual(SubscriptionService.materialize_due(now), 0)

    def test_inactive_subscription_is_ignored(self):
        self.subscription.is_active = False
        self.subscription.save()
        mon = next_monday()
        self.assertEqual(SubscriptionService.materialize_due(local(mon.year, mon.month, mon.day, 7, 5)), 0)

    def test_scheduled_ride_does_not_block_an_instant_ride(self):
        mon = next_monday()
        SubscriptionService.materialize_due(local(mon.year, mon.month, mon.day, 7, 5))
        instant = RideRequestService.create_ride_request(
            customer=self.customer,
            pickup=Point(*JAB, srid=4326), destination=Point(35.9318, 35.3683, srid=4326),
            mode="standard", passenger_count=1,
        )
        self.assertIsNone(instant.scheduled_at)
        self.assertEqual(
            RideRequest.objects.filter(customer=self.customer, status=RideStatus.SEARCHING).count(), 2,
        )


class SubscriptionApiTests(APITestCase):
    def setUp(self):
        make_area()
        self.customer = make_customer()
        auth(self.client, self.customer)

    def test_create_list_cancel(self):
        body = {
            "label": "إلى الجامعة",
            "pickup_lat": JAB[1], "pickup_lng": JAB[0],
            "destination_lat": 35.3683, "destination_lng": 35.9318,
            "departure_time": "07:30", "weekdays": [6, 0, 1, 2, 3],
            "mode": "standard", "passenger_count": 1, "requested_vehicle_type": "taxi",
        }
        created = self.client.post("/api/v1/rides/subscriptions/", body, format="json")
        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual(created.data["pickup"]["lat"], JAB[1])
        self.assertIsNotNone(created.data["next_occurrence"])
        sub_id = created.data["id"]

        listed = self.client.get("/api/v1/rides/subscriptions/")
        self.assertEqual(len(listed.data), 1)

        cancelled = self.client.delete(f"/api/v1/rides/subscriptions/{sub_id}/")
        self.assertEqual(cancelled.status_code, 200)
        self.assertFalse(cancelled.data["is_active"])
        self.assertEqual(len(self.client.get("/api/v1/rides/subscriptions/").data), 0)

    def test_unknown_vehicle_type_rejected(self):
        body = {
            "pickup_lat": JAB[1], "pickup_lng": JAB[0],
            "destination_lat": 35.3683, "destination_lng": 35.9318,
            "departure_time": "07:30", "requested_vehicle_type": "sedan",
        }
        response = self.client.post("/api/v1/rides/subscriptions/", body, format="json")
        self.assertEqual(response.status_code, 400)
