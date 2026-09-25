from drf_spectacular.utils import (
    extend_schema,
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
)

from config.openapi import (
    ErrorResponse,
    RouteResponse,
)
from django.contrib.gis.geos import Point

from rest_framework import status
# المصادقة الموحّدة: عمر التوكن ونسبة الفعل إلى فاعله في سجلّ التدقيق.
from config.observability.auth import ContextTokenAuthentication as TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from maps.services.routing import (
    RoutingError,
    RoutingService,
)


class RouteThrottle(UserRateThrottle):
    scope = "route_test"


class RouteTestView(APIView):

    authentication_classes = [
        TokenAuthentication,
    ]

    permission_classes = [
        IsAuthenticated,
    ]

    throttle_classes = [
        RouteThrottle,
    ]

    @extend_schema(
        tags=["Maps"],
        operation_id="calculate_route",
        summary="Calculate route",
        description=(
            "Calculates a driving route using the configured routing provider. "
            "Coordinates are supplied as latitude/longitude query parameters."
        ),
        parameters=[
            OpenApiParameter(
                name="pickup_lat",
                type=float,
                location=OpenApiParameter.QUERY,
                required=True,
            ),
            OpenApiParameter(
                name="pickup_lng",
                type=float,
                location=OpenApiParameter.QUERY,
                required=True,
            ),
            OpenApiParameter(
                name="destination_lat",
                type=float,
                location=OpenApiParameter.QUERY,
                required=True,
            ),
            OpenApiParameter(
                name="destination_lng",
                type=float,
                location=OpenApiParameter.QUERY,
                required=True,
            ),
        ],
        responses={
            200: RouteResponse,
            400: ErrorResponse,
            502: ErrorResponse,
        },
        examples=[
            OpenApiExample(
                "Damascus short route",
                parameter_only=(
                    "pickup_lat",
                    "query",
                ),
                value=33.5138,
            ),
            OpenApiExample(
                "Pickup longitude",
                parameter_only=(
                    "pickup_lng",
                    "query",
                ),
                value=36.2765,
            ),
        ],
    )
    def get(self, request):

        pickup_lat = request.query_params.get(
            "pickup_lat"
        )

        pickup_lng = request.query_params.get(
            "pickup_lng"
        )

        destination_lat = request.query_params.get(
            "destination_lat"
        )

        destination_lng = request.query_params.get(
            "destination_lng"
        )

        required = {
            "pickup_lat": pickup_lat,
            "pickup_lng": pickup_lng,
            "destination_lat": destination_lat,
            "destination_lng": destination_lng,
        }

        missing = [
            key
            for key, value in required.items()
            if value in (None, "")
        ]

        if missing:

            return Response(
                {
                    "detail": "Missing parameters.",
                    "missing": missing,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:

            pickup = Point(
                float(pickup_lng),
                float(pickup_lat),
                srid=4326,
            )

            destination = Point(
                float(destination_lng),
                float(destination_lat),
                srid=4326,
            )

        except (TypeError, ValueError):

            return Response(
                {
                    "detail": (
                        "Coordinates must be valid numbers."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:

            result = RoutingService.route(
                pickup=pickup,
                destination=destination,
            )

        except RoutingError as exc:

            return Response(
                {
                    "detail": str(exc)
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response(
            result,
            status=status.HTTP_200_OK,
        )