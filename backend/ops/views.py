from drf_spectacular.utils import OpenApiParameter, extend_schema

from config.pagination import paginate
from rest_framework import status
# المصادقة الموحّدة: عمر التوكن ونسبة الفعل إلى فاعله في سجلّ التدقيق.
from config.observability.auth import ContextTokenAuthentication as TokenAuthentication
from rest_framework.permissions import IsAuthenticated

from users.permissions import IsAdmin, IsStaffOrSupport
from rest_framework.response import Response
from rest_framework.views import APIView

from config.openapi import ErrorResponse
from ops.models import AdminAction
from ops.serializers import (
    AdminActionSerializer,
    DriverStatusSerializer,
    ReasonSerializer,
)
from ops.services.console import OpsConsoleService, OpsError
from ops.services.health import OpsHealthService


class _OpsView(APIView):
    """
    قراءة تشغيلية: إداريّ أو دعم.

    ليست صلاحية شكلية: هذه الواجهات تُرجع مواقع دقيقة وأرقام هواتف.
    لكنّ القراءة وظيفة الدعم أيضًا، والتدخّل ليس كذلك — راجع
    `_OpsWriteView` أدناه.
    """

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated, IsStaffOrSupport]


class _OpsWriteView(_OpsView):
    """
    التدخّل الإداري: إداريّ وحده.

    إنهاء رحلة لم تنتهِ، تحرير سائق، إيقاف حساب — صلاحيات بهذا الوزن
    لا تُمنح لحساب دعم. الفصل بين القراءة والتدخّل هو الفرق بين «مَن
    يرى» و«مَن يفعل»، وخلطهما هو كيف يُساء إلى المنصّات من الداخل.
    """

    permission_classes = [IsAuthenticated, IsAdmin]


# =====================================================================
# القراءة
# =====================================================================

class OpsOverviewView(_OpsView):
    @extend_schema(
        tags=["Ops"],
        operation_id="ops_overview",
        summary="Live operational counters",
        responses={200: dict},
    )
    def get(self, request):
        return Response(OpsHealthService.overview(), status=status.HTTP_200_OK)


class OpsAttentionView(_OpsView):
    @extend_schema(
        tags=["Ops"],
        operation_id="ops_attention",
        summary="Everything that needs a human right now",
        description=(
            "Stuck trips, drivers marked busy with no active trip, trips "
            "flagged for review, urgent complaints, stale searches, failed "
            "notifications, and pending driver verifications."
        ),
        responses={200: dict},
    )
    def get(self, request):
        return Response(OpsHealthService.attention(), status=status.HTTP_200_OK)


class OpsLiveDriversView(_OpsView):
    @extend_schema(
        tags=["Ops"],
        operation_id="ops_live_drivers",
        summary="Every visible driver, with exact coordinates",
        description=(
            "Unlike the customer-facing map this returns precise positions: "
            "the ~110m rounding exists to stop a customer tracking a driver "
            "before acceptance, which is meaningless for an operator on the "
            "phone with a lost driver. Admin-only."
        ),
        responses={200: dict},
    )
    def get(self, request):
        return Response(
            OpsHealthService.live_drivers(), status=status.HTTP_200_OK
        )


class OpsActionLogView(_OpsView):
    @extend_schema(
        tags=["Ops"],
        operation_id="ops_action_log",
        summary="Audit log of admin interventions",
        description=(
            "**مرقَّم بالمؤشّر.** سجلّ تدقيق مقطوع عند ١٠٠ ليس سجلّ "
            "تدقيق: التحقيق في حادثة قديمة يحتاج الوصول إلى ما قبلها."
        ),
        parameters=[
            OpenApiParameter("cursor", str, description="مؤشّر الصفحة التالية"),
            OpenApiParameter("page_size", int, description="1..100، الافتراضي 20"),
        ],
        responses={200: AdminActionSerializer(many=True)},
    )
    def get(self, request):
        actions = AdminAction.objects.select_related("actor").order_by("-created_at")

        return paginate(request, actions, AdminActionSerializer, view=self)


# =====================================================================
# التدخّل
# =====================================================================

class _ActionView(_OpsWriteView):
    """كلّ تدخّل إداري يرث من هنا — أي `IsAdmin` لا `IsStaffOrSupport`."""

    serializer_class = ReasonSerializer

    def perform(self, request, target_id, data):
        raise NotImplementedError

    def post(self, request, target_id):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            action = self.perform(request, target_id, serializer.validated_data)
        except OpsError as exc:
            return Response(
                {"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST
            )

        return Response(
            AdminActionSerializer(action).data, status=status.HTTP_200_OK
        )


class OpsReleaseDriverView(_ActionView):
    @extend_schema(
        tags=["Ops"],
        operation_id="ops_release_driver",
        summary="Unstick a driver marked busy with no active trip",
        request=ReasonSerializer,
        responses={200: AdminActionSerializer, 400: ErrorResponse},
    )
    def post(self, request, target_id):
        return super().post(request, target_id)

    def perform(self, request, target_id, data):
        return OpsConsoleService.release_driver(
            driver_id=target_id, actor=request.user, reason=data["reason"]
        )


class OpsForceCompleteView(_ActionView):
    @extend_schema(
        tags=["Ops"],
        operation_id="ops_force_complete_trip",
        summary="Complete a trip on the driver's behalf",
        request=ReasonSerializer,
        responses={200: AdminActionSerializer, 400: ErrorResponse},
    )
    def post(self, request, target_id):
        return super().post(request, target_id)

    def perform(self, request, target_id, data):
        return OpsConsoleService.force_complete_trip(
            ride_id=target_id, actor=request.user, reason=data["reason"]
        )


class OpsForceCancelView(_ActionView):
    @extend_schema(
        tags=["Ops"],
        operation_id="ops_force_cancel_trip",
        summary="Cancel a trip administratively",
        request=ReasonSerializer,
        responses={200: AdminActionSerializer, 400: ErrorResponse},
    )
    def post(self, request, target_id):
        return super().post(request, target_id)

    def perform(self, request, target_id, data):
        return OpsConsoleService.force_cancel_trip(
            ride_id=target_id, actor=request.user, reason=data["reason"]
        )


class OpsDriverStatusView(_ActionView):
    serializer_class = DriverStatusSerializer

    @extend_schema(
        tags=["Ops"],
        operation_id="ops_set_driver_status",
        summary="Verify, reject or suspend a driver",
        description=(
            "Suspension takes the driver off the live map immediately rather "
            "than at their next heartbeat."
        ),
        request=DriverStatusSerializer,
        responses={200: AdminActionSerializer, 400: ErrorResponse},
    )
    def post(self, request, target_id):
        return super().post(request, target_id)

    def perform(self, request, target_id, data):
        return OpsConsoleService.set_driver_status(
            driver_id=target_id,
            actor=request.user,
            new_status=data["status"],
            reason=data["reason"],
        )
