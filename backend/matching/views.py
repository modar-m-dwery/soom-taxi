from rest_framework import serializers
from catalog.permissions import requires_feature, requires_service
from drf_spectacular.utils import inline_serializer

from drf_spectacular.utils import (
    extend_schema,
    OpenApiExample,
    OpenApiResponse,
    OpenApiParameter,
)
from config.pagination import paginate
from config.openapi import (
    ErrorResponse,
    ScheduledSharedTripWithScoreResponse,
    SharedJoinAcceptResponse,
    ScheduledTripJoinResponse
)
from django.contrib.gis.geos import Point

from rest_framework import status
from rest_framework.authentication import (
    TokenAuthentication,
)
from rest_framework.permissions import (
    IsAuthenticated,
)
from rest_framework.response import Response
from rest_framework.views import APIView

from matching.models import RideOffer, ScheduledSharedTrip

from matching.serializers import (
    CreateRideOfferSerializer,
    RideOfferSerializer,
    SharedJoinOfferSerializer,
    ScheduledSharedTripSerializer,
    PublishTripSerializer,
    BookTripSerializer,
)

from matching.services.scheduled_shared import (
    ScheduledSharedTripService,
    ScheduledSharedMatchingError,
)

from matching.services.matching import (
    MatchingError,
    MatchingService,
)

from matching.services.shared_matching import (
    SharedJoinRequest,
    SharedMatchingService,
    SharedMatchingError,
)

from rides.models import RideRequest

from users.permissions import IsDriver, IsCustomer

from vehicles.models import Vehicle
from rides.serializers import RideRequestSerializer


class CustomerScheduledSharedTripsView(APIView):

    authentication_classes = [
        TokenAuthentication,
    ]

    permission_classes = [
        IsAuthenticated,
        IsCustomer,
    ]

    @extend_schema(
        tags=["Scheduled Shared Trips"],
        operation_id="customer_scheduled_shared_trips",
        summary="Compatible scheduled shared trips for a ride",
        description=(
            "Each item is a scheduled shared trip plus the compatibility "
            "score computed for this specific ride."
        ),
        responses={
            200: ScheduledSharedTripWithScoreResponse,
            404: ErrorResponse,
        },
    )
    def get(
        self,
        request,
        ride_id,
    ):

        try:

            ride = (
                RideRequest.objects
                .get(
                    id=ride_id,
                    customer=request.user,
                )
            )

        except RideRequest.DoesNotExist:

            return Response(
                {
                    "detail": "Ride not found."
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        trips = (
            ScheduledSharedTripService
            .get_available_trips_for_ride(
                ride
            )
        )

        data = []

        for trip, score in trips:

            item = (
                ScheduledSharedTripSerializer(
                    trip
                ).data
            )

            item["compatibility_score"] = score

            data.append(item)

        return Response(
            data,
            status=status.HTTP_200_OK,
        )


class CustomerJoinScheduledSharedTripView(APIView):

    authentication_classes = [
        TokenAuthentication,
    ]

    permission_classes = [
        IsAuthenticated,
        IsCustomer,
    ]

    @extend_schema(
        tags=["Scheduled Shared Trips"],
        operation_id="join_scheduled_shared_trip",
        summary="Join scheduled shared trip",
        request=None,
        responses={
            200: ScheduledTripJoinResponse,
            400: ErrorResponse,
            404: ErrorResponse,
        },
    )
    def post(
        self,
        request,
        ride_id,
        trip_id,
    ):

        try:

            membership = (
                ScheduledSharedTripService
                .join_trip(
                    ride_id=ride_id,
                    trip_id=trip_id,
                    customer=request.user,
                )
            )

        except RideRequest.DoesNotExist:

            return Response(
                {
                    "detail": "Ride not found."
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        except ScheduledSharedTrip.DoesNotExist:

            return Response(
                {
                    "detail": "Scheduled shared trip not found."
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        except ScheduledSharedMatchingError as exc:

            return Response(
                {
                    "detail": str(exc)
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                "status": "joined",
                "trip_id": membership.trip_id,
                "ride_id": membership.ride_id,
            },
            status=status.HTTP_200_OK,
        )


class DriverRideCandidatesView(APIView):

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated, IsDriver]

    @extend_schema(
        tags=["Matching"],
        operation_id="driver_ride_candidates",
        summary="List eligible ride candidates",
        description=(
            "Returns rides that the current driver can potentially serve. "
            "Driver status, availability, location freshness, capacity, "
            "vehicle compatibility, distance and busy-driver rules apply."
        ),
        responses={
            200: RideRequestSerializer(many=True),
        },
    )
    def get(self, request):
        driver = request.user.driver_profile

        rides = MatchingService.get_eligible_rides_for_driver(driver)

        return Response(
            RideRequestSerializer(rides, many=True).data,
            status=status.HTTP_200_OK,
        )


class DriverSubmitOfferView(APIView):

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated, IsDriver]

    @extend_schema(
        tags=["Matching"],
        operation_id="driver_submit_offer",
        summary="Submit ride offer",
        description=(
            "Creates or refreshes a driver offer. "
            "The offer expires according to RIDE_OFFER_TTL_SECONDS. "
            "For instant shared rides, eligible join requests may also be created."
        ),
        request=CreateRideOfferSerializer,
        responses={
            201: RideOfferSerializer,
            400: ErrorResponse,
            404: ErrorResponse,
        },
        examples=[
            OpenApiExample(
                "Driver offer",
                request_only=True,
                value={
                    "gross_fare": "25.50",
                    "eta_minutes": 7,
                },
            ),
        ],
    )
    def post(self, request, ride_id):
        driver = request.user.driver_profile

        serializer = CreateRideOfferSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            offer = MatchingService.create_offer(
                ride_id=ride_id,
                driver=driver,
                gross_fare=serializer.validated_data["gross_fare"],
                eta_minutes=serializer.validated_data["eta_minutes"],
            )
        except RideRequest.DoesNotExist:
            return Response(
                {"detail": "Ride not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        except MatchingError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            RideOfferSerializer(offer).data,
            status=status.HTTP_201_CREATED,
        )


class CustomerRideOffersView(APIView):

    authentication_classes = [
        TokenAuthentication,
    ]

    permission_classes = [
        IsAuthenticated,
        IsCustomer,
    ]

    @extend_schema(
        operation_id="customer_ride_offers",
        summary="List ride offers",
        responses={
            200: RideOfferSerializer(many=True),
            404: OpenApiResponse(
                description="Ride not found.",
            ),
        },
        tags=["Matching"],
    )
    def get(
        self,
        request,
        ride_id,
    ):

        try:

            ride = (
                RideRequest.objects
                .get(
                    id=ride_id,
                    customer=request.user,
                )
            )

        except RideRequest.DoesNotExist:

            return Response(
                {
                    "detail": "Ride not found."
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        offers = (
            RideOffer.objects
            .filter(
                ride=ride,
            )
            .exclude(
                status=(
                    "withdrawn"
                )
            )
            .select_related("driver", "driver__user")
            .prefetch_related("driver__vehicles")
            .order_by(
                "gross_fare",
                "eta_minutes",
            )
        )

        return Response(
            RideOfferSerializer(
                offers,
                many=True,
            ).data,
            status=status.HTTP_200_OK,
        )


class CustomerSelectOfferView(APIView):

    authentication_classes = [
        TokenAuthentication,
    ]

    permission_classes = [
        IsAuthenticated,
        IsCustomer,
    ]

    @extend_schema(
        tags=["Matching"],
        operation_id="customer_select_offer",
        summary="Select driver offer",
        description=(
            "Accepts a pending non-expired offer and transitions the ride "
            "to DRIVER_SELECTED. Other pending offers for the ride are cancelled."
        ),
        request=None,
        responses={
            200: RideOfferSerializer,
            404: ErrorResponse,
            409: ErrorResponse,
        },
    )
    def post(
        self,
        request,
        ride_id,
        offer_id,
    ):

        try:

            offer = (
                MatchingService
                .select_offer(
                    ride_id=ride_id,
                    offer_id=offer_id,
                    customer=request.user,
                )
            )

        except RideRequest.DoesNotExist:

            return Response(
                {
                    "detail": "Ride not found."
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        except RideOffer.DoesNotExist:

            return Response(
                {
                    "detail": "Offer not found."
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        except MatchingError as exc:

            return Response(
                {
                    "detail": str(exc)
                },
                status=status.HTTP_409_CONFLICT,
            )

        return Response(
            RideOfferSerializer(
                offer
            ).data,
            status=status.HTTP_200_OK,
        )


class SharedAvailableOffersView(APIView):

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated, IsCustomer]

    @extend_schema(
        tags=["Scheduled Shared Trips"],
        operation_id="shared_available_offers",
        summary="Find scheduled shared trips",
        description=(
            "Finds compatible CITY scheduled shared trips using "
            "pickup radius, destination radius, time window and minimum score."
        ),
        responses={
            200: SharedJoinOfferSerializer(many=True),
            404: ErrorResponse,
        },
    )
    def get(self, request, ride_id):
        try:
            ride = RideRequest.objects.get(id=ride_id, customer=request.user)
        except RideRequest.DoesNotExist:
            return Response(
                {"detail": "Ride not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        offers = SharedMatchingService.get_available_offers_for_customer(ride)

        return Response(
            SharedJoinOfferSerializer(offers, many=True).data,
            status=status.HTTP_200_OK,
        )


class SharedJoinAcceptView(APIView):

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated, IsCustomer]

    @extend_schema(
        tags=["Shared Rides"],
        operation_id="accept_shared_join",
        summary="Accept shared ride join",
        description=(
            "Accepts a pending shared join request. "
            "The operation locks the group to protect the last-seat race."
        ),
        request=None,
        responses={
            200: SharedJoinAcceptResponse,
            400: ErrorResponse,
            404: ErrorResponse,
        },
    )
    def post(self, request, join_request_id):
        try:
            join_request = SharedMatchingService.accept_join(
                join_request_id=join_request_id,
                candidate_customer=request.user,
            )
        except SharedJoinRequest.DoesNotExist:
            return Response(
                {"detail": "Join request not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        except SharedMatchingError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {"status": join_request.status},
            status=status.HTTP_200_OK,
        )


# ================= جديد: سفريات / سرفيس / رحلات ترفيهية =================


class DriverPublishTripView(APIView):
    """السائق (أو لوحة تحكم الشركة) ينشر رحلة سفريات/سرفيس/ترفيهية."""

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated, IsDriver, requires_service("published_trips")]

    @extend_schema(
        tags=["Published Trips"],
        operation_id="publish_trip",
        summary="Publish a trip",
        description=(
            "Publishes an INTERCITY, SERVICE_LINE or RECREATIONAL trip. "
            "City trips are created from accepted scheduled shared offers "
            "and cannot be published directly."
        ),
        request=PublishTripSerializer,
        responses={
            201: ScheduledSharedTripSerializer,
            400: ErrorResponse,
            404: ErrorResponse,
        },
    )
    def post(self, request):
        driver = request.user.driver_profile

        serializer = PublishTripSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            vehicle = Vehicle.objects.get(id=data["vehicle_id"], driver=driver)
        except Vehicle.DoesNotExist:
            return Response(
                {"detail": "Vehicle not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        pickup = Point(data["pickup_lng"], data["pickup_lat"], srid=4326)
        destination = Point(data["destination_lng"], data["destination_lat"], srid=4326)

        try:
            trip = ScheduledSharedTripService.publish_trip(
                driver=driver,
                vehicle=vehicle,
                trip_category=data["trip_category"],
                scheduled_at=data["scheduled_at"],
                capacity=data["capacity"],
                pickup=pickup,
                destination=destination,
                origin_city=data.get("origin_city"),
                destination_city=data.get("destination_city"),
                price_per_seat=data.get("price_per_seat"),
                title=data.get("title"),
                description=data.get("description"),
                features=data.get("features"),
            )
        except ScheduledSharedMatchingError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            ScheduledSharedTripSerializer(trip).data,
            status=status.HTTP_201_CREATED,
        )


class PublishedTripsCatalogView(APIView):
    """
    تصفّح رحلات السفريات/السرفيس/الترفيهية المتاحة.

    كانت هذه النقطة بلا مصادقة إطلاقًا وتُخرج إحداثيات خامّة مع اسم
    السائق وتقييمه ومركبته — أي أنّ أيّ زائر يستطيع بناء سجلّ بالأسطول
    ونقاط انطلاقه ومواعيده بصفحاتٍ متتالية. المصادقة هنا لا تُخفي
    الخدمة عن أحد: أيّ حساب يراها. لكنّها تربط القراءة بهويّة وتجعل
    الخانق يعمل على مستخدم لا على عنوان يتبدّل.
    """

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated, requires_service("published_trips")]

    @extend_schema(
        tags=["Published Trips"],
        operation_id="published_trips_catalog",
        summary="Browse published trips",
        description=(
            "Public catalog containing future OPEN or FULL non-CITY trips."
        ),
        parameters=[
            OpenApiParameter(
                name="trip_category",
                type=str,
                required=False,
                location=OpenApiParameter.QUERY,
            ),
            OpenApiParameter(
                name="origin_city",
                type=str,
                required=False,
                location=OpenApiParameter.QUERY,
            ),
            OpenApiParameter(
                name="destination_city",
                type=str,
                required=False,
                location=OpenApiParameter.QUERY,
            ),
            OpenApiParameter(
                name="cursor",
                type=str,
                required=False,
                location=OpenApiParameter.QUERY,
                description="مؤشّر الصفحة التالية",
            ),
            OpenApiParameter(
                name="page_size",
                type=int,
                required=False,
                location=OpenApiParameter.QUERY,
                description="1..100، الافتراضي 20",
            ),
        ],
        responses={
            200: ScheduledSharedTripSerializer(many=True),
        },
    )
    def get(self, request):
        trip_category = request.query_params.get("trip_category")
        origin_city = request.query_params.get("origin_city")
        destination_city = request.query_params.get("destination_city")

        trips = ScheduledSharedTripService.get_published_trips(
            trip_category=trip_category,
            origin_city=origin_city,
            destination_city=destination_city,
        )

        # مرتَّبة بموعد الانطلاق: الأقرب أوّلًا هو ما يريده المسافر.
        # و"id" كفاصل تعادل — رحلات كثيرة تنطلق الثامنة صباحًا، وبلا
        # فاصل ثابت قد يتكرّر عنصر أو يُفقد بين صفحتين.
        return paginate(
            request,
            trips,
            ScheduledSharedTripSerializer,
            view=self,
            ordering=("scheduled_at", "id"),
        )


class CustomerBookPublishedTripView(APIView):
    """حجز مباشر في رحلة منشورة (سفريات/سرفيس/ترفيهية) دون طلب رحلة مسبق."""

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated, IsCustomer, requires_service("published_trips")]

    @extend_schema(
        operation_id="book_published_trip",
        summary="Book published trip",
        request=BookTripSerializer,
        responses={
            201: OpenApiResponse(
                response=inline_serializer(
                    name="BookPublishedTripResponse",
                    fields={
                        "status": serializers.CharField(),
                        "ride_id": serializers.IntegerField(),
                        "trip_id": serializers.IntegerField(),
                    },
                ),
            ),
            400: OpenApiResponse(
                description="Trip cannot be booked.",
            ),
            404: OpenApiResponse(
                description="Trip not found.",
            ),
        },
        examples=[
            OpenApiExample(
                "Book one passenger",
                request_only=True,
                value={
                    "passenger_count": 1,
                },
            ),
            OpenApiExample(
                "Book multiple passengers",
                request_only=True,
                value={
                    "passenger_count": 4,
                },
            ),
        ],
        tags=["Published Trips"],
    )
    def post(self, request, trip_id):
        serializer = BookTripSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            membership = ScheduledSharedTripService.book_published_trip(
                trip_id=trip_id,
                customer=request.user,
                passenger_count=serializer.validated_data["passenger_count"],
            )
        except ScheduledSharedTrip.DoesNotExist:
            return Response(
                {"detail": "Trip not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        except ScheduledSharedMatchingError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                "status": "booked",
                "ride_id": membership.ride_id,
                "trip_id": membership.trip_id,
            },
            status=status.HTTP_201_CREATED,
        )


# ================= المرحلة 8: الدعوة المباشرة =================

from matching.models import InvitationStatus, RideInvitation
from matching.serializers import (
    CreateInvitationSerializer,
    NearbyVehicleSerializer,
    RejectInvitationSerializer,
    RideInvitationSerializer,
)
from matching.services.invitation import InvitationError, InvitationService
from matching.services.nearby import NearbyVehiclesService


class RideNearbyVehiclesView(APIView):
    """خريطة السيارات الحيّة عبر REST — الوثيقة §21."""

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated, IsCustomer]

    @extend_schema(
        tags=["Live Marketplace"],
        operation_id="ride_nearby_vehicles",
        summary="Nearby available vehicles",
        description=(
            "Returns serviceable vehicles around the ride pickup point. "
            "Coordinates are deliberately rounded (~110m) before the "
            "invitation is accepted; distance and ETA are computed "
            "server-side from the precise position."
        ),
        responses={200: NearbyVehicleSerializer(many=True), 404: ErrorResponse},
    )
    def get(self, request, ride_id):
        try:
            ride = (
                RideRequest.objects
                .select_related("service_area")
                .get(id=ride_id, customer=request.user)
            )
        except RideRequest.DoesNotExist:
            return Response(
                {"detail": "Ride not found."}, status=status.HTTP_404_NOT_FOUND
            )

        return Response(
            NearbyVehiclesService.for_ride(ride), status=status.HTTP_200_OK
        )


class RideInvitationCreateView(APIView):
    """الزبون يضغط على سيارة -> دعوة مباشرة لسائقها."""

    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated, IsCustomer]

    @extend_schema(
        tags=["Live Marketplace"],
        operation_id="create_ride_invitation",
        summary="Invite a specific driver",
        request=CreateInvitationSerializer,
        responses={
            201: RideInvitationSerializer,
            400: ErrorResponse,
            404: ErrorResponse,
        },
        examples=[
            OpenApiExample(
                "Invite with a 40s window",
                request_only=True,
                value={"driver_id": 5, "ttl_seconds": 40},
            ),
        ],
    )
    def post(self, request, ride_id):
        serializer = CreateInvitationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            invitation = InvitationService.create(
                ride_id=ride_id,
                driver_id=serializer.validated_data["driver_id"],
                customer=request.user,
                ttl_seconds=serializer.validated_data.get("ttl_seconds"),
            )
        except RideRequest.DoesNotExist:
            return Response(
                {"detail": "Ride not found."}, status=status.HTTP_404_NOT_FOUND
            )
        except InvitationError as exc:
            return Response(
                {"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST
            )

        return Response(
            RideInvitationSerializer(invitation).data,
            status=status.HTTP_201_CREATED,
        )


class DriverInvitationListView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated, IsDriver]

    @extend_schema(
        tags=["Live Marketplace"],
        operation_id="driver_pending_invitations",
        summary="My pending invitations",
        responses={200: RideInvitationSerializer(many=True)},
    )
    def get(self, request):
        from django.utils import timezone

        invitations = (
            RideInvitation.objects
            .filter(
                driver=request.user.driver_profile,
                status=InvitationStatus.PENDING,
                expires_at__gt=timezone.now(),
            )
            .select_related("driver", "driver__user", "vehicle", "ride")
            .order_by("expires_at")
        )

        return Response(
            RideInvitationSerializer(invitations, many=True).data,
            status=status.HTTP_200_OK,
        )


class DriverInvitationAcceptView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated, IsDriver]

    @extend_schema(
        tags=["Live Marketplace"],
        operation_id="accept_ride_invitation",
        summary="Accept invitation",
        description=(
            "Locks the ride to this driver and creates the accepted offer "
            "that every downstream feature depends on. Idempotent: a second "
            "accept from the same driver returns the same invitation."
        ),
        request=None,
        responses={
            200: RideInvitationSerializer,
            400: ErrorResponse,
            404: ErrorResponse,
        },
    )
    def post(self, request, invitation_id):
        try:
            invitation = InvitationService.accept(
                invitation_id=invitation_id,
                driver=request.user.driver_profile,
            )
        except RideInvitation.DoesNotExist:
            return Response(
                {"detail": "Invitation not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        except InvitationError as exc:
            return Response(
                {"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST
            )

        return Response(
            RideInvitationSerializer(invitation).data, status=status.HTTP_200_OK
        )


class DriverInvitationRejectView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated, IsDriver]

    @extend_schema(
        tags=["Live Marketplace"],
        operation_id="reject_ride_invitation",
        summary="Reject invitation",
        description="The ride stays SEARCHING and the map remains open to the customer.",
        request=RejectInvitationSerializer,
        responses={
            200: RideInvitationSerializer,
            400: ErrorResponse,
            404: ErrorResponse,
        },
    )
    def post(self, request, invitation_id):
        serializer = RejectInvitationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            invitation = InvitationService.reject(
                invitation_id=invitation_id,
                driver=request.user.driver_profile,
                reason=serializer.validated_data.get("reason", ""),
            )
        except RideInvitation.DoesNotExist:
            return Response(
                {"detail": "Invitation not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        except InvitationError as exc:
            return Response(
                {"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST
            )

        return Response(
            RideInvitationSerializer(invitation).data, status=status.HTTP_200_OK
        )