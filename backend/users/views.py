from drf_spectacular.utils import (
    extend_schema,
    OpenApiExample,
    OpenApiResponse,
    inline_serializer,
)
from config.openapi import (
    BecomeDriverResponse,
    DriverProfileResponse,
    ErrorResponse,
    RateLimitResponse,
    RequestOTPResponse,
    VerifyOTPResponse,
)
from rest_framework import serializers
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework.authtoken.models import Token
# المصادقة الموحّدة: عمر التوكن ونسبة الفعل إلى فاعله في سجلّ التدقيق.
from config.observability.auth import ContextTokenAuthentication as TokenAuthentication
from rest_framework.permissions import IsAuthenticated

from users.serializers import RequestOTPSerializer, UserSerializer, VerifyOTPSerializer
from users.services.otp import OTPService
from users.services.rate_limit import RateLimitService
from users.services.drivers import DriverProfileService
from users.models import CustomerProfile, DriverProfile, OTPChallenge, UserRole
from config.throttling import OTPRequestThrottle, OTPVerifyThrottle
from users.permissions import IsDriver



class RequestOTPView(APIView):
    authentication_classes = []
    permission_classes = []
    # طبقة شبكة فوق RateLimitService: تلك تحدّ بالهاتف والجهاز، وهذه تقف
    # قبلها فتوقف مَن يدوّر الأرقام من عنوان واحد.
    throttle_classes = [OTPRequestThrottle]

    @extend_schema(
        tags=["Authentication"],
        operation_id="request_otp",
        summary="Request OTP",
        description=(
            "Creates an OTP challenge for a phone/device combination. "
            "Rate limits are enforced independently for phone, device and IP."
        ),
        request=RequestOTPSerializer,
        responses={
            201: RequestOTPResponse,
            429: RateLimitResponse,
            400: ErrorResponse,
        },
        examples=[
            OpenApiExample(
                "Request OTP",
                request_only=True,
                value={
                    "phone": "+963991234567",
                    "device_id": "android-device-001",
                },
            ),
        ],
    )
    def post(self, request):
        serializer = RequestOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        phone = serializer.validated_data["phone"]
        device_id = serializer.validated_data["device_id"]

        ip_address = self._get_client_ip(request)

        phone_limit = RateLimitService.check_phone(phone)
        if not phone_limit.allowed:
            return Response(
                {
                    "detail": "Too many OTP requests for this phone number.",
                    "retry_after": phone_limit.retry_after,
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        device_limit = RateLimitService.check_device(device_id)
        if not device_limit.allowed:
            return Response(
                {
                    "detail": "Too many OTP requests for this device.",
                    "retry_after": device_limit.retry_after,
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        ip_limit = RateLimitService.check_ip(ip_address)
        if not ip_limit.allowed:
            return Response(
                {
                    "detail": "Too many OTP requests from this IP address.",
                    "retry_after": ip_limit.retry_after,
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        challenge, code = OTPService.create_challenge(
            phone=phone,
            device_id=device_id,
            request_ip=ip_address,
        )

        # -------------------------------------------------------------
        # الإيصال — السطر الذي كان غائبًا.
        #
        # الترتيب مقصود: التحدّي يُكتب أوّلًا ثم يُرسل. العكس يترك رمزًا
        # وصل المستخدم بلا تحدٍّ يقابله إن انهارت العملية بينهما.
        #
        # والإخفاق في الإرسال لا يُبطل الطلب: التحدّي قائم، والمستخدم
        # يستطيع طلب رمز جديد. إرجاع 500 هنا يخفي أن نصف العملية نجح.
        # -------------------------------------------------------------
        self._dispatch_otp(phone, code, challenge.id)

        response_data = {
            "detail": "OTP generated successfully.",
            "expires_at": challenge.expires_at,
        }

        # Development only.
        if getattr(__import__("django.conf", fromlist=["settings"]).settings, "DEBUG", False):
            response_data["development_code"] = code

        return Response(
            response_data,
            status=status.HTTP_201_CREATED,
        )

    @staticmethod
    def _dispatch_otp(phone, code, challenge_id):
        """
        يدفع الإيصال إلى الطابور، ويسقط على الإرسال المباشر إن تعذّر.

        الطابور هو المسار الصحيح (المزوّد بطيء وخارج سيطرتنا)، لكن وسيط
        Celery متوقّفًا يجب ألّا يعني تعطّل تسجيل الدخول كلّه — فالإرسال
        المباشر أبطأ لكنه أفضل من لا شيء.
        """
        import logging

        from users.tasks import send_otp_code

        logger = logging.getLogger(__name__)

        try:
            send_otp_code.delay(phone, code, challenge_id)
            return
        except Exception as exc:  # noqa: BLE001 — وسيط الطابور متوقّف
            logger.warning(
                "otp: تعذّر جدولة الإيصال (%s) — إرسال مباشر بدلًا منه.", exc
            )

        try:
            from users.services.delivery import deliver_otp

            result = deliver_otp(phone, code)

            if not result.ok:
                logger.error(
                    "otp: فشل الإرسال المباشر إلى %s: %s", phone, result.error
                )
        except Exception:
            logger.exception("otp: انهار الإرسال المباشر إلى %s", phone)

    @staticmethod
    def _get_client_ip(request):
        """
        العنوان الذي لا يستطيع العميل تزويره.

        النسخة السابقة كانت تأخذ أوّل عنصر في `X-Forwarded-For` — وهو
        بالضبط ما يكتبه العميل. وNginx يستعمل `$proxy_add_x_forwarded_for`
        الذي **يُلحق** العنوان الحقيقي بما أرسله العميل، فيبقى المزوَّر
        أوّلًا. أي أنّ حدّ الـIP كان يُهزَم بترويسة واحدة.
        """
        from config.throttling import trusted_client_ip

        return trusted_client_ip(request)


class VerifyOTPView(APIView):
    authentication_classes = []
    permission_classes = []
    # كانت هذه النقطة بلا أيّ حدّ: لا خانق ولا نداء لـRateLimitService،
    # والفرملة الوحيدة خمس محاولات لكلّ تحدٍّ. وهي تُصدر توكن مصادقة.
    throttle_classes = [OTPVerifyThrottle]

    @extend_schema(
        tags=["Authentication"],
        operation_id="verify_otp",
        summary="Verify OTP",
        description=(
            "Verifies the latest active OTP challenge and returns "
            "a DRF token."
        ),
        request=VerifyOTPSerializer,
        responses={
            200: VerifyOTPResponse,
            400: ErrorResponse,
            429: ErrorResponse,
        },
        examples=[
            OpenApiExample(
                "Verify OTP",
                request_only=True,
                value={
                    "phone": "+963991234567",
                    "device_id": "android-device-001",
                    "code": "123456",
                },
            ),
        ],
    )
    def post(self, request):
        serializer = VerifyOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        phone = serializer.validated_data["phone"]
        device_id = serializer.validated_data["device_id"]
        code = serializer.validated_data["code"]

        challenge = (
            OTPChallenge.objects
            .filter(
                phone=phone,
                device_id=device_id,
                consumed_at__isnull=True,
            )
            .order_by("-created_at")
            .first()
        )

        if challenge is None:
            return Response(
                {
                    "detail": "Invalid or expired OTP."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if challenge.is_expired:
            return Response(
                {
                    "detail": "Invalid or expired OTP."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if challenge.attempts_exhausted:
            return Response(
                {
                    "detail": "Too many verification attempts."
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        if not OTPService.verify_code(challenge, code):
            return Response(
                {
                    "detail": "Invalid OTP."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            User = get_user_model()

            user, created = User.objects.get_or_create(
                phone=phone,
                defaults={
                    "role": UserRole.CUSTOMER,
                    "is_verified": True,
                    "is_active": True,
                },
            )

            if not user.is_verified:
                user.is_verified = True
                user.save(update_fields=["is_verified"])

            if user.role == UserRole.CUSTOMER:
                CustomerProfile.objects.get_or_create(
                    user=user
                )

            elif user.role == UserRole.DRIVER:
                DriverProfile.objects.get_or_create(
                    user=user
                )

            token, _ = Token.objects.get_or_create(
                user=user
            )

        return Response(
            {
                "token": token.key,
                "user": UserSerializer(user).data,
                "is_new_user": created,
            },
            status=status.HTTP_200_OK,
        )


class BecomeDriverView(APIView):
    authentication_classes = [
        TokenAuthentication,
    ]

    permission_classes = [
        IsAuthenticated,
    ]

    authentication_classes = [
        TokenAuthentication,
    ]

    permission_classes = [
        IsAuthenticated,
    ]

    @extend_schema(
        tags=["Authentication"],
        operation_id="become_driver",
        summary="Become a driver",
        description=(
            "Converts a customer/supportable user into a driver "
            "and creates a PENDING DriverProfile."
        ),
        request=None,
        responses={
            200: BecomeDriverResponse,
            400: ErrorResponse,
        },
    )
    def post(self, request):

        try:
            profile, created = (
                DriverProfileService.become_driver(
                    request.user
                )
            )

        except ValueError as exc:
            return Response(
                {
                    "detail": str(exc),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                "detail": (
                    "Driver application created successfully."
                ),
                "user_id": request.user.id,
                "role": request.user.role,
                "driver_profile_id": profile.id,
                "driver_status": profile.status,
                "is_new_driver_profile": created,
            },
            status=status.HTTP_200_OK,
        )


class LogoutView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Authentication"],
        operation_id="logout",
        summary="Logout",
        request=None,
        responses={
            200: ErrorResponse,
        },
    )
    def post(self, request):
        if request.auth:
            request.auth.delete()

        return Response(
            {
                "detail": "Logged out successfully."
            },
            status=status.HTTP_200_OK,
        )


class MeView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Users"],
        operation_id="get_current_user",
        summary="Get current user",
        responses={
            200: UserSerializer,
        },
    )
    def get(self, request):
        return Response(
            UserSerializer(request.user).data,
            status=status.HTTP_200_OK,
        )


class DriverProfileView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated, IsDriver]

    @extend_schema(
        tags=["Drivers"],
        operation_id="get_driver_profile",
        summary="Get current driver profile",
        responses={
            200: DriverProfileResponse,
            403: ErrorResponse,
        },
    )
    def get(self, request):
        profile, _ = DriverProfile.objects.get_or_create(
            user=request.user
        )

        return Response(
            {
                "user_id": request.user.id,
                "phone": request.user.phone,
                "role": request.user.role,
                "status": profile.status,
                "rating": profile.rating,
                "online": profile.online,
                "current_occupancy": profile.current_occupancy,
                "available_seats": profile.available_seats,
                "last_location_at": profile.last_location_at,
            },
            status=status.HTTP_200_OK,
        )





