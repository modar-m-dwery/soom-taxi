"""ضوابط config/security.py: عمر التوكن، معقوليّة الموقع، قصر لوحات الإدارة."""

from datetime import timedelta

from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.http import Http404, HttpResponse
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from config.security import AdminIPAllowlistMiddleware, location_rejection, token_expired
from users.models import User, UserRole


class LocationPlausibilityTests(SimpleTestCase):

    def test_normal_point_accepted(self):
        self.assertIsNone(location_rejection(35.92, 35.36))

    def test_garbage_rejected(self):
        self.assertEqual(location_rejection(float("nan"), 35.3), "not_finite")
        self.assertEqual(location_rejection(35.9, 95.0), "out_of_range")
        self.assertEqual(location_rejection(0.0, 0.0), "null_island")

    def test_gps_jitter_accepted_even_if_fast(self):
        # ~220 م في نصف ثانية: ارتعاش، لا تزييف.
        self.assertIsNone(location_rejection(35.9225, 35.36, (35.92, 35.36, 100.0), 100.5))

    def test_normal_driving_accepted(self):
        # ~1.1 كم في دقيقة ≈ 66 كم/س.
        self.assertIsNone(location_rejection(35.9321, 35.36, (35.92, 35.36, 0.0), 60.0))

    def test_teleport_rejected(self):
        # جبلة → اللاذقية (~25 كم) في ثلاث ثوانٍ.
        self.assertEqual(
            location_rejection(35.79, 35.52, (35.92, 35.36, 0.0), 3.0),
            "implausible_speed",
        )

    def test_long_gap_is_not_a_teleport(self):
        # 25 كم في ساعة بعد انقطاع: مقبول.
        self.assertIsNone(location_rejection(35.79, 35.52, (35.92, 35.36, 0.0), 3600.0))


class TokenTTLTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            phone="+SEC_USER", password="x", role=UserRole.CUSTOMER, is_verified=True,
        )
        self.token = Token.objects.create(user=self.user)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

    def _age(self, days):
        Token.objects.filter(key=self.token.key).update(
            created=timezone.now() - timedelta(days=days)
        )

    @override_settings(AUTH_TOKEN_TTL_DAYS=90)
    def test_fresh_token_works(self):
        self._age(10)
        self.assertEqual(self.client.get("/api/v1/auth/me/").status_code, 200)

    @override_settings(AUTH_TOKEN_TTL_DAYS=90)
    def test_old_token_rejected_and_deleted(self):
        self._age(91)
        self.assertEqual(self.client.get("/api/v1/auth/me/").status_code, 401)
        self.assertFalse(Token.objects.filter(key=self.token.key).exists())

    @override_settings(AUTH_TOKEN_TTL_DAYS=0)
    def test_zero_disables_expiry(self):
        self._age(3650)
        self.token.refresh_from_db()
        self.assertFalse(token_expired(self.token))


class AdminAllowlistTests(SimpleTestCase):

    def _call(self, path, ip):
        middleware = AdminIPAllowlistMiddleware(lambda request: HttpResponse("ok"))
        request = RequestFactory().get(path, REMOTE_ADDR=ip)
        return middleware(request)

    @override_settings(ADMIN_ALLOWED_IPS=[], ADMIN_URL="admin/")
    def test_no_list_means_open(self):
        self.assertEqual(self._call("/admin/", "8.8.8.8").status_code, 200)

    @override_settings(ADMIN_ALLOWED_IPS=["10.0.0.5"], ADMIN_URL="admin/", TRUSTED_PROXY_COUNT=0)
    def test_admin_and_ops_hidden_from_others(self):
        with self.assertRaises(Http404):
            self._call("/admin/login/", "8.8.8.8")
        with self.assertRaises(Http404):
            self._call("/api/v1/ops/now/", "8.8.8.8")
        self.assertEqual(self._call("/admin/", "10.0.0.5").status_code, 200)

    @override_settings(ADMIN_ALLOWED_IPS=["10.0.0.5"], ADMIN_URL="admin/", TRUSTED_PROXY_COUNT=0)
    def test_public_api_untouched(self):
        self.assertEqual(self._call("/api/v1/rides/", "8.8.8.8").status_code, 200)

    @override_settings(ADMIN_ALLOWED_IPS=["10.0.0.5"], ADMIN_URL="admin/", TRUSTED_PROXY_COUNT=0)
    def test_forged_forwarded_header_does_not_help(self):
        middleware = AdminIPAllowlistMiddleware(lambda request: HttpResponse("ok"))
        request = RequestFactory().get(
            "/admin/", REMOTE_ADDR="8.8.8.8", HTTP_X_FORWARDED_FOR="10.0.0.5"
        )
        with self.assertRaises(Http404):
            middleware(request)
