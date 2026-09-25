"""
واجهات الدفع.

الطبقة رقيقة عمدًا — كما في بقية المشروع: تترجم استثناء الخدمة إلى ردّ
HTTP ولا تحوي قرارًا ماليًا واحدًا. أي منطق تجده هنا يجب أن ينتقل إلى
`PaymentService`.
"""
import logging

from django.db import IntegrityError
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
# المصادقة الموحّدة: عمر التوكن ونسبة الفعل إلى فاعله في سجلّ التدقيق.
from config.observability.auth import ContextTokenAuthentication as TokenAuthentication
from rest_framework.permissions import AllowAny, IsAuthenticated

from users.permissions import IsAdmin
from rest_framework.response import Response
from rest_framework.views import APIView

from config.openapi import ErrorResponse
from payments.gateways import (
    PaymentGatewayError,
    WebhookVerificationError,
    available_gateways,
    get_gateway,
)
from payments.models import DriverBalance, Payment
from payments.serializers import (
    ChargePaymentSerializer,
    DriverBalanceSerializer,
    GatewaySerializer,
    PaymentSerializer,
    RefundRequestSerializer,
    RefundSerializer,
)
from payments.services.payment import (
    PaymentAuthorizationError,
    InvalidTransition,
    PaymentError,
    PaymentService,
)
from users.permissions import IsDriver


logger = logging.getLogger(__name__)


class _AuthedView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]


# =====================================================================
# البوابات المتاحة
# =====================================================================

class AvailableGatewaysView(_AuthedView):
    @extend_schema(
        tags=["Payments"],
        operation_id="list_payment_gateways",
        summary="وسائل الدفع المتاحة الآن",
        description=(
            "البوابات المهيّأة فعلًا فقط. بوابة موجودة في الكود وغير مهيّأة "
            "لا تظهر هنا — وهذا ما يسمح بإبقاء مزوّد مستقبلي في المستودع "
            "بلا أن يراه المستخدم قبل أوانه."
        ),
        responses={200: GatewaySerializer(many=True)},
    )
    def get(self, request):
        currency = request.query_params.get("currency") or None
        gateways = available_gateways(currency=currency)

        return Response(
            GatewaySerializer(
                [gateway.describe() for gateway in gateways], many=True
            ).data,
            status=status.HTTP_200_OK,
        )


# =====================================================================
# دفعة الرحلة
# =====================================================================

class TripPaymentView(_AuthedView):
    @extend_schema(
        tags=["Payments"],
        operation_id="get_trip_payment",
        summary="دفعة رحلة",
        responses={200: PaymentSerializer, 404: ErrorResponse},
    )
    def get(self, request, ride_id):
        payment = self._get_for_actor(request, ride_id)

        if payment is None:
            return Response(
                {"detail": "لا توجد دفعة لهذه الرحلة."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(PaymentSerializer(payment).data, status=status.HTTP_200_OK)

    @staticmethod
    def _get_for_actor(request, ride_id):
        """
        كل طرف يرى دفعة رحلته هو. الغريب يحصل على 404 لا 403 — لأن 403
        تؤكّد له أن الرحلة موجودة، وهي معلومة لا يستحقّها.
        """
        driver_profile = getattr(request.user, "driver_profile", None)

        queryset = Payment.objects.select_related("trip").filter(
            trip__ride_id=ride_id
        )

        payment = queryset.filter(customer=request.user).first()

        if payment is None and driver_profile is not None:
            payment = queryset.filter(driver=driver_profile).first()

        return payment


class ChargeTripPaymentView(_AuthedView):
    @extend_schema(
        tags=["Payments"],
        operation_id="charge_trip_payment",
        summary="تحصيل دفعة الرحلة",
        description=(
            "للنقدي: تأكيد السائق أنه قبض. للإلكتروني: بدء التحصيل لدى "
            "المزوّد. العملية متكافئة — تكرارها لا يسحب المبلغ مرّتين."
        ),
        request=ChargePaymentSerializer,
        responses={
            200: PaymentSerializer,
            400: ErrorResponse,
            404: ErrorResponse,
            409: ErrorResponse,
        },
    )
    def post(self, request, ride_id):
        serializer = ChargePaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        payment = TripPaymentView._get_for_actor(request, ride_id)

        if payment is None:
            return Response(
                {"detail": "لا توجد دفعة لهذه الرحلة."},
                status=status.HTTP_404_NOT_FOUND,
            )

        requested_code = (serializer.validated_data.get("gateway_code") or "").strip()

        if requested_code and requested_code != payment.gateway_code:
            # الصلاحية أوّلًا، قبل أيّ تحقّق آخر.
            #
            # الترتيب مقصود: لو فحصنا صحّة رمز البوّابة أوّلًا لأجاب
            # الخادم 400 على رمز مجهول و409 على دفعة مسوّاة — أي أنّه
            # يجيب عن أسئلة عن دفعةٍ لا يملك السائلُ حقّ تعديلها أصلًا.
            #
            # وجوهر الثغرة: كان الطرفان يستطيعان التبديل، فيقدر السائق
            # أن يحوّل دفعة إلكترونية إلى نقد على أيّ دفعة غير مسوّاة،
            # ثمّ يؤكّد قبضها بنفسه. اختيار وسيلة الدفع قرار الزبون.
            if payment.customer_id != request.user.id and not request.user.is_staff:
                return Response(
                    {"detail": "اختيار وسيلة الدفع للزبون وحده."},
                    status=status.HTTP_403_FORBIDDEN,
                )

            if payment.is_settled:
                return Response(
                    {"detail": "لا يمكن تغيير وسيلة الدفع بعد التحصيل."},
                    status=status.HTTP_409_CONFLICT,
                )

            try:
                get_gateway(requested_code)
            except PaymentGatewayError as exc:
                return Response(
                    {"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST
                )

            payment.gateway_code = requested_code
            payment.save(update_fields=["gateway_code", "updated_at"])

        try:
            payment = PaymentService.charge(payment.pk, actor=request.user)
        except PaymentAuthorizationError as exc:
            return Response(
                {"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN
            )
        except InvalidTransition as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except (PaymentError, PaymentGatewayError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(PaymentSerializer(payment).data, status=status.HTTP_200_OK)


# =====================================================================
# رصيد السائق
# =====================================================================

class MyDriverBalanceView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated, IsDriver]

    @extend_schema(
        tags=["Payments"],
        operation_id="get_my_driver_balance",
        summary="رصيدي كسائق",
        description=(
            "موجب: للسائق عند المنصّة. سالب: على السائق عمولات رحلات نقدية. "
            "سائق بلا رحلات يحصل على أصفار لا على 404."
        ),
        responses={200: DriverBalanceSerializer(many=True)},
    )
    def get(self, request):
        balances = DriverBalance.objects.filter(
            driver=request.user.driver_profile
        )

        if not balances.exists():
            return Response(
                [
                    {
                        "currency": "SYP",
                        "net_balance": "0.00",
                        "owes_platform": False,
                        "amount_owed_to_platform": "0.00",
                        "lifetime_earned": "0.00",
                        "lifetime_commission": "0.00",
                        "updated_at": None,
                    }
                ],
                status=status.HTTP_200_OK,
            )

        return Response(
            DriverBalanceSerializer(balances, many=True).data,
            status=status.HTTP_200_OK,
        )


# =====================================================================
# الإعادة — إدارة فقط
# =====================================================================

class RefundPaymentView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated, IsAdmin]

    @extend_schema(
        tags=["Payments"],
        operation_id="refund_payment",
        summary="إعادة مبلغ",
        description="إدارة فقط (is_staff). السبب إلزامي ويُسجَّل.",
        request=RefundRequestSerializer,
        responses={200: RefundSerializer, 400: ErrorResponse, 404: ErrorResponse},
    )
    def post(self, request, payment_id):
        serializer = RefundRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        payment = get_object_or_404(Payment, pk=payment_id)

        try:
            refund = PaymentService.refund(
                payment.pk,
                amount=serializer.validated_data.get("amount"),
                reason=serializer.validated_data["reason"],
                requested_by=request.user,
            )
        except InvalidTransition as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except (PaymentError, PaymentGatewayError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(RefundSerializer(refund).data, status=status.HTTP_200_OK)


# =====================================================================
# الإشعارات الواردة
# =====================================================================

class GatewayWebhookView(APIView):
    """
    نقطة استقبال إشعارات المزوّدين.

    عامّة بالضرورة — المزوّد لا يملك توكن مستخدم. الحماية بالتوقيع لا
    بالمصادقة، والتحقّق يقع **قبل** أي قراءة أو كتابة.

    ترجع 200 لكل حدث موثَّق حتى لو لم يُغيّر شيئًا: المزوّدون يعيدون
    إرسال ما لا يُجاب عليه بـ2xx، فإرجاع خطأ لحدث لا يعنينا يخلق حلقة
    إعادة إرسال بلا نهاية.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Payments"],
        operation_id="payment_gateway_webhook",
        summary="إشعار وارد من بوابة",
        request=None,
        responses={200: None, 400: ErrorResponse, 403: ErrorResponse},
    )
    def post(self, request, gateway_code):
        try:
            gateway = get_gateway(gateway_code)
        except PaymentGatewayError:
            # لا نكشف أي البوابات مسجَّلة لمن يتحسّس النقاط.
            return Response(
                {"detail": "غير معروف."}, status=status.HTTP_404_NOT_FOUND
            )

        if not gateway.supports_webhook:
            return Response(
                {"detail": "هذه البوابة لا تستقبل إشعارات."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        headers = {key: value for key, value in request.headers.items()}

        try:
            event = gateway.verify_webhook(headers, request.body)
        except WebhookVerificationError as exc:
            logger.warning(
                "إشعار مرفوض من %s: %s", gateway_code, exc
            )
            return Response(
                {"detail": "توقيع غير صالح."}, status=status.HTTP_403_FORBIDDEN
            )
        except Exception:
            logger.exception("خطأ غير متوقّع أثناء التحقّق من إشعار %s", gateway_code)
            return Response(
                {"detail": "تعذّرت معالجة الإشعار."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            PaymentService.apply_webhook(gateway_code, event)
        except IntegrityError:
            logger.exception("تعارض قاعدة بيانات أثناء تطبيق إشعار %s", gateway_code)
        except Exception:
            # لا نُرجع 5xx: المزوّد سيعيد الإرسال بلا نهاية. نسجّل ونحقّق.
            logger.exception("فشل تطبيق إشعار %s", gateway_code)

        return Response(status=status.HTTP_200_OK)
