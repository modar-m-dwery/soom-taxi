from drf_spectacular.utils import OpenApiParameter, extend_schema

from config.pagination import paginate
from rest_framework import status
# المصادقة الموحّدة: عمر التوكن ونسبة الفعل إلى فاعله في سجلّ التدقيق.
from config.observability.auth import ContextTokenAuthentication as TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from config.openapi import ErrorResponse
from notifications.models import Notification
from notifications.serializers import (
    DeviceTokenSerializer,
    NotificationSerializer,
    RegisterDeviceSerializer,
    UnregisterDeviceSerializer,
)
from notifications.services.dispatch import DeviceService


class RegisterDeviceView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Notifications"],
        operation_id="register_device",
        summary="Register a push token",
        description=(
            "Idempotent. A token already registered to another user is moved "
            "to the caller rather than duplicated — a phone changes hands, and "
            "two rows for one token means a notification reaching the wrong person."
        ),
        request=RegisterDeviceSerializer,
        responses={200: DeviceTokenSerializer, 400: ErrorResponse},
    )
    def post(self, request):
        serializer = RegisterDeviceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        device, _created = DeviceService.register(
            user=request.user,
            token=serializer.validated_data["token"],
            platform=serializer.validated_data["platform"],
        )

        return Response(
            DeviceTokenSerializer(device).data, status=status.HTTP_200_OK
        )


class UnregisterDeviceView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Notifications"],
        operation_id="unregister_device",
        summary="Unregister a push token",
        request=UnregisterDeviceSerializer,
        responses={204: None, 400: ErrorResponse},
    )
    def post(self, request):
        serializer = UnregisterDeviceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        DeviceService.unregister(
            user=request.user, token=serializer.validated_data["token"]
        )

        return Response(status=status.HTTP_204_NO_CONTENT)


class MyNotificationsView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Notifications"],
        operation_id="list_my_notifications",
        summary="Recent notifications for the caller",
        description=(
            "**مرقَّمة بالمؤشّر**: الاستجابة كائن فيه `results` و`next`.\n\n"
            "كانت مقطوعة عند ٥٠ إشعارًا بلا وسيلة للوصول إلى ما قبلها — "
            "والمؤشّر هو الصحيح هنا تحديدًا لأن إشعارًا جديدًا يصل أثناء "
            "التصفّح كان سيُزيح الصفحات ويكرّر عناصر على المستخدم."
        ),
        parameters=[
            OpenApiParameter("cursor", str, description="مؤشّر الصفحة التالية"),
            OpenApiParameter("page_size", int, description="1..100، الافتراضي 20"),
        ],
        responses={200: NotificationSerializer(many=True)},
    )
    def get(self, request):
        notifications = Notification.objects.filter(
            user=request.user
        ).order_by("-created_at")

        return paginate(request, notifications, NotificationSerializer, view=self)
