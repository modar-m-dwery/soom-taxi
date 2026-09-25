from django.urls import path

from trips.views import (
    ActiveRideView,
    CustomerCancelTripView,
    DriverArrivedView,
    DriverCompleteTripView,
    DriverCancelTripView,
    DriverStartTripView,
    MyTripsView,
    TripDetailView,
    TripPathView,
)


# تُضمَّن تحت api/v1/ في config/urls.py
urlpatterns = [
    # ----------------------------
    # السائق — أفعال دورة الحياة (§21 في الوثيقة)
    # ----------------------------
    path(
        "driver/rides/<int:ride_id>/arrived/",
        DriverArrivedView.as_view(),
        name="driver-trip-arrived",
    ),
    path(
        "driver/rides/<int:ride_id>/start/",
        DriverStartTripView.as_view(),
        name="driver-trip-start",
    ),
    path(
        "driver/rides/<int:ride_id>/complete/",
        DriverCompleteTripView.as_view(),
        name="driver-trip-complete",
    ),
    path(
        "driver/rides/<int:ride_id>/cancel/",
        DriverCancelTripView.as_view(),
        name="driver-trip-cancel",
    ),

    # ----------------------------
    # الطرفان
    # ----------------------------
    path(
        "trips/<int:ride_id>/",
        TripDetailView.as_view(),
        name="trip-detail",
    ),
    path(
        "trips/<int:ride_id>/path/",
        TripPathView.as_view(),
        name="trip-path",
    ),

    # ----------------------------
    # الزبون
    # ----------------------------
    path(
        "customer/rides/<int:ride_id>/cancel-trip/",
        CustomerCancelTripView.as_view(),
        name="customer-cancel-trip",
    ),

    # ----------------------------
    # نقاط الموبايل — بلا ride_id
    #
    # الترتيب مهمّ: "me/active-ride/" يجب أن يسبق أي نمط يلتقط
    # "me/<شيء>/" لو أُضيف لاحقًا في هذا الملفّ.
    # ----------------------------
    path(
        "me/active-ride/",
        ActiveRideView.as_view(),
        name="my-active-ride",
    ),
    path(
        "me/trips/",
        MyTripsView.as_view(),
        name="my-trips",
    ),
]
