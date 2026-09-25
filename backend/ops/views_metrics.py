"""
لوحة المؤشّرات — `GET /api/v1/ops/metrics/`.

نقطة واحدة تجيب على السؤال الذي تُدار به المنصّة يوميًّا: «هل يعمل
النظام جيّدًا اليوم؟» وليست نقطة عدّادات لحظية — تلك `ops/overview/`.
الفرق أنّ هذه تقيس **نِسبًا عبر نافذة زمنية**، وهي وحدها ما يكشف
انحدارًا بطيئًا: نسبة مطابقة تهبط من 92% إلى 71% خلال أسبوع لا يراها
عدّاد لحظي أبدًا.
"""
from datetime import timedelta

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from drf_spectacular.utils import OpenApiParameter, extend_schema

from rest_framework import status as http_status
# المصادقة الموحّدة: عمر التوكن ونسبة الفعل إلى فاعله في سجلّ التدقيق.
from config.observability.auth import ContextTokenAuthentication as TokenAuthentication
from rest_framework.permissions import IsAuthenticated

from users.permissions import IsStaffOrSupport
from rest_framework.response import Response
from rest_framework.views import APIView

from ops.services.metrics import MetricsService


MAX_WINDOW_DAYS = 90


class _MetricsView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated, IsStaffOrSupport]


class OpsMetricsView(_MetricsView):

    @extend_schema(
        tags=["Ops"],
        operation_id="ops_metrics",
        summary="Platform KPIs for a time window",
        description=(
            "The seven KPIs the build document names — first_offer_time, "
            "rate_success_match, driver/customer_cancel_rate, "
            "rate_accept_invitation, time_response_invitation and "
            "conversion_trip_to_map — plus routing fallback rate, completion "
            "rate and review-flag rate.\n\n"
            "Timings report median (p50) and 90th percentile, not just the "
            "mean: one ride that waited an hour would otherwise hide a "
            "hundred that waited two seconds."
        ),
        parameters=[
            OpenApiParameter("hours", int, description="Window size, default 24, max 2160"),
            OpenApiParameter("since", str, description="ISO-8601 start, overrides hours"),
            OpenApiParameter("until", str, description="ISO-8601 end, default now"),
            OpenApiParameter("service_area", str, description="Service area code, e.g. JAB"),
        ],
        responses={200: dict, 400: dict},
    )
    def get(self, request):
        until = parse_datetime(request.query_params.get("until") or "") or timezone.now()
        since = parse_datetime(request.query_params.get("since") or "")

        if since is None:
            try:
                hours = int(request.query_params.get("hours") or 24)
            except (TypeError, ValueError):
                return Response(
                    {"detail": "hours must be an integer."},
                    status=http_status.HTTP_400_BAD_REQUEST,
                )
            hours = max(1, min(hours, MAX_WINDOW_DAYS * 24))
            since = until - timedelta(hours=hours)

        if since >= until:
            return Response(
                {"detail": "since must be earlier than until."},
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        # حدّ أقصى للنافذة: استعلام على سنتين يقفل القاعدة لدقائق،
        # وهو أسهل طريق لإسقاط الإنتاج من لوحة قراءة فقط.
        if (until - since) > timedelta(days=MAX_WINDOW_DAYS):
            return Response(
                {"detail": f"Window must not exceed {MAX_WINDOW_DAYS} days."},
                status=http_status.HTTP_400_BAD_REQUEST,
            )

        area = self._resolve_area(request.query_params.get("service_area"))

        return Response(MetricsService.compute(since=since, until=until, service_area=area))

    @staticmethod
    def _resolve_area(code):
        if not code:
            return None
        from locations.models import ServiceArea

        return ServiceArea.objects.filter(code=code).first()


class OpsMetricsSeriesView(_MetricsView):

    @extend_schema(
        tags=["Ops"],
        operation_id="ops_metrics_series",
        summary="Hourly counters for charting",
        parameters=[
            OpenApiParameter("hours", int, description="How many hours back, default 24, max 720"),
            OpenApiParameter("service_area", str),
        ],
        responses={200: dict},
    )
    def get(self, request):
        try:
            hours = int(request.query_params.get("hours") or 24)
        except (TypeError, ValueError):
            hours = 24

        hours = max(1, min(hours, 720))

        area = OpsMetricsView._resolve_area(request.query_params.get("service_area"))

        return Response(
            {
                "hours": hours,
                "service_area": getattr(area, "code", None),
                "series": MetricsService.hourly_series(hours=hours, service_area=area),
            }
        )
