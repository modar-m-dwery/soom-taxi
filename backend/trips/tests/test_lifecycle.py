"""
دورة حياة الرحلة — تحويل `test_trip_lifecycle_e2e` إلى اختبارات حقيقية.

هذا الملفّ هو **النمط** الذي تُحوَّل به بقية أوامر E2E العشرة. الفروق
الأربعة عن الأمر الأصلي:

  ١. `TestCase` يلفّ كل اختبار في معاملة تُلغى بعده — فلا حاجة إلى دالّة
     `cleanup()` ولا خطر من بقايا تشغيل فاشل سابق.
  ٢. كل ادّعاء اختبارٌ مستقلّ باسم يشرح نفسه. سقوط واحد لا يمنع البقية،
     وتقرير الفشل يقول أي سلوك انكسر لا "فشل السطر ٢٣٧".
  ٣. البيانات من `config.testkit` لا مكرّرة في كل ملفّ.
  ٤. لا حاجة إلى قاعدة بيانات حيّة ولا Redis ولا بيانات seed — يعمل بـ
     `python manage.py test` في خط تكامل.
"""
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from config.testkit import (
    JABLEH,
    LATTAKIA,
    make_completed_trip,
    make_customer,
    make_driver,
    make_ride,
    make_trip,
    point,
)
from rides.models import RideStatus
from trips.models import Trip, TripStatus
from trips.services.trip import TripError, TripService


class TripLifecycleTests(TestCase):
    """الترتيب الصارم: arrived ← start ← complete. لا يُتجاوَز ولا يُعكس."""

    def setUp(self):
        self.customer = make_customer()
        self.driver = make_driver(location=JABLEH)
        self.ride = make_ride(self.customer, status=RideStatus.DRIVER_SELECTED)
        self.trip = make_trip(self.ride, self.driver, status=TripStatus.CREATED)

    # -- الترتيب ------------------------------------------------------

    def test_start_before_arrived_is_refused(self):
        with self.assertRaises(TripError):
            TripService.start(ride_id=self.ride.pk, driver=self.driver)

    def test_complete_before_start_is_refused(self):
        with self.assertRaises(TripError):
            TripService.complete(ride_id=self.ride.pk, driver=self.driver)

    def test_arrived_then_start_then_complete_succeeds(self):
        TripService.arrived(ride_id=self.ride.pk, driver=self.driver)
        self.trip.refresh_from_db()
        self.assertEqual(self.trip.status, TripStatus.DRIVER_ARRIVED)

        TripService.start(ride_id=self.ride.pk, driver=self.driver)
        self.trip.refresh_from_db()
        self.assertEqual(self.trip.status, TripStatus.IN_PROGRESS)

        TripService.complete(ride_id=self.ride.pk, driver=self.driver)
        self.trip.refresh_from_db()
        self.assertEqual(self.trip.status, TripStatus.COMPLETED)
        self.assertIsNotNone(self.trip.completed_at)

    def test_ride_status_follows_trip_status(self):
        """الطلب والرحلة يُحدَّثان في المعاملة نفسها — لا يمكن أن يفترقا."""
        TripService.arrived(ride_id=self.ride.pk, driver=self.driver)
        TripService.start(ride_id=self.ride.pk, driver=self.driver)
        TripService.complete(ride_id=self.ride.pk, driver=self.driver)

        self.ride.refresh_from_db()
        self.assertEqual(self.ride.status, RideStatus.COMPLETED)

    def test_complete_is_idempotent(self):
        TripService.arrived(ride_id=self.ride.pk, driver=self.driver)
        TripService.start(ride_id=self.ride.pk, driver=self.driver)

        first = TripService.complete(ride_id=self.ride.pk, driver=self.driver)
        second = TripService.complete(ride_id=self.ride.pk, driver=self.driver)

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(second.status, TripStatus.COMPLETED)

    # -- التحقّق الجغرافي ----------------------------------------------

    def test_arrived_far_from_pickup_is_refused(self):
        """
        وصول كاذب من بعيد يبدأ عدّاد عدم حضور الزبون — وهو مدخل احتيال
        حقيقي لا مجرّد خطأ، ولذلك يُمنع لا يُعلَّم.
        """
        far_driver = make_driver(location=LATTAKIA)
        ride = make_ride(make_customer(), status=RideStatus.DRIVER_SELECTED)
        make_trip(ride, far_driver, status=TripStatus.CREATED)

        with self.assertRaises(TripError):
            TripService.arrived(ride_id=ride.pk, driver=far_driver)

    def test_arrived_with_stale_location_is_refused(self):
        stale = make_driver(location=JABLEH, fresh_location=False)
        ride = make_ride(make_customer(), status=RideStatus.DRIVER_SELECTED)
        make_trip(ride, stale, status=TripStatus.CREATED)

        with self.assertRaises(TripError):
            TripService.arrived(ride_id=ride.pk, driver=stale)

    def test_completing_far_from_destination_flags_review_not_blocks(self):
        """
        الفرق عن "وصلت" مقصود: منع الإنهاء يحبس سائقًا في رحلة انتهت
        فعلًا لأن الراكب نزل قبل الوجهة بقليل — وهو سلوك مشروع.
        """
        TripService.arrived(ride_id=self.ride.pk, driver=self.driver)
        TripService.start(ride_id=self.ride.pk, driver=self.driver)

        self.driver.current_location = point(LATTAKIA)
        self.driver.last_location_at = timezone.now()
        self.driver.save()

        trip = TripService.complete(ride_id=self.ride.pk, driver=self.driver)

        self.assertEqual(trip.status, TripStatus.COMPLETED)
        self.assertTrue(trip.needs_review)
        self.assertFalse(trip.dropoff_verified)
        self.assertTrue(trip.review_reason)

    # -- الملكية -------------------------------------------------------

    def test_another_driver_cannot_act_on_the_trip(self):
        intruder = make_driver(location=JABLEH)

        with self.assertRaises(Exception):
            TripService.arrived(ride_id=self.ride.pk, driver=intruder)

    # -- الإلغاء -------------------------------------------------------

    def test_cancel_before_start_succeeds(self):
        TripService.arrived(ride_id=self.ride.pk, driver=self.driver)

        trip = TripService.cancel(
            ride_id=self.ride.pk, actor="customer", reason="تأخّر السائق"
        )

        self.assertEqual(trip.status, TripStatus.CANCELLED)
        self.assertEqual(trip.cancelled_by, "customer")

    def test_cancel_after_start_is_refused(self):
        """ما بعد البدء ليس إلغاءً بل نزاعًا — ومساره الشكوى."""
        TripService.arrived(ride_id=self.ride.pk, driver=self.driver)
        TripService.start(ride_id=self.ride.pk, driver=self.driver)

        with self.assertRaises(TripError):
            TripService.cancel(ride_id=self.ride.pk, actor="customer")

    def test_cancel_after_completion_is_refused(self):
        TripService.arrived(ride_id=self.ride.pk, driver=self.driver)
        TripService.start(ride_id=self.ride.pk, driver=self.driver)
        TripService.complete(ride_id=self.ride.pk, driver=self.driver)

        with self.assertRaises(TripError):
            TripService.cancel(ride_id=self.ride.pk, actor="customer")

    def test_cancel_is_idempotent(self):
        first = TripService.cancel(ride_id=self.ride.pk, actor="customer")
        second = TripService.cancel(ride_id=self.ride.pk, actor="customer")
        self.assertEqual(first.pk, second.pk)


class TripCompletionRecordTests(TestCase):
    """سجلّ الإتمام هو الإثبات الدائم بعد حذف مسار GPS."""

    def test_completion_record_is_written(self):
        customer = make_customer()
        driver = make_driver(location=JABLEH)
        ride = make_ride(customer, status=RideStatus.DRIVER_SELECTED)
        make_trip(ride, driver, status=TripStatus.CREATED)

        TripService.arrived(ride_id=ride.pk, driver=driver)
        TripService.start(ride_id=ride.pk, driver=driver)
        trip = TripService.complete(ride_id=ride.pk, driver=driver)

        record = getattr(trip, "completion_record", None)
        self.assertIsNotNone(record)
        self.assertEqual(record.completed_at, trip.completed_at)


class TripPaymentIntegrationTests(TestCase):
    """الربط الجديد: إنهاء الرحلة يفتح دفعتها."""

    def test_completion_opens_a_payment(self):
        from payments.models import Payment, PaymentStatus

        customer = make_customer()
        driver = make_driver(location=JABLEH)
        ride = make_ride(
            customer,
            status=RideStatus.DRIVER_SELECTED,
            gross_fare="25000.00",
            platform_fee="2500.00",
        )
        make_trip(ride, driver, status=TripStatus.CREATED)

        TripService.arrived(ride_id=ride.pk, driver=driver)
        TripService.start(ride_id=ride.pk, driver=driver)
        trip = TripService.complete(ride_id=ride.pk, driver=driver)

        payment = Payment.objects.filter(trip=trip).first()
        self.assertIsNotNone(payment)
        self.assertEqual(payment.status, PaymentStatus.PENDING)
        self.assertEqual(str(payment.amount), "25000.00")
