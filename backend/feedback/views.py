from drf_spectacular.utils import OpenApiParameter, extend_schema

from rest_framework import status
# المصادقة الموحّدة: عمر التوكن ونسبة الفعل إلى فاعله في سجلّ التدقيق.
from config.observability.auth import ContextTokenAuthentication as TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from config.openapi import ErrorResponse
from config.pagination import paginate
from feedback.models import Complaint, RatingDirection
from feedback.serializers import (
    ComplaintDetailSerializer,
    ComplaintSerializer,
    OpenComplaintSerializer,
    RatingSerializer,
    RatingSummarySerializer,
    RatingTagSerializer,
    SubmitRatingSerializer,
    TripRatingStateSerializer,
)
from feedback.services.complaint import ComplaintError, ComplaintService
from feedback.services.rating import RatingError, RatingService
from trips.models import Trip


class _FeedbackView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]


class SubmitRatingView(_FeedbackView):
    @extend_schema(
        tags=["Feedback"],
        operation_id="submit_rating",
        summary="Rate the other party of a completed trip",
        description=(
            "Direction is derived from the caller, never sent by the client. "
            "Neither side sees the other's rating until they have rated too "
            "or the window closes."
        ),
        request=SubmitRatingSerializer,
        responses={201: RatingSerializer, 400: ErrorResponse, 404: ErrorResponse},
    )
    def post(self, request, ride_id):
        serializer = SubmitRatingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            rating = RatingService.submit(
                ride_id=ride_id,
                rater=request.user,
                score=serializer.validated_data["score"],
                tags=serializer.validated_data.get("tags"),
                comment=serializer.validated_data.get("comment", ""),
            )
        except RatingError as exc:
            return Response(
                {"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST
            )

        return Response(
            RatingSerializer(rating).data, status=status.HTTP_201_CREATED
        )


class TripRatingStateView(_FeedbackView):
    @extend_schema(
        tags=["Feedback"],
        operation_id="get_trip_rating_state",
        summary="Rating state of a trip for the caller",
        responses={200: TripRatingStateSerializer, 404: ErrorResponse},
    )
    def get(self, request, ride_id):
        trip = Trip.objects.filter(ride_id=ride_id).first()

        if trip is None:
            return Response(
                {"detail": "Trip not found."}, status=status.HTTP_404_NOT_FOUND
            )

        try:
            state = RatingService.for_trip(trip, request.user)
        except RatingError as exc:
            return Response(
                {"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN
            )

        return Response(
            TripRatingStateSerializer(state).data, status=status.HTTP_200_OK
        )


class RatingTagListView(_FeedbackView):
    @extend_schema(
        tags=["Feedback"],
        operation_id="list_rating_tags",
        summary="Tags offered after rating",
        parameters=[
            OpenApiParameter("direction", str, description="c2d or d2c"),
            OpenApiParameter("score", int, description="1..5"),
        ],
        responses={200: RatingTagSerializer(many=True)},
    )
    def get(self, request):
        direction = request.query_params.get("direction") or RatingDirection.CUSTOMER_TO_DRIVER
        raw_score = request.query_params.get("score")

        score = None
        if raw_score:
            try:
                score = int(raw_score)
            except ValueError:
                score = None

        tags = RatingService.available_tags(direction=direction, score=score)

        return Response(
            RatingTagSerializer(tags, many=True).data, status=status.HTTP_200_OK
        )


class MyRatingSummaryView(_FeedbackView):
    @extend_schema(
        tags=["Feedback"],
        operation_id="get_my_rating_summary",
        summary="Caller's own rating summary",
        responses={200: RatingSummarySerializer, 404: ErrorResponse},
    )
    def get(self, request):
        driver_profile = getattr(request.user, "driver_profile", None)

        summary = (
            RatingService.get_summary(driver_id=driver_profile.id)
            if driver_profile is not None
            else RatingService.get_summary(customer_id=request.user.id)
        )

        if summary is None:
            return Response(
                {"average": None, "count": 0,
                 "distribution": {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0},
                 "recalculated_at": None},
                status=status.HTTP_200_OK,
            )

        return Response(
            RatingSummarySerializer(summary).data, status=status.HTTP_200_OK
        )


# =====================================================================
# الشكاوى
# =====================================================================

class ComplaintListCreateView(_FeedbackView):
    @extend_schema(
        tags=["Feedback"],
        operation_id="list_my_complaints",
        summary="Complaints filed by the caller",
        description=(
            "**مرقَّمة بالمؤشّر**: الاستجابة كائن فيه `results` و`next`، "
            "لا مصفوفة."
        ),
        parameters=[
            OpenApiParameter("cursor", str, description="مؤشّر الصفحة التالية"),
            OpenApiParameter("page_size", int, description="1..100، الافتراضي 20"),
        ],
        responses={200: ComplaintSerializer(many=True)},
    )
    def get(self, request):
        complaints = (
            Complaint.objects
            .filter(complainant=request.user)
            .select_related("trip")
            .order_by("-created_at")
        )

        return paginate(request, complaints, ComplaintSerializer, view=self)

    @extend_schema(
        tags=["Feedback"],
        operation_id="open_complaint",
        summary="Open a complaint about a trip",
        description=(
            "Freezes an evidence snapshot at creation time, because the raw "
            "GPS path is deleted by the retention task after 30 days."
        ),
        request=OpenComplaintSerializer,
        responses={201: ComplaintDetailSerializer, 400: ErrorResponse},
    )
    def post(self, request):
        serializer = OpenComplaintSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            complaint = ComplaintService.open(
                ride_id=serializer.validated_data["ride_id"],
                complainant=request.user,
                category=serializer.validated_data["category"],
                description=serializer.validated_data["description"],
            )
        except ComplaintError as exc:
            return Response(
                {"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST
            )

        return Response(
            ComplaintDetailSerializer(complaint).data,
            status=status.HTTP_201_CREATED,
        )


class ComplaintDetailView(_FeedbackView):
    @extend_schema(
        tags=["Feedback"],
        operation_id="get_complaint",
        summary="Complaint detail",
        responses={200: ComplaintDetailSerializer, 404: ErrorResponse},
    )
    def get(self, request, complaint_id):
        complaint = (
            Complaint.objects
            .filter(id=complaint_id, complainant=request.user)
            .select_related("trip")
            .first()
        )

        if complaint is None:
            return Response(
                {"detail": "Complaint not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            ComplaintDetailSerializer(complaint).data, status=status.HTTP_200_OK
        )
