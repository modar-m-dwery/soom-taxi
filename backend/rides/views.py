from drf_spectacular.utils import (
    extend_schema,
    OpenApiExample,
    OpenApiParameter,
)

from config.pagination import paginate
from config.openapi import (
    CancelRideResponse,
    ErrorResponse,
)

from django.contrib.gis.geos import Point
from django.shortcuts import get_object_or_404

from rest_framework import status
from catalog.permissions import requires_feature, requires_service
# المصادقة الموحّدة: عمر التوكن ونسبة الفعل إلى فاعله في سجلّ التدقيق.
from config.observability.auth import ContextTokenAuthentication as TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from users.permissions import IsCustomer

from rides.models import (
    RideSubscription,
    RideRequest,
    TripCategory,
)

from rides.serializers import (
    RideSubscriptionSerializer,
    CreateRideRequestSerializer,
    RideRequestSerializer,
)

from rides.services.ride_request import (
    RideRequestConflictError,
    RideRequestService,
    RideRequestValidationError,
)

from matching.services.matching import (
    MatchingService,
    MatchingError,
)


class RideRequestCreateView(APIView):

    authentication_classes = [
        TokenAuthentication,
    ]

    permission_classes = [
        IsAuthenticated,
        IsCustomer,
    ]

    @extend_schema(
        tags=["Rides"],
        operation_id="create_ride_request",
        summary="Create ride request",
        description=(
            "Creates a ride after validating the customer, coordinates, "
            "mode, category and passenger count. "
            "The service then calls the routing provider and pricing service "
            "before saving the ride."
        ),
        request=CreateRideRequestSerializer,
        responses={
            201: RideRequestSerializer,
            400: ErrorResponse,
        },
    )
    def post(self, request):

        serializer = CreateRideRequestSerializer(
            data=request.data
        )

        serializer.is_valid(
            raise_exception=True
        )

        data = serializer.validated_data

        pickup = Point(
            data["pickup_lng"],
            data["pickup_lat"],
            srid=4326,
        )

        destination = Point(
            data["destination_lng"],
            data["destination_lat"],
            srid=4326,
        )

        try:

            ride = RideRequestService.create_ride_request(
                customer=request.user,
                pickup=pickup,
                destination=destination,
                mode=data["mode"],
                passenger_count=data["passenger_count"],
                scheduled_at=data.get("scheduled_at"),
                requested_vehicle_type=data.get(
                    "requested_vehicle_type"
                ),
                trip_category=data.get(
                    "trip_category",
                    TripCategory.CITY,
                ),
                origin_city=data.get("origin_city"),
                destination_city=data.get("destination_city"),
                search_radius_km=data.get("search_radius_km"),
                auto_dispatch=data.get("auto_dispatch", False),
            )

        except RideRequestConflictError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_409_CONFLICT,
            )

        except RideRequestValidationError as exc:

            return Response(
                {
                    "detail": str(exc)
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            RideRequestSerializer(ride).data,
            status=status.HTTP_201_CREATED,
        )


class CustomerCancelRideView(APIView):
    """
    إلغاء رحلة العميل. يوجّه تلقائيًا لمنطق التنظيف المناسب حسب نوع
    الرحلة (مشتركة فورية / مشتركة مجدولة / عادية) دون التأثير على باقي
    الركاب إن وُجدوا (فقط ترقية مضيف جديد إن كان الملغي هو المضيف).
    """

    authentication_classes = [
        TokenAuthentication,
    ]

    permission_classes = [
        IsAuthenticated,
        IsCustomer,
    ]

    @extend_schema(
        tags=["Rides"],
        operation_id="cancel_ride",
        summary="Cancel ride",
        description=(
            "Cancels the customer's ride and performs the correct cleanup "
            "for normal, instant shared and scheduled shared rides."
        ),
        request=None,
        responses={
            200: CancelRideResponse,
            400: ErrorResponse,
            404: ErrorResponse,
        },
    )
    def post(self, request, ride_id):

        try:

            ride = MatchingService.cancel_ride(
                ride_id=ride_id,
                customer=request.user,
            )

        except RideRequest.DoesNotExist:

            return Response(
                {
                    "detail": "Ride not found."
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        except MatchingError as exc:

            return Response(
                {
                    "detail": str(exc)
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                "status": ride.status,
                "ride_id": ride.id,
            },
            status=status.HTTP_200_OK,
        )

class MyRidesView(APIView):
    """
    سجلّ طلبات الزبون — بكل حالاتها، بما فيها الملغاة والمنتهية.

    مقصود أن يشمل غير الناجحة: شاشة «رحلاتي» التي تُخفي الطلبات الملغاة
    تجعل الزبون يظنّ أن طلبه اختفى، فيعيد الطلب ويشكو من الخصم مرّتين.
    """

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated, IsCustomer]

    @extend_schema(
        tags=["Rides"],
        operation_id="list_my_rides",
        summary="سجلّ طلباتي",
        description=(
            "**مرقَّم بالمؤشّر**: الاستجابة كائن فيه `results` و`next`، "
            "لا مصفوفة. اتبع `next` كما هو."
        ),
        parameters=[
            OpenApiParameter(
                "status", str,
                description=(
                    "searching | offers_received | driver_selected | "
                    "driver_arriving | driver_arrived | in_progress | "
                    "completed | cancelled | expired"
                ),
            ),
            OpenApiParameter("cursor", str, description="مؤشّر الصفحة التالية"),
            OpenApiParameter("page_size", int, description="1..100، الافتراضي 20"),
        ],
        responses={200: RideRequestSerializer(many=True)},
    )
    def get(self, request):
        from trips.services.resume import ResumeService

        queryset = ResumeService.customer_rides(
            request.user,
            status=request.query_params.get("status") or None,
        )

        return paginate(request, queryset, RideRequestSerializer, view=self)


class MyRideSubscriptionsView(APIView):
    """
    اشتراكات الصباح: القائمة والإنشاء.

    الاشتراك يولّد طلبًا مجدولًا قبل موعده بنصف ساعة كلّ يومٍ من أيامه، فيمرّ
    بالمزاد العاديّ. لا سعر خاصّ هنا: الخصم — إن أراده المشغّل — إعداد تسعير.
    """

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated, IsCustomer, requires_service("morning_subscription")]

    @extend_schema(
        tags=["Rides"], operation_id="list_my_ride_subscriptions",
        summary="اشتراكاتي (مشوار الصباح)",
        responses={200: RideSubscriptionSerializer(many=True)},
    )
    def get(self, request):
        queryset = RideSubscription.objects.filter(customer=request.user, is_active=True)
        return Response(RideSubscriptionSerializer(queryset, many=True).data)

    @extend_schema(
        tags=["Rides"], operation_id="create_ride_subscription",
        summary="إنشاء اشتراك صباح",
        request=RideSubscriptionSerializer,
        responses={201: RideSubscriptionSerializer, 400: ErrorResponse},
    )
    def post(self, request):
        serializer = RideSubscriptionSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        subscription = serializer.save()
        return Response(
            RideSubscriptionSerializer(subscription).data, status=status.HTTP_201_CREATED,
        )


class CancelRideSubscriptionView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated, IsCustomer]

    @extend_schema(
        tags=["Rides"], operation_id="cancel_ride_subscription",
        summary="إيقاف اشتراك صباح",
        responses={200: RideSubscriptionSerializer, 404: ErrorResponse},
    )
    def delete(self, request, subscription_id):
        subscription = get_object_or_404(
            RideSubscription, id=subscription_id, customer=request.user, is_active=True,
        )
        subscription.is_active = False
        subscription.save(update_fields=["is_active", "updated_at"])
        return Response(RideSubscriptionSerializer(subscription).data)
