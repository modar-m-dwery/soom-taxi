from drf_spectacular.utils import (
    extend_schema,
    OpenApiExample,
    OpenApiResponse,
)
from config.openapi import ErrorResponse
from rest_framework import status
from rest_framework.authentication import (
    TokenAuthentication,
)
from rest_framework.permissions import (
    IsAuthenticated,
)
from rest_framework.response import Response
from rest_framework.views import APIView

from users.permissions import IsDriver
from users.services.drivers import DriverProfileService
from vehicles.models import Vehicle
from vehicles.serializers import (
    RegisterVehicleSerializer,
    VehicleSerializer,
)
from vehicles.services import VehicleService


class VehicleListCreateView(APIView):
    authentication_classes = [
        TokenAuthentication,
    ]

    permission_classes = [
        IsAuthenticated,
        IsDriver,
    ]

    @extend_schema(
        tags=["Vehicles"],
        operation_id="list_driver_vehicles",
        summary="List driver's vehicles",
        responses={
            200: VehicleSerializer(many=True),
        },
    )
    def get(self, request):
        profile = DriverProfileService.get_or_create_profile(
            request.user
        )

        vehicles = (
            Vehicle.objects
            .filter(driver=profile)
            .order_by("-created_at")
        )

        return Response(
            VehicleSerializer(
                vehicles,
                many=True,
            ).data,
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        tags=["Vehicles"],
        operation_id="register_vehicle",
        summary="Register vehicle",
        request=RegisterVehicleSerializer,
        responses={
            201: VehicleSerializer,
            400: ErrorResponse,
        },
        examples=[
            OpenApiExample(
                "Register vehicle",
                request_only=True,
                value={
                    "type": "taxi",
                    "make": "Toyota",
                    "model": "Camry",
                    "year": 2022,
                    "color": "White",
                    "plate_number": "ABC-123",
                    "seats": 4,
                },
            ),
        ],
    )
    def post(self, request):
        serializer = RegisterVehicleSerializer(
            data=request.data
        )

        serializer.is_valid(
            raise_exception=True
        )

        profile = DriverProfileService.get_or_create_profile(
            request.user
        )

        vehicle = VehicleService.register_vehicle(
            driver_profile=profile,
            validated_data=serializer.validated_data,
        )

        return Response(
            VehicleSerializer(vehicle).data,
            status=status.HTTP_201_CREATED,
        )


class ActivateVehicleView(APIView):
    authentication_classes = [
        TokenAuthentication,
    ]

    permission_classes = [
        IsAuthenticated,
        IsDriver,
    ]

    @extend_schema(
        tags=["Vehicles"],
        operation_id="activate_vehicle",
        summary="Activate vehicle",
        request=None,
        responses={
            200: VehicleSerializer,
            404: ErrorResponse,
        },
    )
    def post(
        self,
        request,
        vehicle_id,
    ):
        profile = DriverProfileService.get_or_create_profile(
            request.user
        )

        try:
            vehicle = (
                VehicleService.set_active_vehicle(
                    driver_profile=profile,
                    vehicle_id=vehicle_id,
                )
            )

        except Vehicle.DoesNotExist:
            return Response(
                {
                    "detail": (
                        "Vehicle not found."
                    )
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            VehicleSerializer(vehicle).data,
            status=status.HTTP_200_OK,
        )


class DeactivateVehicleView(APIView):
    authentication_classes = [
        TokenAuthentication,
    ]

    permission_classes = [
        IsAuthenticated,
        IsDriver,
    ]

    @extend_schema(
        tags=["Vehicles"],
        operation_id="deactivate_vehicle",
        summary="Deactivate vehicle",
        request=None,
        responses={
            200: VehicleSerializer,
            404: ErrorResponse,
        },
    )
    def post(
        self,
        request,
        vehicle_id,
    ):
        profile = DriverProfileService.get_or_create_profile(
            request.user
        )

        try:
            vehicle = (
                VehicleService.deactivate_vehicle(
                    driver_profile=profile,
                    vehicle_id=vehicle_id,
                )
            )

        except Vehicle.DoesNotExist:
            return Response(
                {
                    "detail": (
                        "Vehicle not found."
                    )
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            VehicleSerializer(vehicle).data,
            status=status.HTTP_200_OK,
        )