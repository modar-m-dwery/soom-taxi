from rest_framework import serializers

from drf_spectacular.utils import (
    extend_schema,
    OpenApiExample,
    OpenApiRequest,
    OpenApiResponse,
)

from config.openapi import (
    DriverAvailabilityResponse,
    ErrorResponse,
)
from rest_framework import status
# المصادقة الموحّدة: عمر التوكن ونسبة الفعل إلى فاعله في سجلّ التدقيق.
from config.observability.auth import ContextTokenAuthentication as TokenAuthentication
from rest_framework.permissions import (
    IsAuthenticated,
)
from rest_framework.response import Response
from rest_framework.views import APIView

from drivers.models import (
    DriverDocument,
    DocumentStatus,
)
from drivers.serializers import (
    DriverAdminSerializer,
    DriverDocumentSerializer,
    ReviewDocumentSerializer,
    SubmitDocumentSerializer,
    VerifyDriverSerializer,
)
from drivers.services.eligibility import (
    DriverEligibilityService,
)
from drivers.services.availability import (
    DriverAvailabilityService,
)
from users.models import DriverProfile
from users.permissions import (
    IsAdmin,
    IsDriver,
)


class DriverDocumentListCreateView(APIView):
    authentication_classes = [
        TokenAuthentication,
    ]

    permission_classes = [
        IsAuthenticated,
        IsDriver,
    ]

    @extend_schema(
        tags=["Drivers"],
        operation_id="list_driver_documents",
        summary="List driver documents",
        responses={
            200: DriverDocumentSerializer(many=True),
        },
    )
    def get(self, request):
        profile = request.user.driver_profile

        documents = (
            DriverDocument.objects
            .filter(driver=profile)
            .order_by("-created_at")
        )

        return Response(
            DriverDocumentSerializer(
                documents,
                many=True,
            ).data,
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        tags=["Drivers"],
        operation_id="submit_driver_document",
        summary="Submit driver document",
        description=(
            "Uploads a new driver verification document. "
            "A newly submitted document starts as PENDING. "
            "If the driver was ACTIVE, the driver is moved back to "
            "PENDING and taken offline until verification is completed."
        ),
        request=OpenApiRequest(
            request=SubmitDocumentSerializer,
        ),
        responses={
            201: DriverDocumentSerializer,
            400: ErrorResponse,
        },
        examples=[
            OpenApiExample(
                "Driver document",
                request_only=True,
                value={
                    "type": "national_id",
                    "expires_at": "2027-12-31T23:59:59Z",
                },
            ),
        ],
    )
    def post(self, request):
        serializer = SubmitDocumentSerializer(
            data=request.data
        )

        serializer.is_valid(
            raise_exception=True
        )

        profile = request.user.driver_profile

        document = (
            DriverEligibilityService.submit_document(
                driver_profile=profile,
                doc_type=serializer.validated_data["type"],
                file=serializer.validated_data["file"],
                expires_at=serializer.validated_data.get(
                    "expires_at"
                ),
            )
        )

        return Response(
            DriverDocumentSerializer(
                document
            ).data,
            status=status.HTTP_201_CREATED,
        )


class AdminPendingDocumentsView(APIView):
    authentication_classes = [
        TokenAuthentication,
    ]

    permission_classes = [
        IsAuthenticated,
        IsAdmin,
    ]

    @extend_schema(
        tags=["Driver Administration"],
        operation_id="admin_pending_documents",
        summary="List pending driver documents",
        responses={
            200: DriverDocumentSerializer(many=True),
        },
    )
    def get(self, request):
        documents = (
            DriverDocument.objects
            .filter(
                status=DocumentStatus.PENDING
            )
            .select_related(
                "driver__user"
            )
            .order_by("created_at")
        )

        return Response(
            DriverDocumentSerializer(
                documents,
                many=True,
            ).data,
            status=status.HTTP_200_OK,
        )


class AdminDocumentReviewView(APIView):
    authentication_classes = [
        TokenAuthentication,
    ]

    permission_classes = [
        IsAuthenticated,
        IsAdmin,
    ]

    @extend_schema(
        tags=["Driver Administration"],
        operation_id="admin_review_document",
        summary="Review driver document",
        description=(
            "Approves or rejects a document. "
            "A rejection reason is required when approve=false."
        ),
        request=ReviewDocumentSerializer,
        responses={
            200: DriverDocumentSerializer,
            400: ErrorResponse,
            404: ErrorResponse,
        },
        examples=[
            OpenApiExample(
                "Approve",
                request_only=True,
                value={
                    "approve": True,
                    "rejection_reason": "",
                },
            ),
            OpenApiExample(
                "Reject",
                request_only=True,
                value={
                    "approve": False,
                    "rejection_reason": "Document has expired.",
                },
            ),
        ],
    )
    def post(
        self,
        request,
        document_id,
    ):
        serializer = ReviewDocumentSerializer(
            data=request.data
        )

        serializer.is_valid(
            raise_exception=True
        )

        try:
            document = (
                DriverEligibilityService
                .review_document(
                    document_id=document_id,
                    admin_user=request.user,
                    approve=serializer.validated_data[
                        "approve"
                    ],
                    rejection_reason=serializer.validated_data.get(
                        "rejection_reason",
                        "",
                    ),
                )
            )

        except DriverDocument.DoesNotExist:
            return Response(
                {
                    "detail": (
                        "Document not found."
                    )
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            DriverDocumentSerializer(
                document
            ).data,
            status=status.HTTP_200_OK,
        )


class AdminPendingDriversView(APIView):
    """
    السائقون الذين ينتظرون قرار الإدارة.
    """

    authentication_classes = [
        TokenAuthentication,
    ]

    permission_classes = [
        IsAuthenticated,
        IsAdmin,
    ]

    @extend_schema(
        tags=["Driver Administration"],
        operation_id="admin_pending_drivers",
        summary="List pending drivers",
        responses={
            200: DriverAdminSerializer(many=True),
        },
    )
    def get(self, request):
        drivers = (
            DriverProfile.objects
            .filter(
                status=DriverProfile.DriverStatus.PENDING
            )
            .select_related("user")
            .order_by("id")
        )

        return Response(
            DriverAdminSerializer(
                drivers,
                many=True,
            ).data,
            status=status.HTTP_200_OK,
        )


class AdminVerifyDriverView(APIView):
    """
    قبول أو رفض السائق بالكامل.
    """

    authentication_classes = [
        TokenAuthentication,
    ]

    permission_classes = [
        IsAuthenticated,
        IsAdmin,
    ]

    @extend_schema(
        tags=["Driver Administration"],
        operation_id="admin_verify_driver",
        summary="Verify driver",
        description=(
            "Accepts or rejects the final driver verification. "
            "An approval succeeds only when the driver has an active vehicle "
            "and every required document has a valid approved latest version."
        ),
        request=VerifyDriverSerializer,
        responses={
            200: DriverAdminSerializer,
            400: ErrorResponse,
            404: ErrorResponse,
        },
        examples=[
            OpenApiExample(
                "Approve driver",
                request_only=True,
                value={
                    "approve": True,
                    "verification_note": "",
                },
            ),
            OpenApiExample(
                "Reject driver",
                request_only=True,
                value={
                    "approve": False,
                    "verification_note": (
                        "Required verification requirements are incomplete."
                    ),
                },
            ),
        ],
    )
    def post(
        self,
        request,
        driver_id,
    ):
        serializer = VerifyDriverSerializer(
            data=request.data
        )

        serializer.is_valid(
            raise_exception=True
        )

        try:
            driver = (
                DriverProfile.objects
                .select_related("user")
                .get(id=driver_id)
            )

        except DriverProfile.DoesNotExist:
            return Response(
                {
                    "detail": (
                        "Driver not found."
                    )
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            driver = (
                DriverEligibilityService.verify_driver(
                    driver_profile=driver,
                    admin_user=request.user,
                    approve=serializer.validated_data[
                        "approve"
                    ],
                    verification_note=serializer.validated_data.get(
                        "verification_note",
                        "",
                    ),
                )
            )

        except ValueError as exc:
            return Response(
                {
                    "detail": str(exc)
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            DriverAdminSerializer(driver).data,
            status=status.HTTP_200_OK,
        )


class AdminSuspendDriverView(APIView):
    """
    إيقاف سائق فعال.
    """

    authentication_classes = [
        TokenAuthentication,
    ]

    permission_classes = [
        IsAuthenticated,
        IsAdmin,
    ]

    @extend_schema(
        tags=["Driver Administration"],
        operation_id="admin_suspend_driver",
        summary="Suspend driver",
        request={
            "application/json": {
                "type": "object",
                "required": ["reason"],
                "properties": {
                    "reason": {
                        "type": "string",
                        "maxLength": 255,
                    },
                },
            },
        },
        responses={
            200: DriverAdminSerializer,
            400: ErrorResponse,
            404: ErrorResponse,
        },
        examples=[
            OpenApiExample(
                "Suspend driver",
                request_only=True,
                value={
                    "reason": "Repeated passenger complaints.",
                },
            ),
        ],
    )
    def post(
        self,
        request,
        driver_id,
    ):
        reason = str(
            request.data.get(
                "reason",
                "",
            )
        ).strip()

        if not reason:
            return Response(
                {
                    "detail": (
                        "A suspension reason is required."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            driver = DriverProfile.objects.get(
                id=driver_id
            )

        except DriverProfile.DoesNotExist:
            return Response(
                {
                    "detail": (
                        "Driver not found."
                    )
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        driver = (
            DriverEligibilityService.suspend_driver(
                driver_profile=driver,
                admin_user=request.user,
                reason=reason,
            )
        )

        return Response(
            DriverAdminSerializer(driver).data,
            status=status.HTTP_200_OK,
        )


class DriverGoOnlineView(APIView):

    authentication_classes = [
        TokenAuthentication,
    ]

    permission_classes = [
        IsAuthenticated,
        IsDriver,
    ]

    @extend_schema(
        tags=["Drivers"],
        operation_id="driver_go_online",
        summary="Go online",
        description=(
            "Sets the authenticated driver online. "
            "The driver must be ACTIVE and eligible."
        ),
        request=None,
        responses={
            200: DriverAvailabilityResponse,
            400: ErrorResponse,
        },
    )
    def post(self, request):

        profile = request.user.driver_profile

        try:
            profile = (
                DriverAvailabilityService.go_online(
                    profile
                )
            )

        except ValueError as exc:

            return Response(
                {
                    "detail": str(exc),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                "detail": (
                    "Driver is now online."
                ),
                "online": profile.online,
                "status": profile.status,
            },
            status=status.HTTP_200_OK,
        )


class DriverGoOfflineView(APIView):

    authentication_classes = [
        TokenAuthentication,
    ]

    permission_classes = [
        IsAuthenticated,
        IsDriver,
    ]

    @extend_schema(
        tags=["Drivers"],
        operation_id="driver_go_offline",
        summary="Go offline",
        request=None,
        responses={
            200: DriverAvailabilityResponse,
        },
    )
    def post(self, request):

        profile = request.user.driver_profile

        profile = (
            DriverAvailabilityService.go_offline(
                profile
            )
        )

        return Response(
            {
                "detail": (
                    "Driver is now offline."
                ),
                "online": profile.online,
                "status": profile.status,
            },
            status=status.HTTP_200_OK,
        )