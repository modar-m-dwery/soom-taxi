"""
قراءة سجلّ التدقيق.

نقطتان فقط، وكلتاهما للإدارة:

  GET /api/v1/ops/audit/               بحث حرّ بمرشّحات
  GET /api/v1/ops/audit/ride/{id}/     قصّة رحلة واحدة كاملة بالترتيب

لماذا الإدارة فقط؟ لأنّ الصفوف تحمل أرقام هواتف الفاعلين ومعرّفات
السائقين وأسباب التدخّل. زبونٌ يقرأ سجلّ رحلته يقرأ معه بيانات سائقها.
وحين يُطلب لاحقًا عرض «تاريخ رحلتي» في التطبيق، يُبنى منظورٌ مقيَّد
منفصل لا يُفتح هذا.
"""
from django.utils.dateparse import parse_datetime

from drf_spectacular.utils import OpenApiParameter, extend_schema

# المصادقة الموحّدة: عمر التوكن ونسبة الفعل إلى فاعله في سجلّ التدقيق.
from config.observability.auth import ContextTokenAuthentication as TokenAuthentication
from rest_framework.permissions import IsAuthenticated

from users.permissions import IsStaffOrSupport
from rest_framework.response import Response
from rest_framework.views import APIView

from config.pagination import paginate
from ops.models import AuditLog
from ops.serializers_audit import AuditLogSerializer
from ops.services.audit import AuditService


class _AuditView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated, IsStaffOrSupport]


class AuditSearchView(_AuditView):

    @extend_schema(
        tags=["Ops"],
        operation_id="ops_audit_search",
        summary="Search the audit trail",
        description=(
            "Every state transition in the platform: rides, offers, "
            "invitations, trips, payments, drivers, documents and complaints. "
            "Admin only — rows carry actor phone numbers."
        ),
        parameters=[
            OpenApiParameter("entity_type", str, description="ride | offer | invitation | trip | payment | driver | document | complaint | shared_join"),
            OpenApiParameter("entity_id", int),
            OpenApiParameter("actor_label", str, description="Exact actor label, e.g. user:+963991234567"),
            OpenApiParameter("to_state", str),
            OpenApiParameter("action", str),
            OpenApiParameter("request_id", str, description="Correlate with application logs"),
            OpenApiParameter("since", str, description="ISO-8601 datetime, inclusive"),
            OpenApiParameter("until", str, description="ISO-8601 datetime, exclusive"),
        ],
        responses={200: AuditLogSerializer(many=True)},
    )
    def get(self, request):
        queryset = AuditLog.objects.select_related("actor_user")

        exact = {
            "entity_type": "entity_type",
            "entity_id": "entity_id",
            "actor_label": "actor_label",
            "to_state": "to_state",
            "action": "action",
            "request_id": "request_id",
        }

        for param, field in exact.items():
            value = request.query_params.get(param)
            if value:
                queryset = queryset.filter(**{field: value})

        since = parse_datetime(request.query_params.get("since") or "")
        if since:
            queryset = queryset.filter(created_at__gte=since)

        until = parse_datetime(request.query_params.get("until") or "")
        if until:
            queryset = queryset.filter(created_at__lt=until)

        return paginate(
            request,
            queryset,
            AuditLogSerializer,
            view=self,
            ordering="-created_at",
        )


class AuditRideStoryView(_AuditView):

    @extend_schema(
        tags=["Ops"],
        operation_id="ops_audit_ride_story",
        summary="Full timeline of one ride",
        description=(
            "Everything that happened around a ride in chronological order — "
            "the request, every offer, every invitation, the trip, the payment "
            "and any complaint. This is the view to open when a customer or "
            "driver disputes what happened."
        ),
        responses={200: AuditLogSerializer(many=True)},
    )
    def get(self, request, ride_id):
        entries = AuditService.ride_story(ride_id)

        return Response(
            {
                "ride_id": ride_id,
                "count": len(entries),
                "entries": AuditLogSerializer(entries, many=True).data,
            }
        )
