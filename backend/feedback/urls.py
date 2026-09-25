from django.urls import path

from feedback.views import (
    ComplaintDetailView,
    ComplaintListCreateView,
    MyRatingSummaryView,
    RatingTagListView,
    SubmitRatingView,
    TripRatingStateView,
)


# تُضمَّن تحت api/v1/ في config/urls.py
urlpatterns = [
    # ----------------------------
    # التقييم
    # ----------------------------
    path(
        "trips/<int:ride_id>/rate/",
        SubmitRatingView.as_view(),
        name="submit-rating",
    ),
    path(
        "trips/<int:ride_id>/rating/",
        TripRatingStateView.as_view(),
        name="trip-rating-state",
    ),
    path(
        "rating-tags/",
        RatingTagListView.as_view(),
        name="rating-tags",
    ),
    path(
        "me/rating/",
        MyRatingSummaryView.as_view(),
        name="my-rating-summary",
    ),

    # ----------------------------
    # الشكاوى
    # ----------------------------
    path(
        "complaints/",
        ComplaintListCreateView.as_view(),
        name="complaints",
    ),
    path(
        "complaints/<int:complaint_id>/",
        ComplaintDetailView.as_view(),
        name="complaint-detail",
    ),
]
