"""
استعادة الحالة والسجلّ والترقيم — النقاط التي يبني عليها تطبيق الموبايل.

تُختبر هنا ثلاثة أشياء لا يكشفها اختبار وحدة عادي:

  * أن `stage` تعبّر عن الحالة الحقيقية في كل مرحلة، لا في السعيدة فقط.
  * أن العزل بين المستخدمين محكم — أخطر تسريب في تطبيق نقل ركّاب هو أن
    يرى راكب رحلة راكب آخر.
  * أن شكل الاستجابة المرقَّمة ثابت، لأن التطبيق يُبنى عليه.
"""
from decimal import Decimal

from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from config.testkit import (
    JABLEH,
    auth,
    make_accepted_offer,
    make_completed_trip,
    make_customer,
    make_driver,
    make_ride,
    make_trip,
)
from rides.models import RideStatus
from trips.models import TripStatus
from trips.services.resume import ResumeService, Stage


# =====================================================================
# لقطة الحالة
# =====================================================================

class ResumeSnapshotTests(TestCase):

    def test_user_without_ride_gets_idle_not_error(self):
        """
        404 على سؤال «ما حالتي؟» يجبر التطبيق على معالجة الخطأ في أكثر
        مساراته شيوعًا. اللقطة الفارغة استجابة صالحة لا فشل.
        """
        snapshot = ResumeService.snapshot(make_customer())

        self.assertFalse(snapshot["has_active_ride"])
        self.assertEqual(snapshot["stage"], Stage.IDLE)
        self.assertIsNone(snapshot["ride"])
        self.assertIsNone(snapshot["trip"])

    def test_customer_searching(self):
        customer = make_customer()
        make_ride(customer, status=RideStatus.SEARCHING)

        snapshot = ResumeService.snapshot(customer)

        self.assertTrue(snapshot["has_active_ride"])
        self.assertEqual(snapshot["role"], "customer")
        self.assertEqual(snapshot["stage"], Stage.SEARCHING)

    def test_customer_choosing_offer(self):
        customer = make_customer()
        make_ride(customer, status=RideStatus.OFFERS_RECEIVED)

        self.assertEqual(
            ResumeService.snapshot(customer)["stage"], Stage.CHOOSING_OFFER
        )

    def test_trip_status_wins_over_ride_status(self):
        """الرحلة الجارية أدقّ من الطلب حين توجد — وهي مصدر المرحلة."""
        customer = make_customer()
        driver = make_driver()
        ride = make_ride(customer, status=RideStatus.DRIVER_SELECTED)
        make_trip(ride, driver, status=TripStatus.DRIVER_ARRIVED)

        self.assertEqual(
            ResumeService.snapshot(customer)["stage"], Stage.DRIVER_ARRIVED
        )

    def test_in_progress_stage(self):
        customer = make_customer()
        driver = make_driver()
        ride = make_ride(customer, status=RideStatus.IN_PROGRESS)
        make_trip(ride, driver, status=TripStatus.IN_PROGRESS)

        snapshot = ResumeService.snapshot(customer)

        self.assertEqual(snapshot["stage"], Stage.IN_PROGRESS)
        self.assertIsNotNone(snapshot["trip"])

    def test_completed_ride_is_not_active(self):
        customer = make_customer()
        make_ride(customer, status=RideStatus.COMPLETED)

        self.assertFalse(ResumeService.snapshot(customer)["has_active_ride"])

    def test_cancelled_and_expired_rides_are_not_active(self):
        customer = make_customer()
        make_ride(customer, status=RideStatus.CANCELLED)
        make_ride(customer, status=RideStatus.EXPIRED)

        self.assertEqual(ResumeService.snapshot(customer)["stage"], Stage.IDLE)

    # -- السائق --------------------------------------------------------

    def test_driver_sees_ride_only_through_accepted_offer(self):
        """
        نفس تعريف "سائق هذه الرحلة" المعتمد في المطابقة وغرف الزمن
        الحقيقي. تعريف مختلف هنا كان سيُظهر للتطبيق رحلة لا يراها
        بقيّة النظام.
        """
        customer = make_customer()
        driver = make_driver()
        ride = make_ride(customer, status=RideStatus.IN_PROGRESS)
        make_trip(ride, driver, status=TripStatus.IN_PROGRESS)

        before = ResumeService.snapshot(driver.user)
        self.assertFalse(before["has_active_ride"])

        make_accepted_offer(ride, driver)

        after = ResumeService.snapshot(driver.user)
        self.assertTrue(after["has_active_ride"])
        self.assertEqual(after["role"], "driver")
        self.assertEqual(after["stage"], Stage.IN_PROGRESS)

    def test_driver_rooms_include_own_driver_channel(self):
        customer = make_customer()
        driver = make_driver()
        ride = make_ride(customer, status=RideStatus.DRIVER_SELECTED)
        make_accepted_offer(ride, driver)

        rooms = ResumeService.snapshot(driver.user)["realtime"]

        self.assertEqual(rooms["ride_room"], f"/ws/rides/{ride.id}/")
        self.assertEqual(rooms["driver_room"], f"/ws/driver/{driver.id}/")

    def test_customer_gets_no_driver_room(self):
        customer = make_customer()
        make_ride(customer, status=RideStatus.SEARCHING)

        rooms = ResumeService.snapshot(customer)["realtime"]

        self.assertIsNone(rooms["driver_room"])

    # -- العزل ---------------------------------------------------------

    def test_one_customer_never_sees_another_customers_ride(self):
        first = make_customer()
        second = make_customer()
        make_ride(first, status=RideStatus.IN_PROGRESS)

        self.assertFalse(ResumeService.snapshot(second)["has_active_ride"])


@override_settings(
    PAYMENT_GATEWAYS=["payments.gateways.cash.CashGateway"],
    PAYMENT_DEFAULT_GATEWAY="cash",
)
class ResumePendingPaymentTests(TestCase):
    """
    أهمّ سيناريو استعادة: السائق أنهى الرحلة وأُغلق التطبيق قبل أن
    يؤكّد قبض الأجرة. بلا هذا الحقل تضيع الأجرة من السجلّ.
    """

    def setUp(self):
        from payments.gateways import reset_registry

        reset_registry()
        self.addCleanup(reset_registry)

    def test_driver_sees_awaiting_payment_after_completion(self):
        from payments.services.payment import PaymentService

        driver = make_driver()
        trip = make_completed_trip(driver=driver, gross_fare="25000.00")
        PaymentService.open_for_trip(trip)

        snapshot = ResumeService.snapshot(driver.user)

        self.assertFalse(snapshot["has_active_ride"])
        self.assertEqual(snapshot["stage"], Stage.AWAITING_PAYMENT)
        self.assertIsNotNone(snapshot["pending_payment"])

    def test_paid_trip_returns_to_idle(self):
        from payments.services.payment import PaymentService

        driver = make_driver()
        trip = make_completed_trip(driver=driver)
        payment = PaymentService.open_for_trip(trip)
        PaymentService.charge(payment.pk, system=True)

        self.assertEqual(
            ResumeService.snapshot(driver.user)["stage"], Stage.IDLE
        )


# =====================================================================
# الواجهات
# =====================================================================

class ActiveRideApiTests(APITestCase):

    URL = "/api/v1/me/active-ride/"

    def test_requires_authentication(self):
        self.assertEqual(
            self.client.get(self.URL).status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_idle_user_gets_200_with_nulls(self):
        auth(self.client, make_customer())
        response = self.client.get(self.URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["has_active_ride"])
        self.assertEqual(response.data["stage"], "idle")
        self.assertIsNone(response.data["ride"])

    def test_active_customer_gets_full_snapshot(self):
        customer = make_customer()
        driver = make_driver()
        ride = make_ride(customer, status=RideStatus.IN_PROGRESS)
        make_trip(ride, driver, status=TripStatus.IN_PROGRESS)

        auth(self.client, customer)
        response = self.client.get(self.URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["stage"], "in_progress")
        self.assertEqual(response.data["ride"]["id"], ride.id)
        self.assertIsNotNone(response.data["trip"])
        self.assertEqual(
            response.data["realtime"]["ride_room"], f"/ws/rides/{ride.id}/"
        )

    def test_stage_is_always_a_known_value(self):
        """التطبيق يبني شاشته على هذه القيمة — قيمة غير معروفة تعني شاشة بيضاء."""
        auth(self.client, make_customer())
        response = self.client.get(self.URL)
        self.assertIn(response.data["stage"], Stage.ALL)


# =====================================================================
# السجلّ والترقيم
# =====================================================================

class HistoryPaginationTests(APITestCase):

    def setUp(self):
        self.customer = make_customer()
        self.driver = make_driver()

        # ٢٥ رحلة منتهية: أكثر من صفحة واحدة (٢٠) بقليل.
        self.trips = [
            make_completed_trip(customer=self.customer, driver=self.driver)
            for _ in range(25)
        ]

    # -- الشكل ---------------------------------------------------------

    def test_response_is_paginated_object_not_array(self):
        """
        العقد الذي يبني عليه التطبيق. تغييره لاحقًا كسر — ولذلك ثُبِّت
        الآن قبل أن يبدأ مطوّر الموبايل.
        """
        auth(self.client, self.customer)
        response = self.client.get("/api/v1/me/trips/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("results", response.data)
        self.assertIn("next", response.data)
        self.assertIsInstance(response.data["results"], list)

    def test_default_page_size_is_twenty(self):
        auth(self.client, self.customer)
        response = self.client.get("/api/v1/me/trips/")
        self.assertEqual(len(response.data["results"]), 20)

    def test_cursor_reaches_the_rest_without_duplicates(self):
        auth(self.client, self.customer)

        first = self.client.get("/api/v1/me/trips/")
        self.assertIsNotNone(first.data["next"])

        second = self.client.get(first.data["next"])

        first_ids = {row["id"] for row in first.data["results"]}
        second_ids = {row["id"] for row in second.data["results"]}

        self.assertEqual(len(second.data["results"]), 5)
        self.assertEqual(first_ids & second_ids, set())
        self.assertEqual(len(first_ids | second_ids), 25)

    def test_page_size_is_capped(self):
        auth(self.client, self.customer)
        response = self.client.get("/api/v1/me/trips/?page_size=5000")
        self.assertLessEqual(len(response.data["results"]), 100)

    def test_custom_page_size_is_honoured(self):
        auth(self.client, self.customer)
        response = self.client.get("/api/v1/me/trips/?page_size=7")
        self.assertEqual(len(response.data["results"]), 7)

    # -- العزل ---------------------------------------------------------

    def test_history_is_isolated_between_users(self):
        auth(self.client, make_customer())
        response = self.client.get("/api/v1/me/trips/")
        self.assertEqual(response.data["results"], [])

    def test_driver_sees_own_trips(self):
        auth(self.client, self.driver)
        response = self.client.get("/api/v1/me/trips/")
        self.assertEqual(len(response.data["results"]), 20)

    # -- الترشيح -------------------------------------------------------

    def test_status_filter(self):
        make_ride(self.customer, status=RideStatus.CANCELLED)
        auth(self.client, self.customer)

        response = self.client.get("/api/v1/me/trips/?status=cancelled")
        self.assertEqual(response.data["results"], [])

    def test_my_rides_includes_cancelled(self):
        """
        إخفاء الملغاة يجعل الزبون يظنّ أن طلبه اختفى فيعيد الطلب —
        ثم يشكو من خصم مرّتين.
        """
        make_ride(self.customer, status=RideStatus.CANCELLED)
        auth(self.client, self.customer)

        response = self.client.get("/api/v1/rides/mine/")
        statuses = {row["status"] for row in response.data["results"]}

        self.assertIn("cancelled", statuses)

    def test_my_rides_rejects_driver(self):
        auth(self.client, self.driver)
        response = self.client.get("/api/v1/rides/mine/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class NotificationsPaginationTests(APITestCase):
    """كانت مقطوعة عند ٥٠ بلا وسيلة للوصول إلى ما قبلها."""

    def test_notifications_are_paginated(self):
        from notifications.models import Notification

        user = make_customer()
        for index in range(30):
            Notification.objects.create(
                user=user,
                event_type="test.event",
                title=f"إشعار {index}",
                body="نصّ",
            )

        auth(self.client, user)
        response = self.client.get("/api/v1/me/notifications/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("results", response.data)
        self.assertEqual(len(response.data["results"]), 20)
        self.assertIsNotNone(response.data["next"])
