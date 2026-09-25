"""
اختبارات أمنية — كلّ اختبار يقفل ثغرة موجودة فعلًا.

ليست اختبارات «تحقّق من أنّ الشيء يعمل». كلّ واحد منها يعيد تمثيل
هجوم ناجح قبل الإصلاح، ويؤكّد أنّه صار يفشل. اسم كلّ صنف يذكر الثغرة
التي يحرسها، فمَن كسرها لاحقًا يعرف ماذا كسر ولماذا وُجد الشرط.

الترتيب بحسب الخطورة كما صُنّفت في التدقيق.
"""
from datetime import timedelta
from decimal import Decimal

from django.contrib.gis.geos import Point
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone

from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from drivers.models import (
    REQUIRED_DOCUMENT_TYPES,
    DocumentStatus,
    DriverDocument,
)
from payments.models import Payment, PaymentStatus
from trips.models import Trip, TripStatus
from rides.models import RideMode, RideRequest, RideStatus
from users.models import DriverProfile, User, UserRole
from vehicles.models import Vehicle, VehicleType


class SecurityTestBase(APITestCase):
    """طرفان حقيقيان: زبون وسائق برحلة مكتملة بينهما ودفعة نقدية."""

    def setUp(self):
        cache.clear()  # الخوانق تعيش في الكاش؛ اختبار يلوّث تاليه

        self.customer = User.objects.create_user(
            phone="+963900000001", password="x",
            role=UserRole.CUSTOMER, is_verified=True,
        )
        self.other_customer = User.objects.create_user(
            phone="+963900000002", password="x",
            role=UserRole.CUSTOMER, is_verified=True,
        )
        self.driver_user = User.objects.create_user(
            phone="+963900000003", password="x",
            role=UserRole.DRIVER, is_verified=True,
        )
        self.support = User.objects.create_user(
            phone="+963900000004", password="x",
            role=UserRole.SUPPORT, is_verified=True,
        )
        self.admin = User.objects.create_user(
            phone="+963900000005", password="x",
            role=UserRole.ADMIN, is_verified=True,
        )
        self.admin.is_staff = True
        self.admin.save(update_fields=["is_staff"])

        self.driver = DriverProfile.objects.create(
            user=self.driver_user,
            status=DriverProfile.DriverStatus.ACTIVE,
            online=True,
            current_location=Point(35.9010, 35.3620, srid=4326),
            available_seats=4,
            last_location_at=timezone.now(),
        )

        self.vehicle = Vehicle.objects.create(
            driver=self.driver, type_id=VehicleType.SEDAN,
            make="Kia", model="Rio", year=2020, color="أبيض",
            plate_number="SEC-0001", seats=4, active=True,
        )

        for doc_type in REQUIRED_DOCUMENT_TYPES:
            DriverDocument.objects.create(
                driver=self.driver, type=doc_type,
                file=f"driver_documents/sec-{doc_type}.pdf",
                status=DocumentStatus.APPROVED,
                expires_at=timezone.now() + timedelta(days=200),
            )

        self.tokens = {
            "customer": Token.objects.create(user=self.customer).key,
            "other": Token.objects.create(user=self.other_customer).key,
            "driver": Token.objects.create(user=self.driver_user).key,
            "support": Token.objects.create(user=self.support).key,
            "admin": Token.objects.create(user=self.admin).key,
        }

    def auth(self, who):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.tokens[who]}")

    def make_completed_trip_with_cash_payment(self):
        ride = RideRequest.objects.create(
            customer=self.customer,
            pickup=Point(35.9010, 35.3620, srid=4326),
            destination=Point(35.9110, 35.3720, srid=4326),
            mode=RideMode.FAST,
            passenger_count=1,
            status=RideStatus.COMPLETED,
            gross_fare=Decimal("10000.00"),
        )

        trip = Trip.objects.create(
            ride=ride, driver=self.driver, customer=self.customer,
            vehicle=self.vehicle, status=TripStatus.COMPLETED,
            completed_at=timezone.now(),
            final_fare=Decimal("10000.00"),
        )

        payment = Payment.objects.create(
            trip=trip, customer=self.customer, driver=self.driver,
            amount=Decimal("10000.00"), currency="SYP",
            gateway_code="cash", status=PaymentStatus.PENDING,
        )

        return ride, trip, payment


# =====================================================================
# حرج
# =====================================================================


class CashPaymentSelfConfirmTests(SecurityTestBase):
    """
    C1 — الزبون كان يستطيع تأكيد قبض النقد بنفسه.

    الأثر: تنتقل الدفعة إلى PAID ويُقيَّد على السائق قيدُ عمولة على مالٍ
    لم يقبضه. `actor` كان يُمرَّر إلى `PaymentService.charge` ولا يُقرأ
    في أيّ سطر.
    """

    def test_customer_cannot_confirm_own_cash_payment(self):
        ride, _trip, payment = self.make_completed_trip_with_cash_payment()

        self.auth("customer")
        response = self.client.post(
            f"/api/v1/trips/{ride.id}/payment/charge/", {}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentStatus.PENDING)

    def test_unrelated_user_cannot_confirm(self):
        ride, _trip, payment = self.make_completed_trip_with_cash_payment()

        self.auth("other")
        response = self.client.post(
            f"/api/v1/trips/{ride.id}/payment/charge/", {}, format="json"
        )

        self.assertIn(
            response.status_code,
            (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND),
        )
        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentStatus.PENDING)

    def test_driver_can_confirm(self):
        """الإصلاح يجب ألّا يكسر المسار الصحيح."""
        ride, _trip, payment = self.make_completed_trip_with_cash_payment()

        self.auth("driver")
        response = self.client.post(
            f"/api/v1/trips/{ride.id}/payment/charge/", {}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentStatus.PAID)


class DriverDocumentExposureTests(SecurityTestBase):
    """
    C2 — وثائق السائقين (هويّات، رخص) كانت تُخدَم من /media/ بلا مصادقة.
    """

    def test_document_file_requires_authentication(self):
        document = DriverDocument.objects.filter(driver=self.driver).first()

        self.client.credentials()
        response = self.client.get(
            f"/api/v1/drivers/documents/{document.id}/file/"
        )

        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )

    def test_other_user_gets_404_not_403(self):
        """404 لا 403: الردّ المختلف يؤكّد وجود الوثيقة لمن يبحث."""
        document = DriverDocument.objects.filter(driver=self.driver).first()

        self.auth("customer")
        response = self.client.get(
            f"/api/v1/drivers/documents/{document.id}/file/"
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_serializer_does_not_leak_raw_media_path(self):
        self.auth("driver")
        response = self.client.get("/api/v1/drivers/documents/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        body = str(response.content)
        self.assertNotIn("/media/", body)
        self.assertNotIn("driver_documents/", body)


# =====================================================================
# عالٍ
# =====================================================================


class DocumentUploadValidationTests(SecurityTestBase):
    """H5 — `FileField()` عارية كانت تقبل أيّ شيء، بما فيه HTML/SVG."""

    def _upload(self, filename, content=b"x" * 64, content_type="image/png"):
        from django.core.files.uploadedfile import SimpleUploadedFile

        self.auth("driver")
        return self.client.post(
            "/api/v1/drivers/documents/",
            {
                "type": REQUIRED_DOCUMENT_TYPES[0],
                "file": SimpleUploadedFile(filename, content, content_type),
            },
            format="multipart",
        )

    def test_html_upload_rejected(self):
        response = self._upload(
            "payload.html", b"<script>alert(1)</script>", "text/html"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_svg_upload_rejected(self):
        response = self._upload("payload.svg", b"<svg/>", "image/svg+xml")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_oversized_upload_rejected(self):
        response = self._upload("big.png", b"x" * (9 * 1024 * 1024))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_valid_image_accepted(self):
        response = self._upload("license.png")
        self.assertIn(
            response.status_code,
            (status.HTTP_200_OK, status.HTTP_201_CREATED),
        )


class TrustedClientIPTests(SecurityTestBase):
    """
    H1 — حدّ الـIP كان يُهزَم بترويسة `X-Forwarded-For` واحدة.

    Nginx يستعمل `$proxy_add_x_forwarded_for` الذي **يُلحق** العنوان
    الحقيقي بما أرسله العميل، فيبقى المزوَّر أوّلًا في السلسلة.
    """

    def _ip(self, forwarded, remote="10.0.0.9", depth=1):
        from unittest.mock import Mock

        from config.throttling import trusted_client_ip

        request = Mock()
        request.META = {
            "HTTP_X_FORWARDED_FOR": forwarded,
            "REMOTE_ADDR": remote,
        }

        with override_settings(TRUSTED_PROXY_COUNT=depth):
            return trusted_client_ip(request)

    def test_spoofed_first_entry_is_ignored(self):
        # العميل يزوّر "1.2.3.4"، ونجينكس يُلحق عنوانه الحقيقي بعده
        self.assertEqual(self._ip("1.2.3.4, 203.0.113.7"), "203.0.113.7")

    def test_multiple_spoofed_entries_ignored(self):
        self.assertEqual(
            self._ip("1.1.1.1, 2.2.2.2, 3.3.3.3, 203.0.113.7"), "203.0.113.7"
        )

    def test_no_proxy_uses_remote_addr(self):
        self.assertEqual(
            self._ip("1.2.3.4", remote="198.51.100.5", depth=0), "198.51.100.5"
        )


class OTPThrottleTests(SecurityTestBase):
    """
    H1/H2 — الخوانق كانت معرَّفة بلا `DEFAULT_THROTTLE_CLASSES`، أي بلا
    أثر. و`VerifyOTPView` لم يكن عليها أيّ حدّ إطلاقًا.
    """

    def test_verify_otp_is_throttled(self):
        """
        نشدّ المعدّل على الصنف نفسه لا عبر `override_settings`.

        `SimpleRateThrottle.THROTTLE_RATES` سمةُ صنف تُقرأ **وقت
        الاستيراد**، فتغيير `REST_FRAMEWORK` بعده لا يصل إليها — وهو
        فخّ يجعل اختبار الخنق يبدو ناجحًا بينما لا يقيس شيئًا.
        """
        from unittest.mock import patch

        from config.throttling import OTPVerifyThrottle

        cache.clear()
        self.client.credentials()

        rates = dict(OTPVerifyThrottle.THROTTLE_RATES)
        rates["otp_verify"] = "3/hour"

        codes = []
        with patch.object(OTPVerifyThrottle, "THROTTLE_RATES", rates):
            codes = self._hammer_verify(6)

        self.assertIn(
            status.HTTP_429_TOO_MANY_REQUESTS,
            codes,
            "تحقّق الرمز يجب أن يُخنق — وإلّا فهو تخمين حرّ على توكن مصادقة.",
        )

    def _hammer_verify(self, times):
        codes = []
        for index in range(times):
            response = self.client.post(
                "/api/v1/auth/verify-otp/",
                {
                    "phone": f"+96391000{index:04d}",
                    "device_id": f"dev-{index}",
                    "code": "000000",
                },
                format="json",
            )
            codes.append(response.status_code)
        return codes

    def test_throttle_classes_are_configured(self):
        """الحارس ضدّ العودة: معدّلات بلا أصناف = لا خنق إطلاقًا."""
        from django.conf import settings

        self.assertTrue(
            settings.REST_FRAMEWORK.get("DEFAULT_THROTTLE_CLASSES"),
            "DEFAULT_THROTTLE_RATES بلا DEFAULT_THROTTLE_CLASSES لا يفعل شيئًا.",
        )


class AdminPermissionConsistencyTests(SecurityTestBase):
    """
    H4 — ثلاثة تعريفات متضاربة لكلمة «إداري».

    حساب دعم كان يُمنع من REST ويقرأ البيانات نفسها على WebSocket.
    """

    def test_support_can_read_ops(self):
        self.auth("support")
        response = self.client.get("/api/v1/ops/overview/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_support_cannot_intervene(self):
        """القراءة نعم، التدخّل لا."""
        self.auth("support")
        response = self.client.post(
            f"/api/v1/ops/drivers/{self.driver.id}/release/",
            {"reason": "سبب مكتوب كافٍ للاختبار"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_customer_cannot_read_ops(self):
        self.auth("customer")
        response = self.client.get("/api/v1/ops/overview/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_intervene(self):
        self.auth("admin")
        response = self.client.post(
            f"/api/v1/ops/drivers/{self.driver.id}/release/",
            {"reason": "سبب مكتوب كافٍ للاختبار"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class PublicCatalogExposureTests(SecurityTestBase):
    """H3 — الكتالوج العامّ كان يُخرج إحداثيات خامّة بلا مصادقة."""

    def test_catalog_requires_authentication(self):
        self.client.credentials()
        response = self.client.get("/api/v1/trips/")
        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )

    def test_coordinates_are_rounded(self):
        from matching.serializers import _public_point

        point = Point(35.901234567, 35.362987654, srid=4326)
        rounded = _public_point(point)

        self.assertEqual(rounded["lng"], 35.901)
        self.assertEqual(rounded["lat"], 35.363)


class GatewaySwitchTests(SecurityTestBase):
    """M5 — السائق كان يستطيع تحويل دفعة الزبون إلى نقد ثمّ تأكيدها."""

    def test_driver_cannot_switch_gateway(self):
        ride, _trip, payment = self.make_completed_trip_with_cash_payment()

        # رمز مختلف عن الحالي — وإلّا فلا تبديل يقع ولا شيء يُفحص.
        self.auth("driver")
        response = self.client.post(
            f"/api/v1/trips/{ride.id}/payment/charge/",
            {"gateway_code": "card"},
            format="json",
        )

        # 403 لا 400: الصلاحية تُفحص قبل صحّة رمز البوّابة، فلا يجيب
        # الخادم عن أسئلة تخصّ دفعةً لا يملك السائل حقّ تعديلها.
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        payment.refresh_from_db()
        self.assertEqual(payment.gateway_code, "cash")

    def test_customer_may_switch_gateway(self):
        """الإصلاح يجب ألّا يمنع صاحب القرار."""
        ride, _trip, payment = self.make_completed_trip_with_cash_payment()

        self.auth("customer")
        response = self.client.post(
            f"/api/v1/trips/{ride.id}/payment/charge/",
            {"gateway_code": "card"},
            format="json",
        )

        # البوّابة غير مهيّأة في التطوير، فالردّ 400 لا 403 — والمهمّ
        # أنّه ليس رفض صلاحية.
        self.assertNotEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class OTPHashingTests(SecurityTestBase):
    """
    M8 — SHA-256 عارية على ستّ خانات: مليون بصمة تُبنى في ثوانٍ، فأيّ
    قراءة للجدول تكشف كلّ رمز حيّ.
    """

    def test_hash_is_not_plain_sha256(self):
        import hashlib

        from users.services.otp import OTPService

        plain = hashlib.sha256(b"123456").hexdigest()
        self.assertNotEqual(OTPService.hash_code("123456", "salt"), plain)

    def test_same_code_different_salt_gives_different_hash(self):
        from users.services.otp import OTPService

        self.assertNotEqual(
            OTPService.hash_code("123456", "salt-a"),
            OTPService.hash_code("123456", "salt-b"),
        )

    def test_challenge_stores_a_salt(self):
        from users.services.otp import OTPService

        challenge, code = OTPService.create_challenge(
            phone="+963900009999", device_id="dev-1", request_ip="10.0.0.1"
        )

        self.assertTrue(challenge.code_salt)
        self.assertNotIn(code, challenge.code_hash)
        self.assertTrue(OTPService.verify_code(challenge, code))


class ObjectOwnershipTests(SecurityTestBase):
    """
    IDOR — الجزء الأقوى في المشروع أصلًا. هذه الاختبارات حارسٌ ضدّ
    التراجع لا اكتشافٌ لثغرة.
    """

    def test_customer_cannot_read_another_customers_ride_offers(self):
        ride = RideRequest.objects.create(
            customer=self.customer,
            pickup=Point(35.9010, 35.3620, srid=4326),
            destination=Point(35.9110, 35.3720, srid=4326),
            mode=RideMode.FAST, passenger_count=1,
            status=RideStatus.SEARCHING,
        )

        self.auth("other")
        response = self.client.get(f"/api/v1/customer/rides/{ride.id}/offers/")

        self.assertIn(
            response.status_code,
            (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND),
        )

    def test_customer_cannot_cancel_another_customers_ride(self):
        ride = RideRequest.objects.create(
            customer=self.customer,
            pickup=Point(35.9010, 35.3620, srid=4326),
            destination=Point(35.9110, 35.3720, srid=4326),
            mode=RideMode.FAST, passenger_count=1,
            status=RideStatus.SEARCHING,
        )

        self.auth("other")
        response = self.client.post(f"/api/v1/rides/{ride.id}/cancel/", {}, format="json")

        self.assertIn(
            response.status_code,
            (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND),
        )

        ride.refresh_from_db()
        self.assertEqual(ride.status, RideStatus.SEARCHING)

    def test_unauthenticated_is_rejected_everywhere(self):
        self.client.credentials()

        for path in (
            "/api/v1/auth/me/",
            "/api/v1/rides/mine/",
            "/api/v1/me/trips/",
            "/api/v1/ops/overview/",
            "/api/v1/ops/audit/",
            "/api/v1/ops/metrics/",
            "/api/v1/trips/",
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertIn(
                    response.status_code,
                    (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
                    f"{path} مفتوح بلا مصادقة",
                )
