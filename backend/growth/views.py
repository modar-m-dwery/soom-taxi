from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views import View
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from config.observability.auth import ContextTokenAuthentication as TokenAuthentication
from growth.services.incentives import IncentiveService
from growth.services.reports import Reports
from locations.models import ServiceArea
from users.permissions import IsDriver


@method_decorator(staff_member_required, name="dispatch")
class GrowthDashboardView(View):
    """
    لوحة المشغّل: أين يطلب الناس ومتى، أين لا يجدون سيارة، الأنشط والخاملون،
    وزرّ «اعمل عرضًا لهؤلاء» يفتح حملةً بجمهورها جاهزًا.
    """

    def get(self, request):
        try:
            days = max(1, min(int(request.GET.get("days", 7)), 90))
        except ValueError:
            days = 7
        area = ServiceArea.objects.filter(code=request.GET.get("area") or "").first()

        hours = Reports.demand_by_hour(days, area)
        peak = max((h["requests"] for h in hours), default=0) or 1
        for h in hours:
            h["pct"] = round(h["requests"] * 100 / peak)
            h["unmatched_pct"] = round(h["unmatched"] * 100 / peak)

        context = {
            "days": days,
            "area": area,
            "areas": ServiceArea.objects.filter(is_active=True),
            "summary": Reports.summary(days, area),
            "hours": hours,
            "hotspots": Reports.hotspots(days, area),
            "top_customers": Reports.top_customers(max(days, 30)),
            "top_drivers": Reports.top_drivers(max(days, 30)),
            "idle_customers": Reports.idle_customers(14, limit=50),
            "new_customers": Reports.new_customers_without_ride(limit=50),
            "idle_drivers": Reports.idle_drivers(7, limit=50),
        }
        return render(request, "growth/dashboard.html", context)


class IncentiveProgressSerializer(serializers.Serializer):
    program_id = serializers.IntegerField()
    name = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    period = serializers.CharField()
    period_start = serializers.DateField()
    target_trips = serializers.IntegerField()
    completed_trips = serializers.IntegerField()
    remaining_trips = serializers.IntegerField()
    reward_label = serializers.CharField()
    earned = serializers.BooleanField()
    award_status = serializers.CharField(allow_null=True)


class MyIncentivesView(APIView):
    """السائق يرى تقدّمه: «أنجزت 12 من 30 — بقي 18 لعشرة ليترات»."""

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated, IsDriver]

    @extend_schema(
        tags=["Growth"],
        operation_id="my_incentives",
        summary="Driver incentive progress",
        responses={200: IncentiveProgressSerializer(many=True)},
    )
    def get(self, request):
        rows = IncentiveService.progress(request.user.driver_profile)
        return Response(IncentiveProgressSerializer(rows, many=True).data, status=status.HTTP_200_OK)
