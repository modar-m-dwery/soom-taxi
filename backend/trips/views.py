from drf_spectacular.utils import OpenApiParameter, extend_schema

from django.db.models import Q
from rest_framework import status
# المصادقة الموحّدة: عمر التوكن ونسبة الفعل إلى فاعله في سجلّ التدقيق.
from config.observability.auth import ContextTokenAuthentication as TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from config.openapi import ErrorResponse
from config.pagination import paginate
from rides.models import RideRequest
from trips.models import Trip
from trips.serializers import (
    ActiveRideSnapshotSerializer,
    CancelTripSerializer,
    DriverCancelTripSerializer,
    TripCompletionRecordSerializer,
    TripLocationSerializer,
    TripSerializer,
)
from trips.services.resume import ResumeService
from trips.services.trip import TripError, TripService
from users.permissions import IsCustomer, IsDriver


class _DriverTripAction(APIView):
    """
    قاعدة مشتركة لأفعال السائق الثلاثة. الـview لا تحوي منطقًا: تستدعي
    TripService وتترجم استثناءه إلى رد HTTP. آلة الحالات كلها في الخدمة.
    """

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated, IsDriver]

    action = None          # يُحدَّد في الأبناء
    success_status = status.HTTP_200_OK

    def perform(self, ride_id, driver):
        raise NotImplementedError

    def post(self, request, ride_id):
        try:
            trip = self.perform(ride_id, request.user.driver_profile)
        except RideRequest.DoesNotExist:
            return Response(
                {"detail": "Ride not found."}, status=status.HTTP_404_NOT_FOUND
            )
        except TripError as exc:
            return Response(
                {"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST
            )

        return Response(TripSerializer(trip).data, status=self.success_status)


class DriverCancelTripView(APIView):
    """
    السائق يتراجع بعد القبول وقبل البدء. الطلب يعود إلى البحث للزبون،
    ويُحسب الإلغاء على السائق (راجع trips/services/cancellation.py).
    """

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated, IsDriver]

    @extend_schema(
        tags=["Trips"],
        operation_id="driver_cancel_trip",
        summary="Driver cancels an accepted trip before starting",
        request=DriverCancelTripSerializer,
        responses={200: TripSerializer, 400: ErrorResponse, 404: ErrorResponse},
    )
    def post(self, request, ride_id):
        serializer = DriverCancelTripSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            trip = TripService.cancel(
                ride_id=ride_id,
                actor="driver",
                reason=serializer.validated_data["reason"],
                driver=request.user.driver_profile,
            )
        except RideRequest.DoesNotExist:
            return Response(
                {"detail": "Ride not found."}, status=status.HTTP_404_NOT_FOUND
            )
        except TripError as exc:
            return Response(
                {"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST
            )
        return Response(TripSerializer(trip).data, status=status.HTTP_200_OK)


class DriverArrivedView(_DriverTripAction):
    @extend_schema(
        tags=["Trips"],
        operation_id="driver_arrived",
        summary="Driver arrived at pickup",
        description=(
            "Rejected when the driver's position is stale or farther than "
            "TRIP_ARRIVAL_RADIUS_M from the pickup point — a false arrival "
            "starts the passenger no-show clock, so it is guarded."
        ),
        request=None,
        responses={200: TripSerializer, 400: ErrorResponse, 404: ErrorResponse},
    )
    def post(self, request, ride_id):
        return super().post(request, ride_id)

    def perform(self, ride_id, driver):
        return TripService.arrived(ride_id=ride_id, driver=driver)


class DriverStartTripView(_DriverTripAction):
    @extend_schema(
        tags=["Trips"],
        operation_id="driver_start_trip",
        summary="Start the trip",
        description="Requires DRIVER_ARRIVED. The sequence cannot be skipped.",
        request=None,
        responses={200: TripSerializer, 400: ErrorResponse, 404: ErrorResponse},
    )
    def post(self, request, ride_id):
        return super().post(request, ride_id)

    def perform(self, ride_id, driver):
        return TripService.start(ride_id=ride_id, driver=driver)


class DriverCompleteTripView(_DriverTripAction):
    @extend_schema(
        tags=["Trips"],
        operation_id="driver_complete_trip",
        summary="Complete the trip",
        description=(
            "Computes distance from the recorded path, writes the completion "
            "record, and releases the driver back to the live map. A drop-off "
            "far from the destination is flagged for review, not blocked."
        ),
        request=None,
        responses={200: TripSerializer, 400: ErrorResponse, 404: ErrorResponse},
    )
    def post(self, request, ride_id):
        return super().post(request, ride_id)

    def perform(self, ride_id, driver):
        return TripService.complete(ride_id=ride_id, driver=driver)


class TripDetailView(APIView):
    """تفاصيل الرحلة — للطرفين، كلٌّ يرى رحلته هو."""

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Trips"],
        operation_id="get_trip",
        summary="Trip detail",
        responses={200: TripSerializer, 404: ErrorResponse},
    )
    def get(self, request, ride_id):
        trip = self._get_trip(request, ride_id)

        if trip is None:
            return Response(
                {"detail": "Trip not found."}, status=status.HTTP_404_NOT_FOUND
            )

        data = TripSerializer(trip).data

        record = getattr(trip, "completion_record", None)
        data["completion_record"] = (
            TripCompletionRecordSerializer(record).data if record else None
        )

        return Response(data, status=status.HTTP_200_OK)

    @staticmethod
    def _get_trip(request, ride_id):
        driver_profile = getattr(request.user, "driver_profile", None)

        return (
            Trip.objects
            .select_related("driver", "driver__user", "vehicle", "ride")
            .filter(ride_id=ride_id)
            .filter(
                Q(customer=request.user)
                | Q(driver=driver_profile if driver_profile else None)
            )
            .first()
        )


class TripPathView(APIView):
    """مسار الرحلة المسجَّل — للطرفين، ولحل النزاعات."""

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Trips"],
        operation_id="get_trip_path",
        summary="Recorded trip path",
        responses={200: TripLocationSerializer(many=True), 404: ErrorResponse},
    )
    def get(self, request, ride_id):
        trip = TripDetailView._get_trip(request, ride_id)

        if trip is None:
            return Response(
                {"detail": "Trip not found."}, status=status.HTTP_404_NOT_FOUND
            )

        return Response(
            TripLocationSerializer(
                trip.locations.order_by("timestamp"), many=True
            ).data,
            status=status.HTTP_200_OK,
        )


class CustomerCancelTripView(APIView):
    """
    إلغاء الرحلة بعد تثبيت السائق وقبل بدئها. الإلغاء بعد البدء ليس إلغاءً
    بل نزاع — ولذلك تُرفض المحاولة برسالة صريحة بدل تمريرها صامتة.
    """

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated, IsCustomer]

    @extend_schema(
        tags=["Trips"],
        operation_id="customer_cancel_trip",
        summary="Cancel an assigned trip",
        request=CancelTripSerializer,
        responses={200: TripSerializer, 400: ErrorResponse, 404: ErrorResponse},
    )
    def post(self, request, ride_id):
        serializer = CancelTripSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if not RideRequest.objects.filter(id=ride_id, customer=request.user).exists():
            return Response(
                {"detail": "Ride not found."}, status=status.HTTP_404_NOT_FOUND
            )

        try:
            trip = TripService.cancel(
                ride_id=ride_id,
                actor="customer",
                reason=serializer.validated_data.get("reason", ""),
            )
        except TripError as exc:
            return Response(
                {"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST
            )

        return Response(TripSerializer(trip).data, status=status.HTTP_200_OK)


# =====================================================================
# استعادة الحالة والسجلّ — نقاط الموبايل
# =====================================================================

class ActiveRideView(APIView):
    """
    أوّل نداء يُطلقه التطبيق عند الإقلاع.

    الوحيدة في المشروع التي لا تحتاج `ride_id` — وهي بالضبط سبب وجودها:
    التطبيق بعد إعادة التشغيل لا يملك أي معرّف.
    """

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Trips"],
        operation_id="get_active_ride",
        summary="حالة المستخدم الآن — لاستعادة الشاشة عند فتح التطبيق",
        description=(
            "يعيد الرحلة القائمة إن وُجدت، والرحلة الجارية، والدفعة "
            "المعلّقة، ومسارات WebSocket الجاهزة، و`stage` واحدة يبني "
            "عليها التطبيق شاشته.\n\n"
            "**لا يعيد 404 أبدًا**: مستخدم بلا رحلة يحصل على "
            "`has_active_ride=false` و`stage=idle`."
        ),
        responses={200: ActiveRideSnapshotSerializer},
    )
    def get(self, request):
        snapshot = ResumeService.snapshot(request.user)

        return Response(
            ActiveRideSnapshotSerializer(snapshot).data,
            status=status.HTTP_200_OK,
        )


class MyTripsView(APIView):
    """سجلّ رحلات المستخدم — للطرفين، كلٌّ يرى رحلاته هو."""

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Trips"],
        operation_id="list_my_trips",
        summary="سجلّ رحلاتي",
        description=(
            "**مرقَّمة بالمؤشّر**: الاستجابة كائن فيه `results` و`next`، "
            "لا مصفوفة. اتبع `next` كما هو ولا تبنِ الرابط بنفسك."
        ),
        parameters=[
            OpenApiParameter(
                "status", str,
                description="ترشيح بالحالة: completed أو cancelled …",
            ),
            OpenApiParameter("cursor", str, description="مؤشّر الصفحة التالية"),
            OpenApiParameter("page_size", int, description="1..100، الافتراضي 20"),
        ],
        responses={200: TripSerializer(many=True)},
    )
    def get(self, request):
        queryset = ResumeService.trips_for(
            request.user,
            status=request.query_params.get("status") or None,
        )

        return paginate(request, queryset, TripSerializer, view=self)
